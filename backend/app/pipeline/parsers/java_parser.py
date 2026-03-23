"""JavaParser — LanguageParser adapter for Java source code.

Uses regex-based parsing to extract method declarations with access modifiers,
Javadoc comments with @param and @return tags, throw declarations from method
signatures, throw statements in method bodies, and class declarations to
qualify method names (ClassName.methodName).

Requirements: 2.2, 2.6
"""

from __future__ import annotations

import re

from app.pipeline.parsers import LanguageParser
from app.pipeline.parsers.registry import ParserRegistry
from app.schemas import FunctionInfo


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Javadoc block: /** ... */
_JAVADOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# @param name description  (no type braces in Javadoc)
_JAVADOC_PARAM_RE = re.compile(r"@param\s+(\w+)(?:\s+(.*?))?(?=@|\Z)", re.DOTALL)

# @return description
_JAVADOC_RETURN_RE = re.compile(r"@returns?\s+(.*?)(?=@|\Z)", re.DOTALL)

# @throws ExceptionType description
_JAVADOC_THROWS_RE = re.compile(r"@throws\s+(\w+)(?:\s+(.*?))?(?=@|\Z)", re.DOTALL)

# Class declaration: [public|abstract|final] class Name [extends X] [implements Y] {
_CLASS_RE = re.compile(
    r"^(?:(?:public|protected|private|abstract|final|static)\s+)*"
    r"class\s+(\w+)(?:\s+extends\s+\w+)?(?:\s+implements\s+[\w,\s]+)?\s*\{",
    re.MULTILINE,
)

# Method declaration:
# [access] [static] [final] [synchronized] [native] ReturnType methodName(params) [throws X, Y]
_METHOD_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?:public|protected|private|static|final|"
    r"synchronized|native|abstract|default|strictfp)\s+)*"
    r"(?!if\b|else\b|for\b|while\b|switch\b|catch\b|return\b|new\b|throw\b)"
    r"(?P<return_type>(?:[\w<>\[\],\s]+?)\s+)"
    r"(?P<name>\w+)\s*\((?P<params>[^)]*)\)"
    r"(?:\s+throws\s+(?P<throws>[\w,\s]+))?"
    r"\s*(?:\{|;)",
    re.MULTILINE,
)

# throw new ExceptionType(...) or throw variable
_THROW_STMT_RE = re.compile(r"\bthrow\s+(?:new\s+)?(\w+)")

# Annotation lines to skip (e.g. @Override, @Test)
_ANNOTATION_RE = re.compile(r"^\s*@\w+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_number(source: str, pos: int) -> int:
    """Return the 1-based line number for a character offset."""
    return source[:pos].count("\n") + 1


def _clean_javadoc(raw: str) -> str:
    """Strip leading * and whitespace from each line of a Javadoc body."""
    lines = raw.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        # Stop at tag lines — keep only the description part
        if stripped.startswith("@"):
            break
        if stripped:
            cleaned.append(stripped)
    return "\n".join(cleaned)


def _parse_javadoc_params(javadoc_text: str) -> list[dict]:
    """Extract @param entries from a Javadoc block."""
    params: list[dict] = []
    for m in _JAVADOC_PARAM_RE.finditer(javadoc_text):
        params.append({
            "name": m.group(1),
            "annotation": None,  # Javadoc doesn't embed types in @param
            "default": None,
        })
    return params


def _parse_javadoc_return(javadoc_text: str) -> str | None:
    """Extract @return description from a Javadoc block (used as annotation)."""
    m = _JAVADOC_RETURN_RE.search(javadoc_text)
    if m:
        return m.group(1).strip().split("\n")[0].strip() or None
    return None


def _parse_javadoc_throws(javadoc_text: str) -> list[dict]:
    """Extract @throws entries from a Javadoc block."""
    results: list[dict] = []
    for m in _JAVADOC_THROWS_RE.finditer(javadoc_text):
        results.append({
            "exception_class": m.group(1),
            "condition": None,
            "lineno": 0,
        })
    return results


def _params_from_signature(raw_params: str) -> list[dict]:
    """Parse Java parameter list into name/annotation dicts.

    Handles generics like ``List<String> items`` and varargs ``int... nums``.
    """
    params: list[dict] = []
    if not raw_params.strip():
        return params

    # Split on commas not inside angle brackets
    depth = 0
    current = ""
    parts: list[str] = []
    for ch in raw_params:
        if ch == "<":
            depth += 1
            current += ch
        elif ch == ">":
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
        # Strip annotations like @NotNull
        part = re.sub(r"@\w+\s+", "", part)
        # Strip final modifier
        part = re.sub(r"\bfinal\s+", "", part)
        tokens = part.split()
        if len(tokens) >= 2:
            # Last token is the parameter name (strip varargs dots)
            name = tokens[-1].lstrip(".")
            annotation = " ".join(tokens[:-1])
        elif tokens:
            name = tokens[0].lstrip(".")
            annotation = None
        else:
            continue
        params.append({
            "name": name,
            "annotation": annotation,
            "default": None,
        })
    return params


def _extract_body(source: str, start_pos: int) -> str:
    """Extract the method body starting from the opening brace at or after start_pos."""
    brace_idx = source.find("{", start_pos)
    if brace_idx == -1:
        # Abstract method — no body
        return ""

    depth = 0
    i = brace_idx
    in_string: str | None = None
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
                return source[brace_idx: i + 1]

        prev = ch
        i += 1

    return source[brace_idx:]


def _extract_throw_statements(body: str, base_line: int) -> list[dict]:
    """Extract throw statements from a method body."""
    results: list[dict] = []
    for m in _THROW_STMT_RE.finditer(body):
        lineno = base_line + body[: m.start()].count("\n")
        results.append({
            "exception_class": m.group(1),
            "condition": None,
            "lineno": lineno,
        })
    return results


def _find_preceding_javadoc(
    source: str, func_pos: int
) -> tuple[str | None, str | None, int]:
    """Find the Javadoc comment immediately preceding a method declaration.

    Skips blank lines and annotation lines between the Javadoc and the method.
    Returns (raw_javadoc_body, cleaned_docstring, javadoc_start_line).
    """
    before = source[:func_pos]

    # Walk backwards line by line, skipping blank lines and annotations
    lines = before.split("\n")
    idx = len(lines) - 1

    # Skip the current (possibly partial) line
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    # Skip annotation lines
    while idx >= 0 and _ANNOTATION_RE.match(lines[idx]):
        idx -= 1

    # Skip blank lines again
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    if idx < 0:
        return None, None, 0

    # Check if this line ends a Javadoc block
    if not lines[idx].strip().endswith("*/"):
        return None, None, 0

    # Find the start of the Javadoc block
    end_line_idx = idx
    start_line_idx = idx
    while start_line_idx >= 0 and "/**" not in lines[start_line_idx]:
        start_line_idx -= 1

    if start_line_idx < 0:
        return None, None, 0

    raw_block = "\n".join(lines[start_line_idx: end_line_idx + 1])
    # Extract body between /** and */
    inner_start = raw_block.find("/**") + 3
    inner_end = raw_block.rfind("*/")
    if inner_end <= inner_start:
        return None, None, 0

    raw_body = raw_block[inner_start:inner_end]
    cleaned = _clean_javadoc(raw_body)
    start_line = start_line_idx + 1  # 1-based
    return raw_body, cleaned, start_line


# ---------------------------------------------------------------------------
# JavaParser
# ---------------------------------------------------------------------------


class JavaParser(LanguageParser):
    """Java language parser using regex-based extraction."""

    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all method definitions from Java source code."""
        functions: list[FunctionInfo] = []

        # Build a map of class name → (class_start_pos, class_end_pos)
        # so we can qualify method names as ClassName.methodName
        class_ranges: list[tuple[str, int, int]] = []
        for class_m in _CLASS_RE.finditer(source_code):
            class_name = class_m.group(1)
            body = _extract_body(source_code, class_m.end() - 1)
            class_start = class_m.start()
            class_end = class_m.end() - 1 + len(body)
            class_ranges.append((class_name, class_start, class_end))

        def _class_for_pos(pos: int) -> str | None:
            """Return the innermost class name containing *pos*."""
            result: str | None = None
            result_start = -1
            for cname, cstart, cend in class_ranges:
                if cstart <= pos <= cend and cstart > result_start:
                    result = cname
                    result_start = cstart
            return result

        seen_positions: set[int] = set()

        for m in _METHOD_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue

            name = m.group("name")
            raw_params = m.group("params") or ""
            return_type_raw = (m.group("return_type") or "").strip()
            throws_raw = m.group("throws")
            lineno = _line_number(source_code, pos)

            # Skip constructors (return type would be the class name with no
            # separate type token — heuristic: if return_type == name, skip)
            # Actually constructors have no return type; the regex may capture
            # the class name as return_type. We detect this by checking if
            # return_type_raw is a single word equal to name.
            # Better: constructors match when the "return type" token is the
            # class name itself. We'll keep them but mark return_annotation as None.

            # Skip common false positives: control flow keywords
            if name in ("if", "else", "for", "while", "switch", "catch",
                        "return", "new", "throw", "try", "finally"):
                continue

            seen_positions.add(pos)

            # Determine if this is an abstract/interface method (ends with ;)
            method_end_char = source_code[m.end() - 1] if m.end() > 0 else ""
            has_body = method_end_char == "{"
            body = _extract_body(source_code, m.end() - 1) if has_body else ""

            # Qualify with class name
            class_name = _class_for_pos(pos)
            qualified_name = f"{class_name}.{name}" if class_name else name

            # Javadoc
            raw_jsdoc, docstring, _ = _find_preceding_javadoc(source_code, pos)
            jsdoc_params = _parse_javadoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _params_from_signature(raw_params)
            return_ann = return_type_raw or None
            jsdoc_throws = _parse_javadoc_throws(raw_jsdoc) if raw_jsdoc else []

            # throws clause in signature
            sig_throws: list[dict] = []
            if throws_raw:
                for exc in throws_raw.split(","):
                    exc = exc.strip()
                    if exc:
                        sig_throws.append({
                            "exception_class": exc,
                            "condition": None,
                            "lineno": lineno,
                        })

            # throw statements in body
            body_throws = _extract_throw_statements(body, lineno) if body else []

            raise_statements = jsdoc_throws + sig_throws + body_throws

            # Build signature string
            sig_parts = []
            if return_type_raw:
                sig_parts.append(return_type_raw)
            sig_parts.append(f"{name}({raw_params.strip()})")
            if throws_raw:
                sig_parts.append(f"throws {throws_raw.strip()}")
            sig = " ".join(sig_parts)

            func_source = source_code[pos: pos + len(m.group(0)) + len(body)]

            functions.append(FunctionInfo(
                name=name,
                qualified_name=qualified_name,
                source=func_source,
                lineno=lineno,
                signature=sig,
                docstring=docstring,
                params=params,
                return_annotation=return_ann,
                raise_statements=raise_statements,
                mutation_patterns=[],
            ))

        return functions

    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Basic syntax validation for Java source using brace balancing.

        Checks that braces are balanced as a lightweight heuristic.
        Returns (True, None) for valid source, (False, error_message) otherwise.
        """
        depth = 0
        in_string: str | None = None
        in_char = False
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

            if in_char:
                if ch == "'" and prev != "\\":
                    in_char = False
                prev = ch
                continue

            if in_string:
                if ch == '"' and prev != "\\":
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

            if ch == '"':
                in_string = ch
                prev = ch
                continue

            if ch == "'":
                in_char = True
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
        """Return ``'java'``."""
        return "java"

    def extract_comments(self, source_code: str) -> list[dict]:
        """Extract Javadoc comments from Java source.

        Returns list of dicts with keys:
            text, start_line, end_line, associated_function.
        """
        results: list[dict] = []

        for m in _JAVADOC_RE.finditer(source_code):
            start_line = _line_number(source_code, m.start())
            end_line = _line_number(source_code, m.end())
            cleaned = _clean_javadoc(m.group(1))

            # Find the associated method after the Javadoc
            associated_function: str | None = None
            after_pos = m.end()
            # Skip whitespace and annotations
            after_text = source_code[after_pos:]
            lines_after = after_text.split("\n")
            for line in lines_after:
                stripped = line.strip()
                if not stripped or _ANNOTATION_RE.match(line):
                    continue
                meth_m = _METHOD_RE.match(line + "\n{")
                if meth_m:
                    associated_function = meth_m.group("name")
                break

            results.append({
                "text": cleaned,
                "start_line": start_line,
                "end_line": end_line,
                "associated_function": associated_function,
            })

        return results


# Register with the ParserRegistry on import
ParserRegistry.register("java", JavaParser)
