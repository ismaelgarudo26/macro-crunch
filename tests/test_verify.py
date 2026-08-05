import pytest

from macro_crunch.verify import build_message, select_tier


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


def test_select_tier_2_mentions_adjust():
    assert "adjust" in select_tier(2)


def test_select_tier_3_mentions_any_combination():
    assert "any combination" in select_tier(3)


def test_select_tier_2_and_3_differ():
    assert select_tier(2) != select_tier(3)


def test_select_tier_invalid_raises_value_error():
    with pytest.raises(ValueError):
        select_tier(1)
    with pytest.raises(ValueError):
        select_tier(4)


"""
tests/test_verify.py — verify loop contract (Checkpoint 2)

These pin the loop's ORCHESTRATION, not the macro math (that's test_macros.py).
So compute_macros and fit_details are faked per attempt; build_message and
select_tier stay REAL, so the escalation strings are pinned for real.

Contract the loop must honor for these to hold:
  - Lives in macro_crunch/verify.py as run_loop(available, remaining, propose_fn=propose).
  - verify.py imports collaborators as NAMES so they can be patched here:
        from .macros import compute_macros, fit_details
        from .llm import propose          # default only; tests inject propose_fn
  - Pre-flight: remaining["cal"] <= 0 -> status "impossible", 0 proposals,
    empty trail. Nothing else runs. (Per-macro maxed cases are NOT rejected here;
    they ride the None-pct path inside the loop.)
  - Per attempt: propose_fn(available, remaining, feedback) -> proposal,
    then compute_macros(proposal) ONCE, then fit_details(computed, remaining) ONCE.
  - Fit decision comes from the details it already has:
        is_fit = all(m["ok"] for m in details.values())
    The loop does NOT call check_fit (that stays for external callers).
  - Feedback for attempt N>=2 = select_tier(N) + "\n" + build_message(details_{N-1}).
    Attempt 1 gets feedback=None; select_tier is never called for attempt 1.
  - Returns LoopResult; each round recorded as AttemptRecord carrying the INBOUND
    feedback that produced that proposal.
  - Exhaustion -> status "best_effort", return lowest-miss attempt
    (sum |pct| over ALL macros, +1.0 flat per None-pct macro, earliest wins ties).
    Never raises.

Assumed macro keys: cal, protein, carbs, fat. If yours differ, fix det().
"""

import pytest

from macro_crunch import verify
from macro_crunch.verify import run_loop, LoopResult, AttemptRecord


AVAILABLE = [{"id": "chicken_breast_cooked"}, {"id": "white_rice_cooked"}]
REMAINING = {"cal": 500, "protein": 40, "carbs": 50, "fat": 15}
IMPOSSIBLE_REMAINING = {"cal": 0, "protein": 40, "carbs": 50, "fat": 15}


# --- scripting helpers ------------------------------------------------------

def macro(delta=0.0, pct=0.0, ok=False):
    return {"delta": delta, "pct": pct, "ok": ok}

def det(cal, protein, carbs, fat):
    """One fit_details result: macro name -> {delta, pct, ok}."""
    return {"cal": cal, "protein": protein, "carbs": carbs, "fat": fat}

def all_ok():
    return det(macro(ok=True), macro(ok=True), macro(ok=True), macro(ok=True))


class Step:
    """One scripted attempt: what propose returns, and what compute/fit produce."""
    def __init__(self, proposal, details, computed=None):
        self.proposal = proposal
        self.details = details
        self.computed = computed if computed is not None else {"tag": id(proposal)}


class Recorder:
    """Fake propose_fn: returns scripted proposals in order, records feedback args."""
    def __init__(self, steps):
        self.steps = steps
        self.calls = []  # inbound feedback per call, in order

    def __call__(self, available, remaining, feedback=None):
        self.calls.append(feedback)
        return self.steps[len(self.calls) - 1].proposal

    @property
    def count(self):
        return len(self.calls)


@pytest.fixture
def install(monkeypatch):
    """Wire scripted steps into the loop's collaborators. Returns the recorder."""
    def _install(steps):
        computeds = iter([s.computed for s in steps])
        detailses = iter([s.details for s in steps])
        monkeypatch.setattr(verify, "compute_macros",
                            lambda proposal, *a, **k: next(computeds), raising=False)
        monkeypatch.setattr(verify, "fit_details",
                            lambda computed, remaining, *a, **k: next(detailses), raising=False)
        return Recorder(steps)
    return _install


def expected_feedback(attempt, prev_details):
    """Mirror of the loop's feedback assembly. Change the loop's join, change this."""
    return verify.select_tier(attempt) + "\n" + verify.build_message(prev_details)


# --- 1. pre-flight ----------------------------------------------------------

def test_unsatisfiable_input_rejected_before_any_propose(install):
    recorder = install([Step("unused", all_ok())])
    result = run_loop(AVAILABLE, IMPOSSIBLE_REMAINING, propose_fn=recorder)

    assert recorder.count == 0                 # propose never called
    assert result.status == "impossible"
    assert result.attempts == []
    assert result.attempts_used == 0
    assert result.meal is None


# --- 2. fit on attempt 1 ----------------------------------------------------

def test_fit_on_first_attempt(install):
    step = Step([{"id": "chicken_breast_cooked", "grams": 150}], all_ok())
    recorder = install([step])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert recorder.count == 1
    assert recorder.calls == [None]            # first shot is unprimed
    assert result.status == "fit"
    assert result.attempts_used == 1
    assert result.meal is step.proposal
    assert result.details is step.details
    assert result.computed is step.computed
    assert len(result.attempts) == 1
    assert result.attempts[0].feedback is None
    assert result.attempts[0].proposal is step.proposal


# --- 3. fit after tier-2 escalation -----------------------------------------

def test_fit_after_tier_two(install):
    miss = det(macro(ok=True), macro(delta=-6.0, pct=-0.30, ok=False),
               macro(ok=True), macro(ok=True))            # protein short -> retry
    step1 = Step([{"id": "white_rice_cooked", "grams": 100}], miss)
    step2 = Step([{"id": "chicken_breast_cooked", "grams": 180}], all_ok())
    recorder = install([step1, step2])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert recorder.count == 2
    assert recorder.calls[0] is None
    fb2 = recorder.calls[1]
    assert "adjust" in fb2                                 # tier-2 framing
    assert verify.build_message(step1.details) in fb2      # specifics from attempt 1
    assert result.status == "fit"
    assert result.attempts_used == 2
    assert result.meal is step2.proposal
    assert len(result.attempts) == 2
    assert result.attempts[1].feedback == fb2              # trail carries inbound feedback


# --- 4. fit after tier-3 escalation -----------------------------------------

def test_fit_after_tier_three(install):
    miss1 = det(macro(ok=True), macro(delta=-6.0, pct=-0.30, ok=False),
                macro(ok=True), macro(ok=True))
    miss2 = det(macro(delta=40.0, pct=0.08, ok=False), macro(ok=True),
                macro(ok=True), macro(ok=True))
    step1 = Step([{"id": "white_rice_cooked", "grams": 90}], miss1)
    step2 = Step([{"id": "white_rice_cooked", "grams": 140}], miss2)
    step3 = Step([{"id": "chicken_breast_cooked", "grams": 200}], all_ok())
    recorder = install([step1, step2, step3])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert recorder.count == 3
    assert "adjust" in recorder.calls[1]                   # tier-2 came first
    fb3 = recorder.calls[2]
    assert "any combination" in fb3                        # tier-3 framing
    assert verify.build_message(step2.details) in fb3       # specifics from attempt 2
    assert result.status == "fit"
    assert result.attempts_used == 3
    assert result.meal is step3.proposal
    assert len(result.attempts) == 3


# --- 5. exhaustion returns best_effort, never raises ------------------------

def test_exhaustion_returns_best_effort_not_exception(install):
    s1 = Step("p1", det(macro(pct=0.30, ok=False), macro(ok=True), macro(ok=True), macro(ok=True)))
    s2 = Step("p2", det(macro(pct=0.10, ok=False), macro(ok=True), macro(ok=True), macro(ok=True)))
    s3 = Step("p3", det(macro(pct=0.20, ok=False), macro(ok=True), macro(ok=True), macro(ok=True)))
    recorder = install([s1, s2, s3])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert recorder.count == 3
    assert result.status == "best_effort"
    assert result.attempts_used == 3
    assert len(result.attempts) == 3
    assert result.meal is not None
    # feedback trail preserved across all three rounds under exhaustion:
    assert result.attempts[0].feedback is None
    assert result.attempts[1].feedback == recorder.calls[1]
    assert result.attempts[2].feedback == recorder.calls[2]


# --- 6. feedback arg pinned exactly on each retry ---------------------------

def test_feedback_arg_pinned_exactly_on_each_retry(install):
    miss1 = det(macro(ok=True), macro(delta=-6.0, pct=-0.30, ok=False), macro(ok=True), macro(ok=True))
    miss2 = det(macro(delta=40.0, pct=0.08, ok=False), macro(ok=True), macro(ok=True), macro(ok=True))
    step1 = Step("p1", miss1)
    step2 = Step("p2", miss2)
    step3 = Step("p3", all_ok())
    recorder = install([step1, step2, step3])

    run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert recorder.calls[0] is None
    assert recorder.calls[1] == expected_feedback(2, step1.details)
    assert recorder.calls[2] == expected_feedback(3, step2.details)


# --- 7. best_effort picks minimum miss, not last ----------------------------

def test_best_effort_picks_minimum_miss_not_last(install):
    # sum |pct| over 4 macros:  A=2.0,  B=0.4,  C=1.2  -> B wins (and abs matters)
    A = Step("A", det(macro(pct=0.5, ok=False), macro(pct=0.5, ok=False),
                      macro(pct=0.5, ok=False), macro(pct=0.5, ok=False)))
    B = Step("B", det(macro(pct=-0.1, ok=False), macro(pct=0.1, ok=False),
                      macro(pct=-0.1, ok=False), macro(pct=0.1, ok=False)))
    C = Step("C", det(macro(pct=0.3, ok=False), macro(pct=0.3, ok=False),
                      macro(pct=0.3, ok=False), macro(pct=0.3, ok=False)))
    recorder = install([A, B, C])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert result.status == "best_effort"
    assert result.meal == "B"      # middle attempt, lowest miss
    assert result.meal != "C"      # guards accidental attempts[-1]
    assert result.meal != "A"      # guards accidental attempts[0]


# --- 8. None-pct macro incurs the flat 1.0 penalty --------------------------

def test_none_pct_incurs_flat_penalty(install):
    # A: |0.1|*3 + 1.0(None) = 1.3 ; B: 0.5*4 = 2.0 ; C: 0.2*4 = 0.8
    # Without the +1.0, A scores 0.3 and wrongly wins. C winning proves it applied.
    A = Step("A", det(macro(pct=0.1, ok=False), macro(pct=0.1, ok=False),
                      macro(pct=0.1, ok=False), macro(delta=5.0, pct=None, ok=False)))
    B = Step("B", det(macro(pct=0.5, ok=False), macro(pct=0.5, ok=False),
                      macro(pct=0.5, ok=False), macro(pct=0.5, ok=False)))
    C = Step("C", det(macro(pct=0.2, ok=False), macro(pct=0.2, ok=False),
                      macro(pct=0.2, ok=False), macro(pct=0.2, ok=False)))
    recorder = install([A, B, C])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert result.status == "best_effort"
    assert result.meal == "C"      # 0.8 < 1.3 < 2.0


# --- 9. tie-break: earliest of tied minima (optional, but pins a locked rule)-

def test_ties_resolve_to_earliest_attempt(install):
    # A and C both total 0.8; A is earlier, so A wins.
    A = Step("A", det(macro(pct=0.2, ok=False), macro(pct=0.2, ok=False),
                      macro(pct=0.2, ok=False), macro(pct=0.2, ok=False)))
    B = Step("B", det(macro(pct=0.5, ok=False), macro(pct=0.5, ok=False),
                      macro(pct=0.5, ok=False), macro(pct=0.5, ok=False)))
    C = Step("C", det(macro(pct=0.2, ok=False), macro(pct=0.2, ok=False),
                      macro(pct=0.2, ok=False), macro(pct=0.2, ok=False)))
    recorder = install([A, B, C])

    result = run_loop(AVAILABLE, REMAINING, propose_fn=recorder)

    assert result.meal == "A"      # earliest of the tied minima
