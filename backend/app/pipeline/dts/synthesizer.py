"""Dynamic Test Synthesizer — LLM provider abstraction and test synthesis.

Provides a unified async interface for calling OpenAI (GPT-4.1 Mini),
Anthropic (Claude Sonnet 4), and Google (Gemini 3 Flash) with
retry logic (up to 3 retries, exponential backoff 1s/2s/4s).

Implements Algorithm 4 (DTS Prompt Construction) with category-specific
system prompts and the SEV deepcopy-assert pattern from Listing 1.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.1
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from typing import Optional

from app.config import settings
from app.pipeline.frameworks import TestFramework
from app.schemas import BCVCategory, Claim, ClaimSchema, LLMProvider, SynthesizedTest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Algorithm 4: Category-specific system prompts (~47 tokens average)
# ---------------------------------------------------------------------------

CATEGORY_SYSTEM_PROMPTS: dict[BCVCategory, str] = {
    BCVCategory.RSV: (
        "You are a pytest test generator. Given a function signature and ONE return-type claim, "
        "write exactly ONE pytest test function that verifies the return type/value matches the claim. "
        "Use realistic inputs. Output ONLY valid Python code. Derive the test from the CLAIM, not the body."
    ),
    BCVCategory.PCV: (
        "You are a pytest test generator. Given a function signature and ONE parameter contract claim, "
        "write exactly ONE pytest test function that verifies the parameter constraint. "
        "Test both valid and boundary inputs. Output ONLY valid Python code. Derive the test from the CLAIM, not the body."
    ),
    BCVCategory.SEV: (
        "You are a pytest test generator. Given a function signature and ONE side-effect claim, "
        "write exactly ONE pytest test function.\n"
        "RULES:\n"
        "1. deepcopy ALL arguments before calling the function.\n"
        "2. After the call, assert each argument claimed immutable equals its pre-call snapshot.\n"
        "3. Use realistic, non-trivial input values.\n"
        "4. Output ONLY valid Python code.\n"
        "5. Derive the test from the CLAIM, not the body."
    ),
    BCVCategory.ECV: (
        "You are a pytest test generator. Given a function signature and ONE exception contract claim, "
        "write exactly ONE pytest test function using pytest.raises to verify the exception behavior. "
        "Output ONLY valid Python code. Derive the test from the CLAIM, not the body."
    ),
    BCVCategory.COV: (
        "You are a pytest test generator. Given a function signature and ONE completeness claim, "
        "write exactly ONE pytest test function that verifies the described behavior branch exists. "
        "Output ONLY valid Python code. Derive the test from the CLAIM, not the body."
    ),
    BCVCategory.CCV: (
        "You are a pytest test generator. Given a function signature and ONE complexity claim, "
        "write exactly ONE pytest test function that measures execution time across input sizes "
        "to verify the claimed complexity bound. Output ONLY valid Python code."
    ),
}

# Output schema enforced in prompt
OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "test_code": {"type": "string", "description": "Complete pytest test function"},
        "test_name": {"type": "string", "description": "Name of the test function"},
    },
    "required": ["test_code", "test_name"],
}


# ---------------------------------------------------------------------------
# Prompt construction functions (Algorithm 4)
# ---------------------------------------------------------------------------


def build_prompt(claim: Claim, function_signature: str) -> dict:
    """Construct Π(c_i, F) = P_sys ⊕ Claim(c_i) ⊕ Sig(F) ⊕ S_out.

    CRITICAL: Never includes function implementation body.
    Only signature + claim text.

    Parameters
    ----------
    claim : Claim
        The behavioral claim to generate a test for.
    function_signature : str
        The function signature (no body).

    Returns
    -------
    dict
        Prompt dict with ``system``, ``user``, and ``temperature`` keys.
    """
    system_prompt = CATEGORY_SYSTEM_PROMPTS[claim.category]

    user_content = json.dumps({
        "claim": claim.predicate_object,
        "condition": claim.conditionality,
        "signature": function_signature,
        "subjects": [claim.subject],
        "output_schema": OUTPUT_SCHEMA,
    })

    return {
        "system": system_prompt,
        "user": user_content,
        "temperature": 0.1,
    }


def build_sev_prompt(claim: Claim, signature: str) -> dict:
    """SEV-specific prompt construction (Listing 1 from paper).

    Enforces the deepcopy-assert pattern: deepcopy all arguments before
    calling the function, then assert equality after the call.

    Parameters
    ----------
    claim : Claim
        An SEV claim.
    signature : str
        The function signature (no body).

    Returns
    -------
    dict
        Prompt dict with ``system``, ``user``, and ``temperature`` keys.
    """
    return {
        "system": CATEGORY_SYSTEM_PROMPTS[BCVCategory.SEV],
        "user": json.dumps({
            "claim": claim.predicate_object,
            "condition": claim.conditionality,
            "signature": signature,
            "subjects": [claim.subject],
        }),
        "temperature": 0.1,
    }


class LLMClientError(Exception):
    """Raised when all LLM call retries are exhausted."""


class LLMClient:
    """Unified async wrapper around OpenAI, Anthropic, and Google SDKs.

    Parameters
    ----------
    provider : LLMProvider
        Which LLM backend to use.
    max_retries : int
        Maximum number of retry attempts on transient errors (default 3).
    base_delay : float
        Initial backoff delay in seconds (doubles each retry).
    """

    _MAX_RETRIES_DEFAULT = 5
    _BASE_DELAY_DEFAULT = 10.0

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_retries: int = _MAX_RETRIES_DEFAULT,
        base_delay: float = _BASE_DELAY_DEFAULT,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries
        self.base_delay = base_delay

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
    ) -> str:
        """Send a prompt to the configured LLM and return the text response.

        Retries up to *max_retries* times with exponential backoff
        (1 s, 2 s, 4 s …) on API errors or timeouts.  After all retries
        are exhausted an ``LLMClientError`` is raised.

        Parameters
        ----------
        system : str
            System-level instruction for the model.
        user : str
            User message / prompt content.
        temperature : float
            Sampling temperature (default 0.1 per DTS spec).

        Returns
        -------
        str
            The model's text completion.

        Raises
        ------
        LLMClientError
            If all retry attempts fail.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return await self._dispatch(system, user, temperature)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "LLM call attempt %d/%d failed (%s: %s), "
                        "retrying in %.1fs …",
                        attempt + 1,
                        self.max_retries + 1,
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise LLMClientError(
            f"All {self.max_retries + 1} attempts failed for "
            f"provider {self.provider.value}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        system: str,
        user: str,
        temperature: float,
    ) -> str:
        if self.provider == LLMProvider.GPT4_1_MINI:
            return await self._call_openai(system, user, temperature)
        elif self.provider == LLMProvider.CLAUDE_SONNET:
            return await self._call_anthropic(system, user, temperature)
        elif self.provider == LLMProvider.GEMINI_FLASH:
            return await self._call_google(system, user, temperature)
        elif self.provider == LLMProvider.BEDROCK:
            return await self._call_bedrock(system, user, temperature)
        else:
            raise LLMClientError(f"Unsupported provider: {self.provider}")

    # ------------------------------------------------------------------
    # OpenAI (GPT-4.1 Mini)
    # ------------------------------------------------------------------

    async def _call_openai(
        self,
        system: str,
        user: str,
        temperature: float,
    ) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=self.provider.value,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Anthropic (Claude 3.5 Sonnet Latest)
    # ------------------------------------------------------------------

    async def _call_anthropic(
        self,
        system: str,
        user: str,
        temperature: float,
    ) -> str:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=self.provider.value,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
        )
        # Anthropic returns a list of content blocks; take the first text.
        return response.content[0].text if response.content else ""

    # ------------------------------------------------------------------
    # Google (Gemini 2.5 Flash) — new google-genai SDK
    # ------------------------------------------------------------------

    async def _call_google(
        self,
        system: str,
        user: str,
        temperature: float,
    ) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.google_api_key)
        response = await client.aio.models.generate_content(
            model=self.provider.value,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
            ),
        )
        return response.text or ""

    # ------------------------------------------------------------------
    # AWS Bedrock (via boto3 Converse API)
    # ------------------------------------------------------------------

    async def _call_bedrock(
        self,
        system: str,
        user: str,
        temperature: float,
    ) -> str:
        import boto3

        loop = asyncio.get_event_loop()

        def _sync_call() -> str:
            client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id or None,
                aws_secret_access_key=settings.aws_secret_access_key or None,
            )
            response = client.converse(
                modelId=settings.bedrock_model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"temperature": temperature, "maxTokens": 4096},
            )
            output = response.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])
            return content[0]["text"] if content else ""

        return await loop.run_in_executor(None, _sync_call)


# ---------------------------------------------------------------------------
# Test output parsing
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(?:python)?\s*\n(.*?)```",
    re.DOTALL,
)

_DEF_TEST_RE = re.compile(
    r"(def\s+test_\w+\s*\(.*?\).*)",
    re.DOTALL,
)


def _parse_test_output(
    raw_output: str,
    framework: Optional[TestFramework] = None,
) -> Optional[str]:
    """Extract a valid test function from an LLM response.

    When *framework* is provided, uses ``framework.validate_test_syntax()``
    instead of ``ast.parse()`` for validation, enabling non-Python test code.
    When *framework* is ``None``, falls back to the original Python
    ``ast.parse()`` validation for backward compatibility.

    Steps:
    1. If the response contains markdown code blocks, extract the code
       from the first block.
    2. For Python (no framework or pytest): locate ``def test_`` and extract
       the function with imports.  For non-Python frameworks: use the full
       extracted code block.
    3. Validate with ``framework.validate_test_syntax()`` or ``ast.parse()``.
    4. Return the valid test code, or ``None`` if parsing fails.

    Parameters
    ----------
    raw_output : str
        Raw text response from the LLM provider.
    framework : TestFramework | None
        Optional test framework for language-specific validation.

    Returns
    -------
    str | None
        Syntactically valid test function source, or ``None``.
    """
    if not raw_output or not raw_output.strip():
        return None

    # Step 1: extract from markdown code blocks if present
    code = raw_output
    block_match = _CODE_BLOCK_RE.search(raw_output)
    if block_match:
        code = block_match.group(1)

    # Determine if we should use Python-specific extraction logic
    is_python = framework is None or framework.get_framework_name() == "pytest"

    if is_python:
        # Step 2 (Python): find the test function definition
        lines = code.split("\n")
        func_start: Optional[int] = None
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("def test_"):
                func_start = i
                break

        if func_start is None:
            return None

        # Collect the function: from def test_... to the end of the indented block
        func_lines = [lines[func_start]]
        base_indent = len(lines[func_start]) - len(lines[func_start].lstrip())

        for line in lines[func_start + 1:]:
            if not line.strip():
                func_lines.append(line)
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent > base_indent:
                func_lines.append(line)
            else:
                break

        # Also collect any import lines that appear before the function
        import_lines: list[str] = []
        for line in lines[:func_start]:
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                import_lines.append(line)

        if import_lines:
            test_code = "\n".join(import_lines) + "\n\n" + "\n".join(func_lines)
        else:
            test_code = "\n".join(func_lines)

        test_code = test_code.rstrip()

        # Step 3 (Python): validate with ast.parse()
        try:
            ast.parse(test_code)
        except SyntaxError:
            return None

        # Step 4: final check — must contain def test_
        if "def test_" not in test_code:
            return None

        return test_code
    else:
        # Step 2 (non-Python): use the full extracted code block
        test_code = code.strip()
        if not test_code:
            return None

        # Step 3 (non-Python): validate with framework
        if not framework.validate_test_syntax(test_code):
            return None

        return test_code


def _extract_function_name(test_code: str) -> Optional[str]:
    """Extract the test function name from validated test code.

    Parameters
    ----------
    test_code : str
        Syntactically valid Python containing a ``def test_...`` function.

    Returns
    -------
    str | None
        The function name, or ``None`` if not found.
    """
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            return node.name
    return None


# ---------------------------------------------------------------------------
# DynamicTestSynthesizer
# ---------------------------------------------------------------------------


class DynamicTestSynthesizer:
    """Converts behavioral claims into executable test functions.

    For each claim in a :class:`ClaimSchema`, the synthesizer:
    1. Builds a constrained prompt (SEV claims use the deepcopy-assert pattern).
    2. Calls the configured LLM provider via :class:`LLMClient`.
    3. Parses and validates the response as a test function.
    4. Produces a :class:`SynthesizedTest` on success.

    When a :class:`TestFramework` is provided, the synthesizer uses
    ``framework.get_system_prompt_context()`` to build language-specific
    system prompts and ``framework.validate_test_syntax()`` to validate
    generated test code.  When no framework is provided, falls back to
    the existing hardcoded pytest prompts and ``ast.parse()`` validation
    for backward compatibility.

    Parameters
    ----------
    llm_provider : LLMProvider
        Which LLM backend to use for test generation.
    temperature : float
        Sampling temperature for LLM calls (default 0.1 per spec).
    framework : TestFramework | None
        Optional test framework adapter for language-specific prompt
        context and syntax validation.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        temperature: float = 0.1,
        framework: Optional[TestFramework] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.temperature = temperature
        self.framework = framework
        self._client = LLMClient(provider=llm_provider)

    async def synthesize(self, claim_schema: ClaimSchema) -> list[SynthesizedTest]:
        """Synthesize tests for all claims in a function's claim schema.

        Iterates over each claim, builds the appropriate prompt, calls the
        LLM, parses the response, and collects successful results.

        When a framework is set, uses ``framework.get_system_prompt_context()``
        to build language-specific system prompts instead of the hardcoded
        pytest category prompts.

        Parameters
        ----------
        claim_schema : ClaimSchema
            The function's extracted claims to generate tests for.

        Returns
        -------
        list[SynthesizedTest]
            One ``SynthesizedTest`` per successfully synthesized claim.
            Claims that fail synthesis (invalid output, LLM errors after
            retries) are skipped.
        """
        results: list[SynthesizedTest] = []
        signature = claim_schema.function.signature

        for claim in claim_schema.claims:
            # Step 1: build prompt
            if self.framework is not None:
                prompt = self._build_framework_prompt(claim, signature)
            elif claim.category == BCVCategory.SEV:
                prompt = build_sev_prompt(claim, signature)
            else:
                prompt = build_prompt(claim, signature)

            # Rate-limit: wait between LLM calls to avoid quota exhaustion
            # on free-tier API keys (e.g. Gemini 5 req/min).
            await asyncio.sleep(13)

            # Step 2: call LLM
            try:
                raw_output = await self._client.call(
                    system=prompt["system"],
                    user=prompt["user"],
                    temperature=prompt["temperature"],
                )
            except LLMClientError:
                logger.warning(
                    "LLM synthesis failed for claim '%s' after retries, skipping.",
                    claim.predicate_object,
                )
                continue

            # Step 3: parse and validate the response
            test_code = _parse_test_output(raw_output, framework=self.framework)
            if test_code is None:
                logger.warning(
                    "Failed to parse valid test from LLM output for claim '%s'.",
                    claim.predicate_object,
                )
                continue

            # Extract function name (Python-specific for pytest, generic for others)
            if self.framework is None or self.framework.get_framework_name() == "pytest":
                func_name = _extract_function_name(test_code)
            else:
                # For non-Python frameworks, derive a test name from the claim
                func_name = f"test_{claim.subject}_{claim.category.value}".replace(" ", "_")

            if func_name is None:
                logger.warning(
                    "Could not extract test function name for claim '%s'.",
                    claim.predicate_object,
                )
                continue

            # Step 4: produce SynthesizedTest
            results.append(
                SynthesizedTest(
                    claim=claim,
                    test_code=test_code,
                    test_function_name=func_name,
                    synthesis_model=self.llm_provider.value,
                    prompt_tokens=len(prompt["system"].split()) + len(prompt["user"].split()),
                    completion_tokens=len(raw_output.split()),
                )
            )

        return results

    def _build_framework_prompt(self, claim: Claim, signature: str) -> dict:
        """Build a prompt using the framework's system prompt context.

        Combines the framework-specific context with claim and signature
        information, producing a prompt suitable for any supported language.

        Parameters
        ----------
        claim : Claim
            The behavioral claim to generate a test for.
        signature : str
            The function signature (no body).

        Returns
        -------
        dict
            Prompt dict with ``system``, ``user``, and ``temperature`` keys.
        """
        assert self.framework is not None

        # Build system prompt from framework context + category-specific guidance
        framework_context = self.framework.get_system_prompt_context()
        category_guidance = (
            f"You are generating a test for a {claim.category.value} "
            f"(behavioral claim category) claim. "
        )
        if claim.category == BCVCategory.SEV:
            category_guidance += (
                "This is a side-effect verification claim. "
                "Deep-copy all arguments before calling the function, "
                "then assert each argument claimed immutable equals its pre-call snapshot. "
            )

        system_prompt = f"{framework_context}\n\n{category_guidance}"

        user_content = json.dumps({
            "claim": claim.predicate_object,
            "condition": claim.conditionality,
            "signature": signature,
            "subjects": [claim.subject],
            "output_schema": OUTPUT_SCHEMA,
        })

        return {
            "system": system_prompt,
            "user": user_content,
            "temperature": 0.1,
        }
