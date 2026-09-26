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
- [macro_crunch/llm.py](macro_crunch/llm.py) — `propose(available_ingredients, remaining, feedback=None)`,
  calls the OpenAI API and returns a validated list of `{id, grams}` objects. See the "llm.py — propose
  contract" section below.
- [macro_crunch/verify.py](macro_crunch/verify.py) — the orchestration layer: `run_loop` wires
  `propose` → `compute_macros` → `fit_details` together with retry/escalation logic. See the
  "macro_crunch/verify.py — run_loop contract" section below.
- [macro_crunch/vision.py](macro_crunch/vision.py) — `call_vision` sends one image + prompt to the OpenAI vision
  model and returns parsed JSON; `extract_ingredients` and `extract_remaining` ground that output against the
  known-ingredient whitelist / the four macro keys. See the "macro_crunch/vision.py — vision call and grounding
  contract" section below.
- [tests/test_macros.py](tests/test_macros.py) — pytest suite covering `compute_macros`, `check_fit`, and
  `fit_details`, including boundary-value tests for every tolerance threshold and the zero/negative-remaining
  branches.
- [tests/test_llm.py](tests/test_llm.py), [tests/test_verify.py](tests/test_verify.py),
  [tests/test_vision.py](tests/test_vision.py) — pytest suites for `llm.py`, `verify.py`, and `vision.py`
  respectively, mirroring the module split above.
- `.env.example` — contains only `OPENAI_API_KEY=`; `.env` (gitignored) holds the real key that `llm.py` and
  `vision.py` load via `python-dotenv`.
- [README.md](README.md) — public-facing clone-and-run setup (venv, `pip install -r requirements.txt`, `.env`),
  how to run the tests, and a short "Try it" snippet chaining `vision.extract_ingredients` → `verify.run_loop`.
- `conftest.py` at the repo root is intentionally empty — its only job is to make pytest resolve `macro_crunch`
  as an importable package regardless of how pytest is invoked.
- `requirements.txt` pins the full dependency set (openai, pydantic, python-dotenv, pytest, and their
  transitive deps) as resolved by `pip freeze` — not hand-curated. It pins `openai==3.0.0`, which uses `httpx2`
  → `truststore`, so HTTPS verification goes through the OS certificate store.

`macro_crunch/macros.py` must stay free of `streamlit`/`openai` imports and side effects (printing, I/O) — it is
meant to be pure logic that a future UI/API layer imports — this keeps the test suite deterministic (no API key,
no network) and lets the UI and model layers be swapped without touching logic (separation of concerns).

## Commands

There is no `pyproject.toml` — `requirements.txt` pins dependencies (a raw `pip freeze`, not hand-curated).

```bash
# Create and activate a venv, then install dependencies (only needed once)
python -m venv .venv
.venv\Scripts\activate        # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Run the full test suite (no API key or network needed — tests use fake OpenAI clients)
python -m pytest -v

# Run a single test
python -m pytest -v tests/test_macros.py::test_check_fit_15_cal_remaining_zero_computed_zero_passes

# Run only compute_macros or only check_fit tests
python -m pytest -v -k compute_macros
python -m pytest -v -k check_fit
```

On this Windows dev machine, use the venv interpreter, e.g. `.venv\Scripts\python.exe -m pytest -v`. The global
Python has an older `openai` whose live calls fail with `CERTIFICATE_VERIFY_FAILED`, because AVG antivirus
intercepts HTTPS; the pinned `openai`/`truststore` stack in the venv trusts the OS certificate store and works.
Don't add `verify=False`/truststore hacks to the code — fix the environment, not the code.

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

The model proposes meals; it never does arithmetic. `propose(available_ingredients, remaining, feedback=None)`
returns ONLY a JSON list of `{id, grams}` objects.

- IDs must come from the caller-supplied `available_ingredients` list (already filtered to the ingredients
  table). The model may not invent IDs.
- The response contains NO macro numbers — grams only. All macro computation is done by `compute_macros`.
- The response is validated on return: malformed JSON, unknown IDs, or any macro fields are rejected and
  re-requested.
- `feedback` is optional text describing what a previous attempt got wrong. When given, `_build_user_prompt`
  appends it to the prompt under its own labeled section, distinct from the task spec, so the model can tell
  "what to do" from "what you did wrong last time." Callers (currently only `verify.run_loop`) own composing
  that text — `propose` itself never inspects `fit_details` or knows about retries.

## macro_crunch/verify.py — run_loop contract

`run_loop(available, remaining, propose_fn=propose, table=_DEFAULT_TABLE)` orchestrates `propose` →
`compute_macros` → `fit_details`, retrying with escalating feedback up to `MAX_ATTEMPTS` (3). Read the
docstring on `run_loop` before modifying it — it is the source of truth for the attempt/feedback/scoring
contract; the summary here is a pointer, not a substitute.

- Attempt 1 always gets `feedback=None`. Attempts 2+ get `select_tier(attempt)` (fixed framing text — "revise
  the same meal" for attempt 2, "rebuild from scratch" for attempt 3) plus `build_message` of the previous
  attempt's `fit_details` (a human-readable list of only the failing macros, e.g. "carbs 22% over").
- Three terminal statuses: `"impossible"` (short-circuits before any `propose` call when
  `remaining["cal"] <= 0` — nothing to attempt), `"fit"` (some attempt passed every macro's tolerance),
  `"best_effort"` (all `MAX_ATTEMPTS` attempts missed; the lowest-`_miss_score` attempt is returned rather than
  the last one tried).
- `_miss_score` sums `abs(pct)` across macros, with a flat 1.0 penalty for a macro whose `pct` is `None` (the
  zero/negative-remaining edge cases in `fit_details` don't produce a percent) — this is a proxy for "how far
  off," used only to rank `best_effort` candidates, not a pass/fail threshold.
- Every attempt (including the ones that miss) is recorded in order as an `AttemptRecord`, carrying the
  `feedback` string that produced it — this is what makes the escalation auditable rather than a black box.

## macro_crunch/vision.py — vision call and grounding contract

`call_vision(image, prompt, mime_type="image/jpeg")` is the adapter to the live API; `extract_ingredients` and
`extract_remaining` are the grounding logic layered on top, injectable with a fake `vision_fn` for testing
without a real API call.

- `call_vision` base64-encodes the raw image bytes into a data URL and sends ONE multimodal user message (a
  `text` part with the prompt + an `image_url` part) to `MODEL` (`gpt-4o-mini`) with
  `response_format={"type": "json_object"}`. JSON mode can only return objects, so a reply shaped
  `{"items": [...]}` is unwrapped to the bare list; any other object is returned as-is.
- Fails loud: one request, no retry. Malformed JSON raises `json.JSONDecodeError` to the caller. Unlike
  `llm.propose`, retrying doesn't pay here — a vision misread is mostly deterministic for the same image, and
  every retry re-sends the image tokens; the caller (e.g. asking for a clearer photo) decides instead. Transient
  network errors are already retried by the OpenAI SDK.
- `INGREDIENT_PROMPT` embeds every id in `KNOWN_IDS`, so the model is grounded at the prompt too, not just
  filtered after. Every prompt must contain the word "json" — the API returns 400 for `json_object` mode
  otherwise; `test_prompt_mentions_json` pins this.
- Lesson: fakes can't catch real-API rules or behavior. Both of the above were found only by a live run — the
  id-less prompt made the model return row numbers as ids (all silently dropped by grounding), and the missing
  "json" word was a 400 the fake client never enforces.

- **Grounding** here means: take a model's raw, unconstrained guess and filter/coerce it against a known-valid
  set before the rest of the system ever sees it — the same shape of problem `llm.propose`'s id-whitelist
  validation solves, applied to vision output instead of text output.
- `extract_ingredients` drops any row whose `id` isn't in `KNOWN_IDS` (the same ids as `data/ingredients.json`)
  and de-duplicates by keeping the first occurrence of a repeated id — it never raises on a bad row, it just
  silently excludes it.
- `extract_remaining` is stricter: it requires all four macro keys (`cal`, `protein`, `carbs`, `fat`) and raises
  `ValueError` naming every key that's missing or not coercible to `float` if any are bad — a partial reading
  isn't usable, so this fails loudly instead of returning a partial dict. Negative values are allowed (an
  over-budget macro is a real state); `cal <= 0` is not rejected here, since that's `run_loop`'s
  `"impossible"` check, not a vision-parsing concern.
- Both functions trust `vision_fn`'s JSON/format validity and let its exceptions propagate uncaught — format
  validation is `vision_fn`'s job, not theirs.

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