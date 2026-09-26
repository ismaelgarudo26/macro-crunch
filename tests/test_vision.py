"""
tests/test_vision.py — extract_ingredients grounding contract

These pin the ORCHESTRATION around the vision call (filtering against the known-id
whitelist, deduping, coercing approx to str, and letting failures propagate) - not the
vision model itself. vision_fn is always faked and passed in directly via the
vision_fn parameter, so no real vision API call ever runs and the model's
nondeterminism is out of scope here.
"""

import base64
import json
from types import SimpleNamespace

import pytest

from macro_crunch import vision
from macro_crunch.vision import extract_ingredients

IMAGE = "fake_image_bytes"
INVALID_ID = "NOT_A_REAL_INGREDIENT"


def test_happy_path_all_valid_rows_kept():
    valid = list(vision.KNOWN_IDS)[:4]
    rows = [{"id": vid, "approx": f"~{i + 1} units"} for i, vid in enumerate(valid)]

    def fake(image, prompt):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert len(result) == 4
    result_ids = [row["id"] for row in result]
    for vid in valid:
        assert vid in result_ids
    for row in result:
        expected_approx = rows[valid.index(row["id"])]["approx"]
        assert row["approx"] == expected_approx


def test_all_invalid_rows_returns_empty_list():
    rows = [{"id": INVALID_ID, "approx": "1"}, {"id": INVALID_ID + "_2", "approx": "2"}]

    def fake(image, prompt):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert result == []


def test_mixed_valid_and_invalid_keeps_only_valid():
    valid = list(vision.KNOWN_IDS)[:4]
    rows = (
        [{"id": vid, "approx": f"~{i + 1} units"} for i, vid in enumerate(valid)]
        + [{"id": INVALID_ID, "approx": "1"}, {"id": INVALID_ID + "_2", "approx": "2"}]
    )

    def fake(image, prompt):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    result_ids = [row["id"] for row in result]
    assert sorted(result_ids) == sorted(valid)
    assert INVALID_ID not in result_ids
    assert INVALID_ID + "_2" not in result_ids
    for row in result:
        expected_approx = rows[valid.index(row["id"])]["approx"]
        assert row["approx"] == expected_approx


def test_approx_is_always_coerced_to_str():
    valid_id = next(iter(vision.KNOWN_IDS))
    rows = [{"id": valid_id, "approx": 2}]

    def fake(image, prompt):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert result[0]["approx"] == "2"
    assert isinstance(result[0]["approx"], str)


def test_vision_failure_propagates():
    def fake(image, prompt):
        raise ValueError("exhausted JSON retries")

    with pytest.raises(ValueError):
        extract_ingredients(IMAGE, vision_fn=fake)


def test_duplicate_ids_dedupe_keeping_first_approx():
    valid_id = next(iter(vision.KNOWN_IDS))
    rows = [{"id": valid_id, "approx": "first"}, {"id": valid_id, "approx": "second"}]

    def fake(image, prompt):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert len(result) == 1
    assert result[0]["id"] == valid_id
    assert result[0]["approx"] == "first"


# --- extract_remaining contract ----------------------------------------------
#
# extract_remaining(image, vision_fn=call_vision, prompt=REMAINING_PROMPT) turns the
# vision model's reading of a MyFitnessPal screenshot into exactly {cal, protein,
# carbs, fat} as floats. Negative values pass through; any missing or non-numeric key
# raises a ValueError naming every failing key. vision_fn is faked and passed in
# directly, so no real API call runs.


def test_extract_remaining_all_present_returns_four_floats():
    def fake(image, prompt):
        return {"cal": 500, "protein": 40.0, "carbs": 50, "fat": 15.5}

    result = vision.extract_remaining(IMAGE, vision_fn=fake)

    assert set(result.keys()) == {"cal", "protein", "carbs", "fat"}
    for key in ("cal", "protein", "carbs", "fat"):
        assert isinstance(result[key], float)


def test_extract_remaining_one_missing_key_raises_value_error():
    def fake(image, prompt):
        return {"cal": 500, "protein": 40, "fat": 15}  # carbs missing

    with pytest.raises(ValueError) as excinfo:
        vision.extract_remaining(IMAGE, vision_fn=fake)

    assert "carbs" in str(excinfo.value)


def test_extract_remaining_two_missing_keys_raises_value_error_naming_both():
    def fake(image, prompt):
        return {"cal": 500, "protein": 40}  # carbs and fat missing

    with pytest.raises(ValueError) as excinfo:
        vision.extract_remaining(IMAGE, vision_fn=fake)

    message = str(excinfo.value)
    assert "carbs" in message
    assert "fat" in message


def test_extract_remaining_typo_key_treated_as_missing():
    def fake(image, prompt):
        return {"cal": 500, "protein": 40, "carbs": 50, "tas": 15}  # "fat" typoed as "tas"

    with pytest.raises(ValueError) as excinfo:
        vision.extract_remaining(IMAGE, vision_fn=fake)

    assert "fat" in str(excinfo.value)


def test_extract_remaining_negative_value_does_not_raise():
    def fake(image, prompt):
        return {"cal": -200, "protein": 40, "carbs": 50, "fat": 15}

    result = vision.extract_remaining(IMAGE, vision_fn=fake)

    assert result["cal"] == -200.0
    assert isinstance(result["cal"], float)


# --- call_vision -------------------------------------------------------------
#
# call_vision() constructs its own OpenAI client internally, so these fake out the
# `OpenAI` name in vision.py (monkeypatch.setattr(vision, "OpenAI", ...)), same as
# test_llm.py does for propose(). raising=False because vision.OpenAI may not exist
# yet - that way a missing import fails individual tests on behavior, not collection.
# The fake returns scripted raw response strings in order and records the kwargs of
# every create() call. New names (call_vision, MODEL) are accessed as `vision.X`
# attributes so a missing one fails its own test only.

IMAGE_BYTES = b"\x89PNG-fake-bytes"
PROMPT = "describe this image"


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

    monkeypatch.setattr(vision, "OpenAI", _FakeOpenAI, raising=False)
    return recorder


def _content_parts(call_kwargs):
    """Return the content parts of the single user message in a create() call."""
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    return messages[0]["content"]


def _image_url(parts):
    image_parts = [p for p in parts if p.get("type") == "image_url"]
    assert len(image_parts) == 1
    return image_parts[0]["image_url"]["url"]


# Request shape

def test_call_vision_request_has_prompt_text_and_image_data_url(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, [json.dumps({"items": []})])

    vision.call_vision(IMAGE_BYTES, PROMPT)

    parts = _content_parts(recorder.calls[0])
    text_parts = [p for p in parts if p.get("type") == "text"]
    assert len(text_parts) == 1
    assert text_parts[0]["text"] == PROMPT

    expected_b64 = base64.b64encode(IMAGE_BYTES).decode("ascii")
    assert _image_url(parts) == f"data:image/jpeg;base64,{expected_b64}"


def test_call_vision_non_default_mime_type_in_data_url(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, [json.dumps({"items": []})])

    vision.call_vision(IMAGE_BYTES, PROMPT, mime_type="image/png")

    parts = _content_parts(recorder.calls[0])
    assert _image_url(parts).startswith("data:image/png;base64,")


def test_call_vision_uses_model_and_json_object_response_format(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, [json.dumps({"items": []})])

    vision.call_vision(IMAGE_BYTES, PROMPT)

    kwargs = recorder.calls[0]
    assert vision.MODEL == "gpt-4o-mini"
    assert kwargs["model"] == vision.MODEL
    assert kwargs["response_format"] == {"type": "json_object"}


# Response parsing

def test_call_vision_items_wrapper_returns_bare_list(monkeypatch):
    rows = [{"id": "egg", "approx": "2"}, {"id": "butter", "approx": "a knob"}]
    _install_fake_openai(monkeypatch, [json.dumps({"items": rows})])

    result = vision.call_vision(IMAGE_BYTES, PROMPT)

    assert result == rows


def test_call_vision_dict_without_items_returned_as_is(monkeypatch):
    reading = {"cal": 500, "protein": 40, "carbs": 50, "fat": 15}
    _install_fake_openai(monkeypatch, [json.dumps(reading)])

    result = vision.call_vision(IMAGE_BYTES, PROMPT)

    assert result == reading


def test_call_vision_empty_items_returns_empty_list(monkeypatch):
    _install_fake_openai(monkeypatch, [json.dumps({"items": []})])

    result = vision.call_vision(IMAGE_BYTES, PROMPT)

    assert result == []


# Failure

def test_call_vision_malformed_json_raises_without_retry(monkeypatch):
    recorder = _install_fake_openai(monkeypatch, ["not json"])

    with pytest.raises(json.JSONDecodeError):
        vision.call_vision(IMAGE_BYTES, PROMPT)

    assert len(recorder.calls) == 1


# Prompt grounding (no fake needed)

def test_ingredient_prompt_embeds_every_known_id():
    for known_id in vision.KNOWN_IDS:
        assert known_id in vision.INGREDIENT_PROMPT


def test_ingredient_prompt_describes_items_id_approx_shape():
    # Keys must appear quoted (as JSON key names), not just as English words -
    # "food items" in prose would otherwise satisfy a bare substring check.
    def mentions_key(key):
        return f'"{key}"' in vision.INGREDIENT_PROMPT or f"'{key}'" in vision.INGREDIENT_PROMPT

    for key in ("items", "id", "approx"):
        assert mentions_key(key), f"INGREDIENT_PROMPT does not name the {key!r} key"


# End-to-end (default vision_fn, fake client only)

def test_extract_ingredients_default_vision_fn_end_to_end(monkeypatch):
    known_id = sorted(vision.KNOWN_IDS)[0]
    _install_fake_openai(
        monkeypatch, [json.dumps({"items": [{"id": known_id, "approx": "2"}]})]
    )

    result = vision.extract_ingredients(IMAGE_BYTES)

    assert result == [{"id": known_id, "approx": "2"}]


def test_extract_remaining_default_vision_fn_end_to_end(monkeypatch):
    _install_fake_openai(
        monkeypatch, [json.dumps({"cal": 500, "protein": 40, "carbs": 50, "fat": 15})]
    )

    result = vision.extract_remaining(IMAGE_BYTES)

    assert result == {"cal": 500.0, "protein": 40.0, "carbs": 50.0, "fat": 15.0}
    for key in ("cal", "protein", "carbs", "fat"):
        assert isinstance(result[key], float)
