"""JavaScriptParser — LanguageParser adapter for JavaScript/JSX source code.

Uses regex-based parsing to extract function declarations, arrow functions,
class methods, JSDoc comments, parameters from JSDoc @param tags, and
throw statements.

Requirements: 2.2, 2.4
"""

from __future__ import annotations

import re

from app.pipeline.parsers import LanguageParser
from app.pipeline.parsers.registry import ParserRegistry
from app.schemas import FunctionInfo


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# JSDoc block: /** ... */
_JSDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# @param {Type} name - description
_JSDOC_PARAM_RE = re.compile(
    r"@param\s+(?:\{([^}]*)\}\s+)?(\w+)(?:\s*-\s*(.*))?"
)

# @returns / @return {Type}
_JSDOC_RETURN_RE = re.compile(r"@returns?\s+(?:\{([^}]*)\})?")

# @throws / @throw {Type}
_JSDOC_THROWS_RE = re.compile(r"@throws?\s+(?:\{([^}]*)\})?")

# function name(params)
_FUNC_DECL_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)

# const name = (...) => or const name = async (...) =>
_ARROW_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?"
    r"\(?([^)]*?)\)?\s*=>",
    re.MULTILINE,
)

# const name = function(...)
_CONST_FUNC_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?"
    r"function\s*\(([^)]*)\)",
    re.MULTILINE,
)

# class Name { or class Name extends Base {
_CLASS_RE = re.compile(
    r"^(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?\s*\{",
    re.MULTILINE,
)

# Class method: methodName(params) {
_METHOD_RE = re.compile(
    r"^\s+(?:async\s+)?(?!if\b|else\b|for\b|while\b|switch\b|catch\b|return\b)(\w+)\s*\(([^)]*)\)\s*\{",
    re.MULTILINE,
)

# throw new Error(...) or throw expr
_THROW_RE = re.compile(r"\bthrow\s+(?:new\s+)?(\w+)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_number(source: str, pos: int) -> int:
    """Return the 1-based line number for a character offset."""
    return source[:pos].count("\n") + 1


def _parse_jsdoc_params(jsdoc_text: str) -> list[dict]:
    """Extract @param entries from a JSDoc block."""
    params: list[dict] = []
    for m in _JSDOC_PARAM_RE.finditer(jsdoc_text):
        params.append({
            "name": m.group(2),
            "annotation": m.group(1),  # type inside braces, or None
            "default": None,
        })
    return params


def _parse_jsdoc_return(jsdoc_text: str) -> str | None:
    """Extract @returns type from a JSDoc block."""
    m = _JSDOC_RETURN_RE.search(jsdoc_text)
    if m and m.group(1):
        return m.group(1)
    return None


def _parse_jsdoc_throws(jsdoc_text: str) -> list[dict]:
    """Extract @throws entries from a JSDoc block."""
    results: list[dict] = []
    for m in _JSDOC_THROWS_RE.finditer(jsdoc_text):
        exc_class = m.group(1) or "Error"
        results.append({
            "exception_class": exc_class,
            "condition": None,
            "lineno": 0,
        })
    return results


def _clean_jsdoc(raw: str) -> str:
    """Strip leading * and whitespace from each line of a JSDoc body."""
    lines = raw.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped:
            cleaned.append(stripped)
    return "\n".join(cleaned)


def _params_from_signature(raw_params: str) -> list[dict]:
    """Parse parameter names from a function signature string."""
    params: list[dict] = []
    if not raw_params.strip():
        return params
    for part in raw_params.split(","):
        part = part.strip()
        if not part:
            continue
        # Handle destructuring: skip { ... } patterns
        if part.startswith("{") or part.startswith("["):
            continue
        # Handle default values: name = value
        name = part.split("=")[0].strip()
        # Handle rest params: ...args
        name = name.lstrip(".")
        if name:
            params.append({
                "name": name,
                "annotation": None,
                "default": None,
            })
    return params


def _extract_body(source: str, start_pos: int) -> str:
    """Extract the body of a function/method starting from the opening brace."""
    brace_idx = source.find("{", start_pos)
    if brace_idx == -1:
        # Arrow function without braces - take until end of line
        eol = source.find("\n", start_pos)
        return source[start_pos:eol] if eol != -1 else source[start_pos:]

    depth = 0
    i = brace_idx
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[brace_idx : i + 1]
        # Skip string literals
        elif ch in ('"', "'", "`"):
            quote = ch
            i += 1
            while i < len(source) and source[i] != quote:
                if source[i] == "\\":
                    i += 1  # skip escaped char
                i += 1
        i += 1
    return source[brace_idx:]


def _extract_throw_statements(body: str, base_line: int) -> list[dict]:
    """Extract throw statements from a function body."""
    results: list[dict] = []
    for m in _THROW_RE.finditer(body):
        lineno = base_line + body[: m.start()].count("\n")
        results.append({
            "exception_class": m.group(1),
            "condition": None,
            "lineno": lineno,
        })
    return results


def _find_preceding_jsdoc(
    source: str, func_pos: int
) -> tuple[str | None, str | None, int]:
    """Find the JSDoc comment immediately preceding a function definition.

    Returns (raw_jsdoc, cleaned_docstring, jsdoc_start_line).
    """
    before = source[:func_pos].rstrip()
    if not before.endswith("*/"):
        return None, None, 0

    end = len(before)
    start = before.rfind("/**")
    if start == -1:
        return None, None, 0

    raw = before[start + 3 : end - 2]
    cleaned = _clean_jsdoc(raw)
    start_line = _line_number(source, start)
    return raw, cleaned, start_line


# ---------------------------------------------------------------------------
# JavaScriptParser
# ---------------------------------------------------------------------------


class JavaScriptParser(LanguageParser):
    """JavaScript/JSX language parser using regex-based extraction."""

    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all function/method definitions from JS/JSX source."""
        functions: list[FunctionInfo] = []
        seen_positions: set[int] = set()

        # --- 1. Named function declarations ---
        for m in _FUNC_DECL_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group(1)
            raw_params = m.group(2)
            lineno = _line_number(source_code, pos)
            body = _extract_body(source_code, m.end())

            raw_jsdoc, docstring, _ = _find_preceding_jsdoc(source_code, pos)
            jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _params_from_signature(raw_params)
            return_ann = _parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None
            jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
            throw_stmts = _extract_throw_statements(body, lineno)
            raise_statements = jsdoc_throws + throw_stmts

            sig = f"function {name}({raw_params.strip()})"
            func_source = source_code[pos : pos + len(m.group(0)) + len(body)]

            functions.append(FunctionInfo(
                name=name,
                qualified_name=name,
                source=func_source,
                lineno=lineno,
                signature=sig,
                docstring=docstring,
                params=params,
                return_annotation=return_ann,
                raise_statements=raise_statements,
                mutation_patterns=[],
            ))

        # --- 2. Arrow functions ---
        for m in _ARROW_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group(1)
            raw_params = m.group(2)
            lineno = _line_number(source_code, pos)
            body = _extract_body(source_code, m.end())

            raw_jsdoc, docstring, _ = _find_preceding_jsdoc(source_code, pos)
            jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _params_from_signature(raw_params)
            return_ann = _parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None
            jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
            throw_stmts = _extract_throw_statements(body, lineno)
            raise_statements = jsdoc_throws + throw_stmts

            sig = f"const {name} = ({raw_params.strip()}) =>"
            func_source = source_code[pos : pos + len(m.group(0)) + len(body)]

            functions.append(FunctionInfo(
                name=name,
                qualified_name=name,
                source=func_source,
                lineno=lineno,
                signature=sig,
                docstring=docstring,
                params=params,
                return_annotation=return_ann,
                raise_statements=raise_statements,
                mutation_patterns=[],
            ))

        # --- 3. const name = function(...) ---
        for m in _CONST_FUNC_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group(1)
            raw_params = m.group(2)
            lineno = _line_number(source_code, pos)
            body = _extract_body(source_code, m.end())

            raw_jsdoc, docstring, _ = _find_preceding_jsdoc(source_code, pos)
            jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _params_from_signature(raw_params)
            return_ann = _parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None
            jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
            throw_stmts = _extract_throw_statements(body, lineno)
            raise_statements = jsdoc_throws + throw_stmts

            sig = f"const {name} = function({raw_params.strip()})"
            func_source = source_code[pos : pos + len(m.group(0)) + len(body)]

            functions.append(FunctionInfo(
                name=name,
                qualified_name=name,
                source=func_source,
                lineno=lineno,
                signature=sig,
                docstring=docstring,
                params=params,
                return_annotation=return_ann,
                raise_statements=raise_statements,
                mutation_patterns=[],
            ))

        # --- 4. Class methods ---
        for class_m in _CLASS_RE.finditer(source_code):
            class_name = class_m.group(1)
            class_body = _extract_body(source_code, class_m.end() - 1)
            class_start_line = _line_number(source_code, class_m.start())

            for meth_m in _METHOD_RE.finditer(class_body):
                meth_name = meth_m.group(1)
                raw_params = meth_m.group(2)
                meth_lineno = class_start_line + class_body[: meth_m.start()].count("\n")
                meth_body = _extract_body(class_body, meth_m.end() - 1)

                raw_jsdoc, docstring, _ = _find_preceding_jsdoc(
                    class_body, meth_m.start()
                )
                jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
                params = jsdoc_params or _params_from_signature(raw_params)
                return_ann = _parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None
                jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
                throw_stmts = _extract_throw_statements(meth_body, meth_lineno)
                raise_statements = jsdoc_throws + throw_stmts

                qualified = f"{class_name}.{meth_name}"
                sig = f"{meth_name}({raw_params.strip()})"
                func_source = class_body[
                    meth_m.start() : meth_m.start() + len(meth_m.group(0)) + len(meth_body)
                ]

                functions.append(FunctionInfo(
                    name=meth_name,
                    qualified_name=qualified,
                    source=func_source,
                    lineno=meth_lineno,
                    signature=sig,
                    docstring=docstring,
                    params=params,
                    return_annotation=return_ann,
                    raise_statements=raise_statements,
                    mutation_patterns=[],
                ))

        return functions

    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Basic syntax validation for JavaScript source.

        Checks balanced braces, brackets, and parentheses. This is a
        lightweight heuristic - not a full parser.
        """
        stack: list[str] = []
        pairs = {")": "(", "]": "[", "}": "{"}
        in_string: str | None = None
        in_line_comment = False
        in_block_comment = False
        prev = ""

        for i, ch in enumerate(source_code):
            # Handle line comments
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                prev = ch
                continue

            # Handle block comments
            if in_block_comment:
                if prev == "*" and ch == "/":
                    in_block_comment = False
                prev = ch
                continue

            # Handle string literals
            if in_string:
                if ch == in_string and prev != "\\":
                    in_string = None
                prev = ch
                continue

            # Detect comment starts
            if ch == "/" and i + 1 < len(source_code):
                next_ch = source_code[i + 1]
                if next_ch == "/":
                    in_line_comment = True
                    prev = ch
                    continue
                if next_ch == "*":
                    in_block_comment = True
                    prev = ch
                    continue

            # Detect string starts
            if ch in ('"', "'", "`"):
                in_string = ch
                prev = ch
                continue

            # Track brackets
            if ch in ("(", "[", "{"):
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack[-1] != pairs[ch]:
                    lineno = source_code[:i].count("\n") + 1
                    return False, f"Unmatched '{ch}' at line {lineno}"
                stack.pop()

            prev = ch

        if stack:
            return False, f"Unclosed '{stack[-1]}' - expected matching close"

        return True, None

    def get_language(self) -> str:
        """Return ``'javascript'``."""
        return "javascript"

    def extract_comments(self, source_code: str) -> list[dict]:
        """Extract JSDoc comments from JavaScript source.

        Returns list of dicts with keys:
            text, start_line, end_line, associated_function.
        """
        results: list[dict] = []

        for m in _JSDOC_RE.finditer(source_code):
            start_line = _line_number(source_code, m.start())
            end_line = _line_number(source_code, m.end())
            cleaned = _clean_jsdoc(m.group(1))

            # Find the associated function on the line after the JSDoc
            associated_function: str | None = None
            after_pos = m.end()
            after_text = source_code[after_pos:].lstrip()

            # Check for function declaration
            func_m = _FUNC_DECL_RE.match(after_text)
            if func_m:
                associated_function = func_m.group(1)
            else:
                # Check for arrow / const function
                arrow_m = _ARROW_RE.match(after_text)
                if arrow_m:
                    associated_function = arrow_m.group(1)
                else:
                    const_m = _CONST_FUNC_RE.match(after_text)
                    if const_m:
                        associated_function = const_m.group(1)
                    else:
                        # Check for class method
                        meth_m = _METHOD_RE.match(after_text)
                        if meth_m:
                            associated_function = meth_m.group(1)

            results.append({
                "text": cleaned,
                "start_line": start_line,
                "end_line": end_line,
                "associated_function": associated_function,
            })

        return results


# Register with the ParserRegistry on import
ParserRegistry.register("javascript", JavaScriptParser)
