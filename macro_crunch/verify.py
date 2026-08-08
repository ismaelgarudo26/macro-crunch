from dataclasses import dataclass

from .llm import propose
from .macros import compute_macros, fit_details


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


_TIER_FRAMING = {
    2: (
        "Your previous meal missed the targets below. Please adjust the ingredient amounts "
        "to correct these misses, keeping the same general meal."
    ),
    3: (
        "Two attempts have missed. Disregard the previous meals and build a new one from "
        "any combination of available ingredients. Prioritize hitting the macro targets "
        "even if the meal is unconventional."
    ),
}


def select_tier(attempt):
    """Return the fixed framing text to use when re-prompting after a failed attempt.

    Input:
        attempt: the retry attempt number (2 for the first retry, 3 for the second).

    Output:
        str - the framing text for that attempt: "revise" framing (adjust amounts, same
        meal) for attempt 2, "rebuild" framing (start over, any ingredients) for attempt 3.

    Any other attempt number (including 1, 0, or 4+) raises ValueError - there is no framing
    for a first attempt (nothing to revise yet) or beyond the second retry.
    """
    try:
        return _TIER_FRAMING[attempt]
    except KeyError:
        raise ValueError(f"no framing for attempt {attempt!r}") from None


@dataclass
class AttemptRecord:
    feedback: str | None
    proposal: object


@dataclass
class LoopResult:
    status: str
    attempts: list[AttemptRecord]
    attempts_used: int
    meal: object = None
    details: dict | None = None
    computed: dict | None = None


@dataclass
class _Attempt:
    proposal: object
    computed: dict
    details: dict


MAX_ATTEMPTS = 3


def _miss_score(details):
    score = 0.0
    for info in details.values():
        pct = info["pct"]
        score += 1.0 if pct is None else abs(pct)
    return score


def run_loop(available, remaining, propose_fn=propose):
    """Not yet implemented."""
    if remaining["cal"] <= 0:
        return LoopResult(
            status="impossible",
            attempts=[],
            attempts_used=0,
            meal=None,
            details=None,
            computed=None,
        )

    attempts = []
    misses = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt == 1:
            feedback = None
        else:
            feedback = select_tier(attempt) + "\n" + build_message(misses[-1].details)

        meal = propose_fn(available, remaining, feedback=feedback)
        computed = compute_macros(meal)
        details = fit_details(computed, remaining)
        attempts.append(AttemptRecord(feedback=feedback, proposal=meal))

        is_fit = all(m["ok"] for m in details.values())
        if is_fit:
            return LoopResult(
                status="fit",
                attempts=attempts,
                attempts_used=attempt,
                meal=meal,
                details=details,
                computed=computed,
            )

        misses.append(_Attempt(proposal=meal, computed=computed, details=details))

    best = misses[0]
    best_score = _miss_score(best.details)
    for miss in misses[1:]:
        score = _miss_score(miss.details)
        if score < best_score:
            best = miss
            best_score = score

    return LoopResult(
        status="best_effort",
        attempts=attempts,
        attempts_used=MAX_ATTEMPTS,
        meal=best.proposal,
        details=best.details,
        computed=best.computed,
    )
