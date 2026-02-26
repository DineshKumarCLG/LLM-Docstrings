"""NLP Pattern Matching for the Behavioral Claim Extractor (Algorithm 3).

Defines the PATTERN_LIBRARY of 47 NLPPattern instances covering all six BCV
categories (RSV, PCV, SEV, ECV, COV, CCV) and the ``apply_nlp_patterns()``
function that runs spaCy + regex matching with dependency-structure validation.

Requirements: 2.2, 12.1, 12.2, 12.3, 12.4
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.schemas import BCVCategory, Claim


@dataclass(frozen=True)
class NLPPattern:
    """A single NLP extraction pattern.

    Attributes
    ----------
    category : BCVCategory
        The BCV category this pattern targets.
    name : str
        Human-readable pattern identifier.
    regex : str
        Regex pattern applied to the raw docstring text.
    dep_pattern : dict
        spaCy dependency-structure validation rules.  Supported keys:

        - ``predicate`` (str): a token lemma that must appear in the span.
        - ``head_pos`` (str): required POS tag for the predicate token.
        - ``neg`` (bool): when ``True``, a negation dependency must be present.
        - ``object`` (str): a token text that must appear in the span.
        - ``object_mod`` (str): a modifier token that must appear in the span.
    """

    category: BCVCategory
    name: str
    regex: str
    dep_pattern: dict


# ---------------------------------------------------------------------------
# PATTERN_LIBRARY — 47 patterns across 6 BCV categories
# ---------------------------------------------------------------------------

PATTERN_LIBRARY: list[NLPPattern] = [
    # -----------------------------------------------------------------------
    # RSV — Return Specification Violation (10 patterns)
    # -----------------------------------------------------------------------
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_type",
        regex=r"(?i)returns?\s+(?:a\s+)?(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_none",
        regex=r"(?i)returns?\s+None",
        dep_pattern={"predicate": "return", "object": "None"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_bool",
        regex=r"(?i)returns?\s+(?:True|False|a\s+bool(?:ean)?)",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_list",
        regex=r"(?i)returns?\s+(?:a\s+)?(?:sorted\s+)?list\s*(?:of\s+(?P<object>\w[\w\[\], ]*))?",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_dict",
        regex=r"(?i)returns?\s+(?:a\s+)?dict(?:ionary)?\s*(?:of\s+(?P<object>\w[\w\[\], ]*))?",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_tuple",
        regex=r"(?i)returns?\s+(?:a\s+)?tuple\s*(?:of\s+(?P<object>\w[\w\[\], ]*))?",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_int",
        regex=r"(?i)returns?\s+(?:a(?:n)?\s+)?int(?:eger)?",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_float",
        regex=r"(?i)returns?\s+(?:a\s+)?float",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_string",
        regex=r"(?i)returns?\s+(?:a\s+)?str(?:ing)?",
        dep_pattern={"predicate": "return", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.RSV,
        name="returns_self",
        regex=r"(?i)returns?\s+self",
        dep_pattern={"predicate": "return", "object": "self"},
    ),

    # -----------------------------------------------------------------------
    # PCV — Parameter Contract Violation (10 patterns)
    # -----------------------------------------------------------------------
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_must_be",
        regex=r"(?i)(?P<subject>\w+)\s+must\s+be\s+(?:a\s+)?(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "must", "head_pos": "AUX"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_should_be",
        regex=r"(?i)(?P<subject>\w+)\s+should\s+be\s+(?:a\s+)?(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "should", "head_pos": "AUX"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_cannot_be",
        regex=r"(?i)(?P<subject>\w+)\s+(?:cannot|can\s*not|can't)\s+be\s+(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "can", "neg": True},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_expects",
        regex=r"(?i)expects?\s+(?P<subject>\w+)\s+(?:to\s+be\s+)?(?:a\s+)?(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "expect", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_requires",
        regex=r"(?i)(?P<subject>\w+)\s+(?:is\s+)?required\s+to\s+be\s+(?:a\s+)?(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "require", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_must_not_be",
        regex=r"(?i)(?P<subject>\w+)\s+must\s+not\s+be\s+(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "must", "head_pos": "AUX", "neg": True},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_accepts",
        regex=r"(?i)accepts?\s+(?:only\s+)?(?P<object>\w[\w\[\], |]*)\s+(?:as\s+)?(?P<subject>\w+)?",
        dep_pattern={"predicate": "accept", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_type_constraint",
        regex=r"(?i)(?P<subject>\w+)\s+(?:must|should)\s+be\s+(?:of\s+)?type\s+(?P<object>\w[\w\[\], ]*)",
        dep_pattern={"predicate": "type", "head_pos": "NOUN"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_non_negative",
        regex=r"(?i)(?P<subject>\w+)\s+(?:must|should)\s+be\s+(?:a\s+)?(?:non[- ]negative|positive)(?:\s+(?P<object>\w+))?",
        dep_pattern={"predicate": "must", "head_pos": "AUX"},
    ),
    NLPPattern(
        category=BCVCategory.PCV,
        name="param_non_empty",
        regex=r"(?i)(?P<subject>\w+)\s+(?:must|should|cannot)\s+(?:not\s+)?be\s+(?:non[- ]empty|empty|None|null)",
        dep_pattern={"predicate": "must", "head_pos": "AUX"},
    ),

    # -----------------------------------------------------------------------
    # SEV — Side Effect Violation (8 patterns)
    # -----------------------------------------------------------------------
    NLPPattern(
        category=BCVCategory.SEV,
        name="does_not_modify",
        regex=r"(?i)does\s+not\s+modify\s+(?:the\s+)?(?P<subject>\w+)",
        dep_pattern={"predicate": "modify", "neg": True},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="modifies_in_place",
        regex=r"(?i)modif(?:ies|y)\s+(?:the\s+)?(?P<subject>\w+)\s+in[- ]place",
        dep_pattern={"predicate": "modify", "object": "place"},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="returns_new",
        regex=r"(?i)returns?\s+(?:a\s+)?new\s+(?P<object>\w+)",
        dep_pattern={"predicate": "return", "object_mod": "new"},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="mutates",
        regex=r"(?i)mutates?\s+(?:the\s+)?(?P<subject>\w+)",
        dep_pattern={"predicate": "mutate", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="sorts_in_place",
        regex=r"(?i)sorts?\s+(?:the\s+)?(?P<subject>\w+)\s+in[- ]place",
        dep_pattern={"predicate": "sort", "object": "place"},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="no_side_effects",
        regex=r"(?i)(?:has\s+)?no\s+side[- ]effects?",
        dep_pattern={"predicate": "effect", "neg": True},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="pure_function",
        regex=r"(?i)(?:is\s+a\s+)?pure\s+function",
        dep_pattern={"predicate": "pure", "head_pos": "ADJ"},
    ),
    NLPPattern(
        category=BCVCategory.SEV,
        name="updates_in_place",
        regex=r"(?i)updates?\s+(?:the\s+)?(?P<subject>\w+)\s+in[- ]place",
        dep_pattern={"predicate": "update", "object": "place"},
    ),

    # -----------------------------------------------------------------------
    # ECV — Exception Contract Violation (8 patterns)
    # -----------------------------------------------------------------------
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_exception",
        regex=r"(?i)raises?\s+(?P<object>\w+Error|\w+Exception)\s*(?:if\s+(?P<condition>.+))?",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="throws_exception",
        regex=r"(?i)throws?\s+(?:a\s+)?(?P<object>\w+Error|\w+Exception)\s*(?:if\s+(?P<condition>.+))?",
        dep_pattern={"predicate": "throw", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_on_invalid",
        regex=r"(?i)raises?\s+(?P<object>\w+Error|\w+Exception)\s+(?:on|for|when)\s+(?:invalid|bad|wrong)\s+(?P<condition>\w+)",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_if_none",
        regex=r"(?i)raises?\s+(?P<object>\w+Error|\w+Exception)\s+if\s+(?P<subject>\w+)\s+is\s+None",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_type_error",
        regex=r"(?i)raises?\s+TypeError\s*(?:if\s+(?P<condition>.+))?",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_value_error",
        regex=r"(?i)raises?\s+ValueError\s*(?:if\s+(?P<condition>.+))?",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_key_error",
        regex=r"(?i)raises?\s+KeyError\s*(?:if\s+(?P<condition>.+))?",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.ECV,
        name="raises_index_error",
        regex=r"(?i)raises?\s+IndexError\s*(?:if\s+(?P<condition>.+))?",
        dep_pattern={"predicate": "raise", "head_pos": "VERB"},
    ),

    # -----------------------------------------------------------------------
    # COV — Completeness Omission Violation (6 patterns)
    # -----------------------------------------------------------------------
    NLPPattern(
        category=BCVCategory.COV,
        name="handles_case",
        regex=r"(?i)handles?\s+(?:the\s+)?(?:case\s+(?:where|when|of)\s+)?(?P<object>.+?)(?:\.|$)",
        dep_pattern={"predicate": "handle", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.COV,
        name="supports",
        regex=r"(?i)supports?\s+(?P<object>\w[\w\s,]*?)(?:\.|$)",
        dep_pattern={"predicate": "support", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.COV,
        name="works_with",
        regex=r"(?i)works?\s+with\s+(?P<object>\w[\w\s,]*?)(?:\.|$)",
        dep_pattern={"predicate": "work", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.COV,
        name="processes",
        regex=r"(?i)processes?\s+(?P<object>\w[\w\s,]*?)(?:\.|$)",
        dep_pattern={"predicate": "process", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.COV,
        name="accepts_input",
        regex=r"(?i)accepts?\s+(?P<object>\w[\w\s,|]*?)\s+(?:as\s+)?input",
        dep_pattern={"predicate": "accept", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.COV,
        name="implements",
        regex=r"(?i)implements?\s+(?P<object>\w[\w\s,]*?)(?:\.|$)",
        dep_pattern={"predicate": "implement", "head_pos": "VERB"},
    ),

    # -----------------------------------------------------------------------
    # CCV — Complexity Contract Violation (5 patterns)
    # -----------------------------------------------------------------------
    NLPPattern(
        category=BCVCategory.CCV,
        name="time_complexity",
        regex=r"(?i)(?:time\s+)?complexity\s*(?:is\s+)?O\((?P<object>[^)]+)\)",
        dep_pattern={"predicate": "complexity", "head_pos": "NOUN"},
    ),
    NLPPattern(
        category=BCVCategory.CCV,
        name="space_complexity",
        regex=r"(?i)space\s+complexity\s*(?:is\s+)?O\((?P<object>[^)]+)\)",
        dep_pattern={"predicate": "complexity", "head_pos": "NOUN"},
    ),
    NLPPattern(
        category=BCVCategory.CCV,
        name="runs_in",
        regex=r"(?i)runs?\s+in\s+O\((?P<object>[^)]+)\)(?:\s+time)?",
        dep_pattern={"predicate": "run", "head_pos": "VERB"},
    ),
    NLPPattern(
        category=BCVCategory.CCV,
        name="linear_time",
        regex=r"(?i)(?:runs?\s+in\s+)?linear\s+time",
        dep_pattern={"predicate": "time", "head_pos": "NOUN"},
    ),
    NLPPattern(
        category=BCVCategory.CCV,
        name="constant_time",
        regex=r"(?i)(?:runs?\s+in\s+)?constant\s+time",
        dep_pattern={"predicate": "time", "head_pos": "NOUN"},
    ),
]

assert len(PATTERN_LIBRARY) == 47, (
    f"Expected 47 patterns, got {len(PATTERN_LIBRARY)}"
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_docstring_line(docstring: str, char_offset: int) -> int:
    """Compute the 1-based line number within *docstring* for *char_offset*.

    The first line of the docstring is line 1.
    """
    return docstring[:char_offset].count("\n") + 1


def _validate_dep_pattern(span, dep_pattern: dict) -> bool:
    """Validate a spaCy span against dependency-structure rules.

    Parameters
    ----------
    span
        A ``spacy.tokens.Span`` covering the regex match.
    dep_pattern : dict
        Validation rules.  Supported keys:

        - ``predicate`` (str): a token whose lemma matches must exist in the span.
        - ``head_pos`` (str): the predicate token's POS tag must match.
        - ``neg`` (bool): when ``True``, a negation child (``dep_=="neg"``) must
          be present on some token in the span.
        - ``object`` (str): a token whose lower-cased text matches must exist.
        - ``object_mod`` (str): a token whose lower-cased text matches must exist
          (typically an adjective modifier like "new").

    Returns
    -------
    bool
        ``True`` when all specified rules are satisfied.
    """
    if span is None or len(span) == 0:
        return False

    predicate_text = dep_pattern.get("predicate", "")
    required_pos = dep_pattern.get("head_pos")
    requires_neg = dep_pattern.get("neg", False)
    required_object = dep_pattern.get("object")
    required_mod = dep_pattern.get("object_mod")

    # --- Check predicate token exists with correct POS ---
    predicate_found = False
    for token in span:
        if token.lemma_.lower() == predicate_text.lower() or token.text.lower() == predicate_text.lower():
            if required_pos is None or token.pos_ == required_pos:
                predicate_found = True
                break
    # If no exact match, do a relaxed check: any token whose lemma *contains*
    # the predicate (handles multi-word predicates like "must be").
    if not predicate_found:
        for token in span:
            if predicate_text.lower() in token.lemma_.lower():
                if required_pos is None or token.pos_ == required_pos:
                    predicate_found = True
                    break

    if not predicate_found:
        return False

    # --- Check negation ---
    if requires_neg:
        neg_found = False
        for token in span:
            # Direct negation dependency
            if token.dep_ == "neg":
                neg_found = True
                break
            # Check children for negation
            for child in token.children:
                if child.dep_ == "neg":
                    neg_found = True
                    break
            if neg_found:
                break
        # Also accept "not" / "no" / "non" as text tokens in the span
        if not neg_found:
            for token in span:
                if token.text.lower() in ("not", "no", "non", "n't"):
                    neg_found = True
                    break
        if not neg_found:
            return False

    # --- Check required object token ---
    if required_object is not None:
        obj_found = any(
            token.text.lower() == required_object.lower()
            for token in span
        )
        if not obj_found:
            return False

    # --- Check required modifier token ---
    if required_mod is not None:
        mod_found = any(
            token.text.lower() == required_mod.lower()
            for token in span
        )
        if not mod_found:
            return False

    return True


def _normalize_predicate_object(match: re.Match, pattern: NLPPattern) -> str:
    """Build a normalized predicate-object string from a regex match.

    Uses the full matched text, stripping leading/trailing whitespace.
    When named groups ``object`` or ``subject`` are present, they are
    incorporated into a readable predicate-object phrase.
    """
    groups = match.groupdict()
    obj = groups.get("object")
    subject = groups.get("subject")

    # Build a concise predicate_object from the pattern name + captured groups
    name = pattern.name
    if obj:
        return f"{name.replace('_', ' ')}: {obj.strip()}"
    if subject:
        return f"{name.replace('_', ' ')}: {subject.strip()}"
    return name.replace("_", " ")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def apply_nlp_patterns(
    docstring: str,
    nlp_model,
    *,
    docstring_start_line: int = 1,
) -> list[Claim]:
    """Apply all 47 PATTERN_LIBRARY patterns over a spaCy-parsed docstring.

    Parameters
    ----------
    docstring : str
        The raw docstring text extracted from a Python function.
    nlp_model
        A loaded spaCy ``Language`` model (e.g. ``en_core_web_sm``).
    docstring_start_line : int
        The 1-based line number in the source file where the docstring begins.
        Used to compute accurate ``source_line`` values for each claim.

    Returns
    -------
    list[Claim]
        Claims extracted from the docstring, each validated against the spaCy
        dependency structure.

    Requirements: 2.2, 12.1, 12.2, 12.3, 12.4
    """
    doc = nlp_model(docstring)
    claims: list[Claim] = []

    for pattern in PATTERN_LIBRARY:
        for match in re.finditer(pattern.regex, docstring):
            span_start = match.start()
            span_end = match.end()

            # Get the spaCy span covering the regex match
            spacy_span = doc.char_span(span_start, span_end)

            # If char_span returns None (alignment issue), try with
            # alignment_mode="expand" for a best-effort span.
            if spacy_span is None:
                spacy_span = doc.char_span(
                    span_start, span_end, alignment_mode="expand"
                )

            # Requirement 12.2: validate against spaCy dependency structure
            if spacy_span is not None and _validate_dep_pattern(
                spacy_span, pattern.dep_pattern
            ):
                groups = match.groupdict()
                subject = groups.get("subject", "").strip() if groups.get("subject") else "return"
                predicate_object = _normalize_predicate_object(match, pattern)
                conditionality = groups.get("condition")
                if conditionality:
                    conditionality = conditionality.strip().rstrip(".")

                # Requirement 12.4: accurate source_line relative to docstring
                relative_line = _get_docstring_line(docstring, span_start)
                source_line = docstring_start_line + relative_line - 1

                # Requirement 12.3: raw_text is a substring of the docstring
                raw_text = match.group(0).strip()
                if not raw_text:
                    continue

                # Ensure subject is non-empty (Requirement 10.2)
                if not subject:
                    subject = "return"

                claims.append(
                    Claim(
                        category=pattern.category,
                        subject=subject,
                        predicate_object=predicate_object,
                        conditionality=conditionality,
                        source_line=source_line,
                        raw_text=raw_text,
                    )
                )

    return claims
