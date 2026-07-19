from decimal import Decimal, ROUND_HALF_UP


def _round1(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def compute_macros(items, table):
    totals = {"cal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for item in items:
        macros = table[item["id"]]
        factor = item["grams"] / 100
        for key in totals:
            totals[key] += macros[key] * factor
    return {key: _round1(value) for key, value in totals.items()}


def check_fit(computed, remaining):
    deltas = {key: computed[key] - remaining[key] for key in computed}

    def pct(key):
        return deltas[key] / remaining[key]

    passes = (
        -0.15 <= pct("cal") <= 0.05
        and pct("protein") >= -0.10
        and abs(pct("carbs")) <= 0.20
        and abs(pct("fat")) <= 0.20
    )
    return passes, deltas


def _check(label, remaining, expected_passes, computed):
    passes, deltas = check_fit(computed, remaining)
    status = "PASS" if passes == expected_passes else "FAIL"
    print(f"[{status}] {label}")
    print(f"    remaining = {remaining}")
    print(f"    deltas    = {deltas}")
    print(f"    passes    = {passes} (expected {expected_passes})")
    assert passes == expected_passes, f"{label}: got passes={passes}, expected {expected_passes}"


if __name__ == "__main__":
    table = {
        "chicken_breast": {"cal": 165, "protein": 31, "carbs": 0, "fat": 3.6},
        "white_rice_cooked": {"cal": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
        "broccoli": {"cal": 34, "protein": 2.8, "carbs": 7, "fat": 0.4},
    }
    items = [
        {"id": "chicken_breast", "grams": 50},
        {"id": "white_rice_cooked", "grams": 75},
        {"id": "broccoli", "grams": 35},
    ]

    print("=== compute_macros ===")
    print(f"items = {items}")
    computed = compute_macros(items, table)
    print(f"computed = {computed}")
    expected_computed = {"cal": 191.9, "protein": 18.5, "carbs": 23.5, "fat": 2.2}
    assert computed == expected_computed, f"computed mismatch: got {computed}, expected {expected_computed}"
    print("[PASS] compute_macros matches expected totals\n")

    print("=== check_fit ===")
    _check("1. within all limits", {"cal": 192, "protein": 19, "carbs": 24, "fat": 2}, True, computed)
    _check("2. cal over 5%", {"cal": 170, "protein": 19, "carbs": 24, "fat": 2}, False, computed)
    _check("3. protein under 10%", {"cal": 192, "protein": 21, "carbs": 24, "fat": 2}, False, computed)
    _check("4. cal exactly 5% over (boundary)", {"cal": 182.8, "protein": 19, "carbs": 24, "fat": 2}, True, computed)
    _check("5. cal way over, protein way under", {"cal": 114, "protein": 30, "carbs": 24, "fat": 2}, False, computed)
    _check("6. cal under 15% floor (not yet implemented)", {"cal": 240, "protein": 19, "carbs": 24, "fat": 2}, False, computed)

    print("\nall tests passed")
