from decimal import Decimal, ROUND_HALF_UP


def _round1(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _round2(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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
            passes: bool, True only if every macro's `fit_details` entry is `ok`.
            deltas: dict {"cal", "protein", "carbs", "fat"} - raw computed - remaining per
                macro (always all four keys, regardless of pass/fail or which branch ran).

    A thin wrapper around `fit_details` - see that function's docstring for the tolerance
    rules and zero/negative-remaining behavior, which live there and only there.
    """
    details = fit_details(computed, remaining)
    passes = all(detail["ok"] for detail in details.values())
    deltas = {macro: detail["delta"] for macro, detail in details.items()}
    return passes, deltas


def _macro_detail(delta, computed_value, remaining_value, ok_predicate, zero_or_negative_ok):
    if remaining_value <= 0:
        return {"delta": delta, "pct": None, "ok": zero_or_negative_ok(computed_value, remaining_value)}
    raw_pct = delta / remaining_value
    return {"delta": delta, "pct": _round2(raw_pct), "ok": ok_predicate(raw_pct)}


def _passes_only_if_both_zero(computed_value, remaining_value):
    return remaining_value == 0 and computed_value == 0


def _always_ok(_computed_value, _remaining_value):
    return True


def fit_details(computed, remaining):
    """Per-macro breakdown of how a meal's computed macros compare to the remaining budget.

    Inputs:
        computed: dict {"cal", "protein", "carbs", "fat"} - macros for the meal being checked.
        remaining: dict {"cal", "protein", "carbs", "fat"} - macros still budgeted for the day
            before this meal.

    Output:
        dict with one entry per macro, each {"delta", "pct", "ok"}:
            delta: raw computed - remaining.
            pct: delta / remaining rounded to 2 decimals, or None when remaining <= 0 (percent
                diff is undefined there, so it is never computed).
            ok: whether this macro alone satisfies its tolerance.

    Tolerances (percent diff = (computed - remaining) / remaining), all inclusive:
        - Calories: between 15% under and 5% over (-0.15 <= diff <= 0.05).
        - Protein: no more than 10% under; any amount over is fine (diff >= -0.10).
        - Carbs: within 20% either direction (|diff| <= 0.20).
        - Fat: within 20% either direction (|diff| <= 0.20).

    Zero/negative remaining (checked before any percentage division, to avoid dividing by zero):
        - remaining == 0: that macro is ok only if computed is also 0, except protein, which
          still follows "over is always fine" and is ok regardless of computed.
        - remaining < 0: calories/carbs/fat are not ok, unconditionally (already over budget);
          protein is still ok regardless of computed, consistent with "over is always fine".
    """
    deltas = {key: computed[key] - remaining[key] for key in computed}

    return {
        "cal": _macro_detail(
            deltas["cal"], computed["cal"], remaining["cal"],
            ok_predicate=lambda pct: -0.15 <= pct <= 0.05,
            zero_or_negative_ok=_passes_only_if_both_zero,
        ),
        "protein": _macro_detail(
            deltas["protein"], computed["protein"], remaining["protein"],
            ok_predicate=lambda pct: pct >= -0.10,
            zero_or_negative_ok=_always_ok,
        ),
        "carbs": _macro_detail(
            deltas["carbs"], computed["carbs"], remaining["carbs"],
            ok_predicate=lambda pct: abs(pct) <= 0.20,
            zero_or_negative_ok=_passes_only_if_both_zero,
        ),
        "fat": _macro_detail(
            deltas["fat"], computed["fat"], remaining["fat"],
            ok_predicate=lambda pct: abs(pct) <= 0.20,
            zero_or_negative_ok=_passes_only_if_both_zero,
        ),
    }
