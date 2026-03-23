"""PythonParser — LanguageParser adapter wrapping the existing ``ast`` module logic.

Delegates to the extraction helpers in ``backend/app/pipeline/bce/extractor.py``
so that the existing Python-specific behaviour is preserved while conforming to
the language-agnostic ``LanguageParser`` interface.

Requirements: 2.2, 2.3
"""

from __future__ import annotations

import ast

from app.pipeline.parsers import LanguageParser
from app.pipeline.parsers.registry import ParserRegistry
from app.pipeline.bce.extractor import extract_all_function_infos
from app.schemas import FunctionInfo


class PythonParser(LanguageParser):
    """Python language parser using the built-in ``ast`` module."""

    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all function/method definitions from Python source code.

        Returns FunctionInfo objects with name, signature, docstring,
        params, return_annotation, raise_statements, and mutation_patterns.
        """
        return extract_all_function_infos(source_code)

    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Check if *source_code* is syntactically valid Python.

        Returns ``(True, None)`` on success, ``(False, error_message)`` on
        failure.
        """
        try:
            ast.parse(source_code)
        except SyntaxError as exc:
            msg = f"SyntaxError: {exc.msg} (line {exc.lineno})"
            return False, msg
        return True, None

    def get_language(self) -> str:
        """Return ``'python'``."""
        return "python"

    def extract_comments(self, source_code: str) -> list[dict]:
        """Extract docstrings from Python source code.

        Returns a list of dicts with keys:
            text, start_line, end_line, associated_function.
        """
        results: list[dict] = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return results

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node)
            if not docstring:
                continue

            # The docstring is the first Expr(Constant(str)) in the body.
            first_stmt = node.body[0]
            start_line = first_stmt.lineno
            end_line = first_stmt.end_lineno or start_line

            results.append({
                "text": docstring,
                "start_line": start_line,
                "end_line": end_line,
                "associated_function": node.name,
            })

        return results


# Register with the ParserRegistry on import
ParserRegistry.register("python", PythonParser)
