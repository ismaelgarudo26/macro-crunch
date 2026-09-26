import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-4o-mini"

_INGREDIENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "ingredients.json"
KNOWN_IDS = set(json.loads(_INGREDIENTS_PATH.read_text()).keys())


INGREDIENT_PROMPT = (
    "List the food items you see in this image that match one of these ingredient ids: "
    + ", ".join(sorted(KNOWN_IDS)) + ". "
    "Use each id exactly as written above, and skip any food that doesn't match one. "
    "Respond in JSON as an object with an 'items' list; each row has an 'id' (one of the "
    "ids above) and an 'approx' (a rough amount on hand, as free text)."
)


REMAINING_PROMPT = (
    "Read the remaining macro values from this MyFitnessPal screenshot. Return them as "
    "a JSON object with keys 'cal', 'protein', 'carbs', and 'fat'."
)

_REMAINING_KEYS = ("cal", "protein", "carbs", "fat")


def call_vision(image, prompt, mime_type="image/jpeg"):
    """Send one image + prompt to the vision model and return its parsed JSON reply.

    Input:
        image: raw image bytes (e.g. from a browser upload), sent inline as a base64 data URL.
        prompt: instruction text, sent as the text part of the same user message.
        mime_type: the image's media type, used in the data URL.

    Output:
        the model's reply parsed from JSON. If it's an object with an "items" key, the
        list under "items" is returned (JSON mode can only return objects, so list-shaped
        answers come wrapped); otherwise the parsed object itself.

    Fails loud: one request, no retry. Malformed JSON raises json.JSONDecodeError - a
    re-sent image usually gets the same misread, so the caller (e.g. asking the user for
    a clearer photo) decides what to do. Transient network errors are already retried by
    the OpenAI SDK itself.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content)
    if isinstance(parsed, dict) and "items" in parsed:
        return parsed["items"]
    return parsed


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
