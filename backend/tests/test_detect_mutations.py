"""Unit tests for detect_mutations.

Validates Requirement 2.4 — AST detection of in-place mutation patterns on
function parameters (method calls, subscript/slice/attribute assignment,
augmented assignment).
"""

from __future__ import annotations

import ast

from app.pipeline.bce.extractor import (
    detect_mutations,
    extract_all_function_infos,
)


def _parse_first_func(source: str):
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found")


# ---------------------------------------------------------------------------
# Method call mutations
# ---------------------------------------------------------------------------


class TestMethodCallMutations:
    def test_list_sort(self):
        src = '''\
def process(data):
    data.sort()
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0] == {"target": "data", "method": "sort", "line": 2}

    def test_list_append(self):
        src = '''\
def add_item(items, val):
    items.append(val)
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["target"] == "items"
        assert muts[0]["method"] == "append"

    def test_dict_update(self):
        src = '''\
def merge(config, overrides):
    config.update(overrides)
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["target"] == "config"
        assert muts[0]["method"] == "update"

    def test_set_add(self):
        src = '''\
def register(seen, item):
    seen.add(item)
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["target"] == "seen"
        assert muts[0]["method"] == "add"

    def test_non_mutation_method_ignored(self):
        """Methods not in MUTATION_METHODS should not be detected."""
        src = '''\
def process(data):
    data.copy()
    data.count(1)
    data.index(1)
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert muts == []

    def test_method_on_non_param_ignored(self):
        """Method calls on local variables should not be detected."""
        src = '''\
def process(data):
    local = [1, 2, 3]
    local.sort()
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert muts == []

    def test_multiple_mutation_methods(self):
        src = '''\
def process(data):
    data.append(1)
    data.extend([2, 3])
    data.sort()
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 3
        methods = [m["method"] for m in muts]
        assert methods == ["append", "extend", "sort"]


# ---------------------------------------------------------------------------
# Subscript assignment mutations
# ---------------------------------------------------------------------------


class TestSubscriptAssignment:
    def test_item_assignment(self):
        src = '''\
def update(data, idx, val):
    data[idx] = val
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0] == {"target": "data", "method": "item_assignment", "line": 2}

    def test_slice_assignment(self):
        src = '''\
def replace_range(data, vals):
    data[1:3] = vals
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["method"] == "slice_assignment"
        assert muts[0]["target"] == "data"

    def test_subscript_on_non_param_ignored(self):
        src = '''\
def process(data):
    local = list(data)
    local[0] = 99
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert muts == []


# ---------------------------------------------------------------------------
# Attribute assignment mutations
# ---------------------------------------------------------------------------


class TestAttributeAssignment:
    def test_attribute_assignment(self):
        src = '''\
def configure(obj):
    obj.name = "updated"
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0] == {"target": "obj", "method": "attribute_assignment", "line": 2}

    def test_attribute_on_non_param_ignored(self):
        src = '''\
def process(data):
    local = data
    local.x = 10
'''
        node = _parse_first_func(src)
        # local is not a parameter, so no mutation detected
        muts = detect_mutations(node)
        assert muts == []


# ---------------------------------------------------------------------------
# Augmented assignment mutations
# ---------------------------------------------------------------------------


class TestAugmentedAssignment:
    def test_augmented_add(self):
        src = '''\
def extend_list(data, extra):
    data += extra
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0] == {"target": "data", "method": "augmented_assignment", "line": 2}

    def test_augmented_on_non_param_ignored(self):
        src = '''\
def process(data):
    total = 0
    total += data
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert muts == []


# ---------------------------------------------------------------------------
# Edge cases and combinations
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_mutations(self):
        src = '''\
def pure(x, y):
    return x + y
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert muts == []

    def test_mixed_mutations(self):
        """Multiple mutation types on the same parameter."""
        src = '''\
def transform(data, config):
    data.append(1)
    data[0] = 99
    config.name = "new"
    data += [2]
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 4
        methods = {m["method"] for m in muts}
        assert methods == {"append", "item_assignment", "attribute_assignment", "augmented_assignment"}

    def test_kwargs_param_detected(self):
        """Mutations on **kwargs parameter should be detected."""
        src = '''\
def process(**kwargs):
    kwargs.update({"key": "val"})
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["target"] == "kwargs"
        assert muts[0]["method"] == "update"

    def test_vararg_param_detected(self):
        """Mutations on *args are unlikely but the param name should be tracked."""
        src = '''\
def process(*args):
    args.append(1)
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["target"] == "args"

    def test_kwonly_param_detected(self):
        src = '''\
def process(*, items):
    items.clear()
'''
        node = _parse_first_func(src)
        muts = detect_mutations(node)
        assert len(muts) == 1
        assert muts[0]["target"] == "items"
        assert muts[0]["method"] == "clear"


# ---------------------------------------------------------------------------
# Integration: mutation_patterns populated in FunctionInfo
# ---------------------------------------------------------------------------


class TestMutationPatternsInFunctionInfo:
    def test_function_info_has_mutation_patterns(self):
        src = '''\
def normalize_list(data: list[float]) -> None:
    """Normalize values in-place."""
    min_val = min(data)
    max_val = max(data)
    rng = max_val - min_val
    data[:] = [(v - min_val) / rng for v in data]
'''
        infos = extract_all_function_infos(src)
        assert len(infos) == 1
        mp = infos[0].mutation_patterns
        assert len(mp) == 1
        assert mp[0]["target"] == "data"
        assert mp[0]["method"] == "slice_assignment"

    def test_function_without_mutations_has_empty_list(self):
        src = '''\
def add(a, b):
    """Add two numbers."""
    return a + b
'''
        infos = extract_all_function_infos(src)
        assert len(infos) == 1
        assert infos[0].mutation_patterns == []
