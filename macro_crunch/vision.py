import json
from pathlib import Path

_INGREDIENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "ingredients.json"
KNOWN_IDS = set(json.loads(_INGREDIENTS_PATH.read_text()).keys())


INGREDIENT_PROMPT = (
    "List the food items you see in this image. For each, return a row with an "
    "'id' and an 'approx' (a rough amount, as free text)."
)


REMAINING_PROMPT = (
    "Read the remaining macro values from this MyFitnessPal screenshot. Return them as "
    "a JSON object with keys 'cal', 'protein', 'carbs', and 'fat'."
)

_REMAINING_KEYS = ("cal", "protein", "carbs", "fat")


def call_vision(image, prompt):
    """Not yet implemented."""
    raise NotImplementedError


def extract_ingredients(image, vision_fn=call_vision, prompt=INGREDIENT_PROMPT):
    """Ground a vision model's raw ingredient guesses against the known-id whitelist.

    Input:
        image: passed straight through to `vision_fn`, uninspected.
        vision_fn: callable(image, prompt) -> list of {"id", "approx"}, already
            valid and well-formed (JSON/format validation is vision_fn's job, not
            this function's). If it raises, the error propagates uncaught.
        prompt: passed straight through as vision_fn's second argument, uninspected.
            Defaults to INGREDIENT_PROMPT.

    Output:
        list of {"id", "approx"} - only rows whose id is in KNOWN_IDS, first
        occurrence per id (later duplicates dropped), each approx coerced to str.
        Empty list if nothing survived.
    """
    rows = vision_fn(image, prompt)

    kept = []
    seen_ids = set()
    for row in rows:
        row_id = row["id"]
        if row_id not in KNOWN_IDS or row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        kept.append({"id": row_id, "approx": str(row["approx"])})

    return kept


def extract_remaining(image, vision_fn=call_vision, prompt=REMAINING_PROMPT):
    """Ground a vision model's reading of a MyFitnessPal screenshot into remaining macros.

    Input:
        image: passed straight through to `vision_fn`, uninspected.
        vision_fn: callable(image, prompt) -> dict, already parsed into a dict (JSON/format
            validation is vision_fn's job, not this function's). If it raises, the error
            propagates uncaught.
        prompt: passed straight through as vision_fn's second argument, uninspected.
            Defaults to REMAINING_PROMPT.

    Output:
        dict with exactly {"cal", "protein", "carbs", "fat"}, each value coerced to float.
        Negative values are allowed (over-budget macros are real); cal <= 0 is not rejected
        here - that's run_loop's job.

    Failure:
        raises ValueError naming every key that is either missing or not coercible to
        float - missing and non-numeric collapse into the same failing-keys list, never a
        generic message.
    """
    reading = vision_fn(image, prompt)

    remaining = {}
    failing_keys = []
    for key in _REMAINING_KEYS:
        if key not in reading:
            failing_keys.append(key)
            continue
        try:
            remaining[key] = float(reading[key])
        except (TypeError, ValueError):
            failing_keys.append(key)

    if failing_keys:
        raise ValueError(f"missing or non-numeric macro value(s): {', '.join(failing_keys)}")

    return remaining
