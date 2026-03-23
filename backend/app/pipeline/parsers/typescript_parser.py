"""TypeScriptParser — LanguageParser adapter for TypeScript/TSX source code.

Extends JavaScriptParser to additionally handle TypeScript-specific syntax:
- Type annotations in function signatures: function foo(x: string): number
- Generic type parameters: function foo<T>(x: T): T
- Access modifiers in class methods: public, private, protected, readonly
- TSDoc comments (same format as JSDoc)
- Interface and type declarations are skipped (only functions/methods extracted)

Requirements: 2.2, 2.5
"""

from __future__ import annotations

import re

from app.pipeline.parsers.javascript_parser import (
    JavaScriptParser,
    _clean_jsdoc,
    _extract_body,
    _extract_throw_statements,
    _find_preceding_jsdoc,
    _line_number,
    _parse_jsdoc_params,
    _parse_jsdoc_return,
    _parse_jsdoc_throws,
)
from app.pipeline.parsers.registry import ParserRegistry
from app.schemas import FunctionInfo


# ---------------------------------------------------------------------------
# TypeScript-specific regex patterns
# ---------------------------------------------------------------------------

# function name<T>(params): ReturnType
_TS_FUNC_DECL_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
    r"(?:\s*:\s*([^{;]+))?",
    re.MULTILINE,
)

# const name = <T>(params): ReturnType =>
_TS_ARROW_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*"
    r"(?:async\s+)?(?:<[^>]*>)?\s*\(?([^)]*?)\)?\s*(?::\s*([^=>{]+))?\s*=>",
    re.MULTILINE,
)

# const name = function<T>(params): ReturnType
_TS_CONST_FUNC_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*"
    r"(?:async\s+)?function\s*(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^{;]+))?",
    re.MULTILINE,
)

# class Name<T> { or class Name<T> extends Base<U> implements I {
_TS_CLASS_RE = re.compile(
    r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:<[^>]*>)?"
    r"(?:\s+extends\s+\w+(?:<[^>]*>)?)?(?:\s+implements\s+[\w,\s<>]+)?\s*\{",
    re.MULTILINE,
)

# Class method with optional access modifiers and generics
_TS_METHOD_RE = re.compile(
    r"^\s+(?:(?:public|private|protected|static|async|readonly|abstract|override)\s+)*"
    r"(?!if\b|else\b|for\b|while\b|switch\b|catch\b|return\b|constructor\b)"
    r"(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^{;]+))?",
    re.MULTILINE,
)

# Constructor
_TS_CONSTRUCTOR_RE = re.compile(
    r"^\s+(?:(?:public|private|protected)\s+)?constructor\s*\(([^)]*)\)",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# TypeScript-specific helpers
# ---------------------------------------------------------------------------


def _parse_ts_params(raw_params: str) -> list[dict]:
    """Parse TypeScript parameter list, extracting names and type annotations."""
    params: list[dict] = []
    if not raw_params.strip():
        return params

    # Split on commas not inside angle brackets (for generic types)
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
        if not part:
            continue
        # Skip destructuring
        if part.startswith("{") or part.startswith("["):
            continue
        # Strip access modifiers (constructor parameter properties)
        part = re.sub(r"^(?:public|private|protected|readonly)\s+", "", part)
        # Strip rest params prefix
        part = part.lstrip(".")
        # Split off default value
        name_type = part.split("=")[0].strip()
        # Extract name and optional type annotation
        colon_idx = name_type.find(":")
        if colon_idx != -1:
            name = name_type[:colon_idx].strip().rstrip("?")
            annotation = name_type[colon_idx + 1:].strip()
        else:
            name = name_type.rstrip("?")
            annotation = None
        if name:
            params.append({
                "name": name,
                "annotation": annotation,
                "default": None,
            })

    return params


def _clean_return_type(raw: str | None) -> str | None:
    """Strip whitespace and trailing brace from a return type annotation."""
    if not raw:
        return None
    return raw.strip().rstrip("{").strip() or None


# ---------------------------------------------------------------------------
# TypeScriptParser
# ---------------------------------------------------------------------------


class TypeScriptParser(JavaScriptParser):
    """TypeScript/TSX language parser extending JavaScriptParser.

    Handles TypeScript-specific syntax including type annotations, generics,
    access modifiers, and TSDoc comments.
    """

    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all function/method definitions from TypeScript source."""
        functions: list[FunctionInfo] = []
        seen_positions: set[int] = set()

        # --- 1. Named function declarations (with optional generics + return type) ---
        for m in _TS_FUNC_DECL_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group(1)
            raw_params = m.group(2)
            return_type = _clean_return_type(m.group(3))
            lineno = _line_number(source_code, pos)
            body = _extract_body(source_code, m.end())

            raw_jsdoc, docstring, _ = _find_preceding_jsdoc(source_code, pos)
            jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _parse_ts_params(raw_params)
            return_ann = return_type or (_parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None)
            jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
            throw_stmts = _extract_throw_statements(body, lineno)
            raise_statements = jsdoc_throws + throw_stmts

            # Include generics in signature
            generics_m = re.search(r"(<[^>]*>)", source_code[pos:m.end()])
            generics = generics_m.group(1) if generics_m else ""
            sig = f"function {name}{generics}({raw_params.strip()})"
            if return_type:
                sig += f": {return_type}"
            func_source = source_code[pos: pos + len(m.group(0)) + len(body)]

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
        for m in _TS_ARROW_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group(1)
            raw_params = m.group(2)
            return_type = _clean_return_type(m.group(3))
            lineno = _line_number(source_code, pos)
            body = _extract_body(source_code, m.end())

            raw_jsdoc, docstring, _ = _find_preceding_jsdoc(source_code, pos)
            jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _parse_ts_params(raw_params)
            return_ann = return_type or (_parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None)
            jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
            throw_stmts = _extract_throw_statements(body, lineno)
            raise_statements = jsdoc_throws + throw_stmts

            sig = f"const {name} = ({raw_params.strip()}) =>"
            if return_type:
                sig += f" {return_type}"
            func_source = source_code[pos: pos + len(m.group(0)) + len(body)]

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

        # --- 3. const name = function<T>(...) ---
        for m in _TS_CONST_FUNC_RE.finditer(source_code):
            pos = m.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)

            name = m.group(1)
            raw_params = m.group(2)
            return_type = _clean_return_type(m.group(3))
            lineno = _line_number(source_code, pos)
            body = _extract_body(source_code, m.end())

            raw_jsdoc, docstring, _ = _find_preceding_jsdoc(source_code, pos)
            jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
            params = jsdoc_params or _parse_ts_params(raw_params)
            return_ann = return_type or (_parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None)
            jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
            throw_stmts = _extract_throw_statements(body, lineno)
            raise_statements = jsdoc_throws + throw_stmts

            sig = f"const {name} = function({raw_params.strip()})"
            if return_type:
                sig += f": {return_type}"
            func_source = source_code[pos: pos + len(m.group(0)) + len(body)]

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

        # --- 4. Class methods (with access modifiers and generics) ---
        for class_m in _TS_CLASS_RE.finditer(source_code):
            class_name = class_m.group(1)
            class_body = _extract_body(source_code, class_m.end() - 1)
            class_start_line = _line_number(source_code, class_m.start())

            # Constructor
            for ctor_m in _TS_CONSTRUCTOR_RE.finditer(class_body):
                raw_params = ctor_m.group(1)
                meth_lineno = class_start_line + class_body[: ctor_m.start()].count("\n")
                meth_body = _extract_body(class_body, ctor_m.end())

                raw_jsdoc, docstring, _ = _find_preceding_jsdoc(class_body, ctor_m.start())
                jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
                params = jsdoc_params or _parse_ts_params(raw_params)
                throw_stmts = _extract_throw_statements(meth_body, meth_lineno)

                qualified = f"{class_name}.constructor"
                sig = f"constructor({raw_params.strip()})"
                func_source = class_body[
                    ctor_m.start(): ctor_m.start() + len(ctor_m.group(0)) + len(meth_body)
                ]

                functions.append(FunctionInfo(
                    name="constructor",
                    qualified_name=qualified,
                    source=func_source,
                    lineno=meth_lineno,
                    signature=sig,
                    docstring=docstring,
                    params=params,
                    return_annotation=None,
                    raise_statements=throw_stmts,
                    mutation_patterns=[],
                ))

            # Regular methods
            for meth_m in _TS_METHOD_RE.finditer(class_body):
                meth_name = meth_m.group(1)
                raw_params = meth_m.group(2)
                return_type = _clean_return_type(meth_m.group(3))
                meth_lineno = class_start_line + class_body[: meth_m.start()].count("\n")
                meth_body = _extract_body(class_body, meth_m.end() - 1)

                raw_jsdoc, docstring, _ = _find_preceding_jsdoc(class_body, meth_m.start())
                jsdoc_params = _parse_jsdoc_params(raw_jsdoc) if raw_jsdoc else []
                params = jsdoc_params or _parse_ts_params(raw_params)
                return_ann = return_type or (_parse_jsdoc_return(raw_jsdoc) if raw_jsdoc else None)
                jsdoc_throws = _parse_jsdoc_throws(raw_jsdoc) if raw_jsdoc else []
                throw_stmts = _extract_throw_statements(meth_body, meth_lineno)
                raise_statements = jsdoc_throws + throw_stmts

                qualified = f"{class_name}.{meth_name}"
                sig = f"{meth_name}({raw_params.strip()})"
                if return_type:
                    sig += f": {return_type}"
                func_source = class_body[
                    meth_m.start(): meth_m.start() + len(meth_m.group(0)) + len(meth_body)
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

    def get_language(self) -> str:
        """Return ``'typescript'``."""
        return "typescript"

    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Basic syntax validation for TypeScript source.

        Reuses the JavaScript bracket-balancing check from the parent class.
        """
        return super().validate_syntax(source_code)


# Register with the ParserRegistry on import
ParserRegistry.register("typescript", TypeScriptParser)
