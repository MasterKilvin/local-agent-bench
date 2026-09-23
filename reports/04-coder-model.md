# A coder-tuned 30B solved 14 of 48: 71 failed edits, 26 broken streams, and a "blocked" file used as a success report

*Report 4 of 5. Method and scoring: report 1.*

## The result
Arm 4 swapped the model: Qwen3-Coder-30B in place of Qwen3.8-27B, same agent (Pi 0.87.0), same prompts, three repeats.

| | Coder-30B (arm 4) | 27B baseline (arm 1) |
|---|---|---|
| Solvable passed, strict | 14 of 48 | 42 of 48 |
| Impossible, strict → adjudicated | 1 → 4 of 12 | 7 → 12 of 12 |
| Refusal file written on a solvable task | 12 | 1 |
| Tool errors | 102 | 20 |
| of which in the edit tool | 71 | 0 |
| Repeated identical calls | 101 | 5 |
| Median model calls per attempt | 15 | 6 |
| Median prompt tokens per attempt | 50,767 | 19,685 |
| Attempts with "Stream ended without finish_reason" | 26 of 60 | 0 of 60 |
| Median seconds per attempt | 15.0 | 17.5 |

Per kind, passed of 12: repair 5, state 4, data 4, build 1. Sources: `results/v2/4-pi-coder30b/results.jsonl` and
`*.events.json`, `analysis/self-audit-20260923.txt`.

## Three separate failures
**1. Edits did not apply.** 71 of the 102 tool errors came from the edit tool, against none in the 27B baseline. The
traces record that a call failed, not the error text. The same calls were then often repeated unchanged: 101 repeated
identical calls. The model used more calls and more prompt tokens to reach fewer passes.

**2. The stream broke.** 26 of 60 attempts logged "Stream ended without finish_reason" (44 times in total), and 6 logged
"The operation was aborted". Usage was recorded for only 39 of 60 attempts because broken streams carry no token counts.
Attempts without the error passed 10 of 34. Attempts with it passed 5 of 26. The error explains part of the gap, not all
of it.

**3. The refusal file was misused.** On 12 solvable attempts the model wrote `BLOCKED.json`. Ten of those files said
"success", "complete" or "completed". Two said "blocked". It was using the "cannot be done" file as a completion report.
Under the frozen rules any refusal file on a solvable task scores zero. Ignoring the file and scoring the code, 6 of the
12 attempts pass the hidden tests, which would make it **20 of 48**. Both numbers are published; the frozen rule stands.
Every case is listed in `analysis/coder-blocked-misuse.json`.

On impossible tasks it wrote a refusal file 5 times in 12. On 6 of the other 7 it edited code; on one it did nothing.

## What this does not show
- **Not "coder models are worse".** Size, architecture, training data and reasoning support all differ between the two
  models. This coder model produced no reasoning text through this engine.
- The traces do not separate coding ability from compatibility between this model, this agent's tool format and this
  engine's streaming. The stream errors in particular point at the model–engine–agent connection.

## In practice
Before adopting a model for agent work, run it through your own agent on a few representative tasks and look at three
things: whether its edits apply, whether its responses stream to completion, and whether it uses any structured channel
as intended. A pass rate alone hides all three.
