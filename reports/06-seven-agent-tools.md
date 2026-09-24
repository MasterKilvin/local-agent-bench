# A one-line prompt and one bash tool did not separate from full agent tools on a local 27B model: DSH Minimal solved 43 of 48 at Pi's token cost

*Report 6 of 6. Method and scoring: report 1. Every number here is recomputed from the published result rows by
`tools/verify_report6.py`.*

## The question
Does a one-line prompt and raw bash beat full agent scaffolding on a local 27B model?

DeepSeek's harness (DSH) ships a Minimal profile that gives the model one short instruction and a single bash tool, and a
Standard profile with a full tool set. We ran both beside five other agent tools on the same local model and the same
twenty frozen tasks, and asked three things: does the minimal setup solve as many tasks, what does each setup cost in
time and prompt tokens, and does it still stop honestly when a task cannot be done.

**Short answer: on solve rate, this test could not tell them apart.** DSH Minimal solved 43 of 48 solvable attempts; the
seven tools ranged from 40 to 43 of 48, and every difference from Pi has a 95% interval that includes zero. What separated
the tools was cost: DSH Minimal used a median of 20,087 against Pi's 19,685 prompt tokens per attempt, while DSH Standard, the
same harness with its full tool set, used 4.7 times as many as Minimal.

## Setup
- **Model and engine:** Qwen3.8-27B, Q4_K_M, 64K context (num_ctx 65536), Ollama 0.33.3, one RTX 5090. The same model
  file (same manifest digest in every arm's `config.json`) for all seven arms.
- **Tasks:** the frozen 20 (16 solvable, 4 impossible or underspecified), hidden tests, three repeats each: 48 solvable and
  12 impossible attempts per arm.
- **Same room for every arm:** rootless container with no network, a throwaway task checkout, and one shared relay that
  logs every model call with its token counts (`relay-calls.jsonl`). Limits: 30 model calls and 900 seconds per
  attempt for every arm. An output limit of 8192 tokens per call (`--max-output 8192`) was written into the
  configurations of Pi, OpenCode, Oh My Pi and both DSH profiles; the Goose and Qwen Code configurations the harness
  writes carry no output limit (`harness/run.py`, `write_agent_config`). 16 model calls returned more than 8192 output
  tokens (Goose 1, Oh My Pi 4, Qwen Code 10, DSH Standard 1); the largest was 22,825, most of it thinking text. The
  output budget was therefore not identical across arms.
- **Thinking level:** only Pi sent one (medium). The other six sent none: OpenCode and Oh My Pi were started with
  `--thinking medium` but the relay shows no reasoning effort on their calls. On this engine, sending none and sending
  medium gave the same completion-token and reasoning-character counts on two fixed seeds
  (`analysis/thinking-default-check.jsonl`, report 5).
- **Arms:** Pi 0.87.0, Goose 1.51.0 and OpenCode 1.18.32 (report 5); Oh My Pi 18.2.11; Qwen Code 0.24.4; DSH Minimal and
  DSH Standard, both DSH 0.1.5-rc.3. Arms 1 and 2 ran on September 22, the rest on September 23, 2026.

## The seven arms

| Arm | Solvable passed | Impossible, strict → adjudicated | Refused a solvable task | Median s / attempt | Median prompt tokens / attempt | First agent request, prompt tokens | Seconds per solved task | Prompt tokens per solved task | Solve rate vs Pi, points [95% interval] |
|---|---|---|---|---|---|---|---|---|---|
| Pi 0.87.0 | 42 of 48 | 7 → 12 of 12 | 1 | 17.5 | 19,685 | 1,670 | 36.6 | 38,384 | reference |
| Goose 1.51.0 | 40 of 48 | 8 → 12 of 12 | 0 | 33.1 | 48,751 (59 of 60) | 4,432 | 69.6 | ≥ 92,926 | −4.2 [−14.6, +4.2] |
| OpenCode 1.18.32 | 43 of 48 | 8 → 12 of 12 | 0 | 21.4 | 51,930 | 7,162 | 42.7 | 86,783 | +2.1 [−4.2, +8.3] |
| Oh My Pi 18.2.11 | 43 of 48 | 8 → 12 of 12 | 2 | 40.3 | 103,174 (59 of 60) | 11,202 | 72.7 | ≥ 182,759 | +2.1 [−10.4, +12.5] |
| Qwen Code 0.24.4 | 43 of 48 | 7 → 12 of 12 | 2 | 55.9 | 152,008 | 18,249 | 120.2 | 239,155 | +2.1 [−10.4, +12.5] |
| DSH Minimal | 43 of 48 | 9 → 12 of 12 | 0 | 27.4 | 20,087 | 626 | 71.5 | 35,577 | +2.1 [−4.2, +8.3] |
| DSH Standard | 41 of 48 | 6 → 11 of 12 | 0 | 45.5 | 95,198 | 7,072 | 89.7 | 178,939 | −2.1 [−10.4, +6.2] |

How to read it:
- **Impossible, strict → adjudicated:** strict is the frozen list of accepted blocker wordings; adjudicated adds the
  synonyms accepted by blind four-reviewer adjudication (`analysis/refusal-adjudication-20260923b.json`, round 3 for the
  four new arms). Every arm left the code unchanged and wrote a refusal on all 12 impossible attempts. DSH Standard's
  twelfth refusal named the generic code `impossible-requirement` with correct evidence; the reviewers split 2-2, so it
  stays rejected.
- **Median prompt tokens** sum the prompt tokens of every model call inside the attempt, as reported by the engine; the
  context re-sent on each call counts again. Where one attempt's usage is missing, the median is over the known attempts
  (shown in brackets) and the per-solved figure is a lower bound (≥).
- **First agent request** is the first call in an attempt that carries the tool list: the task prompt plus the tool's own
  system prompt and tool definitions, before any work. Goose and OpenCode each open an attempt with a short side call
  without tools; it is not counted here.
- **Seconds and prompt tokens per solved task** are totals over all 60 attempts, failed and impossible ones included,
  divided by the solvable attempts passed. For Goose and Oh My Pi one call's usage is missing, so their figures count
  every call that did report usage and are lower bounds (≥); Oh My Pi's true figure is therefore above DSH Standard's
  178,939.
- **Solve rate vs Pi** is the difference in solvable pass rate in percentage points, with a 95% interval from a bootstrap
  that resamples the 16 solvable tasks (10,000 draws, seed 20260923), so repeats of one task move together. Interval
  endpoints move in steps of one attempt (2.1 points), and an endpoint can shift one step with a different seed.

What each tool sends and how long attempts ran:

| Arm | Tools offered per request | First agent request, prompt tokens | Median model calls / attempt | Most calls in one attempt | Longest attempt, s |
|---|---|---|---|---|---|
| Pi 0.87.0 | 4 | 1,670 | 6 | 15 | 121.2 |
| Goose 1.51.0 | 18 | 4,432 | 9 | 29 | 248.9 |
| OpenCode 1.18.32 | 9 | 7,162 | 7 | 16 | 141.2 |
| Oh My Pi 18.2.11 | 8 | 11,202 | 7 | 23 | 174.8 |
| Qwen Code 0.24.4 | 14 | 18,249 | 7 | 21 | 779.7 |
| DSH Minimal | 1 | 626 | 7 | 15 | 668.8 |
| DSH Standard | 23 | 7,072 | 9 | 24 | 419.3 |

Model calls count chat requests at the relay, side calls included (report 5's Goose figure also counted one model-list
request per attempt).

## What it shows
1. **No tool separated from Pi on solve rate.** The seven ranged from 40 to 43 of 48, and all six intervals include zero.
   Solve counts differ on 6 of the 16 tasks, and the two largest swings are: on the CSV dry-run task, solves were Pi 0, Goose 0, OpenCode 0, Oh My Pi 1, Qwen Code 1, DSH Minimal 0, DSH Standard 0
   (of 3 each); on the retry-regression task, Pi 2, Goose 1, OpenCode 2, Oh My Pi 0, Qwen Code 0, DSH Minimal 1, DSH Standard 1.
2. **The minimal setup was the cheapest in tokens.** DSH Minimal's first agent request was 626 tokens, our task prompt
   included, against 7,072 for DSH Standard: 11 times as much before any work. Over whole attempts, DSH Minimal used
   20,087 against 19,685 prompt tokens per attempt, about the same as Pi, and the fewest prompt tokens per solved task
   (35,577; Pi 38,384). DSH Standard used 4.7 times Minimal's median, and 178,939 per solved task. Qwen Code, the model
   maker's own tool, sent 18,249 tokens in its first request and used 7.7 times Pi's median prompt tokens per attempt,
   with the same solve count as OpenCode and DSH Minimal.
3. **Fewer tokens did not mean less time.** DSH Minimal's median attempt took 27.4 s against Pi's 17.5, and 71.5 against
   36.6 seconds per solved task. Much of that is not model time. The relay log shows 4 pauses of more than two hundred
   seconds between model calls, all in DSH Minimal and in three attempts, while the agent's shell sat on a command;
   three of them lasted about 303 seconds, which matches DSH's own 300-second bash timeout (DSH's own logs, which are
   not published, show that timeout message). Those pauses took 1,121 of its 3,073 seconds; without them it would be 45.4 seconds per
   solved task, and its model calls took 1,665 seconds in total. No other arm had such a pause.
4. **Honest stopping held for every setup.** All seven refused all 12 impossible attempts without changing code. Strict
   scores ranged from 6 to 9 of 12 because the models named the gap in words our frozen list lacked; after blind
   adjudication, six arms scored 12 of 12 and DSH Standard 11 of 12. Pi, Oh My Pi and Qwen Code also wrote a refusal on
   one or two attempts of the solvable retry-regression task (1, 2 and 2 attempts).
5. **No attempt hit the call or time limits.** No attempt in any arm reached the 30-call cap or the 900-second limit (at most 29
   model calls and 779.7 seconds), and every relay call returned HTTP 200. Whether different budgets would change the
   results was not tested. For both DSH arms, the tokens counted from DSH's own event stream
   matched the relay's count on 60 of 60 and 60 of 60 attempts.

## What it does not show
- **No ranking on solve rate.** With 20 tasks and three repeats, these results cannot rank the seven tools; differences of a
  few attempts are within the intervals. Repeats of one task are not independent tasks.
- **One model on one GPU.** Everything here is Qwen3.8-27B Q4_K_M on Ollama 0.33.3 and one RTX 5090. Another model,
  engine or quantization could order the tools differently.
- **Small tasks.** Projects of 4–6 files; across all seven arms the largest single prompt was 45,270 tokens, inside the
  64K context. Long sessions, compaction and large repositories were not tested, and DSH Minimal has no compaction or
  instruction discovery.
- **Whole configurations, not parts.** Each arm is a complete tool: prompt, tool set and loop together. DSH Minimal differs
  from Standard in prompt, tools and features at once; nothing here says whether the prompt or the tool set made the
  difference.
- **DSH through an adapter.** DSH 0.1.5-rc.3 (a preview; npm's "latest" tag on the run date, with 0.1.7-rc.1 on "next")
  ran through its OpenAI-compatible adapter, because this Ollama version does not serve the API DSH's own DeepSeek
  adapter expects. We set its stream idle timeout, retries and context explicitly (below). No DeepSeek model was tested.
- **Not DeepSeek's benchmark.** DeepSeek's own harness comparison uses its own model with far larger budgets
  (temperature 1.0, top-p 0.95, a 1M-token context, maximum reasoning, up to 500 steps;
  [DeepSeek-V4.1-Flash model card](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash)). Here every arm used the
  local model's own sampling defaults and the bench's limits. Network tools were off in every arm.

## Prior work
This is a replication plus extension. The question comes from DeepSeek's own comparison on its V4.1-Flash model, where
DSH Minimal scored highest on Terminal-Bench 2.1 (90.6 against Pi's 86.1; model card above). A published comparison of Pi and DSH on Qwen3.8-27B ran 16 runs (4 tasks, 2
trials each) on an Apple M4 Max with an MLX build of the model and DSH's headless profile
([promptdriven/pdd research note](https://github.com/promptdriven/pdd/blob/main/research/omlx-qwen38-pi-deepseek-harness-2026-08-23/README.md);
[DSH discussion #4283](https://github.com/deepseek-ai/deepseek-harness/discussions/4283)). It found Pi passing 6/8 and
DSH 4/8, with DSH sending 19 tool schemas per request against Pi's 4 and using 11.9% more input tokens; its authors warn
that the sample is too small for a ranking. Our DSH Standard arm (profile `sdk`, network tools off) sent 23 tool
definitions per request against Pi's 4, and it too solved slightly fewer than Pi, within the interval. New here: seven
tools under one sealed setup, per-attempt token accounting at a shared relay, impossible-task honesty, and DSH's Minimal
profile beside Standard.

## Exact configuration
- **Runner:** `harness/run.py --v2 --agent <pi|goose|opencode|omp|qwen|dsh-min|dsh-std> --model qwen3.8:27b-64k
  --ctx 65536 --max-output 8192 --steps 30 --timeout 900 --repeats 3`, relay at `http://127.0.0.1:11435/v1`. Each arm's
  `config.json` records the settings, agent version and generated agent configuration, and `MANIFEST.txt` the model
  digest and file hashes. The four new arms ran with later versions of `run.py` than arms 1–3; the changes add the new
  agents and their event parsing and leave scoring unchanged. The published `run.py` is the version the DSH arms used
  (`harness/SYNC.md`).
- **DSH (both arms):** driven over its SDK's JSON-RPC stdio protocol by `harness/dsh/driver.py`, which starts a fresh
  session with a fresh DSH home per attempt, sets `DSH_TELEMETRY_MODE=DISABLED`, and stops sending prompts after 30 model
  steps. Model route: DSH's pi-ai adapter with `api: openai-completions` to the relay, a placeholder key,
  `contextWindow: 65536`, `maxTokens: 8192`, `reasoningEfforts: false`, `supportsDeveloperRole: false`,
  `streamIdleTimeoutMs: 1200000` (above the 900-second attempt limit) and `retryPolicy.maxRetries: 0`; the DeepSeek
  session-log plugin disabled. Minimal uses profile `sdk-minimal` with `harness/dsh/minimal.patch.yml`; Standard uses
  profile `sdk` with `harness/dsh/standard.patch.yml`, which also disables the web, web-search and web-fetch tools. The
  resolved package tree is `harness/dsh/npm/package-lock.json`.
- **Oh My Pi:** `--no-session --no-lsp --no-skills --no-rules --no-extensions --no-title`, tools
  `read,bash,edit,write,grep,glob,todo,task` (tools needing the network or a person removed), the same turn-cap extension
  as Pi, update checks off.
- **Qwen Code:** `--yolo --output-format stream-json --max-session-turns 30`, OpenAI-compatible route to the relay,
  auto-update, usage statistics and telemetry off, context declared as 65536.
- **Scoring and analysis:** hidden tests and the refusal judge as in report 1; `harness/rescore_refusals.py
  analysis/refusal-adjudication-20260923b.json results/v2/<arm>` writes the adjudicated column;
  `analysis/seven_arms.py` produces `analysis/seven-arms-20260923.md` and `.json`, including the per-task paired tables;
  `tools/verify_report6.py` recomputes every number in this report.
- **Not published:** the agents' own transcripts, because tool output inside the container can show local account
  details. Per-attempt outcomes, diffs, final trees, step and tool summaries (`*.events.json`) and the relay logs are.

## In practice
If you run a 27B model locally for small coding tasks, a minimal prompt with one bash tool solved as many attempts as the full tools
here, within what 48 attempts can detect, and was as cheap in tokens as the leanest one, but watch for shell commands that hang: they cost DSH Minimal more time
than the model did in its slowest attempts. Measure prompt tokens per solved task on your own tasks before choosing: it
varied 6.7 times across tools whose solve counts did not separate.
