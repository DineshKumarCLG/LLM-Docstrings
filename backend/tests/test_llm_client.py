"""Unit tests for the LLM provider abstraction (LLMClient).

Validates Requirements 3.5 and 5.1:
- Unified interface across OpenAI, Anthropic, and Google SDKs
- Retry logic: up to 3 retries with exponential backoff on API errors/timeouts
- Raises LLMClientError after all retries exhausted
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.dts.synthesizer import LLMClient, LLMClientError
from app.schemas import LLMProvider


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_succeeds_on_first_attempt():
    """Happy path: LLM responds on the first try."""
    client = LLMClient(LLMProvider.GPT4_1_MINI)
    with patch.object(client, "_dispatch", new_callable=AsyncMock, return_value="ok"):
        result = await client.call("sys", "usr")
    assert result == "ok"


@pytest.mark.asyncio
async def test_call_retries_on_transient_error():
    """Should retry and succeed after transient failures."""
    client = LLMClient(LLMProvider.GPT4_1_MINI, base_delay=0.0)

    mock_dispatch = AsyncMock(
        side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), "success"]
    )
    with patch.object(client, "_dispatch", mock_dispatch):
        result = await client.call("sys", "usr")

    assert result == "success"
    assert mock_dispatch.call_count == 3


@pytest.mark.asyncio
async def test_call_raises_after_all_retries_exhausted():
    """After max_retries + 1 attempts, LLMClientError is raised."""
    client = LLMClient(LLMProvider.GPT4_1_MINI, max_retries=3, base_delay=0.0)

    mock_dispatch = AsyncMock(side_effect=RuntimeError("always fails"))
    with patch.object(client, "_dispatch", mock_dispatch):
        with pytest.raises(LLMClientError, match="All 4 attempts failed"):
            await client.call("sys", "usr")

    # 1 initial + 3 retries = 4 total attempts
    assert mock_dispatch.call_count == 4


@pytest.mark.asyncio
async def test_retry_count_is_configurable():
    """max_retries=1 means 2 total attempts."""
    client = LLMClient(LLMProvider.CLAUDE_SONNET, max_retries=1, base_delay=0.0)

    mock_dispatch = AsyncMock(side_effect=RuntimeError("fail"))
    with patch.object(client, "_dispatch", mock_dispatch):
        with pytest.raises(LLMClientError):
            await client.call("sys", "usr")

    assert mock_dispatch.call_count == 2


@pytest.mark.asyncio
async def test_exponential_backoff_delays():
    """Verify that sleep is called with exponential delays: 1, 2, 4."""
    client = LLMClient(LLMProvider.GPT4_1_MINI, max_retries=3, base_delay=1.0)

    mock_dispatch = AsyncMock(side_effect=RuntimeError("fail"))
    recorded_delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        recorded_delays.append(delay)

    with (
        patch.object(client, "_dispatch", mock_dispatch),
        patch("app.pipeline.dts.synthesizer.asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(LLMClientError):
            await client.call("sys", "usr")

    assert recorded_delays == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_routes_to_openai():
    client = LLMClient(LLMProvider.GPT4_1_MINI)
    with patch.object(client, "_call_openai", new_callable=AsyncMock, return_value="gpt") as mock:
        result = await client._dispatch("sys", "usr", 0.1)
    assert result == "gpt"
    mock.assert_awaited_once_with("sys", "usr", 0.1)


@pytest.mark.asyncio
async def test_dispatch_routes_to_anthropic():
    client = LLMClient(LLMProvider.CLAUDE_SONNET)
    with patch.object(client, "_call_anthropic", new_callable=AsyncMock, return_value="claude") as mock:
        result = await client._dispatch("sys", "usr", 0.1)
    assert result == "claude"
    mock.assert_awaited_once_with("sys", "usr", 0.1)


@pytest.mark.asyncio
async def test_dispatch_routes_to_google():
    client = LLMClient(LLMProvider.GEMINI_FLASH)
    with patch.object(client, "_call_google", new_callable=AsyncMock, return_value="gemini") as mock:
        result = await client._dispatch("sys", "usr", 0.1)
    assert result == "gemini"
    mock.assert_awaited_once_with("sys", "usr", 0.1)


# ---------------------------------------------------------------------------
# Temperature passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_temperature_passed_to_dispatch():
    """Temperature value should be forwarded to the provider call."""
    client = LLMClient(LLMProvider.GPT4_1_MINI)
    with patch.object(client, "_dispatch", new_callable=AsyncMock, return_value="ok") as mock:
        await client.call("sys", "usr", temperature=0.7)
    mock.assert_awaited_once_with("sys", "usr", 0.7)


# ---------------------------------------------------------------------------
# Default temperature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_temperature_is_0_1():
    """Default temperature should be 0.1 per DTS spec."""
    client = LLMClient(LLMProvider.GPT4_1_MINI)
    with patch.object(client, "_dispatch", new_callable=AsyncMock, return_value="ok") as mock:
        await client.call("sys", "usr")
    mock.assert_awaited_once_with("sys", "usr", 0.1)
