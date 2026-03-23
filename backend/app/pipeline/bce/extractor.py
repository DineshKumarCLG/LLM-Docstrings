"""Behavioral Claim Extractor (BCE) — AST-based function info extraction.

Parses Python source code using the ``ast`` module and extracts structural
information for every function definition (``FunctionDef`` and
``AsyncFunctionDef``).

Requirements: 2.1
"""

from __future__ import annotations

import ast
from typing import Union

import spacy

from app.schemas import BCVCategory, Claim, ClaimSchema, FunctionInfo
from app.pipeline.bce.patterns import apply_nlp_patterns
from app.pipeline.parsers import LanguageParser


_FuncNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _unparse_annotation(node: ast.expr | None) -> str | None:
    """Return the string representation of a type-annotation AST node.

    Returns ``None`` when *node* is ``None`` (i.e. no annotation present).
    """
    if node is None:
        return None
    return ast.unparse(node)


def _extract_raise_statements(func_node: _FuncNode) -> list[dict]:
    """Walk the function body for ``ast.Raise`` nodes and extract exception info.

    For each ``raise`` statement found, extracts:
    - ``exception_class``: the name of the exception being raised (e.g. ``"ValueError"``).
      Falls back to ``"Exception"`` when the exception class cannot be determined.
    - ``condition``: the unparsed source of the enclosing ``if`` test, or ``None``
      when the raise is unconditional.
    - ``lineno``: the line number of the raise statement.

    Requirements: 2.3
    """
    results: list[dict] = []

    # Build a parent map so we can walk up to find enclosing ``if`` statements.
    parent_map: dict[int, ast.AST] = {}
    for node in ast.walk(func_node):
        for child in ast.iter_child_nodes(node):
            parent_map[id(child)] = node

    for node in ast.walk(func_node):
        if not isinstance(node, ast.Raise):
            continue

        # --- Determine exception class ---
        exception_class = "Exception"
        exc = node.exc
        if exc is not None:
            if isinstance(exc, ast.Name):
                # raise ValueError
                exception_class = exc.id
            elif isinstance(exc, ast.Call):
                # raise ValueError("msg")
                func = exc.func
                if isinstance(func, ast.Name):
                    exception_class = func.id
                elif isinstance(func, ast.Attribute):
                    # raise module.SomeError(...)
                    exception_class = func.attr

        # --- Determine enclosing if-condition ---
        condition: str | None = None
        current: ast.AST = node
        while id(current) in parent_map:
            parent = parent_map[id(current)]
            if isinstance(parent, ast.If):
                condition = ast.unparse(parent.test)
                break
            current = parent

        results.append({
            "exception_class": exception_class,
            "condition": condition,
            "lineno": node.lineno,
        })

    return results


# ---------------------------------------------------------------------------
# Algorithm 2: AST Mutation Detection
# ---------------------------------------------------------------------------

MUTATION_METHODS: dict[str, set[str]] = {
    "list": {"sort", "append", "extend", "insert", "remove", "pop", "clear", "reverse"},
    "dict": {"update", "pop", "clear", "setdefault", "popitem"},
    "set": {"add", "remove", "discard", "pop", "clear", "update"},
}

# Flattened set for fast lookup
_ALL_MUTATION_METHODS: set[str] = set()
for _methods in MUTATION_METHODS.values():
    _ALL_MUTATION_METHODS |= _methods


def detect_mutations(func_node: _FuncNode) -> list[dict]:
    """Detect in-place mutation patterns on function parameters.

    Scans the function body for:
    1. Method calls on parameters matching MUTATION_METHODS
       (e.g. ``data.sort()``, ``items.append(x)``)
    2. Subscript assignment — item (``a[i] = ...``) or slice (``a[i:j] = ...``)
    3. Attribute assignment (``a.attr = ...``)
    4. Augmented assignment (``a += ...``)

    Returns a list of dicts: ``[{"target": str, "method": str, "line": int}]``

    Requirements: 2.4
    """
    mutations: list[dict] = []

    # Collect parameter names from the function signature
    args = func_node.args
    param_names: set[str] = set()
    for arg in args.args:
        param_names.add(arg.arg)
    if args.vararg:
        param_names.add(args.vararg.arg)
    for arg in args.kwonlyargs:
        param_names.add(arg.arg)
    if args.kwarg:
        param_names.add(args.kwarg.arg)

    for node in ast.walk(func_node):
        # 1. Method calls: param.method()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name) and value.id in param_names:
                method = node.func.attr
                if method in _ALL_MUTATION_METHODS:
                    mutations.append({
                        "target": value.id,
                        "method": method,
                        "line": node.lineno,
                    })

        # 2. Subscript assignment: param[x] = ... or param[i:j] = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    if target.value.id in param_names:
                        method = (
                            "slice_assignment"
                            if isinstance(target.slice, ast.Slice)
                            else "item_assignment"
                        )
                        mutations.append({
                            "target": target.value.id,
                            "method": method,
                            "line": node.lineno,
                        })

        # 3. Attribute assignment: param.attr = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id in param_names:
                        mutations.append({
                            "target": target.value.id,
                            "method": "attribute_assignment",
                            "line": node.lineno,
                        })

        # 4. Augmented assignment: param += ...
        if isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name) and node.target.id in param_names:
                mutations.append({
                    "target": node.target.id,
                    "method": "augmented_assignment",
                    "line": node.lineno,
                })

    return mutations


def _extract_params(args: ast.arguments) -> list[dict]:
    """Extract parameter info (name, annotation, default) from an ``ast.arguments`` node.

    Defaults are aligned from the *end* of the positional args list, matching
    Python's semantics (the last N args have defaults when there are N defaults).
    """
    params: list[dict] = []

    # Regular positional / keyword args
    all_args = args.args
    defaults = args.defaults
    # defaults align to the tail of all_args
    n_no_default = len(all_args) - len(defaults)

    for idx, arg in enumerate(all_args):
        default_idx = idx - n_no_default
        default: str | None = None
        if default_idx >= 0:
            default = ast.unparse(defaults[default_idx])

        params.append({
            "name": arg.arg,
            "annotation": _unparse_annotation(arg.annotation),
            "default": default,
        })

    # *args
    if args.vararg:
        params.append({
            "name": f"*{args.vararg.arg}",
            "annotation": _unparse_annotation(args.vararg.annotation),
            "default": None,
        })

    # keyword-only args
    for idx, arg in enumerate(args.kwonlyargs):
        kw_default = args.kw_defaults[idx]
        default = ast.unparse(kw_default) if kw_default is not None else None
        params.append({
            "name": arg.arg,
            "annotation": _unparse_annotation(arg.annotation),
            "default": default,
        })

    # **kwargs
    if args.kwarg:
        params.append({
            "name": f"**{args.kwarg.arg}",
            "annotation": _unparse_annotation(args.kwarg.annotation),
            "default": None,
        })

    return params


def _build_signature(node: _FuncNode) -> str:
    """Reconstruct the full signature string including type annotations.

    Produces e.g. ``"def normalize_list(data: list[float]) -> list[float]"``
    or ``"async def fetch(url: str) -> bytes"``.
    """
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"

    parts: list[str] = []
    args = node.args

    # positional args
    defaults = args.defaults
    n_no_default = len(args.args) - len(defaults)
    for idx, arg in enumerate(args.args):
        piece = arg.arg
        if arg.annotation:
            piece += f": {ast.unparse(arg.annotation)}"
        default_idx = idx - n_no_default
        if default_idx >= 0:
            piece += f" = {ast.unparse(defaults[default_idx])}"
        parts.append(piece)

    # *args
    if args.vararg:
        piece = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            piece += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(piece)
    elif args.kwonlyargs:
        # bare * separator when there are keyword-only args but no *args
        parts.append("*")

    # keyword-only args
    for idx, arg in enumerate(args.kwonlyargs):
        piece = arg.arg
        if arg.annotation:
            piece += f": {ast.unparse(arg.annotation)}"
        kw_default = args.kw_defaults[idx]
        if kw_default is not None:
            piece += f" = {ast.unparse(kw_default)}"
        parts.append(piece)

    # **kwargs
    if args.kwarg:
        piece = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            piece += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(piece)

    sig = f"{prefix} {node.name}({', '.join(parts)})"
    if node.returns:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def _get_function_source(node: _FuncNode, source_lines: list[str]) -> str:
    """Slice the original source lines to get the full function text."""
    # ast nodes use 1-based line numbers
    start = node.lineno - 1
    end = node.end_lineno  # end_lineno is inclusive, but slice is exclusive
    if end is None:
        end = start + 1
    return "\n".join(source_lines[start:end])


def _extract_function_info(
    node: _FuncNode,
    source: str,
    source_lines: list[str],
    module_name: str | None = None,
) -> FunctionInfo:
    """Extract structural information from a single function AST node.

    Parameters
    ----------
    node:
        An ``ast.FunctionDef`` or ``ast.AsyncFunctionDef`` node.
    source:
        The complete source code string (used for ``ast.get_source_segment``).
    source_lines:
        The source split into lines (used as fallback for source extraction).
    module_name:
        Optional module qualifier.  When provided the ``qualified_name`` is
        ``module_name.function_name``; otherwise it equals the bare function
        name.

    Returns
    -------
    FunctionInfo
        Populated with name, qualified_name, source text, line number,
        signature, docstring, params, and return_annotation.
        ``raise_statements`` and ``mutation_patterns`` are left as empty
        lists (filled by tasks 3.2 and 3.3).
    """
    name = node.name

    qualified_name = f"{module_name}.{name}" if module_name else name

    func_source = (
        ast.get_source_segment(source, node)
        or _get_function_source(node, source_lines)
    )

    signature = _build_signature(node)
    docstring = ast.get_docstring(node)
    params = _extract_params(node.args)
    return_annotation = _unparse_annotation(node.returns)

    return FunctionInfo(
        name=name,
        qualified_name=qualified_name,
        source=func_source,
        lineno=node.lineno,
        signature=signature,
        docstring=docstring,
        params=params,
        return_annotation=return_annotation,
        raise_statements=_extract_raise_statements(node),
        mutation_patterns=detect_mutations(node),
    )


def extract_all_function_infos(
    source_code: str,
    module_name: str | None = None,
) -> list[FunctionInfo]:
    """Parse *source_code* and return :class:`FunctionInfo` for every function.

    Walks the top-level body of the module looking for ``FunctionDef`` and
    ``AsyncFunctionDef`` nodes.
    """
    tree = ast.parse(source_code)
    source_lines = source_code.splitlines()
    results: list[FunctionInfo] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            results.append(
                _extract_function_info(node, source_code, source_lines, module_name)
            )

    return results


# ---------------------------------------------------------------------------
# Claim merge / deduplication
# ---------------------------------------------------------------------------


def _merge_and_deduplicate(
    ast_claims: list[Claim],
    nlp_claims: list[Claim],
) -> list[Claim]:
    """Combine AST-track and NLP-track claims, removing duplicates.

    Deduplication key: ``(category, subject, predicate_object)`` tuple.
    When duplicates exist the first occurrence (AST claims come first) is kept.

    Requirements: 2.5, 10.4
    """
    seen: set[tuple[str, str, str]] = set()
    merged: list[Claim] = []

    for claim in [*ast_claims, *nlp_claims]:
        key = (claim.category.value, claim.subject, claim.predicate_object)
        if key not in seen:
            seen.add(key)
            merged.append(claim)

    return merged


# ---------------------------------------------------------------------------
# BehavioralClaimExtractor — main BCE entry point
# ---------------------------------------------------------------------------


def _get_docstring_start_line(func_node: _FuncNode) -> int:
    """Return the 1-based source line where the function's docstring begins.

    The docstring is the first statement in the body when it is an ``Expr``
    wrapping a ``Constant`` string.  Falls back to the function's own line
    number + 1 if the node structure is unexpected.
    """
    if func_node.body:
        first_stmt = func_node.body[0]
        if (
            isinstance(first_stmt, ast.Expr)
            and isinstance(first_stmt.value, ast.Constant)
            and isinstance(first_stmt.value.value, str)
        ):
            return first_stmt.lineno
    return func_node.lineno + 1


class BehavioralClaimExtractor:
    """Stage 1 of the VeriDoc pipeline — Behavioral Claim Extraction.

    Implements Algorithm 1 from the paper: for each function in the source
    code that has a docstring, run the AST track (raise statements → ECV,
    mutation patterns → SEV) and the NLP track (47 regex patterns over spaCy
    dependency parse), merge and deduplicate, and return a ``ClaimSchema``
    per function.

    Accepts an optional ``LanguageParser`` instance.  When provided, the
    extractor delegates function extraction to ``parser.parse_functions()``
    instead of the hardcoded Python ``ast`` module.  When *parser* is
    ``None`` (the default), the existing Python-only behaviour is preserved
    for backward compatibility.

    The NLP pattern matching (spaCy) remains language-agnostic — it operates
    on extracted docstrings/comments regardless of source language.

    Requirements: 2.1–2.8, 2.10
    """

    def __init__(self, parser: LanguageParser | None = None) -> None:
        self._nlp = spacy.load("en_core_web_sm")
        self._parser = parser

    # -- public API ---------------------------------------------------------

    def extract(self, source_code: str) -> list[ClaimSchema]:
        """Extract behavioural claims from every documented function.

        Parameters
        ----------
        source_code : str
            Syntactically valid source code (Python or any supported language).

        Returns
        -------
        list[ClaimSchema]
            One ``ClaimSchema`` per function that has a docstring.
            Functions without docstrings are skipped (Requirement 2.7).
        """
        if self._parser is not None:
            func_infos = self._parser.parse_functions(source_code)
        else:
            func_infos = extract_all_function_infos(source_code)
        results: list[ClaimSchema] = []

        for func_info in func_infos:
            # Requirement 2.7: skip functions without docstrings
            if not func_info.docstring:
                continue

            ast_claims = self._ast_track(func_info)
            nlp_claims = self._nlp_track(func_info)
            merged = _merge_and_deduplicate(ast_claims, nlp_claims)

            results.append(ClaimSchema(function=func_info, claims=merged))

        return results

    # -- internal tracks ----------------------------------------------------

    def _ast_track(self, func_info: FunctionInfo) -> list[Claim]:
        """Produce ECV claims from raise statements and SEV claims from mutations."""
        claims: list[Claim] = []

        # ECV claims from raise statements (Requirement 2.3)
        for raise_info in func_info.raise_statements:
            exc_class = raise_info["exception_class"]
            condition = raise_info.get("condition")
            lineno = raise_info["lineno"]

            claims.append(
                Claim(
                    category=BCVCategory.ECV,
                    subject=exc_class,
                    predicate_object=f"raises {exc_class}",
                    conditionality=condition,
                    source_line=lineno,
                    raw_text=f"raises {exc_class}" + (
                        f" if {condition}" if condition else ""
                    ),
                )
            )

        # SEV claims from mutation patterns (Requirement 2.4)
        for mut in func_info.mutation_patterns:
            target = mut["target"]
            method = mut["method"]
            lineno = mut["line"]

            claims.append(
                Claim(
                    category=BCVCategory.SEV,
                    subject=target,
                    predicate_object=f"modifies {target} via {method}",
                    conditionality=None,
                    source_line=lineno,
                    raw_text=f"modifies {target} via {method}",
                )
            )

        return claims

    def _nlp_track(self, func_info: FunctionInfo) -> list[Claim]:
        """Apply NLP patterns over the function's docstring.

        The NLP track is language-agnostic — it operates on extracted
        docstrings/comments regardless of source language (Requirement 2.10).
        """
        if not func_info.docstring:
            return []

        # Compute the source line where the docstring text starts.
        # For Python source (no parser or Python parser), re-parse with ast
        # for accurate line info.  For other languages, use a simple fallback.
        docstring_start_line = func_info.lineno + 1  # default fallback

        if self._parser is None or (
            self._parser is not None and self._parser.get_language() == "python"
        ):
            try:
                tree = ast.parse(func_info.source)
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        docstring_start_line = (
                            func_info.lineno
                            + _get_docstring_start_line(node)
                            - node.lineno
                        )
                        break
            except SyntaxError:
                pass  # keep the default fallback

        return apply_nlp_patterns(
            func_info.docstring,
            self._nlp,
            docstring_start_line=docstring_start_line,
        )
