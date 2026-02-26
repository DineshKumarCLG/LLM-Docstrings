"""Property tests for the Dynamic Test Synthesizer (DTS).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**

Properties tested:
- Property 7:  Implementation isolation in DTS prompts
- Property 8:  DTS prompt construction invariants
- Property 9:  SEV deepcopy-assert pattern enforcement
- Property 10: Test output validation
"""

from __future__ import annotations

import json

from hypothesis import given, settings as h_settings, assume, HealthCheck
from hypothesis import strategies as st

from app.pipeline.dts.synthesizer import (
    CATEGORY_SYSTEM_PROMPTS,
    build_prompt,
    build_sev_prompt,
    _parse_test_output,
)
from app.schemas import BCVCategory, Claim


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def claim_strategy(draw: st.DrawFn) -> Claim:
    """Generate a random valid Claim with any BCV category."""
    category = draw(st.sampled_from(list(BCVCategory)))
    subject = draw(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True))
    predicate_object = draw(st.from_regex(r"[a-z][a-z ]{2,30}", fullmatch=True))
    conditionality = draw(
        st.one_of(st.none(), st.from_regex(r"[a-z ]{3,20}", fullmatch=True))
    )
    source_line = draw(st.integers(min_value=1, max_value=500))
    raw_text = draw(st.from_regex(r"[A-Za-z ]{3,30}", fullmatch=True))
    return Claim(
        category=category,
        subject=subject,
        predicate_object=predicate_object,
        conditionality=conditionality,
        source_line=source_line,
        raw_text=raw_text,
    )



@st.composite
def sev_claim_strategy(draw: st.DrawFn) -> Claim:
    """Generate a random valid Claim with category SEV."""
    subject = draw(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True))
    predicate_object = draw(st.from_regex(r"[a-z][a-z ]{2,30}", fullmatch=True))
    conditionality = draw(
        st.one_of(st.none(), st.from_regex(r"[a-z ]{3,20}", fullmatch=True))
    )
    source_line = draw(st.integers(min_value=1, max_value=500))
    raw_text = draw(st.from_regex(r"[A-Za-z ]{3,30}", fullmatch=True))
    return Claim(
        category=BCVCategory.SEV,
        subject=subject,
        predicate_object=predicate_object,
        conditionality=conditionality,
        source_line=source_line,
        raw_text=raw_text,
    )


@st.composite
def function_signature_strategy(draw: st.DrawFn) -> str:
    """Generate a realistic Python function signature (no body)."""
    func_name = draw(st.from_regex(r"[a-z][a-z0-9_]{1,15}", fullmatch=True))
    param_names = draw(
        st.lists(
            st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True),
            min_size=0,
            max_size=4,
            unique=True,
        )
    )
    annotations = ["int", "str", "float", "list", "dict", "bool", "None", "list[int]", "list[str]"]
    params: list[str] = []
    for p in param_names:
        if draw(st.booleans()):
            ann = draw(st.sampled_from(annotations))
            params.append(f"{p}: {ann}")
        else:
            params.append(p)
    ret = draw(st.one_of(st.none(), st.sampled_from(annotations)))
    sig = f"def {func_name}({', '.join(params)})"
    if ret:
        sig += f" -> {ret}"
    return sig


@st.composite
def function_with_body_strategy(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a (signature, body) pair for a Python function.

    Returns the signature string and a multi-line body string that should
    NOT appear in any DTS prompt.  Body lines use a ``__BODY__`` prefix
    to guarantee they cannot coincidentally match claim fields or
    signature tokens.
    """
    sig = draw(function_signature_strategy())
    body_lines = draw(
        st.lists(
            st.from_regex(
                r"    __BODY__[a-z][a-z0-9_ =+\-*/()]{5,40}",
                fullmatch=True,
            ),
            min_size=1,
            max_size=5,
        )
    )
    body = "\n".join(body_lines)
    return sig, body


# ---------------------------------------------------------------------------
# Property 7: Implementation isolation in DTS prompts
# ---------------------------------------------------------------------------


@given(claim=claim_strategy(), sig_body=function_with_body_strategy())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_implementation_isolation_in_prompts(
    claim: Claim, sig_body: tuple[str, str]
) -> None:
    """Property 7: For any claim + function pair, the prompt must not
    contain the function body.

    The Constrained_Prompt Π(c_i, F) must contain only the function
    signature and claim text — never the implementation body.

    **Validates: Requirements 3.1**
    """
    signature, body = sig_body

    # Build prompt using only the signature (correct usage)
    prompt = build_prompt(claim, signature)

    # Serialise the entire prompt to a single string for checking
    prompt_text = json.dumps(prompt)

    # The body must NOT appear anywhere in the prompt
    for body_line in body.strip().splitlines():
        stripped = body_line.strip()
        if stripped:
            assert stripped not in prompt_text, (
                f"Function body line {stripped!r} leaked into prompt"
            )

    # Also verify for SEV prompts
    if claim.category == BCVCategory.SEV:
        sev_prompt = build_sev_prompt(claim, signature)
        sev_text = json.dumps(sev_prompt)
        for body_line in body.strip().splitlines():
            stripped = body_line.strip()
            if stripped:
                assert stripped not in sev_text, (
                    f"Function body line {stripped!r} leaked into SEV prompt"
                )


# ---------------------------------------------------------------------------
# Property 8: DTS prompt construction invariants
# ---------------------------------------------------------------------------


@given(claim=claim_strategy(), sig=function_signature_strategy())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prompt_construction_invariants(claim: Claim, sig: str) -> None:
    """Property 8: For any Claim, the constructed prompt must have
    temperature=0.1 and the system prompt must match the claim's category.

    **Validates: Requirements 3.2, 3.6**
    """
    prompt = build_prompt(claim, sig)

    # Temperature must be exactly 0.1
    assert prompt["temperature"] == 0.1, (
        f"Expected temperature 0.1, got {prompt['temperature']}"
    )

    # System prompt must be the category-specific prompt
    expected_system = CATEGORY_SYSTEM_PROMPTS[claim.category]
    assert prompt["system"] == expected_system, (
        f"System prompt mismatch for category {claim.category}: "
        f"expected {expected_system!r}, got {prompt['system']!r}"
    )

    # Prompt must have the required keys
    assert "system" in prompt
    assert "user" in prompt
    assert "temperature" in prompt

    # User content must be valid JSON containing claim and signature
    user_data = json.loads(prompt["user"])
    assert user_data["claim"] == claim.predicate_object
    assert user_data["signature"] == sig
    assert user_data["subjects"] == [claim.subject]


# ---------------------------------------------------------------------------
# Property 9: SEV deepcopy-assert pattern enforcement
# ---------------------------------------------------------------------------


@given(claim=sev_claim_strategy(), sig=function_signature_strategy())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_sev_deepcopy_assert_pattern_enforcement(claim: Claim, sig: str) -> None:
    """Property 9: For any SEV claim, the DTS prompt must enforce the
    deepcopy-assert pattern. The SEV system prompt must contain both
    "deepcopy" and "assert".

    **Validates: Requirements 3.3**
    """
    prompt = build_sev_prompt(claim, sig)

    # Temperature must still be 0.1
    assert prompt["temperature"] == 0.1

    # System prompt must be the SEV-specific prompt
    assert prompt["system"] == CATEGORY_SYSTEM_PROMPTS[BCVCategory.SEV]

    # SEV system prompt must enforce deepcopy-assert pattern
    system_lower = prompt["system"].lower()
    assert "deepcopy" in system_lower, (
        "SEV system prompt must mention 'deepcopy'"
    )
    assert "assert" in system_lower, (
        "SEV system prompt must mention 'assert'"
    )

    # User content must contain the claim and signature
    user_data = json.loads(prompt["user"])
    assert user_data["claim"] == claim.predicate_object
    assert user_data["signature"] == sig


# ---------------------------------------------------------------------------
# Property 10: Test output validation
# ---------------------------------------------------------------------------

# Strategy: syntactically valid Python test functions
@st.composite
def valid_test_function_strategy(draw: st.DrawFn) -> str:
    """Generate a syntactically valid Python function starting with def test_."""
    func_name = draw(st.from_regex(r"test_[a-z][a-z0-9_]{1,20}", fullmatch=True))
    # Generate a simple function body
    body_type = draw(st.sampled_from(["assert", "pass", "return"]))
    if body_type == "assert":
        body = "    assert True"
    elif body_type == "pass":
        body = "    pass"
    else:
        body = "    return None"
    return f"def {func_name}():\n{body}"


@st.composite
def invalid_test_output_strategy(draw: st.DrawFn) -> str:
    """Generate strings that should NOT be accepted by _parse_test_output."""
    kind = draw(st.sampled_from([
        "empty",
        "no_def_test",
        "syntax_error",
        "non_test_function",
        "plain_text",
    ]))
    if kind == "empty":
        return ""
    elif kind == "no_def_test":
        return "def helper():\n    return 42"
    elif kind == "syntax_error":
        return "def test_broken(:\n    assert True"
    elif kind == "non_test_function":
        return "def my_function():\n    pass"
    else:
        return draw(st.from_regex(r"[A-Za-z ]{5,50}", fullmatch=True))


@given(test_func=valid_test_function_strategy())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_parser_accepts_valid_test_functions(test_func: str) -> None:
    """Property 10 (positive): The parser accepts syntactically valid Python
    functions starting with ``def test_``.

    **Validates: Requirements 3.4**
    """
    result = _parse_test_output(test_func)
    assert result is not None, (
        f"Parser rejected valid test function:\n{test_func}"
    )
    # Result must contain def test_
    assert "def test_" in result


@given(bad_output=invalid_test_output_strategy())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_parser_rejects_invalid_output(bad_output: str) -> None:
    """Property 10 (negative): The parser rejects strings that are not
    syntactically valid Python functions starting with ``def test_``.

    **Validates: Requirements 3.4**
    """
    result = _parse_test_output(bad_output)
    assert result is None, (
        f"Parser accepted invalid output:\n{bad_output}\nParsed as:\n{result}"
    )


@given(test_func=valid_test_function_strategy())
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_parser_handles_markdown_wrapped_code(test_func: str) -> None:
    """Property 10 (markdown): The parser extracts valid test functions
    from markdown code blocks.

    **Validates: Requirements 3.4**
    """
    wrapped = f"```python\n{test_func}\n```"
    result = _parse_test_output(wrapped)
    assert result is not None, (
        f"Parser rejected markdown-wrapped test function:\n{wrapped}"
    )
    assert "def test_" in result
