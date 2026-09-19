---
name: tdd
description: Use this skill immediately after a plan is approved (via ExitPlanMode or an equivalent explicit go-ahead) for any new logic in macro-crunch — any function, module, or behavior change, including UI/glue, not just load-bearing modules. It must run BEFORE any non-test code is written. It has a subagent draft the tests the approved plan calls for, describes that test list to the user in plain English, and only writes the tests once the user separately approves that.
---

# TDD workflow for macro-crunch

This project builds test-first. This skill is the gate between "plan approved" and
"implementation code gets written" — nothing outside a test file gets written before
it completes.

## When to use

Trigger this the moment a plan is approved (plan-mode approval, or an equivalent
explicit "go ahead" on a plain-English plan) for any new logic — a new function, a
behavior change, a bug fix that changes logic, UI/glue included. Skip only for pure
non-functional changes with nothing to test (docs, comments, pure renames).

## Steps

1. **Start from the approved plan.** This skill runs right after plan approval, not
   before — it doesn't replace planning, it's the next step once the plan is settled.

2. **Draft the test list via a subagent.** Launch a fresh `general-purpose` subagent
   (not a fork — it should start clean; its only job is reading the plan and existing
   code, not carrying forward the planning conversation). Give it:
   - The approved plan, verbatim.
   - The file(s) that will change.
   - The existing test file(s) for that module, so it matches this project's test
     style (pytest, plain functions, `monkeypatch` for fakes, boundary-value test
     naming like `test_check_fit_7_...` where that convention applies).

   Instruct it to return **only a test list**, not code: proposed test names plus a
   one-line description of what each verifies, grouped by the behavior/function it
   covers, including edge cases and boundary conditions worth pinning. It must not
   write any test code yet — this keeps the main session's context free of
   exploration noise.

3. **Describe the test list to the user in plain English, then stop.** This is the
   step the user actually reads, so it has its own bar:
   - Translate the subagent's list into plain, simple English a non-programmer could
     follow — no code, no jargon, no function signatures. Describe each case as a
     situation and what should happen, e.g. "if the model asks for an ingredient
     that isn't on the list, reject it and explain why" rather than "test_validate_
     unknown_id_rejected asserts error contains the id."
   - Keep it brief — one short line per case, grouped under the behavior it belongs
     to. Long enough to be concrete, short enough to scan in a few seconds.
   - End by asking a plain yes/no: go ahead and write these, or talk through
     something first. Make it easy for the user to say yes, say no, or point at one
     specific case and question it — don't bundle the approval into a wall of text.
   - Do not write anything until the user answers. If they want changes to the list,
     revise it and describe it again the same way.

4. **On approval, write the tests via a subagent.** Launch a subagent to write the
   actual test code for the approved list only, matching the target test file's
   existing conventions. It touches test files only — no implementation code.

5. **Confirm red.** Run the new tests and confirm they fail for the expected reason
   (the behavior doesn't exist yet / doesn't do X yet) — not from an import error, a
   typo, or a fixture mistake. A test that already passes, or fails for the wrong
   reason, doesn't prove anything yet; fix the test before moving on.

6. **Only now write implementation code**, incrementally, following this project's
   existing working style (no speculative abstractions, no scope creep beyond the
   plan) until the new tests pass.

7. **Confirm green.** Run the full suite (`python -m pytest -v`, or the pinned
   interpreter path from CLAUDE.md on this Windows machine) to confirm everything
   passes and nothing regressed.

## Why subagents

Drafting a test list means reading the plan and skimming existing code/tests for
conventions — exploration output the main session doesn't need to keep. Delegating
that (and the actual test-writing) to subagents keeps the main session's context to
just the test list (for approval) and a final diff/summary, not the subagent's
intermediate reasoning.
