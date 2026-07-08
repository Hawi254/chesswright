"""Unit tests for claude_narrative.converse() -- the AI Coach multi-round
entry point. No real network calls: anthropic.Anthropic is mocked
throughout, following this repo's existing mocking convention (patch the
module's own imported reference to the external client -- see
test_lichess_cloud_eval.py)."""
from unittest.mock import patch, MagicMock

import pytest

import claude_narrative


def _mock_client():
    client = MagicMock()
    client.messages.create.return_value = MagicMock(name="response")
    return client


@pytest.mark.unit
class TestConverse:
    def test_raises_without_api_key(self):
        with patch("claude_narrative.api_key_store.get_api_key", return_value=None):
            with pytest.raises(claude_narrative.MissingApiKeyError):
                claude_narrative.converse(messages=[{"role": "user", "content": "hi"}])

    def test_messages_pass_through_unchanged(self):
        client = _mock_client()
        messages = [
            {"role": "user", "content": "How's my endgame?"},
            {"role": "assistant", "content": [{"type": "text", "text": "Let's see."}]},
        ]
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(messages=messages)

        _, kwargs = client.messages.create.call_args
        assert kwargs["messages"] == messages
        # messages must not be mutated in place (same object identity, same content)
        assert kwargs["messages"] is messages

    def test_system_wrapped_with_cache_control_only_when_tools_given(self):
        client = _mock_client()
        tools = [{"name": "get_stats", "description": "d", "input_schema": {}}]
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                system="You are a chess coach.",
                tools=tools,
            )
        _, kwargs = client.messages.create.call_args
        assert kwargs["system"] == [{
            "type": "text",
            "text": "You are a chess coach.",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_system_plain_string_when_no_tools(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                system="You are a chess coach.",
            )
        _, kwargs = client.messages.create.call_args
        assert kwargs["system"] == "You are a chess coach."

    def test_system_omitted_when_not_given(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(messages=[{"role": "user", "content": "hi"}])
        _, kwargs = client.messages.create.call_args
        assert "system" not in kwargs

    def test_tools_get_cache_control_on_last_entry_only(self):
        client = _mock_client()
        tools = [
            {"name": "get_stats", "description": "d1", "input_schema": {}},
            {"name": "get_games", "description": "d2", "input_schema": {}},
        ]
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
            )
        _, kwargs = client.messages.create.call_args
        result_tools = kwargs["tools"]
        assert len(result_tools) == 2
        assert "cache_control" not in result_tools[0]
        assert result_tools[1]["cache_control"] == {"type": "ephemeral"}
        # original tool dicts must not be mutated
        assert "cache_control" not in tools[0]
        assert "cache_control" not in tools[1]

    def test_tools_omitted_when_not_given(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(messages=[{"role": "user", "content": "hi"}])
        _, kwargs = client.messages.create.call_args
        assert "tools" not in kwargs

    def test_model_override(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-sonnet-5",
            )
        _, kwargs = client.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"

    def test_default_model_is_file_wide_constant(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(messages=[{"role": "user", "content": "hi"}])
        _, kwargs = client.messages.create.call_args
        assert kwargs["model"] == claude_narrative.MODEL

    def test_returns_raw_response_object(self):
        client = _mock_client()
        sentinel_response = MagicMock()
        client.messages.create.return_value = sentinel_response
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            result = claude_narrative.converse(messages=[{"role": "user", "content": "hi"}])
        assert result is sentinel_response

    def test_max_tokens_default_and_override(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(messages=[{"role": "user", "content": "hi"}])
        _, kwargs = client.messages.create.call_args
        assert kwargs["max_tokens"] == 1024

        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(messages=[{"role": "user", "content": "hi"}], max_tokens=2048)
        _, kwargs = client.messages.create.call_args
        assert kwargs["max_tokens"] == 2048
