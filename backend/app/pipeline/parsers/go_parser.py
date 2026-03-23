"""GoParser — LanguageParser adapter for Go source code.

Uses regex-based parsing to extract function and method declarations,
Go doc comments (// lines immediately preceding a declaration), parameters
with types, return types (single or multiple), and panic() calls as
raise_statements. Syntax validation uses balanced-brace heuristics.

Requirements: 2.2, 2.7
"""

from __future__ import annotations

import re

from app.pipeline.parsers import LanguageParser
from app.pipeline.parsers.registry import ParserRegistry
from app.schemas import FunctionInfo


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Go doc comment line: // text  (not ///)
_DOC_LINE_RE = re.compile(r"^[ \t]*//(?!/)[ \t]?(.*)")

# Function declaration:
#   func FunctionName(params) ReturnType {
#   func FunctionName(params) (ReturnType1, ReturnType2) {
_FUNC_RE = re.compile(
    r"^func\s+"
    r"(?P<name>\w+)\s*"
    r"\((?P<params>[^)]*)\)\s*"
    r"(?P<returns>[^{;]*)?"
    r"\s*\{",
    re.MULTILINE,
)

# Method declaration:
#   func (receiver ReceiverType) MethodName(params) ReturnType {
_METHOD_RE = re.compile(
    r"^func\s+"
    r"\((?P<receiver>[^)]*)\)\s+"
    r"(?P<name>\w+)\s*"
    r"\((?P<params>[^)]*)\)\s*"
    r"(?P<returns>[^{;]*)?"
    r"\s*\{",
    re.MULTILINE,
)

# panic(...) call
_PANIC_RE = re.compile(r"\bpanic\s*\(")

# Import block or package line (used to detect non-Go files quickly)
_PACKAGE_RE = re.compile(r"^\s*package\s+\w+", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_number(source: str, pos: int) -> int:
    """Return the 1-based line number for a character offset."""
    return source[:pos].count("\n") + 1


def _extract_body(source: str, open_brace_pos: int) -> str:
    """Extract the function body starting from the opening brace.

    Handles nested braces, string literals, and comments.
    Returns the full body including the surrounding braces.
    """
    depth = 0
    i = open_brace_pos
    in_string: str | None = None
    in_raw_string = False
    in_line_comment = False
    in_block_comment = False
    prev = ""

    while i < len(source):
        ch = source[i]

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            prev = ch
            i += 1
            continue

        if in_block_comment:
            if prev == "*" and ch == "/":
                in_block_comment = False
            prev = ch
            i += 1
            continue

        if in_raw_string:
            if ch == "`":
                in_raw_string = False
            prev = ch
            i += 1
            continue

        if in_string:
            if ch == in_string and prev != "\\":
                in_string = None
            prev = ch
            i += 1
            continue

        if ch == "/" and i + 1 < len(source):
            nxt = source[i + 1]
            if nxt == "/":
                in_line_comment = True
                prev = ch
                i += 1
                continue
            if nxt == "*":
                in_block_comment = True
                prev = ch
                i += 1
                continue

        if ch == "`":
            in_raw_string = True
            prev = ch
            i += 1
            continue

        if ch in ('"', "'"):
            in_string = ch
            prev = ch
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace_pos: i + 1]

        prev = ch
        i += 1

    return source[open_brace_pos:]


def _find_preceding_doc_comment(source: str, func_pos: int) -> str | None:
    """Find Go doc comment lines immediately preceding a function declaration.

    Go doc comments are consecutive // lines with no blank line between
    the last comment line and the func keyword.

    Returns the combined comment text, or None if no doc comment found.
    """
    before = source[:func_pos]
    lines = before.split("\n")

    # The last line before func_pos may be blank (the func line itself starts
    # at func_pos, so lines[-1] is the partial line up to func_pos).
    # Walk backwards collecting // comment lines.
    idx = len(lines) - 1

    # Skip the current partial line (it's the func line itself)
    # and any trailing blank lines
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    # Collect consecutive doc comment lines
    comment_lines: list[str] = []
    while idx >= 0:
        line = lines[idx]
        m = _DOC_LINE_RE.match(line)
        if m:
            comment_lines.append(m.group(1))
            idx -= 1
        else:
            break

    if not comment_lines:
        return None

    # Reverse to restore original order
    comment_lines.reverse()
    return "\n".join(comment_lines)


def _parse_params(raw_params: str) -> list[dict]:
    """Parse a Go parameter list into name/annotation dicts.

    Handles:
    - ``x int, y string``
    - ``x, y int``  (shared type)
    - ``_ int``     (blank identifier)
    - ``args ...string`` (variadic)
    - No names: ``int, string`` (return type lists)
    """
    params: list[dict] = []
    if not raw_params.strip():
        return params

    # Split on commas not inside parentheses or brackets
    depth = 0
    current = ""
    parts: list[str] = []
    for ch in raw_params:
        if ch in ("(", "["):
            depth += 1
            current += ch
        elif ch in (")", "]"):
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    # First pass: collect (names, type) groups
    # Go allows: a, b int  — both a and b have type int
    # We need to detect whether the last token is a type or a name.
    # Heuristic: if a part has >= 2 tokens, last token is the type.
    # If a part has 1 token, it's a type-only param (e.g. in return lists).
    for part in parts:
        tokens = part.split()
        if not tokens:
            continue
        if len(tokens) == 1:
            # Type only (no name), or single-token name — treat as type
            params.append({
                "name": tokens[0].lstrip("*").lstrip("..."),
                "annotation": tokens[0],
                "default": None,
            })
        else:
            # Last token is the type; everything before is the name(s)
            type_token = tokens[-1]
            name_tokens = tokens[:-1]
            for name in name_tokens:
                # Strip variadic prefix from name
                clean_name = name.lstrip("...").lstrip("*")
                params.append({
                    "name": clean_name,
                    "annotation": type_token,
                    "default": None,
                })

    return params


def _parse_return_type(raw_returns: str) -> str | None:
    """Normalise a Go return type string.

    Handles:
    - Empty string → None
    - ``string`` → ``"string"``
    - ``(string, error)`` → ``"(string, error)"``
    - ``(n int, err error)`` → ``"(n int, err error)"``
    """
    cleaned = raw_returns.strip()
    if not cleaned:
        return None
    return cleaned


def _extract_panic_statements(body: str, base_line: int) -> list[dict]:
    """Extract panic() calls from a function body."""
    results: list[dict] = []
    for m in _PANIC_RE.finditer(body):
        lineno = base_line + body[: m.start()].count("\n")
        results.append({
            "exception_class": "panic",
            "condition": None,
            "lineno": lineno,
        })
    return results


def _receiver_type(raw_receiver: str) -> str | None:
    """Extract the type name from a Go receiver expression.

    e.g. ``r *MyStruct`` → ``"MyStruct"``
         ``s MyStruct``  → ``"MyStruct"``
    """
    tokens = raw_receiver.strip().split()
    if not tokens:
        return None
    type_token = tokens[-1].lstrip("*")
    return type_token if type_token else None


# ---------------------------------------------------------------------------
# GoParser
# ---------------------------------------------------------------------------


class GoParser(LanguageParser):
    """Go language parser using regex-based extraction."""

    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all function and method definitions from Go source code."""
        functions: list[FunctionInfo] = []
        seen_positions: set[int] = set()

        # --- 1. Method declarations (must come before plain func to avoid
        #        the receiver being swallowed by the plain func regex) ---
        for m in _METHOD_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group("name")
            raw_params = m.group("params") or ""
            raw_returns = m.group("returns") or ""
            raw_receiver = m.group("receiver") or ""
            lineno = _line_number(source_code, pos)

            # Find the opening brace position (end of match - 1 because the
            # regex ends with \{)
            brace_pos = source_code.index("{", m.start())
            body = _extract_body(source_code, brace_pos)

            docstring = _find_preceding_doc_comment(source_code, pos)
            params = _parse_params(raw_params)
            return_ann = _parse_return_type(raw_returns)
            panic_stmts = _extract_panic_statements(body, lineno)

            receiver_type = _receiver_type(raw_receiver)
            qualified_name = f"{receiver_type}.{name}" if receiver_type else name

            # Build signature
            sig_parts = [f"func ({raw_receiver.strip()}) {name}({raw_params.strip()})"]
            if return_ann:
                sig_parts.append(return_ann)
            sig = " ".join(sig_parts)

            func_source = source_code[pos: pos + len(m.group(0)) - 1 + len(body)]

            functions.append(FunctionInfo(
                name=name,
                qualified_name=qualified_name,
                source=func_source,
                lineno=lineno,
                signature=sig,
                docstring=docstring,
                params=params,
                return_annotation=return_ann,
                raise_statements=panic_stmts,
                mutation_patterns=[],
            ))

        # --- 2. Plain function declarations ---
        for m in _FUNC_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group("name")
            raw_params = m.group("params") or ""
            raw_returns = m.group("returns") or ""
            lineno = _line_number(source_code, pos)

            brace_pos = source_code.index("{", m.start())
            body = _extract_body(source_code, brace_pos)

            docstring = _find_preceding_doc_comment(source_code, pos)
            params = _parse_params(raw_params)
            return_ann = _parse_return_type(raw_returns)
            panic_stmts = _extract_panic_statements(body, lineno)

            sig_parts = [f"func {name}({raw_params.strip()})"]
            if return_ann:
                sig_parts.append(return_ann)
            sig = " ".join(sig_parts)

            func_source = source_code[pos: pos + len(m.group(0)) - 1 + len(body)]

            functions.append(FunctionInfo(
                name=name,
                qualified_name=name,
                source=func_source,
                lineno=lineno,
                signature=sig,
                docstring=docstring,
                params=params,
                return_annotation=return_ann,
                raise_statements=panic_stmts,
                mutation_patterns=[],
            ))

        return functions

    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Basic syntax validation for Go source using balanced-brace heuristic.

        Checks that braces are balanced and that the file contains a package
        declaration. Returns (True, None) for valid source, (False, msg) otherwise.
        """
        # Must have a package declaration
        if not _PACKAGE_RE.search(source_code):
            return False, "Missing 'package' declaration"

        depth = 0
        in_string: str | None = None
        in_raw_string = False
        in_line_comment = False
        in_block_comment = False
        prev = ""

        for i, ch in enumerate(source_code):
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                prev = ch
                continue

            if in_block_comment:
                if prev == "*" and ch == "/":
                    in_block_comment = False
                prev = ch
                continue

            if in_raw_string:
                if ch == "`":
                    in_raw_string = False
                prev = ch
                continue

            if in_string:
                if ch == in_string and prev != "\\":
                    in_string = None
                prev = ch
                continue

            if ch == "/" and i + 1 < len(source_code):
                nxt = source_code[i + 1]
                if nxt == "/":
                    in_line_comment = True
                    prev = ch
                    continue
                if nxt == "*":
                    in_block_comment = True
                    prev = ch
                    continue

            if ch == "`":
                in_raw_string = True
                prev = ch
                continue

            if ch in ('"', "'"):
                in_string = ch
                prev = ch
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    lineno = source_code[:i].count("\n") + 1
                    return False, f"Unexpected '}}' at line {lineno}"

            prev = ch

        if depth != 0:
            return False, f"Unbalanced braces: {depth} unclosed '{{'"

        return True, None

    def get_language(self) -> str:
        """Return ``'go'``."""
        return "go"

    def extract_comments(self, source_code: str) -> list[dict]:
        """Extract Go doc comments from source code.

        Go doc comments are consecutive // lines immediately preceding a
        func declaration. Returns list of dicts with keys:
            text, start_line, end_line, associated_function.
        """
        results: list[dict] = []

        # Collect all func positions (both methods and plain funcs)
        all_funcs: list[tuple[int, str]] = []
        for m in _METHOD_RE.finditer(source_code):
            all_funcs.append((m.start(), m.group("name")))
        for m in _FUNC_RE.finditer(source_code):
            if not any(pos == m.start() for pos, _ in all_funcs):
                all_funcs.append((m.start(), m.group("name")))

        for func_pos, func_name in all_funcs:
            before = source_code[:func_pos]
            lines = before.split("\n")

            idx = len(lines) - 1
            # Skip blank lines immediately before func
            while idx >= 0 and not lines[idx].strip():
                idx -= 1

            comment_lines: list[str] = []
            end_idx = idx
            while idx >= 0:
                line = lines[idx]
                m = _DOC_LINE_RE.match(line)
                if m:
                    comment_lines.append(m.group(1))
                    idx -= 1
                else:
                    break

            if not comment_lines:
                continue

            comment_lines.reverse()
            start_line = idx + 2  # 1-based, +1 for 0-index, +1 for next line
            end_line = end_idx + 1  # 1-based

            results.append({
                "text": "\n".join(comment_lines),
                "start_line": start_line,
                "end_line": end_line,
                "associated_function": func_name,
            })

        return results


# Register with the ParserRegistry on import
ParserRegistry.register("go", GoParser)
