# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

macro-crunch is a small, pure-Python macro-nutrient calculator. There is no application entry point yet. Code,
tests, and data live in separate top-level folders:

- [data/ingredients.json](data/ingredients.json) — 31 common fridge/pantry ingredients keyed by snake_case id,
  each with `cal`, `protein`, `carbs`, `fat` per 100g (numbers only, no units). Kept outside the package since
  it's loaded by path at runtime, not imported as Python, and may grow or be replaced independently of the code.
- [macro_crunch/macros.py](macro_crunch/macros.py) — pure logic, no side effects: `compute_macros(items, table)`,
  `fit_details(computed, remaining)`, and `check_fit(computed, remaining)` (a thin wrapper around
  `fit_details`). Read the docstrings on these functions before modifying them — they are the source of truth
  for the rounding rule, the KeyError-on-unknown-id contract, and the per-macro tolerance rules (including the
  zero/negative-remaining edge cases), which live only in `fit_details`.
- [macro_crunch/llm.py](macro_crunch/llm.py) — `propose(available_ingredients, remaining)`, calls the OpenAI API
  and returns a validated list of `{id, grams}` objects. See the "llm.py — propose contract" section below.
- [tests/test_macros.py](tests/test_macros.py) — pytest suite covering `compute_macros`, `check_fit`, and
  `fit_details`, including boundary-value tests for every tolerance threshold and the zero/negative-remaining
  branches.
- `.env.example` — contains only `OPENAI_API_KEY=`; `.env` (gitignored) holds the real key that `llm.py` loads
  via `python-dotenv`.
- `conftest.py` at the repo root is intentionally empty — its only job is to make pytest resolve `macro_crunch`
  as an importable package regardless of how pytest is invoked.
- `scratch.py` at the repo root is a throwaway script for manually exercising `propose`/`compute_macros`/
  `check_fit` end to end — not a test, safe to delete/overwrite at any time.

`macro_crunch/macros.py` must stay free of `streamlit`/`openai` imports and side effects (printing, I/O) — it is
meant to be pure logic that a future UI/API layer imports — this keeps the test suite deterministic (no API key,
no network) and lets the UI and model layers be swapped without touching logic (separation of concerns).

## Commands

There is no `requirements.txt` or `pyproject.toml` — pytest was installed directly and isn't pinned anywhere.

```bash
# Install test dependency (only needed once per environment)
python -m pip install pytest

# Run the full test suite
python -m pytest -v

# Run a single test
python -m pytest -v tests/test_macros.py::test_check_fit_15_cal_remaining_zero_computed_zero_passes

# Run only compute_macros or only check_fit tests
python -m pytest -v -k compute_macros
python -m pytest -v -k check_fit
```

On this Windows dev machine, a bare `python`/`py` may not resolve (Microsoft Store alias stub). If that happens,
call the interpreter directly, e.g.
`"C:\Users\Ismael\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -v`.

## Architecture notes

- `compute_macros` and `check_fit` are independent and composable: `compute_macros(items, table)` produces a
  `{cal, protein, carbs, fat}` dict, which is then passed as the `computed` argument to
  `check_fit(computed, remaining)` alongside a caller-supplied `remaining` budget dict of the same shape.
- Rounding happens exactly once, in `compute_macros`, after all items are summed — never per-item and never
  inside `check_fit`. `_round1` uses `Decimal`/`ROUND_HALF_UP` on `str(value)` rather than plain `round()`,
  because plain `round()` on a binary float can round a true `x.x5` sum (e.g. 23.45) down instead of up.
- `check_fit` checks `remaining[macro] <= 0` per macro *before* computing any percent diff, to avoid division by
  zero. The zero/negative-remaining behavior differs by macro: protein always passes when remaining ≤ 0 (over is
  always fine, same as its normal rule); calories/carbs/fat pass only when remaining is exactly 0 and computed is
  also 0, and fail unconditionally when remaining is negative.
- `deltas` in `check_fit`'s return value is always the raw `computed - remaining` per macro (all four keys),
  regardless of which branch determined pass/fail — nothing in the tolerance logic ever mutates or filters it.
- Test names encode which numbered test case they correspond to (e.g. `test_check_fit_7_...`) from the boundary
  sweep across cal/protein/carbs/fat — when adding a new tolerance rule, follow the same one-macro-at-a-time
  isolation pattern (hold the other three macros at a trivially-passing baseline) so a failure is attributable to
  a single rule.

## macro_crunch/llm.py — propose contract

The model proposes meals; it never does arithmetic. `propose(available_ingredients, remaining)` returns ONLY a
JSON list of `{id, grams}` objects.

- IDs must come from the caller-supplied `available_ingredients` list (already filtered to the ingredients
  table). The model may not invent IDs.
- The response contains NO macro numbers — grams only. All macro computation is done by `compute_macros`.
- The response is validated on return: malformed JSON, unknown IDs, or any macro fields are rejected and
  re-requested.

## Working style

- I drive incrementally. If I ask for one function, write only that function — no extra files or scaffolding, no
  building ahead.
- Test-first via the `tdd` skill ([.claude/skills/tdd/SKILL.md](.claude/skills/tdd/SKILL.md)): once a plan is
  approved, a subagent drafts the tests it calls for and describes them to me in plain English; I approve the
  test list before any test code is written, and nothing outside a test file gets written before that. This
  applies to all new logic in the project now, including UI/glue — not just load-bearing modules like the verify
  loop or eval harness.

## Git

- Default branch is `main`.
- `.gitignore` covers `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `.DS_Store`.

## Learning goals

This project doubles as how I'm learning to build and reason about AI
products (I'm moving toward AI PM work). That means:

- When you implement something non-trivial, explain the *why* — the
  design tradeoff, not just the code. One or two sentences, not a lecture.
- Use precise names for concepts when they come up (grounding, adapter vs.
  domain logic, fakes/mocks, context window) so I build the vocabulary.
- When there's a real design fork, surface it and let me decide rather than
  picking silently — the decision is the thing I'm here to learn.
- Keep explanations brief. Teach through the work, not around it.