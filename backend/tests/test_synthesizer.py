"""Tests for DTS test synthesis and output parsing.

Validates:
- _parse_test_output() extracts valid pytest functions from LLM responses
- _parse_test_output() rejects invalid/non-test output
- _extract_function_name() extracts test function names
- DynamicTestSynthesizer.synthesize() iterates claims, calls LLM, produces SynthesizedTest

Requirements: 3.4, 3.7
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.dts.synthesizer import (
    DynamicTestSynthesizer,
    LLMClient,
    LLMClientError,
    _extract_function_name,
    _parse_test_output,
    build_prompt,
    build_sev_prompt,
)
from app.schemas import (
    BCVCategory,
    Claim,
    ClaimSchema,
    FunctionInfo,
    LLMProvider,
    SynthesizedTest,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _make_function_info() -> FunctionInfo:
    return FunctionInfo(
        name="normalize_list",
        qualified_name="utils.normalize_list",
        source="def normalize_list(data): pass",
        lineno=1,
        signature="def normalize_list(data: list[float]) -> list[float]",
        docstring="Returns a new list.",
        params=[{"name": "data", "annotation": "list[float]", "default": None}],
        return_annotation="list[float]",
    )


def _make_claim_schema(claims: list[Claim] | None = None) -> ClaimSchema:
    func = _make_function_info()
    if claims is None:
        claims = [_make_claim()]
    return ClaimSchema(function=func, claims=claims)


# ---------------------------------------------------------------------------
# _parse_test_output()
# ---------------------------------------------------------------------------


class TestParseTestOutput:
    """Requirement 3.4: parse and validate LLM output as a pytest function."""

    def test_accepts_plain_test_function(self):
        raw = "def test_returns_list():\n    assert isinstance(normalize_list([1.0]), list)\n"
        result = _parse_test_output(raw)
        assert result is not None
        assert "def test_returns_list" in result

    def test_accepts_code_in_markdown_block(self):
        raw = (
            "Here is the test:\n"
            "```python\n"
            "def test_returns_list():\n"
            "    assert isinstance(normalize_list([1.0]), list)\n"
            "```\n"
        )
        result = _parse_test_output(raw)
        assert result is not None
        assert "def test_returns_list" in result

    def test_accepts_code_in_bare_markdown_block(self):
        raw = (
            "```\n"
            "def test_foo():\n"
            "    assert True\n"
            "```\n"
        )
        result = _parse_test_output(raw)
        assert result is not None
        assert "def test_foo" in result

    def test_preserves_imports_before_function(self):
        raw = (
            "```python\n"
            "import copy\n"
            "from copy import deepcopy\n"
            "\n"
            "def test_no_mutation():\n"
            "    data = [1, 2, 3]\n"
            "    snapshot = deepcopy(data)\n"
            "    assert data == snapshot\n"
            "```\n"
        )
        result = _parse_test_output(raw)
        assert result is not None
        assert "import copy" in result
        assert "from copy import deepcopy" in result
        assert "def test_no_mutation" in result

    def test_rejects_empty_string(self):
        assert _parse_test_output("") is None

    def test_rejects_whitespace_only(self):
        assert _parse_test_output("   \n\n  ") is None

    def test_rejects_no_test_function(self):
        raw = "def helper():\n    return 42\n"
        assert _parse_test_output(raw) is None

    def test_rejects_syntax_error(self):
        raw = "def test_bad(:\n    assert True\n"
        assert _parse_test_output(raw) is None

    def test_rejects_non_code_text(self):
        raw = "This is just a description of what the test should do."
        assert _parse_test_output(raw) is None

    def test_extracts_only_first_test_function(self):
        raw = (
            "def test_first():\n"
            "    assert True\n"
            "\n"
            "def test_second():\n"
            "    assert False\n"
        )
        result = _parse_test_output(raw)
        assert result is not None
        assert "def test_first" in result

    def test_handles_multiline_function_body(self):
        raw = (
            "def test_complex():\n"
            "    data = [1.0, 2.0, 3.0]\n"
            "    result = normalize_list(data)\n"
            "    assert isinstance(result, list)\n"
            "    assert len(result) == 3\n"
        )
        result = _parse_test_output(raw)
        assert result is not None
        assert "assert len(result) == 3" in result


# ---------------------------------------------------------------------------
# _extract_function_name()
# ---------------------------------------------------------------------------


class TestExtractFunctionName:
    def test_extracts_simple_name(self):
        code = "def test_returns_list():\n    assert True\n"
        assert _extract_function_name(code) == "test_returns_list"

    def test_extracts_name_with_params(self):
        code = "def test_with_args(x, y):\n    assert x == y\n"
        assert _extract_function_name(code) == "test_with_args"

    def test_returns_none_for_non_test(self):
        code = "def helper():\n    return 42\n"
        assert _extract_function_name(code) is None

    def test_returns_none_for_syntax_error(self):
        assert _extract_function_name("def test_bad(:\n") is None

    def test_returns_none_for_empty(self):
        assert _extract_function_name("") is None


# ---------------------------------------------------------------------------
# DynamicTestSynthesizer.synthesize()
# ---------------------------------------------------------------------------


class TestSynthesizeMethod:
    """Requirement 3.7: synthesize produces SynthesizedTest with correct fields."""

    @pytest.mark.asyncio
    async def test_synthesize_single_claim_success(self):
        """Happy path: one claim, LLM returns valid test code."""
        schema = _make_claim_schema()
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        llm_response = (
            "```python\n"
            "def test_returns_list():\n"
            "    result = normalize_list([1.0, 2.0])\n"
            "    assert isinstance(result, list)\n"
            "```\n"
        )

        with patch.object(
            dts._client, "call", new_callable=AsyncMock, return_value=llm_response
        ):
            results = await dts.synthesize(schema)

        assert len(results) == 1
        st = results[0]
        assert isinstance(st, SynthesizedTest)
        assert st.test_function_name == "test_returns_list"
        assert st.synthesis_model == "gpt-4o"
        assert "def test_returns_list" in st.test_code
        assert st.claim == schema.claims[0]

    @pytest.mark.asyncio
    async def test_synthesize_multiple_claims(self):
        """Multiple claims produce multiple SynthesizedTests."""
        claims = [
            _make_claim(category=BCVCategory.RSV, predicate_object="returns a list"),
            _make_claim(
                category=BCVCategory.SEV,
                subject="data",
                predicate_object="does not modify the input",
            ),
        ]
        schema = _make_claim_schema(claims)
        dts = DynamicTestSynthesizer(LLMProvider.CLAUDE_SONNET)

        responses = [
            "def test_returns_list():\n    assert True\n",
            "from copy import deepcopy\n\ndef test_no_mutation():\n    data = [1]\n    snap = deepcopy(data)\n    normalize_list(data)\n    assert data == snap\n",
        ]

        mock_call = AsyncMock(side_effect=responses)
        with patch.object(dts._client, "call", mock_call):
            results = await dts.synthesize(schema)

        assert len(results) == 2
        assert results[0].test_function_name == "test_returns_list"
        assert results[1].test_function_name == "test_no_mutation"

    @pytest.mark.asyncio
    async def test_synthesize_skips_on_llm_error(self):
        """Claims that fail LLM call are skipped, not raised."""
        schema = _make_claim_schema()
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        with patch.object(
            dts._client, "call", new_callable=AsyncMock, side_effect=LLMClientError("fail")
        ):
            results = await dts.synthesize(schema)

        assert results == []

    @pytest.mark.asyncio
    async def test_synthesize_skips_on_invalid_output(self):
        """Claims with unparseable LLM output are skipped."""
        schema = _make_claim_schema()
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        with patch.object(
            dts._client, "call", new_callable=AsyncMock, return_value="not valid python code"
        ):
            results = await dts.synthesize(schema)

        assert results == []

    @pytest.mark.asyncio
    async def test_synthesize_uses_sev_prompt_for_sev_claims(self):
        """SEV claims should use build_sev_prompt, not build_prompt."""
        sev_claim = _make_claim(
            category=BCVCategory.SEV,
            subject="data",
            predicate_object="does not modify the input",
        )
        schema = _make_claim_schema([sev_claim])
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        llm_response = "def test_sev():\n    assert True\n"

        mock_call = AsyncMock(return_value=llm_response)
        with patch.object(dts._client, "call", mock_call):
            await dts.synthesize(schema)

        # Verify the system prompt used was the SEV prompt
        call_args = mock_call.call_args
        from app.pipeline.dts.synthesizer import CATEGORY_SYSTEM_PROMPTS

        assert call_args.kwargs["system"] == CATEGORY_SYSTEM_PROMPTS[BCVCategory.SEV]

    @pytest.mark.asyncio
    async def test_synthesize_uses_regular_prompt_for_non_sev(self):
        """Non-SEV claims should use build_prompt."""
        rsv_claim = _make_claim(category=BCVCategory.RSV)
        schema = _make_claim_schema([rsv_claim])
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        llm_response = "def test_rsv():\n    assert True\n"

        mock_call = AsyncMock(return_value=llm_response)
        with patch.object(dts._client, "call", mock_call):
            await dts.synthesize(schema)

        call_args = mock_call.call_args
        from app.pipeline.dts.synthesizer import CATEGORY_SYSTEM_PROMPTS

        assert call_args.kwargs["system"] == CATEGORY_SYSTEM_PROMPTS[BCVCategory.RSV]

    @pytest.mark.asyncio
    async def test_synthesize_token_counts_populated(self):
        """SynthesizedTest should have non-zero token counts."""
        schema = _make_claim_schema()
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        llm_response = "def test_ok():\n    assert True\n"

        with patch.object(
            dts._client, "call", new_callable=AsyncMock, return_value=llm_response
        ):
            results = await dts.synthesize(schema)

        assert len(results) == 1
        assert results[0].prompt_tokens > 0
        assert results[0].completion_tokens > 0

    @pytest.mark.asyncio
    async def test_synthesize_empty_claims_returns_empty(self):
        """A ClaimSchema with no claims produces no tests."""
        schema = _make_claim_schema(claims=[])
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)
        results = await dts.synthesize(schema)
        assert results == []

    @pytest.mark.asyncio
    async def test_synthesize_partial_success(self):
        """If some claims succeed and some fail, only successes are returned."""
        claims = [
            _make_claim(category=BCVCategory.RSV, predicate_object="returns a list"),
            _make_claim(category=BCVCategory.ECV, predicate_object="raises ValueError"),
        ]
        schema = _make_claim_schema(claims)
        dts = DynamicTestSynthesizer(LLMProvider.GPT4_1_MINI)

        responses = [
            "def test_returns_list():\n    assert True\n",
            "this is not valid python",
        ]

        mock_call = AsyncMock(side_effect=responses)
        with patch.object(dts._client, "call", mock_call):
            results = await dts.synthesize(schema)

        assert len(results) == 1
        assert results[0].test_function_name == "test_returns_list"
