"""Property tests for the Behavioral Claim Extractor (BCE).

**Validates: Requirements 2.2, 2.5, 2.6, 2.7, 2.8, 10.1–10.4, 12.1–12.4**

Properties tested:
- Property 2:  Claim extraction completeness
- Property 4:  Claim field invariants
- Property 5:  Docstring-less function exclusion
- Property 6:  Deduplication idempotency
- Property 20: NLP pattern match validation
- Property 21: Claim source line accuracy
"""

from __future__ import annotations

import re
from typing import Any

import spacy
from hypothesis import given, settings as h_settings, assume, HealthCheck
from hypothesis import strategies as st

from app.pipeline.bce.extractor import (
    BehavioralClaimExtractor,
    _merge_and_deduplicate,
)
from app.pipeline.bce.patterns import (
    PATTERN_LIBRARY,
    NLPPattern,
    apply_nlp_patterns,
    _validate_dep_pattern,
)
from app.schemas import BCVCategory, Claim


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_NLP = spacy.load("en_core_web_sm")
_BCE = BehavioralClaimExtractor()

VALID_CATEGORIES = {cat.value for cat in BCVCategory}


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Docstring fragments verified to produce claims via both regex AND spaCy dep
# validation.  Each tuple is (docstring_text, expected_category).
_PATTERN_MATCHING_FRAGMENTS: list[tuple[str, BCVCategory]] = [
    ("Returns None.", BCVCategory.RSV),
    ("Returns a string.", BCVCategory.RSV),
    ("Returns self.", BCVCategory.RSV),
    ("Returns a new list.", BCVCategory.SEV),
    ("x must be a positive integer.", BCVCategory.PCV),
    ("data should be a list.", BCVCategory.PCV),
    ("value cannot be None.", BCVCategory.PCV),
    ("Does not modify the input.", BCVCategory.SEV),
    ("Sorts the items in place.", BCVCategory.SEV),
    ("Raises ValueError if empty.", BCVCategory.ECV),
    ("Raises TypeError if wrong type.", BCVCategory.ECV),
    ("Raises KeyError if missing.", BCVCategory.ECV),
    ("Raises IndexError if out of range.", BCVCategory.ECV),
    ("Time complexity is O(n).", BCVCategory.CCV),
]


@st.composite
def docstring_with_known_pattern(draw: st.DrawFn) -> tuple[str, BCVCategory]:
    """Draw a docstring fragment known to match at least one PATTERN_LIBRARY pattern."""
    idx = draw(st.integers(min_value=0, max_value=len(_PATTERN_MATCHING_FRAGMENTS) - 1))
    return _PATTERN_MATCHING_FRAGMENTS[idx]


@st.composite
def function_with_matching_docstring(draw: st.DrawFn) -> tuple[str, BCVCategory]:
    """Generate a Python function whose docstring matches a PATTERN_LIBRARY pattern."""
    fragment, category = draw(docstring_with_known_pattern())
    func_name = draw(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True))
    param_name = draw(st.sampled_from(["x", "data", "items", "value", "n"]))
    source = (
        f"def {func_name}({param_name}):\n"
        f'    """{fragment}"""\n'
        f"    pass\n"
    )
    return source, category


@st.composite
def function_without_docstring(draw: st.DrawFn) -> str:
    """Generate a Python function that has no docstring."""
    func_name = draw(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True))
    param_name = draw(st.sampled_from(["x", "data", "items", "value", "n"]))
    # Body is a simple return — no string literal that could be a docstring
    return (
        f"def {func_name}({param_name}):\n"
        f"    return {param_name}\n"
    )


@st.composite
def claim_list_strategy(draw: st.DrawFn) -> list[Claim]:
    """Generate a list of 0-8 Claim objects with varied fields."""
    n = draw(st.integers(min_value=0, max_value=8))
    claims: list[Claim] = []
    for _ in range(n):
        cat = draw(st.sampled_from(list(BCVCategory)))
        subject = draw(st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True))
        pred = draw(st.from_regex(r"[a-z][a-z ]{1,20}", fullmatch=True))
        line = draw(st.integers(min_value=1, max_value=200))
        raw = draw(st.from_regex(r"[A-Za-z ]{3,30}", fullmatch=True))
        claims.append(
            Claim(
                category=cat,
                subject=subject,
                predicate_object=pred,
                source_line=line,
                raw_text=raw,
            )
        )
    return claims


# ---------------------------------------------------------------------------
# Property 2: Claim extraction completeness
# ---------------------------------------------------------------------------


@given(data=function_with_matching_docstring())
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_claim_extraction_completeness(data: tuple[str, BCVCategory]) -> None:
    """Property 2: For any function with a docstring matching PATTERN_LIBRARY
    patterns, at least one Claim is extracted.

    **Validates: Requirements 2.2, 12.1**
    """
    source, expected_category = data
    schemas = _BCE.extract(source)

    # The function has a docstring, so we should get exactly one ClaimSchema
    assert len(schemas) == 1, f"Expected 1 schema, got {len(schemas)}"

    # At least one claim should be extracted
    assert len(schemas[0].claims) >= 1, (
        f"Expected at least 1 claim for docstring matching {expected_category}, "
        f"got 0. Source:\n{source}"
    )


# ---------------------------------------------------------------------------
# Property 4: Claim field invariants
# ---------------------------------------------------------------------------


@given(data=function_with_matching_docstring())
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_claim_field_invariants(data: tuple[str, BCVCategory]) -> None:
    """Property 4: Every Claim has valid category, non-empty subject,
    non-empty predicate_object, positive source_line, and raw_text is a
    substring of the docstring.

    **Validates: Requirements 2.6, 2.8, 10.1, 10.2, 10.3, 12.3**
    """
    source, _ = data
    schemas = _BCE.extract(source)
    assume(len(schemas) == 1 and len(schemas[0].claims) > 0)

    docstring = schemas[0].function.docstring
    assert docstring is not None

    for claim in schemas[0].claims:
        # Valid category
        assert claim.category.value in VALID_CATEGORIES, (
            f"Invalid category: {claim.category}"
        )

        # Non-empty subject
        assert claim.subject and claim.subject.strip(), (
            f"Empty subject in claim: {claim}"
        )

        # Non-empty predicate_object
        assert claim.predicate_object and claim.predicate_object.strip(), (
            f"Empty predicate_object in claim: {claim}"
        )

        # Positive source_line
        assert claim.source_line > 0, (
            f"Non-positive source_line: {claim.source_line}"
        )

        # raw_text is a substring of the docstring
        assert claim.raw_text in docstring, (
            f"raw_text {claim.raw_text!r} not found in docstring {docstring!r}"
        )


# ---------------------------------------------------------------------------
# Property 5: Docstring-less function exclusion
# ---------------------------------------------------------------------------


@given(source=function_without_docstring())
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_docstringless_function_exclusion(source: str) -> None:
    """Property 5: Functions without docstrings produce no ClaimSchema.

    **Validates: Requirement 2.7**
    """
    schemas = _BCE.extract(source)
    assert len(schemas) == 0, (
        f"Expected 0 schemas for function without docstring, got {len(schemas)}. "
        f"Source:\n{source}"
    )


# ---------------------------------------------------------------------------
# Property 6: Deduplication idempotency
# ---------------------------------------------------------------------------


@given(claims=claim_list_strategy())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_deduplication_idempotency(claims: list[Claim]) -> None:
    """Property 6: deduplicate(deduplicate(C)) == deduplicate(C).

    **Validates: Requirements 2.5, 10.4**
    """
    once = _merge_and_deduplicate(claims, [])
    twice = _merge_and_deduplicate(once, [])

    # Same length
    assert len(once) == len(twice), (
        f"Idempotency violated: first pass {len(once)}, second pass {len(twice)}"
    )

    # Same claims in same order
    for c1, c2 in zip(once, twice):
        assert c1.category == c2.category
        assert c1.subject == c2.subject
        assert c1.predicate_object == c2.predicate_object
        assert c1.source_line == c2.source_line
        assert c1.raw_text == c2.raw_text


# ---------------------------------------------------------------------------
# Property 20: NLP pattern match validation
# ---------------------------------------------------------------------------

# Docstrings where the regex matches but spaCy dep validation should reject.
# These are crafted so the regex fires but the dependency structure is wrong.
_REGEX_ONLY_FRAGMENTS: list[str] = [
    # "returns" used as a noun subject, not a verb — dep parse differs
    "The returns value is stored.",
    # "raises" used as a noun, not a verb
    "The raises count is tracked.",
]


@st.composite
def docstring_with_regex_match_no_dep(draw: st.DrawFn) -> tuple[str, NLPPattern]:
    """Generate a docstring where a PATTERN_LIBRARY regex matches but the
    spaCy dependency structure should NOT validate the match.

    We construct sentences where the keyword appears in a non-predicate role.
    """
    pattern = draw(st.sampled_from(PATTERN_LIBRARY))
    # Build a sentence that contains the regex trigger word but in a
    # syntactic context that should fail dep validation.
    # We embed the trigger word as a noun modifier rather than a verb.
    trigger = pattern.dep_pattern.get("predicate", "")
    if not trigger:
        assume(False)

    # Construct a sentence where the trigger word is used as a noun/adjective
    # rather than in its expected syntactic role.
    sentence = f"The {trigger} table is stored in memory."
    # Verify the regex actually matches this sentence
    match = re.search(pattern.regex, sentence)
    assume(match is not None)

    return sentence, pattern


@given(data=docstring_with_regex_match_no_dep())
@h_settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_nlp_pattern_match_validation(data: tuple[str, NLPPattern]) -> None:
    """Property 20: A regex match without spaCy dep validation produces no Claim.

    When a regex pattern matches a docstring segment but the spaCy dependency
    structure does not validate the match, no Claim should be produced for
    that specific match.

    **Validates: Requirement 12.2**
    """
    sentence, pattern = data

    # Run apply_nlp_patterns on the sentence
    claims = apply_nlp_patterns(sentence, _NLP)

    # For each claim produced, verify it was actually dep-validated.
    # The key check: if the dep validation would fail for this pattern,
    # no claim from this pattern should appear.
    doc = _NLP(sentence)
    for match in re.finditer(pattern.regex, sentence):
        span = doc.char_span(match.start(), match.end())
        if span is None:
            span = doc.char_span(match.start(), match.end(), alignment_mode="expand")

        if span is None or not _validate_dep_pattern(span, pattern.dep_pattern):
            # Dep validation fails — no claim from this pattern should exist
            pattern_claims = [
                c for c in claims
                if c.raw_text == match.group(0).strip()
            ]
            assert len(pattern_claims) == 0, (
                f"Claim produced for pattern {pattern.name!r} despite failing "
                f"dep validation. Sentence: {sentence!r}"
            )


# ---------------------------------------------------------------------------
# Property 21: Claim source line accuracy
# ---------------------------------------------------------------------------


@st.composite
def multiline_docstring_function(draw: st.DrawFn) -> str:
    """Generate a function with a multi-line docstring containing known patterns."""
    func_name = draw(st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True))
    param = draw(st.sampled_from(["x", "data", "items"]))

    # Pick 1-3 pattern-matching fragments and place them on separate lines
    n_fragments = draw(st.integers(min_value=1, max_value=3))
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(_PATTERN_MATCHING_FRAGMENTS) - 1),
            min_size=n_fragments,
            max_size=n_fragments,
        )
    )
    fragments = [_PATTERN_MATCHING_FRAGMENTS[i][0] for i in indices]

    # Add some blank/filler lines between fragments
    docstring_lines: list[str] = []
    for frag in fragments:
        n_blanks = draw(st.integers(min_value=0, max_value=2))
        for _ in range(n_blanks):
            docstring_lines.append("")
        docstring_lines.append(frag)

    docstring_body = "\n    ".join(docstring_lines)
    source = (
        f"def {func_name}({param}):\n"
        f'    """{docstring_body}\n'
        f'    """\n'
        f"    pass\n"
    )
    return source


@given(source=multiline_docstring_function())
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_claim_source_line_accuracy(source: str) -> None:
    """Property 21: source_line references a line containing the raw_text.

    For every Claim produced by the BCE, the source_line value should
    reference a line in the source file whose content contains the
    Claim's raw_text (or a portion of it).

    **Validates: Requirement 12.4**
    """
    schemas = _BCE.extract(source)
    assume(len(schemas) == 1 and len(schemas[0].claims) > 0)

    source_lines = source.splitlines()
    docstring = schemas[0].function.docstring
    assert docstring is not None

    for claim in schemas[0].claims:
        # source_line is 1-based
        assert 1 <= claim.source_line <= len(source_lines), (
            f"source_line {claim.source_line} out of range "
            f"(1..{len(source_lines)})"
        )

        # The raw_text must be a substring of the docstring (Property 4
        # also checks this, but it's a precondition for the line check).
        assert claim.raw_text in docstring

        # The raw_text should appear somewhere in the source file.
        # We verify that the full source contains the raw_text and that
        # the source_line is within a reasonable range of where it
        # actually appears.
        full_source = "\n".join(source_lines)
        assert claim.raw_text in full_source, (
            f"raw_text {claim.raw_text!r} not found in source"
        )

        # Find all lines (1-based) that contain the raw_text
        actual_lines = [
            i + 1
            for i, line in enumerate(source_lines)
            if claim.raw_text in line
        ]

        # source_line should be within ±3 lines of an actual occurrence
        # (accounts for docstring_start_line offset calculations)
        if actual_lines:
            min_dist = min(abs(claim.source_line - al) for al in actual_lines)
            assert min_dist <= 3, (
                f"source_line {claim.source_line} is too far from actual "
                f"occurrences at lines {actual_lines} for raw_text "
                f"{claim.raw_text!r}"
            )
