import pytest

from macros import check_fit, compute_macros

TABLE = {
    "chicken_breast": {"cal": 165, "protein": 31, "carbs": 0, "fat": 3.6},
    "white_rice_cooked": {"cal": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
    "broccoli": {"cal": 34, "protein": 2.8, "carbs": 7, "fat": 0.4},
}

MEAL_ITEMS = [
    {"id": "chicken_breast", "grams": 50},
    {"id": "white_rice_cooked", "grams": 75},
    {"id": "broccoli", "grams": 35},
]

MEAL_COMPUTED = {"cal": 191.9, "protein": 18.5, "carbs": 23.5, "fat": 2.2}

BASE_REMAINING = {"cal": 100, "protein": 10, "carbs": 20, "fat": 2}
BASE_COMPUTED = {"cal": 100, "protein": 10, "carbs": 20, "fat": 2}


def _override(base, macro, value):
    d = dict(base)
    d[macro] = value
    return d


# --- compute_macros ---

def test_compute_macros_basic_meal():
    assert compute_macros(MEAL_ITEMS, TABLE) == MEAL_COMPUTED


def test_compute_macros_empty_items_returns_zeros():
    assert compute_macros([], TABLE) == {"cal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}


def test_compute_macros_unknown_id_raises_keyerror():
    with pytest.raises(KeyError):
        compute_macros([{"id": "not_a_real_ingredient", "grams": 50}], TABLE)


def test_compute_macros_zero_grams_contributes_nothing():
    result = compute_macros([{"id": "chicken_breast", "grams": 0}], TABLE)
    assert result == {"cal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}


def test_compute_macros_31_duplicate_id_accumulates():
    items = [
        {"id": "chicken_breast", "grams": 50},
        {"id": "chicken_breast", "grams": 50},
    ]
    assert compute_macros(items, TABLE) == {"cal": 165.0, "protein": 31.0, "carbs": 0.0, "fat": 3.6}


def test_compute_macros_32_rounds_total_once_not_per_item():
    round_table = {"carb_trace": {"cal": 0, "protein": 0, "carbs": 8, "fat": 0}}
    items = [
        {"id": "carb_trace", "grams": 0.5},
        {"id": "carb_trace", "grams": 0.5},
    ]
    # each item contributes 0.04 carbs alone (rounds to 0.0), true sum 0.08 rounds to 0.1
    assert compute_macros(items, round_table) == {"cal": 0.0, "protein": 0.0, "carbs": 0.1, "fat": 0.0}


# --- check_fit: core tolerance behavior (tests 1-6) ---

def test_check_fit_1_within_all_limits():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 192, "protein": 19, "carbs": 24, "fat": 2})
    assert passes is True


def test_check_fit_2_cal_over_5_percent_fails():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 170, "protein": 19, "carbs": 24, "fat": 2})
    assert passes is False


def test_check_fit_3_protein_under_fails():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 192, "protein": 21, "carbs": 24, "fat": 2})
    assert passes is False


def test_check_fit_4_cal_exactly_5_percent_over_boundary_passes():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 182.8, "protein": 19, "carbs": 24, "fat": 2})
    assert passes is True


def test_check_fit_5_cal_way_over_and_protein_way_under_fails():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 114, "protein": 30, "carbs": 24, "fat": 2})
    assert passes is False


def test_check_fit_6_cal_under_15_percent_floor_fails():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 240, "protein": 19, "carbs": 24, "fat": 2})
    assert passes is False


# --- check_fit: boundary cases per macro (tests 7-14) ---

def test_check_fit_7_carbs_exactly_20_percent_over_boundary_passes():
    passes, _ = check_fit(
        {"cal": 100, "protein": 10, "carbs": 24, "fat": 2},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is True


def test_check_fit_8_carbs_21_percent_over_fails():
    passes, _ = check_fit(
        {"cal": 100, "protein": 10, "carbs": 24.2, "fat": 2},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is False


def test_check_fit_9_fat_exactly_20_percent_under_boundary_passes():
    passes, _ = check_fit(
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 1.6},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is True


def test_check_fit_10_protein_exactly_10_percent_under_boundary_passes():
    passes, _ = check_fit(
        {"cal": 100, "protein": 9, "carbs": 20, "fat": 2},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is True


def test_check_fit_11_protein_11_percent_under_fails():
    passes, _ = check_fit(
        {"cal": 100, "protein": 8.9, "carbs": 20, "fat": 2},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is False


def test_check_fit_12_cal_exactly_15_percent_under_boundary_passes():
    passes, _ = check_fit(
        {"cal": 85, "protein": 10, "carbs": 20, "fat": 2},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is True


def test_check_fit_13_cal_16_percent_under_fails():
    passes, _ = check_fit(
        {"cal": 84, "protein": 10, "carbs": 20, "fat": 2},
        {"cal": 100, "protein": 10, "carbs": 20, "fat": 2},
    )
    assert passes is False


def test_check_fit_14_cal_carbs_fat_pass_but_protein_fails_whole_meal_fails():
    passes, _ = check_fit(MEAL_COMPUTED, {"cal": 200, "protein": 25, "carbs": 24, "fat": 2})
    assert passes is False


# --- check_fit: zero/negative remaining rules (tests 15-30) ---

def test_check_fit_15_cal_remaining_zero_computed_zero_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "cal", 0), _override(BASE_REMAINING, "cal", 0))
    assert passes is True


def test_check_fit_16_protein_remaining_zero_computed_zero_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "protein", 0), _override(BASE_REMAINING, "protein", 0))
    assert passes is True


def test_check_fit_17_carbs_remaining_zero_computed_zero_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "carbs", 0), _override(BASE_REMAINING, "carbs", 0))
    assert passes is True


def test_check_fit_18_fat_remaining_zero_computed_zero_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "fat", 0), _override(BASE_REMAINING, "fat", 0))
    assert passes is True


def test_check_fit_19_protein_remaining_zero_computed_positive_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "protein", 5), _override(BASE_REMAINING, "protein", 0))
    assert passes is True


def test_check_fit_20_cal_remaining_zero_computed_positive_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "cal", 5), _override(BASE_REMAINING, "cal", 0))
    assert passes is False


def test_check_fit_21_carbs_remaining_zero_computed_positive_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "carbs", 5), _override(BASE_REMAINING, "carbs", 0))
    assert passes is False


def test_check_fit_22_fat_remaining_zero_computed_positive_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "fat", 5), _override(BASE_REMAINING, "fat", 0))
    assert passes is False


def test_check_fit_23_cal_remaining_negative_computed_zero_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "cal", 0), _override(BASE_REMAINING, "cal", -50))
    assert passes is False


def test_check_fit_24_cal_remaining_negative_computed_positive_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "cal", 30), _override(BASE_REMAINING, "cal", -50))
    assert passes is False


def test_check_fit_25_carbs_remaining_negative_computed_zero_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "carbs", 0), _override(BASE_REMAINING, "carbs", -10))
    assert passes is False


def test_check_fit_26_carbs_remaining_negative_computed_positive_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "carbs", 15), _override(BASE_REMAINING, "carbs", -10))
    assert passes is False


def test_check_fit_27_fat_remaining_negative_computed_zero_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "fat", 0), _override(BASE_REMAINING, "fat", -5))
    assert passes is False


def test_check_fit_28_fat_remaining_negative_computed_positive_fails():
    passes, _ = check_fit(_override(BASE_COMPUTED, "fat", 3), _override(BASE_REMAINING, "fat", -5))
    assert passes is False


def test_check_fit_29_protein_remaining_negative_computed_zero_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "protein", 0), _override(BASE_REMAINING, "protein", -5))
    assert passes is True


def test_check_fit_30_protein_remaining_negative_computed_positive_passes():
    passes, _ = check_fit(_override(BASE_COMPUTED, "protein", 8), _override(BASE_REMAINING, "protein", -5))
    assert passes is True


# --- check_fit: output contract (test 33) ---

def test_check_fit_33_deltas_has_exactly_four_keys_as_raw_differences():
    computed = {"cal": 50, "protein": 5, "carbs": 10, "fat": 1}
    remaining = {"cal": 0, "protein": -3, "carbs": 20, "fat": 2}
    passes, deltas = check_fit(computed, remaining)
    assert set(deltas.keys()) == {"cal", "protein", "carbs", "fat"}
    assert deltas == {"cal": 50, "protein": 8, "carbs": -10, "fat": -1}
