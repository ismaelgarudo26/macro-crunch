from macro_crunch.verify import build_message


def test_message_names_failing_macro_with_direction():
    details = {
        "cal": {"delta": 0, "pct": 0.0, "ok": True},
        "protein": {"delta": 0, "pct": 0.0, "ok": True},
        "carbs": {"delta": 13.2, "pct": 0.22, "ok": False},
        "fat": {"delta": 0, "pct": 0.0, "ok": True},
    }
    msg = build_message(details)
    assert "carbs" in msg
    assert "22" in msg
    assert "over" in msg


def test_message_lists_only_failing_macros():
    details = {
        "cal": {"delta": 0, "pct": 0.0, "ok": True},
        "protein": {"delta": -8.0, "pct": -0.18, "ok": False},
        "carbs": {"delta": 13.2, "pct": 0.22, "ok": False},
        "fat": {"delta": 0, "pct": 0.0, "ok": True},
    }
    msg = build_message(details)
    assert "protein" in msg
    assert "carbs" in msg
    assert "over" in msg
    assert "under" in msg
    assert "cal" not in msg
    assert "fat" not in msg


def test_message_shows_delta_when_pct_is_none():
    details = {
        "cal": {"delta": 0, "pct": 0.0, "ok": True},
        "protein": {"delta": 0, "pct": 0.0, "ok": True},
        "carbs": {"delta": 0, "pct": 0.0, "ok": True},
        "fat": {"delta": 7.3, "pct": None, "ok": False},
    }
    msg = build_message(details)
    assert "fat" in msg
    assert "7.3" in msg


def test_message_blank_when_all_macros_pass():
    details = {
        "cal": {"delta": 6.0, "pct": 0.01, "ok": True},
        "protein": {"delta": -2.0, "pct": -0.05, "ok": True},
        "carbs": {"delta": 2.0, "pct": 0.10, "ok": True},
        "fat": {"delta": 0, "pct": 0.0, "ok": True},
    }
    msg = build_message(details)
    assert msg == ""


def test_message_shows_all_four_macros_when_all_fail():
    details = {
        "cal": {"delta": 12.0, "pct": 0.06, "ok": False},
        "protein": {"delta": -8.0, "pct": -0.20, "ok": False},
        "carbs": {"delta": -9.0, "pct": -0.30, "ok": False},
        "fat": {"delta": 3.3, "pct": 0.22, "ok": False},
    }
    msg = build_message(details)
    assert "cal" in msg
    assert "protein" in msg
    assert "carbs" in msg
    assert "fat" in msg
    assert "over" in msg
    assert "under" in msg
