def build_message(details):
    """Build a human-readable feedback string for the macros that failed their tolerance.

    Input:
        details: dict of macro -> {"delta", "pct", "ok"}, as returned by
            `macro_crunch.macros.fit_details`.

    Output:
        str listing only the failing macros (ok is False), each as
        "<macro> <magnitude> <direction>" - whole-number percent when `pct` is available
        (e.g. "carbs 22% over"), falling back to the raw delta in grams when `pct` is None
        (e.g. "fat 7.3g over"). Direction is "over" when pct/delta is positive, "under" when
        negative. Macros that passed are never mentioned.
    """
    parts = []
    for macro, info in details.items():
        if info["ok"]:
            continue

        pct = info["pct"]
        delta = info["delta"]
        direction_value = pct if pct is not None else delta
        direction = "over" if direction_value > 0 else "under"

        if pct is not None:
            magnitude = f"{abs(round(pct * 100))}%"
        else:
            magnitude = f"{abs(delta)}g"

        parts.append(f"{macro} {magnitude} {direction}")

    return ", ".join(parts)
