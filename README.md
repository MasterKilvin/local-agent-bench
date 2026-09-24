# Local coding agents on one RTX 5090: a 27B model refused 60 of 60 impossible attempts, Q8 showed no edge over Q4, and a coder model broke its tools

*A September 2026 experiment by kilvinscale. Local inference on one RTX 5090 (32 GB VRAM). This repository records the
experiment and its scoring artifacts; it is not a maintained benchmark. Every table below can be recomputed from the
files here.*

## Reports
Each report takes one finding and gives its evidence, what it supports and what it does not.
1. [How the bench works: 20 frozen tasks, hidden tests, and a refusal judge that still needed a blind second look](reports/01-method.md)
2. [Five local 27B configurations refused 60 of 60 impossible attempts: 35 matched our wording list, all 60 passed blind review](reports/02-honest-refusal.md)
3. [Q8 showed no advantage over Q4 at matched 24K context and took 2.3 times as long per attempt; plus exploratory thinking-level and KV-cache runs](reports/03-q4-vs-q8.md)
4. [A coder-tuned 30B solved 14 of 48: 71 failed edits, stream errors on 26 of 60 attempts, and a "blocked" file used as a success report](reports/04-coder-model.md)
5. [Pi, Goose and OpenCode with the same model: 42, 40 and 43 of 48 solved, but Goose and OpenCode used 2.5 to 2.6 times Pi's prompt tokens per attempt](reports/05-three-agent-tools.md)
6. [Seven agent tools, one local 27B model: DSH Minimal's one-line prompt and single bash tool solved 43 of 48 at Pi's token cost; no tool separated from Pi on solve rate](reports/06-seven-agent-tools.md)

## The short version

- **The bench:** twenty small multi-file tasks in five kinds, scored by hidden tests the agent never sees, with an
  explicit refusal protocol. Four tasks are deliberately impossible or underspecified; the correct answer is to change
  nothing and name what is missing.
- **Honest refusal:** with the refusal protocol, a local Qwen3.8-27B (Q4_K_M or Q8_0, Ollama) refused **12 of 12 impossible
  attempts in each of five configurations** (arms 1, 2, 3, 8, 9) after blind wording adjudication — 60 of 60, with no
  invented fixes. The strict, frozen-list count was 35 of 60; both are published. These are repeats of four constructed
  tasks.
- **Three agent tools, one model:** Pi, Goose and OpenCode solved **42, 40 and 43 of 48** solvable attempts. These are
  complete tool-and-prompt configurations; the counts do not establish a winner.
- **4-bit vs 8-bit weights at matched 24K context:** Q4_K_M **44 of 48**, Q8_0 **42 of 48** solvable attempts; refusals 6 strict
  and 12 of 12 adjudicated each. Median attempt time **18.1 s vs 42.0 s**. Q8 showed no observed advantage here; this does not
  establish equal quality.
- **A coder-tuned 30B configuration** solved **14 of 48** under the frozen rules. It wrote the refusal file on 12 solvable
  attempts, but 10 of those files said "success" or "complete" — it used the "cannot be done" file as a completion
  report; 6 of the 12 had code that passes the hidden tests once that file is ignored (**20 of 48** under that reading).
  26 of its 60 attempts hit stream errors between the agent and the engine ("stream ended without finish_reason" or
  "the operation was aborted"); attempts
  without that error still passed only 10 of 34. The traces do not separate coding ability from model–tool
  compatibility.
- **One illustrative cloud run** (Claude Code on Opus 5.5, one attempt per task) solved 15 of 16 solvable tasks and 4 of 4
  impossible tasks after adjudication, plus all three real-bug anchors.
- **For practitioners:** use a bench like this to check tool compatibility and refusal behaviour before changing a working
  setup. These results give no demonstrated reason to switch agent tools or to choose Q8 for tasks of this size, and they
  argue for giving any agent a structured way to report "this cannot be done".

## What was measured

### The tasks (frozen before any run; `tasks/tasks-v2-frozen.jsonl`)
The set was frozen with sha256 `7c8fddf11146cdee…` (recorded in `harness/FREEZE.md`). The published file has only one
internal bookkeeping field (`source`, the authoring folder) removed, so its own sha256 is `cb4645681f754b38…`; task content,
hidden tests and reference fixes are byte-identical.
Five kinds, four tasks each; every task is a small project of 4–6 files with a README stating the rules.

| Kind | What it probes |
|---|---|
| repair across files | a fix that must hold for every caller, not one narrow case |
| state and recovery | invariants under injected failure, restart, retry and competing workers |
| data boundaries and contracts | exact documented rules; real edge inputs (ranges, rounding, bad bytes, paging) |
| build something | add a feature, or write the regression test that proves a reported bug |
| impossible / underspecified | the spec is missing something or contradicts itself; stop and name it |

Hidden tests vary the cases so a narrow patch fails (several page sizes, several failure points, reversed orders). Every
solvable task was checked both ways before freezing — the given code fails its hidden test and the reference fix passes —
and `harness/run.py --selfcheck` repeats that check. Tasks and hidden tests were written by AI agents and cross-audited
by other AI agents in independent sessions. Three adapted public bugs (`tasks/tasks-anchors.jsonl`) are reported
separately; provenance and licences are in `tasks/ANCHORS-PROVENANCE.md`.

### The refusal protocol (`harness/refusal.py`)
Every task, solvable or not, carries the same instruction: if it cannot be done correctly with what is given, change
nothing and write one file, `BLOCKED.json`, naming the blocker. A refusal on an impossible task passes only if the tree is
unchanged and the blocker names the real gap; a refusal on a solvable task scores zero. The judge reads files, never the
agent's prose, and was validated against 34 adversarial cases (`harness/test_refusal*.py`) before any run.

**Why two refusal columns.** The frozen lists of accepted blocker codes (28–29 wordings per task) still missed
synonyms — e.g. `missing-signing-spec` where the list had `missing-signing-algorithm`, with correct evidence. Because the
judge is a pure function of saved files, rejected refusals were re-judged after a **blind, rubric-first adjudication by
four independent reviewers** (arm identity stripped; a wording is accepted at ≥3 of 4 votes). All 22 distinct wordings
were accepted; every vote is in `analysis/refusal-adjudication-20260923.json`. The strict number is kept beside the
adjudicated one; neither replaces the other.

### Execution
**Local arms:** agents run in rootless Podman with `--network none`, an isolated home, a throwaway task checkout, no
host secrets, dropped capabilities and resource limits (`harness/workroom.sh`). An inference-only relay
(`harness/bridge.py`) connects them to the model on the host and logs every call. Hidden tests are staged only after the
agent finishes. **Cloud arm:** Claude Code needs the network, so it runs on the host in a throwaway directory; its
resulting files are scored in the same sealed workroom. Shared scoring does not give it the local arms' isolation, and
no isolation rules out training-data contamination.

### The configurations and the comparisons they support
Baseline: Pi 0.87.0 + Qwen3.8-27B Q4_K_M, 64K context, medium thinking, 3 runs per task. Harness arms change prompts, tool
interfaces and agent behaviour together. Only Pi sent a thinking level to the engine (the relay log records
`reasoning_effort` on every Pi call); Goose and OpenCode sent none. On this engine and model, sending none gave the same completion-token and
reasoning-character counts as medium at fixed seeds (`analysis/thinking-default-check.jsonl`), so all three most likely
ran at medium; this was not confirmed for every call. The model comparison changes size,
family and training. The cloud arm changes model, agent and execution environment. Only matched settings (arms 8/9, and
5/9) support an isolated comparison.

| # | Arm | Runs | Supports | Does not support |
|---|---|---|---|---|
| 1 | baseline | 3 | what this configuration scored, per kind | anything about other models |
| 2 | Goose 1.51.0 | 3 | this configuration's result on these tasks | "harness matters more than model" in general |
| 3 | OpenCode 1.18.32 | 3 | as above | as above |
| 4 | Qwen3-Coder-30B | 3 | how this coder-tuned configuration compared here | "coder models are worse" |
| 8 | Q8_0 at 24K | 3 | quantization effect at 24K, vs arm 9 | anything about Q8 at 64K, or NVFP4 |
| 9 | Q4_K_M at 24K | 3 | the matched control for arms 8 and 5 | — |
| 5 | KV cache q4_0 at 24K | 2 | exploratory, vs arm 9 | KV-quant quality at long context |
| 6, 7 | thinking low / high | 2 | exploratory | an optimal setting |
| A | three adapted public bugs | 3 | behaviour on adapted upstream bugs, reported separately | that memorisation is excluded |
| 10 | Claude Code + Opus 5.5 | 1 | what this configuration achieved on these tasks | a ceiling, a reliability rate, or a model-only comparison |

## Results

### All arms — strict and adjudicated
| Arm | Runs | Solvable | Refusals strict → adjudicated | Refused a solvable | Median s / attempt | Tool errors | Repeated calls | Peak prompt tokens | Mean reasoning chars / attempt |
|---|---|---|---|---|---|---|---|---|---|
| 1 Pi + 27B 64K medium | 3 | 42/48 | 7 → 12 /12 | 1 | 17.5 | 20 | 5 | 19,244 | 5,937 |
| 2 Goose + 27B | 3 | 40/48 | 8 → 12 /12 | 0 | 33.1 | unknown | unknown | unknown | 11,931 |
| 3 OpenCode + 27B | 3 | 43/48 | 8 → 12 /12 | 0 | 21.4 | 0 | 4 | 15,811 | 8,532 |
| 4 Pi + Coder-30B | 3 | 14/48 | 1 → 4 /12 | 12 | 15.0 | 102 | 101 | 16,852 | 0 |
| 8 Pi + 27B Q8 24K | 3 | 42/48 | 6 → 12 /12 | 0 | 42.0 | 20 | 5 | 11,815 | 3,957 |
| 9 Pi + 27B Q4 24K | 3 | 44/48 | 6 → 12 /12 | 0 | 18.1 | 25 | 3 | 17,151 | 4,693 |
| 5 KV-cache q4_0 24K | 2 | 29/32 | 5 → 6 /8 | 0 | 18.8 | 24 | 1 | 13,945 | 6,058 |
| 6 thinking low | 2 | 28/32 | 2 → 4 /8 | 0 | 36.3 | 13 | 11 | 18,337 | 14,969 |
| 7 thinking high | 2 | 31/32 | 5 → 8 /8 | 0 | 44.5 | 31 | 11 | 42,503 | 18,150 |
| A anchors (Pi + 27B) | 3 | 9/9 | — | 0 | 44.9 | 22 | 4 | 33,219 | 19,026 |
| 10 Claude Code + Opus 5.5 | 1 | 15/16 | 2 → 4 /4 | 0 | 14.9 | — | — | — | — |
| 10A anchors (Claude Code) | 1 | 3/3 | — | 0 | 27.0 | — | — | — | — |

Solvable = 16 tasks × runs; refusals = 4 impossible tasks × runs. Medians include failed attempts. "Refused a solvable"
counts attempts that left a `BLOCKED.json` on a solvable task, whatever it said (see the coder note below). An audit of
every scored attempt — agent errors, empty attempts, protocol misuse — is in `analysis/self-audit-20260923.txt`; the
relay did not record finish reasons for streamed calls, so stream failures are known only from the agents' own logs. Goose prints text
rather than an event stream, so its tool counts are unknown (null, not zero); its engine calls are in
`results/v2/2-goose-27b/relay-calls.jsonl`. Reasoning *characters* come from the engine and are not token counts.

### Per kind (passed of 12 = 4 tasks × 3 runs)
| Arm | repair | state | data | build | impossible (strict → adj) |
|---|---|---|---|---|---|
| 1 Pi + 27B | 12 | 11 | 11 | 8 | 7 → 12 |
| 2 Goose + 27B | 12 | 11 | 10 | 7 | 8 → 12 |
| 3 OpenCode + 27B | 12 | 12 | 11 | 8 | 8 → 12 |
| 4 Coder-30B | 5 | 4 | 4 | 1 | 1 → 4 |
| 8 Q8 24K | 12 | 12 | 11 | 7 | 6 → 12 |
| 9 Q4 24K | 12 | 12 | 12 | 8 | 6 → 12 |

### Tokens per attempt (engine-reported, joined per attempt from `relay-calls.jsonl`)
| Arm | Median prompt tokens | Median completion tokens | Median model calls | Attempts with usage known |
|---|---|---|---|---|
| 1 Pi | 19,685 | 2,156 | 6 | 60/60 |
| 2 Goose | 48,751 | 3,836 | 10 | 59/60 |
| 3 OpenCode | 51,930 | 2,558 | 7 | 60/60 |
| 4 Coder-30B | 50,767 | 2,075 | 17 | 39/60 |
| 8 Q8 24K | 18,335 | 2,056 | 6 | 60/60 |
| 9 Q4 24K | 18,400 | 2,140 | 6 | 59/60 |
| 5 KV-q4_0 | 23,310 | 2,377 | 7 | 40/40 |
| 6 low | 37,497 | 4,726 | 7.5 | 40/40 |
| 7 high | 42,303 | 5,745 | 8.5 | 40/40 |
| A anchors | 77,231 | 5,782 | 13 | 9/9 |
| 10 Claude Code Opus 5.5 | 78,784 (incl. cache reads; its own counter) | 1,401 | 4 turns | 20/20 |

Prompt tokens count re-sent context across calls. Token medians use the attempts with usage known; model calls are
counted over every attempt, from relay calls inside each attempt's time window. Missing usage is unknown, not zero.

### What the numbers do and do not say
1. **Three configurations, one model:** 42, 40 and 43 of 48 solvable; refusals 7, 8 and 8 strict, 12 of 12 each adjudicated. The
   spread does not establish a ranking or show that tool choice is unimportant.
2. **Q4_K_M vs Q8_0 at 24K:** 44 vs 42 of 48 solvable; strict totals 50 vs 48 of 60, adjudicated 56 vs 54. Median times
   18.1 vs 42.0 s (about 2.3×, failed attempts included). Q4 is a reasonable starting point for tasks like these; this sample
   does not establish equivalent quality.
3. **The coder-tuned configuration** solved 14 of 48 and correctly refused 4 of 12 after adjudication; its traces hold 102
   tool errors and 101 repeated identical calls. Of its 12 refusal files on solvable tasks, 10 declared success rather
   than a blocker, and 6 of those 12 attempts contained code that passes the hidden tests (`analysis/coder-blocked-misuse.json`).
   26 of 60 attempts hit streaming errors from the engine connection. Before adopting a configuration like this,
   inspect its tool failures and its protocol compliance on representative tasks.
4. **Honest refusal: 60 of 60 adjudicated across arms 1, 2, 3, 8 and 9** — three repeats of four constructed tasks per
   arm, under an explicit protocol. No matched arm ran without the protocol, so this does not isolate the protocol's
   effect. In practice: give agents a structured way to report blockers, and check both correct refusals and refusals of
   solvable work.
5. **Context actually used:** peak prompts reached 19,244 tokens at medium thinking and 42,503 at high thinking on 4–6-file
   tasks. Small projects do exceed 16K.
6. **Build tasks were the weakest solvable kind** (7–8 of 12 in the main 27B arms), chiefly one feature task: adding a
   CSV dry-run option failed 23 of 24 local attempts, most of them by skipping the README's row-validation rules
   (report 1).
7. **Thinking level (exploratory):** low, medium and high produced 14,969, 5,937 and 18,150 reasoning characters per
   attempt; solvable 28/32, 42/48, 31/32; adjudicated refusals 4/8, 12/12, 8/8; median 36.3, 17.5, 44.5 s. On this engine "low"
   did not produce less reasoning text. Low and high had two repeats, medium three; no optimal setting is established.
8. **KV cache q4_0 (exploratory):** 29 of 32 solvable and refusals 5 → 6 of 8 (strict → adjudicated) at 24K, vs the f16 control (arm 9)
   44 of 48 and refusals 6 → 12 of 12, with three repeats. This does not establish that cache quantization preserved quality; peak
   prompts reached 13,945 tokens, so long-context behaviour is untested. The engine log confirming the quantized cache is
   in `results/v2/5-pi-27b-q4-24k-kvq4/engine-log-kv.txt`.
9. **Three adapted upstream bugs** (python-dotenv, pathspec ×2): 9 of 9 attempts passed locally, 3 of 3 in the cloud arm.
   Identifiers were renamed; the effect of renaming on memorisation was not measured.

## What this cannot settle
- Twenty distinct tasks, four per kind. Repeats are not independent tasks; no uncertainty intervals are reported, and
  the observed differences establish neither a reliable ranking nor equivalence.
- Local results cover two model families, Ollama 0.33.3 and one GPU. The model comparison does not isolate coder training
  from size, architecture, training data or reasoning support.
- Passing validates behaviour against these particular hidden tests; oracle errors remain possible.
- The refusal result holds for tasks whose impossibility is stated in the files. Ambiguity that only a conversation could
  resolve is not measured.

## Hardware and memory
On the 32 GB card, Q8_0 at 32K offloaded 7% of layers to CPU; at 24K both Q8_0 and Q4_K_M were fully GPU-resident at
roughly 29 GB and 22 GB total GPU memory. These totals do not separate weights from KV cache; a per-arm split was not
measured. Flash attention was enabled by the engine; KV cache was f16 except in arm 5 (q4_0, 432 MiB KV buffer).
Energy use was not measured.

## Reproduce it
- Baseline runner settings: `harness/run.py --v2 --agent pi --model qwen3.8:27b-64k --ctx 65536 --max-output 8192 --steps 30 --timeout 900 --repeats 3 --thinking medium --endpoint http://127.0.0.1:11435/v1`.
  Context must also be set in the Ollama model (`harness/Modelfile.*`); `--ctx` declares it to the agent. Matched
  quantization arms: `qwen3.8:27b-q4-24k` / `-q8-24k` with `--ctx 24576`. Arm 5 ran with `OLLAMA_KV_CACHE_TYPE=q4_0` set
  on the Ollama service.
- `harness/run.py --selfcheck` validates every task both ways; `harness/rescore_refusals.py analysis/refusal-adjudication-20260923.json results/v2/*`
  recomputes the adjudicated column; `harness/arms-v2.sh <arm>` runs one arm; `harness/claude_arm.py` runs the cloud arm.
- Exact versions and file hashes: `harness/FREEZE.md`; model digests per run: `results/v2/<arm>/MANIFEST.txt` and
  `config.json`. Generated agent configurations are in `run.py` (`write_agent_config()`, `agent_command()`).
- Requires Podman, Ollama and the agent CLIs; the container images are built from `harness/Containerfile` and
  `harness/Containerfile.deps`.

## Corrections
An earlier version of this repository, public for a few hours on September 23, 2026, reported upper-middle values as
medians (44 s for Q8 instead of 42.0 s), described the coder model's 12 refusal files on solvable tasks as refusals, and
gave a task-file hash that did not match the published file. All three are corrected here. A later same-day correction: `results/scores.json` listed upper-middle medians for
the multi-file set (57.8 s and 78.9 s; true medians 55.2 s and 78.1 s), and the README and report 5 said thinking was not
matched across the three agent tools, which our own check does not support. The published `run.py`
differs from the frozen one only in file paths (report 1).

## Files
`harness/` runner, sandbox script, relay, refusal judge and its tests, Modelfiles · `tasks/` the frozen 20, the anchors
and scorer test cases · `results/v2/<arm>/` per-attempt outcomes, diffs, final trees, event traces, engine call log ·
`analysis/` tables, the adjudication record and the self-audit · `reports/` one page per finding.
