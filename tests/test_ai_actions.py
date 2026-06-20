import pytest

import actions.ai as ai_module
from actions.ai import ask, decide

# --- ask() tests ---


def test_ask_returns_llm_query_response(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "LLM text")
    result = ask("What is 2+2?")
    assert result == "LLM text"


def test_ask_includes_serialized_context(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["user"] = user
        return "ok"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    ask("question", context={"key": "value"})
    assert '"key": "value"' in captured["user"]
    assert "question" in captured["user"]


def test_ask_includes_none_when_no_context(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["user"] = user
        return "ok"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    ask("question")
    assert "None" in captured["user"]


def test_ask_uses_default_system_prompt_when_omitted(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["system"] = system
        return "ok"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    ask("question")
    assert "automation playbook" in captured["system"]


def test_ask_uses_caller_system_prompt_when_provided(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["system"] = system
        return "ok"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    ask("question", system_prompt="Custom system prompt")
    assert captured["system"] == "Custom system prompt"


def test_ask_does_not_pass_options(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["options"] = options
        return "ok"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    ask("question")
    assert captured["options"] is None


# --- decide() validation tests ---


def test_decide_rejects_empty_prompt(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "")
    with pytest.raises(ValueError, match="prompt"):
        decide("", options=["a"])


def test_decide_rejects_whitespace_only_prompt(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "")
    with pytest.raises(ValueError, match="prompt"):
        decide("   ", options=["a"])


def test_decide_rejects_empty_options(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "")
    with pytest.raises(ValueError, match="options"):
        decide("question", options=[])


def test_decide_rejects_duplicate_options(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "")
    with pytest.raises(ValueError, match="duplicate"):
        decide("question", options=["a", "a"])


def test_decide_rejects_empty_string_option(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "")
    with pytest.raises(ValueError, match="option"):
        decide("question", options=["a", ""])


def test_decide_rejects_invalid_default(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "")
    with pytest.raises(ValueError, match="default"):
        decide("question", options=["a"], default="b")


# --- decide() success tests ---


def test_decide_returns_valid_decision(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "escalate")
    result = decide("What to do?", options=["escalate", "ignore"])
    assert result == "escalate"


def test_decide_passes_options_to_llm_query(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["options"] = options
        return "a"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    decide("q", options=["a", "b"])
    assert captured["options"] == ["a", "b"]


def test_decide_retries_on_provider_error_then_succeeds(monkeypatch):
    responses = iter([RuntimeError("provider down"), "a"])

    def fake_llm_query(s, u, options=None):
        resp = next(responses)
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    result = decide("q", options=["a"])
    assert result == "a"


def test_decide_includes_context_in_prompt(monkeypatch):
    captured = {}

    def fake_llm_query(system, user, options=None):
        captured["user"] = user
        return "a"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    decide("q", options=["a"], context={"alert": "high"})
    assert '"alert": "high"' in captured["user"]


# --- decide() failure tests ---


def test_decide_defensive_check_rejects_out_of_options_result(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "unexpected")
    result = decide("q", options=["a"], default="a")
    assert result == "a"


def test_decide_returns_default_after_all_attempts_fail(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "garbage")
    result = decide("q", options=["a"], default="a")
    assert result == "a"


def test_decide_raises_runtime_error_when_no_default(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "garbage")
    with pytest.raises(RuntimeError, match="last error"):
        decide("q", options=["a"])


def test_decide_runtime_error_includes_last_error(monkeypatch):
    monkeypatch.setattr(ai_module, "llm_query", lambda s, u, options=None: "garbage")
    with pytest.raises(RuntimeError) as exc_info:
        decide("q", options=["a"])
    assert "garbage" in str(exc_info.value)


def test_decide_makes_exactly_three_attempts(monkeypatch):
    call_count = 0

    def fake_llm_query(s, u, options=None):
        nonlocal call_count
        call_count += 1
        return "garbage"

    monkeypatch.setattr(ai_module, "llm_query", fake_llm_query)
    with pytest.raises(RuntimeError):
        decide("q", options=["a"])
    assert call_count == 3
