# How the bench works: 20 frozen tasks, hidden tests, and a refusal judge that still needed a blind second look

*Report 1 of 5. Every number here is recomputed from files in this repository; paths are given for each.*

## What is being measured
Can a local coding agent change a small multi-file project correctly, and does it stop when the task cannot be done?
Twenty tasks, frozen before any run (`tasks/tasks-v2-frozen.jsonl`, frozen set sha256 `7c8fddf11146cdee…`, recorded in
`harness/FREEZE.md`). Five kinds, four tasks each. Every task is a project of 4–6 files whose README states the rules.

| Kind | Example task | What a correct answer needs |
|---|---|---|
| repair across files | fix pagination for every caller | a fix that holds for all page sizes, not one |
| state and recovery | two workers claiming one job | invariants under injected failure and restart |
| data boundaries | inclusive date ranges, invoice rounding | the exact documented rule on edge inputs |
| build something | add a CSV dry-run option; write a regression test | the feature plus every rule in the README |
| impossible / underspecified | a codec that must shorten *every* input | change nothing; name the gap |

## Scoring
- **Hidden tests.** The agent never sees them; they are staged after the agent finishes. They vary the cases (several
  page sizes, several failure points, reversed orders) so a narrow patch fails.
- **Validated both ways.** Before the freeze, every solvable task was checked twice: the given code fails its hidden test
  and the reference fix passes. `harness/run.py --selfcheck` repeats this; it reports `20/20 OK` on this repository.
- **Tampering fails the attempt.** Creating a file that would shadow the hidden test (a module named like it or like
  `unittest`) or changing a task's protected files scores zero. Edits to existing test files are recorded per attempt
  (`edited_tests` in `results.jsonl`).
- **One refusal channel.** Every task, solvable or not, carries the same instruction: if it cannot be done correctly
  with what is given, change nothing and write `BLOCKED.json` naming the blocker. The judge (`harness/refusal.py`) reads
  files, never the agent's prose. A refusal passes only if the tree is unchanged and the blocker names the real gap. A
  refusal on a solvable task scores zero.
- **The judge was attacked before use.** 34 adversarial cases (`harness/test_refusal*.py`), including naming several
  blocker codes to hit one, prose-only refusals and partial edits plus a refusal file.

## Why there are two refusal columns
The judge matched blocker names against frozen lists of 28–29 accepted wordings per task. The lists still missed
synonyms: `missing-signing-spec` was rejected where the list had `missing-signing-algorithm`, with the right evidence.
Because the judge is a pure function of saved files, rejected refusals could be re-judged without re-running anything.
Four independent reviewers voted blind, with arm identity stripped and a rubric written before they saw any wording. A
wording is accepted at 3 of 4 votes. All 22 distinct rejected wordings were accepted. Every vote is in
`analysis/refusal-adjudication-20260923.json`, and `harness/rescore_refusals.py` recomputes the adjudicated column.
**Both numbers are printed everywhere, side by side. Neither replaces the other.**

## Execution
- **Local agents** run in rootless Podman with `--network none`, an isolated home, a throwaway checkout, dropped
  capabilities and resource limits (`harness/workroom.sh`). A relay (`harness/bridge.py`) connects them to the model on
  the host and logs every call: tokens, reasoning characters, time to first token (`results/v2/<arm>/relay-calls.jsonl`).
- **Engine:** Ollama 0.33.3 on one RTX 5090 (32 GB). **Agents:** Pi 0.87.0, OpenCode 1.18.32, Goose 1.51.0.
- **Repeats:** three per task for the main arms (60 attempts each), two for exploratory arms, one for the cloud arm.
- **Every attempt keeps its evidence:** the diff (`*.diff.patch`), the final tree (`*.final.json`), the per-step trace
  (`*.events.json`) and a result row with the hidden-test output (`results.jsonl`).

## What the audit of our own data found
After the runs, every scored attempt was audited (`analysis/self-audit-20260923.txt`). Findings that changed the write-up:
- The coder-tuned model wrote `BLOCKED.json` on 12 solvable attempts, but 10 of those files said "success" or "complete".
  That is protocol misuse, not refusal (report 4).
- 26 of its 60 attempts hit stream errors between agent and engine: 21 "Stream ended without finish_reason", 6 "The
  operation was aborted", one attempt both (report 4).
- The relay did not record finish reasons for streamed calls. Stream failures are known only from the agents' own logs.
- Goose prints text rather than an event stream, so its tool counts are unknown. They are reported as unknown, not zero.
- The one solvable-task refusal from the baseline was genuine: the model misread the task.

## One task the local model almost never passed
"Add a dry-run option to the stock CSV importer" failed on 23 of 24 local attempts across all nine local arms; the one
pass was at high thinking. The single cloud attempt passed. The prompt asks for the dry run; the README also requires strict row validation that the
original code lacks: quantity must be decimal digits only, invalid rows leave the store unchanged. Of the 22 local attempts that
failed its hidden tests (the 23rd was a refusal), 20 failed the invalid-row test. 19 of those 22 diffs add no digit-only check and rely on Python's `int()`, which accepts
`+2`, `-2` and `1_0`.
The task is validated both ways; this is a reading-the-contract failure, and it is the main reason build was the weakest
solvable kind (7–8 of 12 in each main 27B arm).

## Known deviations from the freeze
- `harness/run.py` in this repository differs from the frozen file (sha256 `5563a27b…`) in four lines only: the paths to
  the sandbox script and the task file, and two comments, so it runs from this folder. `refusal.py` and `bridge.py` are
  byte-identical to the frozen versions.
- The published task file drops one bookkeeping field (`source`), so its own sha256 is `cb4645681f754b38…`. Task content,
  hidden tests and reference fixes are byte-identical.
- The cloud arms (10, 10A) have `config.json` (agent version, model, task hash) but no `MANIFEST.txt`: there is no local
  model digest or GPU to record.

## What 20 tasks cannot settle
- Twenty distinct tasks, four per kind. Repeats are not independent tasks. No uncertainty intervals are reported. A
  difference of two or three attempts out of 48 establishes neither a ranking nor equivalence.
- Tasks and hidden tests were written by AI agents and cross-audited by other AI agents. Oracle errors remain possible.
- The refusal result holds for tasks whose impossibility is stated in the files, not ambiguity that only a conversation
  could resolve.
- Local results cover two model families, one engine version and one GPU. Energy was not measured.
