# Pi, Goose and OpenCode with the same model: 42, 40 and 43 of 48 solved, but Goose and OpenCode used 2.5 to 2.6 times Pi's prompt tokens per attempt

*Report 5 of 5. Method and scoring: report 1.*

## The result
Same model (Qwen3.8-27B Q4_K_M, 64K context, Ollama 0.33.3), same twenty tasks, three repeats. Each arm is a complete
configuration: the agent's own system prompt, tool set and loop. Only Pi sent a thinking level (medium, on
every call in the relay log). Goose and OpenCode sent none. On this engine and model,
sending none gave the same completion-token and reasoning-character counts as medium at fixed seeds
(`analysis/thinking-default-check.jsonl`, two seeds), so all three most likely ran at medium; this was not confirmed for
every call.

| | Pi 0.87.0 (arm 1) | Goose 1.51.0 (arm 2) | OpenCode 1.18.32 (arm 3) |
|---|---|---|---|
| Solvable passed | 42 of 48 | 40 of 48 | 43 of 48 |
| Impossible, strict → adjudicated | 7 → 12 of 12 | 8 → 12 of 12 | 8 → 12 of 12 |
| Refused a solvable task | 1 | 0 | 0 |
| Median seconds per attempt | 17.5 | 33.1 | 21.4 |
| Median prompt tokens per attempt | 19,685 | 48,751 | 51,930 |
| Median completion tokens per attempt | 2,156 | 3,836 | 2,558 |
| Median model calls per attempt | 6 | 10 | 7 |
| Tool errors | 20 | unknown | 0 |
| Mean reasoning characters per attempt | 5,937 | 11,931 | 8,532 |

Per kind, passed of 12 (repair / state / data / build): Pi 12 / 11 / 11 / 8, Goose 12 / 11 / 10 / 7, OpenCode 12 / 12 / 11 / 8.
Sources: `results/v2/{1-baseline-pi-27b,2-goose-27b,3-opencode-27b}/`, `analysis/tokens-per-attempt.txt`.

## What differed
- **Pass counts:** within three attempts of each other. All three failed the CSV dry-run task on every attempt (report
  1). This does not establish a ranking, and it does not show that tool choice is unimportant.
- **Prompt overhead:** Goose and OpenCode sent 2.5 and 2.6 times Pi's median prompt tokens per attempt for similar
  results. Prompt tokens count the context re-sent on every call. How much of the difference comes from system
  prompts, tool definitions or call count, and what it costs in time or money, was not measured.
- **Time:** Goose's median attempt took 1.9 times Pi's.
- **Telemetry:** Goose prints text rather than an event stream, so its tool errors and repeated calls are unknown, not
  zero. Its engine calls are in `results/v2/2-goose-27b/relay-calls.jsonl`. One Goose attempt changed nothing.

## In practice
If a setup already works, these results give no reason to switch agent tools for tasks like these. If you are choosing,
measure prompt tokens per attempt on your own tasks alongside pass rate: it varied by up to 2.6 times here while pass rates
did not separate.
