import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-4o-mini"
MAX_ATTEMPTS = 3

_ALLOWED_KEYS = {"id", "grams"}
_MACRO_KEYS = {"cal", "protein", "carbs", "fat"}

_SYSTEM_PROMPT = (
    "You propose meals from a fixed ingredient list. You never compute or state any macro "
    "numbers (calories, protein, carbs, fat) - only ingredient ids and gram amounts. "
    'Respond with a JSON object of the exact form {"meal": [{"id": <ingredient id>, '
    '"grams": <number>}, ...]}. Every id must be chosen from the ingredient ids provided '
    "by the user - never invent an id. Do not include any other fields and never include "
    "macro numbers."
)


def propose(available_ingredients, remaining):
    """Ask the model to propose a meal, returning ONLY a validated list of {id, grams} objects.

    The model proposes meals; it never does arithmetic - all macro computation is done by
    compute_macros, not here.

    Inputs:
        available_ingredients: list of {"id": str, "approx": str} rows the model may choose
            from (already filtered to the ingredients table by the caller). `approx` is a
            rough on-hand amount, so the model doesn't propose more of an ingredient than
            is actually available.
        remaining: dict {"cal", "protein", "carbs", "fat"} - the macro budget the proposed
            meal should aim to fit.

    Output:
        list of {"id": str, "grams": number}. IDs always come from `available_ingredients`;
        the response never contains macro numbers.

    The model's raw response is validated before being returned: malformed JSON, ids not in
    `available_ingredients`, or any macro fields in an item are all rejected, and the request
    is re-sent to the model (up to MAX_ATTEMPTS) rather than returned to the caller.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(available_ingredients, remaining)},
    ]

    last_error = None
    for _ in range(MAX_ATTEMPTS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content

        items, error = _validate(raw, available_ingredients)
        if error is None:
            return items

        last_error = error
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": f"That response was invalid: {error}. Reply again with ONLY the corrected JSON.",
            }
        )

    raise ValueError(f"model failed to produce a valid proposal after {MAX_ATTEMPTS} attempts: {last_error}")


def _build_user_prompt(available_ingredients, remaining):
    return (
        "Available ingredients (id and approximate amount on hand): "
        + json.dumps(available_ingredients) + "\n"
        "Remaining macro budget for this meal: " + json.dumps(remaining) + "\n"
        "Propose a meal using only the available ingredient ids that roughly fits the "
        "remaining macro budget."
    )


def _validate(raw, available_ingredients):
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"malformed JSON ({e})"

    items = parsed.get("meal") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return None, "response is not a JSON list of items"

    available = {row["id"] for row in available_ingredients}
    validated = []
    for item in items:
        if not isinstance(item, dict):
            return None, f"item is not an object: {item!r}"

        keys = set(item.keys())
        extra = keys - _ALLOWED_KEYS
        missing = _ALLOWED_KEYS - keys
        if extra & _MACRO_KEYS:
            return None, f"item contains macro fields: {sorted(extra & _MACRO_KEYS)}"
        if extra:
            return None, f"item has unexpected fields: {sorted(extra)}"
        if missing:
            return None, f"item missing required fields: {sorted(missing)}"

        item_id = item["id"]
        if item_id not in available:
            return None, f"unknown ingredient id: {item_id!r}"

        grams = item["grams"]
        if not isinstance(grams, (int, float)) or isinstance(grams, bool):
            return None, f"grams is not a number for id {item_id!r}"

        validated.append({"id": item_id, "grams": grams})

    return validated, None
