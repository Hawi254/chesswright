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

    def test_system_wrapped_with_cache_control_when_tools_given(self):
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

    def test_system_wrapped_with_cache_control_even_without_tools(self):
        # Regression test for the forced-final-tool-round gap: caching used
        # to be gated on `tools is not None` for system too, which silently
        # dropped the cache_control breakpoint (and therefore the cache
        # read) on the one round of a turn that matters most -- see
        # converse()'s docstring. system must be cached whenever it's
        # given, independent of tools.
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                system="You are a chess coach.",
            )
        _, kwargs = client.messages.create.call_args
        assert kwargs["system"] == [{
            "type": "text",
            "text": "You are a chess coach.",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_system_suffix_appended_uncached_after_cached_system_block(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                system="stable persona + game brief + tools",
                system_suffix="volatile: current FEN is ...",
            )
        _, kwargs = client.messages.create.call_args
        assert kwargs["system"] == [
            {
                "type": "text",
                "text": "stable persona + game brief + tools",
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": "volatile: current FEN is ..."},
        ]

    def test_system_suffix_ignored_when_system_not_given(self):
        client = _mock_client()
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            claude_narrative.converse(
                messages=[{"role": "user", "content": "hi"}],
                system_suffix="volatile: current FEN is ...",
            )
        _, kwargs = client.messages.create.call_args
        assert "system" not in kwargs

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


@pytest.mark.unit
class TestGenerateScoutingNotes:
    def test_calls_contextualize_with_repertoire_data(self, monkeypatch):
        import pandas as pd
        import claude_narrative
        from claude_narrative import commentary
        captured = {}

        def _fake_contextualize(prompt, max_tokens=600):
            captured["prompt"] = prompt
            return "generated notes"

        # generate_scouting_notes calls contextualize as a module-local name
        # inside claude_narrative/commentary.py (a from-import, not a shared
        # module-object attribute like api_key_store/anthropic above) --
        # patching the package re-export wouldn't intercept that call.
        monkeypatch.setattr(commentary, "contextualize", _fake_contextualize)
        repertoire_df = pd.DataFrame([
            {"opening": "Sicilian Defense", "color": "black", "n_games": 5,
             "score_pct": 40.0, "avg_cpl": 55.0, "blunder_pct": 12.0},
        ])
        result = claude_narrative.generate_scouting_notes("DrNykterstein", repertoire_df, 8)
        assert result == "generated notes"
        assert "DrNykterstein" in captured["prompt"]
        assert "Sicilian Defense" in captured["prompt"]
        assert "12.0" in captured["prompt"]


class _FakeStreamCtx:
    """Duck-types anthropic's `with client.messages.stream(...) as stream:`
    context manager -- .text_stream is the only attribute answer_question_
    stream reads."""
    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        self.text_stream = iter(self._chunks)
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.unit
class TestAnswerQuestionStream:
    def test_raises_without_api_key(self):
        with patch("claude_narrative.api_key_store.get_api_key", return_value=None):
            gen = claude_narrative.answer_question_stream("When do I blunder most?", "brief text")
            with pytest.raises(claude_narrative.MissingApiKeyError):
                next(gen)

    def test_yields_deltas_from_the_stream(self):
        client = MagicMock()
        client.messages.stream.return_value = _FakeStreamCtx(["You blunder ", "most in the middlegame."])
        with patch("claude_narrative.api_key_store.get_api_key", return_value="sk-test"), \
             patch("claude_narrative.anthropic.Anthropic", return_value=client):
            deltas = list(claude_narrative.answer_question_stream("When do I blunder most?", "brief text"))

        assert deltas == ["You blunder ", "most in the middlegame."]
        _, kwargs = client.messages.stream.call_args
        assert kwargs["model"] == claude_narrative.MODEL
        assert kwargs["max_tokens"] == 300
        assert "When do I blunder most?" in kwargs["messages"][0]["content"]
        assert "brief text" in kwargs["messages"][0]["content"]
