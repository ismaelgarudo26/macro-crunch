import json
from pathlib import Path

_INGREDIENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "ingredients.json"
KNOWN_IDS = set(json.loads(_INGREDIENTS_PATH.read_text()).keys())


def call_vision(image, known_ids):
    """Not yet implemented."""
    raise NotImplementedError


def extract_ingredients(image, vision_fn=call_vision):
    """Ground a vision model's raw ingredient guesses against the known-id whitelist.

    Input:
        image: passed straight through to `vision_fn`, uninspected.
        vision_fn: callable(image, known_ids) -> list of {"id", "approx"}, already
            valid and well-formed (JSON/format validation is vision_fn's job, not
            this function's). If it raises, the error propagates uncaught.

    Output:
        list of {"id", "approx"} - only rows whose id is in KNOWN_IDS, first
        occurrence per id (later duplicates dropped), each approx coerced to str.
        Empty list if nothing survived.
    """
    rows = vision_fn(image, KNOWN_IDS)

    kept = []
    seen_ids = set()
    for row in rows:
        row_id = row["id"]
        if row_id not in KNOWN_IDS or row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        kept.append({"id": row_id, "approx": str(row["approx"])})

    return kept
