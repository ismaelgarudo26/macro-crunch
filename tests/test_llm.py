"""
tests/test_llm.py — propose() and its pure helpers: _build_user_prompt and _validate

_build_user_prompt and _validate are pure (no network, no OpenAI client), so they're
tested directly with no mocking. propose() wraps them in a retry loop around a real
OpenAI API call, so its tests fake the OpenAI client instead (via monkeypatch.setattr
on llm.OpenAI) - no real network call ever runs and no real API key is needed.
"""

import json
from types import SimpleNamespace

import pytest

from macro_crunch import llm
from macro_crunch.llm import MAX_ATTEMPTS, _build_user_prompt, _validate, propose

AVAILABLE = [
    {"id": "chicken_breast", "approx": "~2 pieces"},
    {"id": "white_rice_cooked", "approx": "1 cup"},
]
REMAINING = {"cal": 500, "protein": 40, "carbs": 50, "fat": 15}


# --- _validate ---------------------------------------------------------------

def test_validate_malformed_json_rejected():
    items, error = _validate("not json", AVAILABLE)

    assert items is None
    assert "malformed JSON" in error


def test_validate_meal_wrapper_object_accepted():
    raw = json.dumps({"meal": [{"id": "chicken_breast", "grams": 150}]})

    items, error = _validate(raw, AVAILABLE)

    assert error is None
    assert items == [{"id": "chicken_breast", "grams": 150}]


def test_validate_bare_list_accepted():
    raw = json.dumps([{"id": "chicken_breast", "grams": 150}])

    items, error = _validate(raw, AVAILABLE)

    assert error is None
    assert items == [{"id": "chicken_breast", "grams": 150}]


def test_validate_dict_without_meal_key_rejected():
    raw = json.dumps({"foo": "bar"})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "not a JSON list" in error


def test_validate_meal_not_a_list_rejected():
    raw = json.dumps({"meal": "not a list"})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "not a JSON list" in error


def test_validate_item_not_an_object_rejected():
    raw = json.dumps({"meal": ["chicken_breast"]})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "item is not an object" in error


def test_validate_macro_field_rejected_with_specific_message():
    raw = json.dumps({"meal": [{"id": "chicken_breast", "grams": 150, "cal": 200}]})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "macro fields" in error
    assert "cal" in error


def test_validate_unexpected_non_macro_field_rejected():
    raw = json.dumps({"meal": [{"id": "chicken_breast", "grams": 150, "note": "yum"}]})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "unexpected fields" in error
    assert "note" in error


def test_validate_missing_required_field_rejected():
    raw = json.dumps({"meal": [{"id": "chicken_breast"}]})  # missing grams

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "missing required fields" in error
    assert "grams" in error


def test_validate_unknown_id_rejected_against_row_shaped_available():
    raw = json.dumps({"meal": [{"id": "not_a_real_ingredient", "grams": 100}]})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "unknown ingredient id" in error
    assert "not_a_real_ingredient" in error


def test_validate_grams_non_numeric_rejected():
    raw = json.dumps({"meal": [{"id": "chicken_breast", "grams": "150"}]})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "grams is not a number" in error


def test_validate_grams_bool_rejected():
    raw = json.dumps({"meal": [{"id": "chicken_breast", "grams": True}]})

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert "grams is not a number" in error


def test_validate_multiple_valid_items_kept_in_order():
    raw = json.dumps(
        {
            "meal": [
                {"id": "chicken_breast", "grams": 150},
                {"id": "white_rice_cooked", "grams": 200},
            ]
        }
    )

    items, error = _validate(raw, AVAILABLE)

    assert error is None
    assert items == [
        {"id": "chicken_breast", "grams": 150},
        {"id": "white_rice_cooked", "grams": 200},
    ]


def test_validate_empty_meal_list_is_valid():
    raw = json.dumps({"meal": []})

    items, error = _validate(raw, AVAILABLE)

    assert items == []
    assert error is None


def test_validate_one_bad_item_rejects_whole_batch():
    raw = json.dumps(
        {
            "meal": [
                {"id": "chicken_breast", "grams": 150},
                {"id": "not_a_real_ingredient", "grams": 50},
            ]
        }
    )

    items, error = _validate(raw, AVAILABLE)

    assert items is None
    assert error is not None


# --- _build_user_prompt -------------------------------------------------------

def test_build_user_prompt_includes_full_available_rows():
    prompt = _build_user_prompt(AVAILABLE, REMAINING)

    assert json.dumps(AVAILABLE) in prompt


def test_build_user_prompt_includes_remaining_budget():
    prompt = _build_user_prompt(AVAILABLE, REMAINING)

    assert json.dumps(REMAINING) in prompt


# --- propose -------------------------------------------------------------------
#
# propose() constructs its own OpenAI client internally, so these fake out the
# `OpenAI` name imported into llm.py (monkeypatch.setattr(llm, "OpenAI", ...)) rather
# than propose()'s own arguments. The fake returns scripted raw response strings in
# order and records the kwargs of every create() call, so tests can assert on call
# count and on how the retry conversation (the `messages` list) grows.

VALID_RAW = json.dumps({"meal": [{"id": "chicken_breast", "grams": 150}]})
INVALID_RAW = json.dumps({"meal": [{"id": "chicken_breast"}]})  # missing "grams"


class _Recorder:
    """Scripted fake for client.chat.completions.create(): returns raw_responses in
    order, one per call, and records the kwargs each call was made with."""

    def __init__(self, raw_responses):
        self.raw_responses = raw_responses
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raw = self.raw_responses[len(self.calls) - 1]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))])


def _install_fake_openai(monkeypatch, raw_responses):
    recorder = _Recorder(raw_responses)

    class _FakeCompletions:
        create = staticmethod(recorder.create)

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _FakeChat()

    monkeypatch.setattr(llm, "OpenAI", _FakeOpenAI)
    return recorder


def test_propose_succeeds_on_first_attempt(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, [VALID_RAW])

    result = propose(AVAILABLE, REMAINING)

    assert result == [{"id": "chicken_breast", "grams": 150}]
    assert len(recorder.calls) == 1


def test_propose_retries_then_succeeds_with_feedback_in_trail(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, [INVALID_RAW, VALID_RAW])

    result = propose(AVAILABLE, REMAINING)

    assert result == [{"id": "chicken_breast", "grams": 150}]
    assert len(recorder.calls) == 2

    second_call_messages = recorder.calls[1]["messages"]
    assert len(second_call_messages) == 4
    assert second_call_messages[2] == {"role": "assistant", "content": INVALID_RAW}
    assert second_call_messages[3]["role"] == "user"
    assert "invalid" in second_call_messages[3]["content"].lower()


def test_propose_exhausts_attempts_and_raises(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, [INVALID_RAW] * MAX_ATTEMPTS)

    with pytest.raises(ValueError):
        propose(AVAILABLE, REMAINING)

    assert len(recorder.calls) == MAX_ATTEMPTS
