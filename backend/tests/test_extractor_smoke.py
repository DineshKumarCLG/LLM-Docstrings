"""Smoke tests for BehavioralClaimExtractor and _merge_and_deduplicate."""

from app.pipeline.bce.extractor import BehavioralClaimExtractor, _merge_and_deduplicate
from app.schemas import BCVCategory, Claim


class TestMergeAndDeduplicate:
    def test_removes_duplicates_by_key(self):
        c1 = Claim(
            category=BCVCategory.ECV,
            subject="ValueError",
            predicate_object="raises ValueError",
            source_line=5,
            raw_text="raises ValueError",
        )
        c2 = Claim(
            category=BCVCategory.ECV,
            subject="ValueError",
            predicate_object="raises ValueError",
            source_line=10,
            raw_text="Raises ValueError if empty",
        )
        c3 = Claim(
            category=BCVCategory.SEV,
            subject="data",
            predicate_object="modifies data via sort",
            source_line=7,
            raw_text="modifies data via sort",
        )
        merged = _merge_and_deduplicate([c1], [c2, c3])
        assert len(merged) == 2
        assert merged[0].category == BCVCategory.ECV
        assert merged[1].category == BCVCategory.SEV

    def test_ast_claims_take_priority(self):
        """When AST and NLP produce the same claim, the AST version is kept."""
        ast_claim = Claim(
            category=BCVCategory.ECV,
            subject="ValueError",
            predicate_object="raises ValueError",
            source_line=5,
            raw_text="raises ValueError",
        )
        nlp_claim = Claim(
            category=BCVCategory.ECV,
            subject="ValueError",
            predicate_object="raises ValueError",
            source_line=10,
            raw_text="Raises ValueError if empty",
        )
        merged = _merge_and_deduplicate([ast_claim], [nlp_claim])
        assert len(merged) == 1
        assert merged[0].source_line == 5  # AST version kept

    def test_idempotency(self):
        c1 = Claim(
            category=BCVCategory.ECV,
            subject="ValueError",
            predicate_object="raises ValueError",
            source_line=5,
            raw_text="raises ValueError",
        )
        c2 = Claim(
            category=BCVCategory.SEV,
            subject="data",
            predicate_object="modifies data via sort",
            source_line=7,
            raw_text="modifies data via sort",
        )
        once = _merge_and_deduplicate([c1, c2], [])
        twice = _merge_and_deduplicate(once, [])
        assert len(once) == len(twice)

    def test_empty_inputs(self):
        assert _merge_and_deduplicate([], []) == []


class TestBehavioralClaimExtractor:
    def setup_method(self):
        self.bce = BehavioralClaimExtractor()

    def test_skips_functions_without_docstrings(self):
        source = "def foo(x):\n    return x + 1\n"
        schemas = self.bce.extract(source)
        assert len(schemas) == 0

    def test_extracts_claims_from_documented_function(self):
        source = (
            "def greet(name: str) -> str:\n"
            '    """Returns a greeting string.\n'
            "\n"
            "    Raises:\n"
            "        ValueError: If name is empty.\n"
            '    """\n'
            "    if not name:\n"
            "        raise ValueError('empty')\n"
            "    return f'Hello {name}'\n"
        )
        schemas = self.bce.extract(source)
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema.function.name == "greet"
        # Should have at least the ECV claim from the raise statement
        categories = {c.category for c in schema.claims}
        assert BCVCategory.ECV in categories

    def test_multiple_functions_mixed_docstrings(self):
        source = (
            "def documented(x):\n"
            '    """Returns x squared."""\n'
            "    return x ** 2\n"
            "\n"
            "def undocumented(x):\n"
            "    return x + 1\n"
            "\n"
            "def also_documented(data: list):\n"
            '    """Sorts the data in place."""\n'
            "    data.sort()\n"
        )
        schemas = self.bce.extract(source)
        assert len(schemas) == 2
        names = {s.function.name for s in schemas}
        assert names == {"documented", "also_documented"}

    def test_ast_and_nlp_claims_merged(self):
        source = (
            "def process(data: list) -> list:\n"
            '    """Returns a new list with processed values.\n'
            "\n"
            "    Does not modify the input list.\n"
            "\n"
            "    Raises:\n"
            "        ValueError: If data is empty.\n"
            '    """\n'
            "    if not data:\n"
            "        raise ValueError('empty')\n"
            "    data.sort()\n"
            "    return data\n"
        )
        schemas = self.bce.extract(source)
        assert len(schemas) == 1
        claims = schemas[0].claims
        # Should have claims from both tracks
        assert len(claims) > 0
        # No duplicate (category, subject, predicate_object) tuples
        keys = [(c.category.value, c.subject, c.predicate_object) for c in claims]
        assert len(keys) == len(set(keys))
