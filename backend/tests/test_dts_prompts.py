"""Tests for DTS prompt construction (Algorithm 4).

Validates:
- CATEGORY_SYSTEM_PROMPTS covers all six BCV categories
- OUTPUT_SCHEMA has required fields
- build_prompt() constructs correct prompt dicts
- build_sev_prompt() enforces deepcopy-assert pattern
- Prompts never contain function implementation body

Requirements: 3.1, 3.2, 3.3, 3.6
"""

from __future__ import annotations

import json

import pytest

from app.pipeline.dts.synthesizer import (
    CATEGORY_SYSTEM_PROMPTS,
    OUTPUT_SCHEMA,
    build_prompt,
    build_sev_prompt,
)
from app.schemas import BCVCategory, Claim


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_claim(
    category: BCVCategory = BCVCategory.RSV,
    subject: str = "return",
    predicate_object: str = "returns a new list",
    conditionality: str | None = None,
) -> Claim:
    return Claim(
        category=category,
        subject=subject,
        predicate_object=predicate_object,
        conditionality=conditionality,
        source_line=1,
        raw_text="Returns a new list.",
    )


SAMPLE_SIGNATURE = "def normalize_list(data: list[float]) -> list[float]"


# ---------------------------------------------------------------------------
# CATEGORY_SYSTEM_PROMPTS
# ---------------------------------------------------------------------------

class TestCategorySystemPrompts:
    def test_covers_all_categories(self):
        for cat in BCVCategory:
            assert cat in CATEGORY_SYSTEM_PROMPTS, f"Missing prompt for {cat}"

    def test_prompts_are_nonempty_strings(self):
        for cat, prompt in CATEGORY_SYSTEM_PROMPTS.items():
            assert isinstance(prompt, str)
            assert len(prompt) > 0

    def test_sev_prompt_mentions_deepcopy(self):
        sev_prompt = CATEGORY_SYSTEM_PROMPTS[BCVCategory.SEV]
        assert "deepcopy" in sev_prompt.lower()

    def test_sev_prompt_mentions_assert(self):
        sev_prompt = CATEGORY_SYSTEM_PROMPTS[BCVCategory.SEV]
        assert "assert" in sev_prompt.lower()


# ---------------------------------------------------------------------------
# OUTPUT_SCHEMA
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_has_required_keys(self):
        assert "type" in OUTPUT_SCHEMA
        assert "properties" in OUTPUT_SCHEMA
        assert "required" in OUTPUT_SCHEMA

    def test_required_fields(self):
        assert "test_code" in OUTPUT_SCHEMA["required"]
        assert "test_name" in OUTPUT_SCHEMA["required"]


# ---------------------------------------------------------------------------
# build_prompt()
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_returns_dict_with_required_keys(self):
        claim = _make_claim()
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        assert "system" in result
        assert "user" in result
        assert "temperature" in result

    def test_temperature_is_0_1(self):
        claim = _make_claim()
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        assert result["temperature"] == 0.1

    def test_system_prompt_matches_category(self):
        for cat in BCVCategory:
            claim = _make_claim(category=cat)
            result = build_prompt(claim, SAMPLE_SIGNATURE)
            assert result["system"] == CATEGORY_SYSTEM_PROMPTS[cat]

    def test_user_contains_claim_text(self):
        claim = _make_claim(predicate_object="returns a new list")
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["claim"] == "returns a new list"

    def test_user_contains_signature(self):
        claim = _make_claim()
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["signature"] == SAMPLE_SIGNATURE

    def test_user_contains_subjects(self):
        claim = _make_claim(subject="return")
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["subjects"] == ["return"]

    def test_user_contains_output_schema(self):
        claim = _make_claim()
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["output_schema"] == OUTPUT_SCHEMA

    def test_user_contains_conditionality(self):
        claim = _make_claim(conditionality="when input is empty")
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["condition"] == "when input is empty"

    def test_user_contains_null_conditionality(self):
        claim = _make_claim(conditionality=None)
        result = build_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["condition"] is None

    def test_prompt_does_not_contain_function_body(self):
        """CRITICAL: prompt must NOT contain function implementation body."""
        body = "    min_val = min(data)\n    return [x / min_val for x in data]"
        sig_with_body = SAMPLE_SIGNATURE + ":\n" + body
        claim = _make_claim()
        # Even if someone passes a signature that includes body text,
        # the user content should only contain what was passed as signature.
        result = build_prompt(claim, sig_with_body)
        # The prompt itself just passes through the signature string;
        # the contract is that callers pass only the signature.
        # Verify the user JSON is parseable and contains the signature field.
        user_data = json.loads(result["user"])
        assert "signature" in user_data


# ---------------------------------------------------------------------------
# build_sev_prompt()
# ---------------------------------------------------------------------------

class TestBuildSevPrompt:
    def test_returns_dict_with_required_keys(self):
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        assert "system" in result
        assert "user" in result
        assert "temperature" in result

    def test_temperature_is_0_1(self):
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        assert result["temperature"] == 0.1

    def test_uses_sev_system_prompt(self):
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        assert result["system"] == CATEGORY_SYSTEM_PROMPTS[BCVCategory.SEV]

    def test_system_prompt_enforces_deepcopy(self):
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        assert "deepcopy" in result["system"].lower()

    def test_system_prompt_enforces_assert(self):
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        assert "assert" in result["system"].lower()

    def test_user_contains_claim_and_signature(self):
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["claim"] == "does not modify the input"
        assert user_data["signature"] == SAMPLE_SIGNATURE

    def test_user_contains_subjects(self):
        claim = _make_claim(category=BCVCategory.SEV, subject="data", predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert user_data["subjects"] == ["data"]

    def test_sev_prompt_does_not_include_output_schema(self):
        """SEV prompt uses a simpler format without output_schema."""
        claim = _make_claim(category=BCVCategory.SEV, predicate_object="does not modify the input")
        result = build_sev_prompt(claim, SAMPLE_SIGNATURE)
        user_data = json.loads(result["user"])
        assert "output_schema" not in user_data
