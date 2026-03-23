"""RustParser — LanguageParser adapter for Rust source code.

Uses regex-based parsing to extract function and method declarations,
Rust doc comments (/// lines immediately preceding a declaration),
parameters with types, return types (including generics like Result<T, E>),
and panic!() macro calls as raise_statements. Syntax validation uses
balanced-brace heuristics.

Requirements: 2.2, 2.8
"""

from __future__ import annotations

import re

from app.pipeline.parsers import LanguageParser
from app.pipeline.parsers.registry import ParserRegistry
from app.schemas import FunctionInfo


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Rust doc comment line: /// text
_DOC_LINE_RE = re.compile(r"^[ \t]*///[ \t]?(.*)")

# Plain line comment: // text  (not ///)
_LINE_COMMENT_RE = re.compile(r"^[ \t]*//(?!/)[ \t]?(.*)")

# Function declaration (free function or method inside impl):
#   [pub] [async] [unsafe] [extern "C"] fn name<generics>(params) -> ReturnType {
#   [pub] [async] fn name(params) {
_FUNC_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?:pub(?:\s*\([^)]*\))?\s+)?"   # optional visibility: pub / pub(crate) / pub(super)
    r"(?:(?:async|unsafe|extern\s+\"[^\"]*\")\s+)*"  # optional qualifiers
    r"fn\s+"
    r"(?P<name>\w+)"
    r"(?:<[^>]*>)?"                    # optional generic params <T, U>
    r"\s*\((?P<params>[^)]*)\)"
    r"(?:\s*->\s*(?P<returns>[^{;]+?))?"  # optional return type
    r"\s*(?:\{|where\b)",              # opening brace or where clause
    re.MULTILINE,
)

# impl block: impl [Trait for] TypeName [<generics>] {
_IMPL_RE = re.compile(
    r"^[ \t]*(?:pub\s+)?impl(?:<[^>]*>)?\s+"
    r"(?:[\w:]+\s+for\s+)?"           # optional Trait for
    r"(?P<type_name>[\w:]+)"
    r"(?:<[^>]*)?"                     # optional generics
    r"\s*\{",
    re.MULTILINE,
)

# panic!(...) macro call
_PANIC_RE = re.compile(r"\bpanic\s*!")

# unwrap() / expect() — common panic-inducing patterns
_UNWRAP_RE = re.compile(r"\.(unwrap|expect)\s*\(")

# Attribute lines: #[...] or #![...]
_ATTR_RE = re.compile(r"^[ \t]*#!?\[")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_number(source: str, pos: int) -> int:
    """Return the 1-based line number for a character offset."""
    return source[:pos].count("\n") + 1


def _extract_body(source: str, open_brace_pos: int) -> str:
    """Extract the function body starting from the opening brace.

    Handles nested braces, string literals (including raw strings), and
    comments. Returns the full body including the surrounding braces.
    """
    depth = 0
    i = open_brace_pos
    in_string: str | None = None
    in_raw_string = False
    raw_string_hashes = 0
    in_char = False
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
            # Raw string ends with " followed by raw_string_hashes '#'
            if ch == '"':
                # Count trailing hashes
                j = i + 1
                count = 0
                while j < len(source) and source[j] == "#":
                    count += 1
                    j += 1
                if count >= raw_string_hashes:
                    in_raw_string = False
                    i = j
                    prev = "#"
                    continue
            prev = ch
            i += 1
            continue

        if in_char:
            if ch == "'" and prev != "\\":
                in_char = False
            prev = ch
            i += 1
            continue

        if in_string:
            if ch == in_string and prev != "\\":
                in_string = None
            prev = ch
            i += 1
            continue

        # Detect raw strings: r"..." or r#"..."# or r##"..."##
        if ch == "r" and i + 1 < len(source):
            j = i + 1
            hashes = 0
            while j < len(source) and source[j] == "#":
                hashes += 1
                j += 1
            if j < len(source) and source[j] == '"':
                in_raw_string = True
                raw_string_hashes = hashes
                i = j + 1
                prev = '"'
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

        if ch == '"':
            in_string = ch
            prev = ch
            i += 1
            continue

        if ch == "'":
            # Could be a lifetime ('a) or a char literal
            # Heuristic: if next char is alphanumeric or _, it's a lifetime
            if i + 1 < len(source) and (source[i + 1].isalnum() or source[i + 1] == "_"):
                # Peek ahead: if it ends with ' it's a char, otherwise lifetime
                j = i + 1
                while j < len(source) and (source[j].isalnum() or source[j] == "_"):
                    j += 1
                if j < len(source) and source[j] == "'":
                    in_char = True
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
    """Find Rust doc comment lines (///) immediately preceding a function.

    Skips blank lines and attribute lines (#[...]) between the doc comment
    and the fn keyword. Returns the combined comment text, or None.
    """
    before = source[:func_pos]
    lines = before.split("\n")

    idx = len(lines) - 1

    # Skip the current partial line and blank lines / attribute lines
    while idx >= 0 and (not lines[idx].strip() or _ATTR_RE.match(lines[idx])):
        idx -= 1

    # Collect consecutive /// lines
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

    comment_lines.reverse()
    return "\n".join(comment_lines)


def _parse_params(raw_params: str) -> list[dict]:
    """Parse a Rust parameter list into name/annotation dicts.

    Handles:
    - ``x: i32, y: &str``
    - ``&self``, ``&mut self``, ``self``
    - ``_: i32`` (ignored parameter)
    - ``args: impl Trait``
    - Generics in types: ``items: Vec<String>``
    """
    params: list[dict] = []
    if not raw_params.strip():
        return params

    # Split on commas not inside angle brackets or parentheses
    depth = 0
    current = ""
    parts: list[str] = []
    for ch in raw_params:
        if ch in ("<", "(", "["):
            depth += 1
            current += ch
        elif ch in (">", ")", "]"):
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # self / &self / &mut self
        if part in ("self", "&self", "&mut self", "mut self"):
            params.append({
                "name": "self",
                "annotation": part,
                "default": None,
            })
            continue

        # name: Type  or  mut name: Type
        if ":" in part:
            colon_idx = part.index(":")
            name_part = part[:colon_idx].strip()
            type_part = part[colon_idx + 1:].strip()
            # Strip mut from name
            name_part = re.sub(r"^mut\s+", "", name_part).strip()
            params.append({
                "name": name_part,
                "annotation": type_part,
                "default": None,
            })
        else:
            # No colon — treat whole thing as name
            params.append({
                "name": part,
                "annotation": None,
                "default": None,
            })

    return params


def _parse_return_type(raw_returns: str | None) -> str | None:
    """Normalise a Rust return type string."""
    if not raw_returns:
        return None
    cleaned = raw_returns.strip().rstrip("{").strip()
    return cleaned if cleaned else None


def _extract_panic_statements(body: str, base_line: int) -> list[dict]:
    """Extract panic!() macro calls from a function body."""
    results: list[dict] = []
    for m in _PANIC_RE.finditer(body):
        lineno = base_line + body[: m.start()].count("\n")
        results.append({
            "exception_class": "panic",
            "condition": None,
            "lineno": lineno,
        })
    return results


def _find_impl_type(source: str, func_pos: int) -> str | None:
    """Find the impl block type name that contains func_pos, if any."""
    best_type: str | None = None
    best_start = -1

    for m in _IMPL_RE.finditer(source):
        impl_start = m.start()
        if impl_start >= func_pos:
            break
        # Find the impl body end
        brace_pos = source.find("{", m.start())
        if brace_pos == -1:
            continue
        body = _extract_body(source, brace_pos)
        impl_end = brace_pos + len(body)
        if impl_start <= func_pos <= impl_end and impl_start > best_start:
            best_type = m.group("type_name")
            best_start = impl_start

    return best_type


# ---------------------------------------------------------------------------
# RustParser
# ---------------------------------------------------------------------------


class RustParser(LanguageParser):
    """Rust language parser using regex-based extraction."""

    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all function and method definitions from Rust source code."""
        functions: list[FunctionInfo] = []
        seen_positions: set[int] = set()

        for m in _FUNC_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group("name")
            raw_params = m.group("params") or ""
            raw_returns = m.group("returns")
            lineno = _line_number(source_code, pos)

            # Find the opening brace (may be after a where clause)
            brace_pos = source_code.find("{", m.end() - 1)
            if brace_pos == -1:
                # No body (trait method declaration without default)
                body = ""
            else:
                body = _extract_body(source_code, brace_pos)

            docstring = _find_preceding_doc_comment(source_code, pos)
            params = _parse_params(raw_params)
            return_ann = _parse_return_type(raw_returns)
            panic_stmts = _extract_panic_statements(body, lineno) if body else []

            # Qualify with impl type if inside an impl block
            impl_type = _find_impl_type(source_code, pos)
            qualified_name = f"{impl_type}::{name}" if impl_type else name

            # Build signature
            sig_parts = [f"fn {name}({raw_params.strip()})"]
            if return_ann:
                sig_parts.append(f"-> {return_ann}")
            sig = " ".join(sig_parts)

            func_end = brace_pos + len(body) if body else m.end()
            func_source = source_code[pos:func_end]

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

        return functions

    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Basic syntax validation for Rust source using balanced-brace heuristic.

        Checks that braces are balanced. Returns (True, None) for valid source,
        (False, error_message) otherwise.
        """
        depth = 0
        in_string: str | None = None
        in_raw_string = False
        raw_string_hashes = 0
        in_char = False
        in_line_comment = False
        in_block_comment = False
        prev = ""

        i = 0
        while i < len(source_code):
            ch = source_code[i]

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
                if ch == '"':
                    j = i + 1
                    count = 0
                    while j < len(source_code) and source_code[j] == "#":
                        count += 1
                        j += 1
                    if count >= raw_string_hashes:
                        in_raw_string = False
                        i = j
                        prev = "#"
                        continue
                prev = ch
                i += 1
                continue

            if in_char:
                if ch == "'" and prev != "\\":
                    in_char = False
                prev = ch
                i += 1
                continue

            if in_string:
                if ch == '"' and prev != "\\":
                    in_string = None
                prev = ch
                i += 1
                continue

            # Raw strings
            if ch == "r" and i + 1 < len(source_code):
                j = i + 1
                hashes = 0
                while j < len(source_code) and source_code[j] == "#":
                    hashes += 1
                    j += 1
                if j < len(source_code) and source_code[j] == '"':
                    in_raw_string = True
                    raw_string_hashes = hashes
                    i = j + 1
                    prev = '"'
                    continue

            if ch == "/" and i + 1 < len(source_code):
                nxt = source_code[i + 1]
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

            if ch == '"':
                in_string = ch
                prev = ch
                i += 1
                continue

            if ch == "'":
                if i + 1 < len(source_code) and (source_code[i + 1].isalnum() or source_code[i + 1] == "_"):
                    j = i + 1
                    while j < len(source_code) and (source_code[j].isalnum() or source_code[j] == "_"):
                        j += 1
                    if j < len(source_code) and source_code[j] == "'":
                        in_char = True
                prev = ch
                i += 1
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    lineno = source_code[:i].count("\n") + 1
                    return False, f"Unexpected '}}' at line {lineno}"

            prev = ch
            i += 1

        if depth != 0:
            return False, f"Unbalanced braces: {depth} unclosed '{{'"

        return True, None

    def get_language(self) -> str:
        """Return ``'rust'``."""
        return "rust"

    def extract_comments(self, source_code: str) -> list[dict]:
        """Extract Rust doc comments (///) from source code.

        Returns list of dicts with keys:
            text, start_line, end_line, associated_function.
        """
        results: list[dict] = []

        for m in _FUNC_RE.finditer(source_code):
            func_pos = m.start()
            func_name = m.group("name")
            before = source_code[:func_pos]
            lines = before.split("\n")

            idx = len(lines) - 1

            # Skip blank lines and attribute lines
            while idx >= 0 and (not lines[idx].strip() or _ATTR_RE.match(lines[idx])):
                idx -= 1

            comment_lines: list[str] = []
            end_idx = idx
            while idx >= 0:
                line = lines[idx]
                doc_m = _DOC_LINE_RE.match(line)
                if doc_m:
                    comment_lines.append(doc_m.group(1))
                    idx -= 1
                else:
                    break

            if not comment_lines:
                continue

            comment_lines.reverse()
            start_line = idx + 2   # 1-based
            end_line = end_idx + 1  # 1-based

            results.append({
                "text": "\n".join(comment_lines),
                "start_line": start_line,
                "end_line": end_line,
                "associated_function": func_name,
            })

        return results


# Register with the ParserRegistry on import
ParserRegistry.register("rust", RustParser)
