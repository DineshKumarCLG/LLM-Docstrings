"""Documentation tree builder for the VeriDoc three-tab dashboard.

Parses Python source code using the ``ast`` module and produces a
hierarchical DocumentationTree containing modules, classes, functions,
and methods — each with id, name, type, docstring, signature, children,
lineno, and endLineno.

Requirements: 8.4, 8.5, 8.6
"""

from __future__ import annotations

import ast
import uuid
from datetime import datetime, timezone
from typing import Union


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ASTFunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


# ---------------------------------------------------------------------------
# Signature builder
# ---------------------------------------------------------------------------


def _build_signature(func_node: ASTFunctionNode) -> str:
    """Build a human-readable signature string from an AST function node.

    Includes parameter names, type annotations, defaults, and the return
    annotation when present.  Async functions are prefixed with ``async ``.

    Examples::

        def foo(x: int, y: str = "hi") -> bool  →  "foo(x: int, y: str = 'hi') -> bool"
        async def bar(self)                       →  "async bar(self)"
    """
    args = func_node.args
    params: list[str] = []

    # Collect all positional/keyword args with optional annotation + default
    # Defaults are right-aligned: len(args.args) - len(args.defaults) is the
    # index of the first arg that has a default.
    n_args = len(args.args)
    n_defaults = len(args.defaults)
    defaults_offset = n_args - n_defaults

    for i, arg in enumerate(args.args):
        part = arg.arg
        if arg.annotation is not None:
            part += f": {ast.unparse(arg.annotation)}"
        default_idx = i - defaults_offset
        if default_idx >= 0:
            part += f" = {ast.unparse(args.defaults[default_idx])}"
        params.append(part)

    # *args
    if args.vararg is not None:
        part = f"*{args.vararg.arg}"
        if args.vararg.annotation is not None:
            part += f": {ast.unparse(args.vararg.annotation)}"
        params.append(part)
    elif args.kwonlyargs:
        # bare * separator when there are keyword-only args but no *args
        params.append("*")

    # keyword-only args
    kw_defaults = args.kw_defaults  # may contain None entries
    for i, arg in enumerate(args.kwonlyargs):
        part = arg.arg
        if arg.annotation is not None:
            part += f": {ast.unparse(arg.annotation)}"
        if i < len(kw_defaults) and kw_defaults[i] is not None:
            part += f" = {ast.unparse(kw_defaults[i])}"  # type: ignore[arg-type]
        params.append(part)

    # **kwargs
    if args.kwarg is not None:
        part = f"**{args.kwarg.arg}"
        if args.kwarg.annotation is not None:
            part += f": {ast.unparse(args.kwarg.annotation)}"
        params.append(part)

    sig = f"{func_node.name}({', '.join(params)})"

    if func_node.returns is not None:
        sig += f" -> {ast.unparse(func_node.returns)}"

    if isinstance(func_node, ast.AsyncFunctionDef):
        sig = f"async {sig}"

    return sig


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------


def _build_function_node(
    func_node: ASTFunctionNode,
    node_type: str = "function",
) -> dict:
    """Build a DocumentationNode dict for a function or method.

    PRECONDITION: func_node is a valid ast.FunctionDef or ast.AsyncFunctionDef
    POSTCONDITION: returns a node dict with type == node_type and no children
    """
    return {
        "id": str(uuid.uuid4()),
        "name": func_node.name,
        "type": node_type,
        "docstring": ast.get_docstring(func_node),
        "signature": _build_signature(func_node),
        "children": [],
        "lineno": func_node.lineno,
        "endLineno": getattr(func_node, "end_lineno", None),
    }


def _build_class_node(class_node: ast.ClassDef) -> dict:
    """Build a DocumentationNode dict for a class, with method children.

    PRECONDITION: class_node is a valid ast.ClassDef
    POSTCONDITION: returns a node with type == "class" and children for all
                   direct methods (FunctionDef / AsyncFunctionDef) in the body
    LOOP INVARIANT: all processed methods are added as children
    """
    children: list[dict] = []
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            children.append(_build_function_node(item, node_type="method"))

    return {
        "id": str(uuid.uuid4()),
        "name": class_node.name,
        "type": "class",
        "docstring": ast.get_docstring(class_node),
        "signature": None,
        "children": children,
        "lineno": class_node.lineno,
        "endLineno": getattr(class_node, "end_lineno", None),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_documentation_tree(source_code: str, analysis_id: str) -> dict:
    """Parse *source_code* and return a DocumentationTree dict.

    PRECONDITION: source_code is syntactically valid Python (parseable by
                  ``ast.parse``).
    POSTCONDITION:
      - Returns a dict with keys ``analysisId``, ``rootNodes``, ``generatedAt``
      - ``rootNodes`` contains one entry per top-level function or class
      - Each class node contains child nodes for all its direct methods
      - All ``lineno`` values are positive integers (>= 1)

    Requirements: 8.4, 8.5, 8.6
    """
    tree = ast.parse(source_code)
    root_nodes: list[dict] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            root_nodes.append(_build_function_node(node, node_type="function"))
        elif isinstance(node, ast.ClassDef):
            root_nodes.append(_build_class_node(node))

    return {
        "analysisId": analysis_id,
        "rootNodes": root_nodes,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
