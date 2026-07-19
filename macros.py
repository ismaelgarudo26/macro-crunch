from decimal import Decimal, ROUND_HALF_UP


def _round1(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def compute_macros(items, table):
    """Sum the macros for a list of ingredient amounts.

    Inputs:
        items: list of {"id": str, "grams": number}.
        table: dict mapping ingredient id -> {"cal", "protein", "carbs", "fat"},
            each value given per 100g of that ingredient.

    Output:
        dict {"cal", "protein", "carbs", "fat"} - the totals across all items.

    Rules:
        - Each item's macros are scaled by grams / 100 before being added to the running total.
        - An id not present in `table` raises KeyError (unknown ingredients are never skipped).
        - Totals are rounded to 1 decimal place once, after all items are summed - never
          rounded per item, so small per-item roundoffs don't accumulate incorrectly.
    """
    totals = {"cal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for item in items:
        macros = table[item["id"]]
        factor = item["grams"] / 100
        for key in totals:
            totals[key] += macros[key] * factor
    return {key: _round1(value) for key, value in totals.items()}


def check_fit(computed, remaining):
    """Check whether a meal's computed macros fit within the remaining daily budget.

    Inputs:
        computed: dict {"cal", "protein", "carbs", "fat"} - macros for the meal being checked.
        remaining: dict {"cal", "protein", "carbs", "fat"} - macros still budgeted for the day
            before this meal.

    Output:
        (passes, deltas) tuple:
            passes: bool, True only if every macro satisfies its tolerance below.
            deltas: dict {"cal", "protein", "carbs", "fat"} - raw computed - remaining per
                macro (always all four keys, regardless of pass/fail or which branch ran).

    Tolerances (percent diff = (computed - remaining) / remaining), all inclusive:
        - Calories: between 15% under and 5% over (-0.15 <= diff <= 0.05).
        - Protein: no more than 10% under; any amount over is fine (diff >= -0.10).
        - Carbs: within 20% either direction (|diff| <= 0.20).
        - Fat: within 20% either direction (|diff| <= 0.20).

    Zero/negative remaining (checked before any percentage division, to avoid dividing by zero):
        - remaining == 0: that macro passes only if computed is also 0, except protein, which
          still follows "over is always fine" and passes regardless of computed.
        - remaining < 0: calories/carbs/fat fail unconditionally (already over budget); protein
          still passes regardless of computed, consistent with "over is always fine".
    """
    deltas = {key: computed[key] - remaining[key] for key in computed}

    def pct(key):
        return deltas[key] / remaining[key]

    if remaining["cal"] <= 0:
        cal_ok = remaining["cal"] == 0 and computed["cal"] == 0
    else:
        cal_ok = -0.15 <= pct("cal") <= 0.05

    if remaining["protein"] <= 0:
        protein_ok = True  # over is always fine, including when remaining <= 0
    else:
        protein_ok = pct("protein") >= -0.10

    if remaining["carbs"] <= 0:
        carbs_ok = remaining["carbs"] == 0 and computed["carbs"] == 0
    else:
        carbs_ok = abs(pct("carbs")) <= 0.20

    if remaining["fat"] <= 0:
        fat_ok = remaining["fat"] == 0 and computed["fat"] == 0
    else:
        fat_ok = abs(pct("fat")) <= 0.20

    passes = cal_ok and protein_ok and carbs_ok and fat_ok
    return passes, deltas
