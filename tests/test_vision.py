"""
tests/test_vision.py — extract_ingredients grounding contract

These pin the ORCHESTRATION around the vision call (filtering against the known-id
whitelist, deduping, coercing approx to str, and letting failures propagate) - not the
vision model itself. vision_fn is always faked and passed in directly via the
vision_fn parameter, so no real vision API call ever runs and the model's
nondeterminism is out of scope here.
"""

import pytest

from macro_crunch import vision
from macro_crunch.vision import extract_ingredients

IMAGE = "fake_image_bytes"
INVALID_ID = "NOT_A_REAL_INGREDIENT"


def test_happy_path_all_valid_rows_kept():
    valid = list(vision.KNOWN_IDS)[:4]
    rows = [{"id": vid, "approx": f"~{i + 1} units"} for i, vid in enumerate(valid)]

    def fake(image, known_ids):
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

    def fake(image, known_ids):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert result == []


def test_mixed_valid_and_invalid_keeps_only_valid():
    valid = list(vision.KNOWN_IDS)[:4]
    rows = (
        [{"id": vid, "approx": f"~{i + 1} units"} for i, vid in enumerate(valid)]
        + [{"id": INVALID_ID, "approx": "1"}, {"id": INVALID_ID + "_2", "approx": "2"}]
    )

    def fake(image, known_ids):
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

    def fake(image, known_ids):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert result[0]["approx"] == "2"
    assert isinstance(result[0]["approx"], str)


def test_vision_failure_propagates():
    def fake(image, known_ids):
        raise ValueError("exhausted JSON retries")

    with pytest.raises(ValueError):
        extract_ingredients(IMAGE, vision_fn=fake)


def test_duplicate_ids_dedupe_keeping_first_approx():
    valid_id = next(iter(vision.KNOWN_IDS))
    rows = [{"id": valid_id, "approx": "first"}, {"id": valid_id, "approx": "second"}]

    def fake(image, known_ids):
        return rows

    result = extract_ingredients(IMAGE, vision_fn=fake)

    assert len(result) == 1
    assert result[0]["id"] == valid_id
    assert result[0]["approx"] == "first"
