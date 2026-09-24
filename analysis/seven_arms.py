#!/usr/bin/env python3
"""Seven-arm v2 comparison (TEST-PLAN v2 items 6 and 10). Standard library only; reads result dirs, writes nothing there.

Per arm: solvable passes; impossible-task strict passes and refusals; refused-solvable; median seconds over ALL attempts;
per-attempt prompt tokens (sum of relay /v1/chat/completions prompt_tokens with t in [t_start, t_end]; an attempt counts
only if every such call reports prompt_tokens); first-request prompt tokens; model calls per attempt; relay finish
reasons; timeout and cap hits; time and prompt tokens per solved task; paired task-level differences vs Pi with a
task-clustered bootstrap 95% interval; outcome categories (solved, honest refusal, timeout, cap, other failure).

"First request" is the attempt's first model call. Goose and OpenCode open each attempt with a short side call that
carries no tool list, so the published copy also reports the first *agent* request: the first call that carries the
tool list, with its tool count. Adjudicated refusals are read from each arm's refusals-adjudicated.json
(harness/rescore_refusals.py) when present. A cap hit is also inferred when an attempt made 30 or more model calls.

Usage: python3 analysis/seven_arms.py [--results DIR] [--out summary.json]
"""
import argparse
import collections
import glob
import json
import os
import random
import re
import statistics
import sys

DEFAULT_RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "v2")
ARMS = [  # (label, published dir name); the working bench's v2-YYYYMMDD-<name> dirs match too
    ("Pi", "1-baseline-pi-27b"),
    ("Goose", "2-goose-27b"),
    ("OpenCode", "3-opencode-27b"),
    ("Oh My Pi", "11-omp-27b"),
    ("Qwen Code", "12-qwencode-27b"),
    ("DSH Minimal", "13-dsh-min-27b"),
    ("DSH Standard", "14-dsh-std-27b"),
]
STEP_CAP = 30
SOLVABLE_KIND, IMPOSSIBLE_KIND = "unittest", "blocked"
CHAT = "/v1/chat/completions"
CAP_RE = re.compile(r"step[ _-]?(cap|limit)|max[ _-]?turns|turn limit|maximum (number of )?(turns|steps)", re.I)
BOOT_DRAWS, BOOT_SEED = 10000, 20260923


def read_jsonl(path):
    """Rows of a JSONL file; a torn last line (arm still running) is skipped."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return rows


def med(xs):
    return statistics.median(xs) if xs else None


def cap_hit(arm_dir, r, n_calls=0):
    if n_calls >= STEP_CAP:
        return True
    if r.get("ended") in ("step-limit-kill", "step-cap", "cap"):
        return True
    if any(CAP_RE.search(str(e)) for e in r.get("agent_errors") or []):
        return True
    stem = os.path.join(arm_dir, f"{r['task']}-r{r['repeat']}")
    for suffix, needle in ((".agent.jsonl", '"driver": "step-cap"'), (".agent.stderr", "[bench] step limit")):
        try:
            with open(stem + suffix, errors="replace") as f:
                if needle in f.read():
                    return True
        except FileNotFoundError:
            pass
    return False


def outcome(r, capped):
    if r["kind"] == SOLVABLE_KIND and r.get("passed"):
        return "solved"
    if r["kind"] == IMPOSSIBLE_KIND and r.get("refused"):
        return "honest refusal"
    if r.get("ended") == "timeout":
        return "timeout"
    if capped:
        return "cap"
    return "other failure"


def attempt_calls(calls, r):
    lo, hi = r["t_start"], r["t_end"]
    return [c for c in calls if lo <= c["t"] <= hi]


def analyse_arm(label, arm_dir):
    rows = read_jsonl(os.path.join(arm_dir, "results.jsonl"))
    calls = sorted((c for c in read_jsonl(os.path.join(arm_dir, "relay-calls.jsonl")) if c.get("path") == CHAT),
                   key=lambda c: c["t"])
    solv = [r for r in rows if r["kind"] == SOLVABLE_KIND]
    imp = [r for r in rows if r["kind"] == IMPOSSIBLE_KIND]
    prompt_tok, first_tok, first_agent_tok, first_agent_tools, n_calls = [], [], [], [], []
    finish = collections.Counter()
    outcomes = collections.Counter()
    timeouts = caps = 0
    per_task = collections.defaultdict(lambda: [0, 0])  # solvable task -> [passes, attempts]
    for r in rows:
        mine = attempt_calls(calls, r)
        n_calls.append(len(mine))
        finish.update(("absent" if c.get("finish_reason") is None else str(c["finish_reason"])) if "finish_reason" in c
                      else "not recorded" for c in mine)
        if mine and all(isinstance(c.get("prompt_tokens"), int) for c in mine):
            prompt_tok.append(sum(c["prompt_tokens"] for c in mine))
        if mine and isinstance(mine[0].get("prompt_tokens"), int):
            first_tok.append(mine[0]["prompt_tokens"])
        agent_calls = [c for c in mine if c.get("n_tools")]
        if agent_calls and isinstance(agent_calls[0].get("prompt_tokens"), int):
            first_agent_tok.append(agent_calls[0]["prompt_tokens"])
            first_agent_tools.append(agent_calls[0]["n_tools"])
        capped = cap_hit(arm_dir, r, len(mine))
        timeouts += r.get("ended") == "timeout"
        caps += capped
        outcomes[outcome(r, capped)] += 1
        if r["kind"] == SOLVABLE_KIND:
            per_task[r["task"]][0] += bool(r.get("passed"))
            per_task[r["task"]][1] += 1
    solved = sum(bool(r.get("passed")) for r in solv)
    total_secs = sum(r["seconds"] for r in rows)
    known_all = len(prompt_tok) == len(rows)
    adj = None
    try:
        with open(os.path.join(arm_dir, "refusals-adjudicated.json")) as f:
            adj = sum(bool(x["adjudicated_passed"]) for x in json.load(f)["rows"])
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    return {
        "label": label, "dir": os.path.basename(arm_dir), "attempts": len(rows),
        "solvable_passed": solved, "solvable_attempts": len(solv),
        "impossible_strict_passed": sum(bool(r.get("passed")) for r in imp),
        "impossible_refused": sum(bool(r.get("refused")) for r in imp), "impossible_attempts": len(imp),
        "impossible_adjudicated_passed": adj,
        "refused_solvable": sum(bool(r.get("refused_solvable")) for r in rows),
        "median_seconds": med([r["seconds"] for r in rows]),
        "prompt_tokens_known": len(prompt_tok), "median_prompt_tokens": med(prompt_tok),
        "median_first_request_prompt_tokens": med(first_tok), "first_request_known": len(first_tok),
        "median_first_agent_request_prompt_tokens": med(first_agent_tok), "first_agent_request_known": len(first_agent_tok),
        "first_agent_request_tools": sorted(set(first_agent_tools)),
        "median_model_calls": med(n_calls), "finish_reasons": dict(finish),
        "timeouts": timeouts, "cap_hits": caps,
        "seconds_per_solved": total_secs / solved if solved else None,
        # Only exact when every attempt's usage is known; otherwise a lower bound over the known attempts.
        "prompt_tokens_per_solved": sum(prompt_tok) / solved if solved else None,
        "prompt_tokens_per_solved_is_lower_bound": not known_all,
        "outcomes": {k: outcomes.get(k, 0) for k in ("solved", "honest refusal", "timeout", "cap", "other failure")},
        "per_task": {t: v for t, v in sorted(per_task.items())},
    }


def paired_vs(base, arm, draws=BOOT_DRAWS, seed=BOOT_SEED):
    tasks = sorted(set(base["per_task"]) & set(arm["per_task"]))
    if not tasks:
        return None
    b = [base["per_task"][t] for t in tasks]
    a = [arm["per_task"][t] for t in tasks]

    def diff(idx):
        return (sum(a[i][0] for i in idx) / sum(a[i][1] for i in idx)
                - sum(b[i][0] for i in idx) / sum(b[i][1] for i in idx))

    rng = random.Random(seed)
    n = len(tasks)
    boots = sorted(diff([rng.randrange(n) for _ in range(n)]) for _ in range(draws))
    return {
        "tasks": n,
        "per_task": [{"task": t, "arm": f"{a[i][0]}/{a[i][1]}", "pi": f"{b[i][0]}/{b[i][1]}",
                      "difference": a[i][0] / a[i][1] - b[i][0] / b[i][1]} for i, t in enumerate(tasks)],
        "rate_difference": diff(range(n)),
        "ci95": [boots[int(0.025 * draws)], boots[int(0.975 * draws) - 1]],
        "draws": draws, "seed": seed,
    }


def find_arm_dir(results, name):
    hits = sorted(glob.glob(os.path.join(results, name)) + glob.glob(os.path.join(results, "v2-*-" + name)))
    hits = [h for h in hits if os.path.isfile(os.path.join(h, "results.jsonl"))]
    return hits[0] if hits else None


def analyse(results=DEFAULT_RESULTS):
    arms, missing = [], []
    for label, pattern in ARMS:
        d = find_arm_dir(results, pattern)
        if d is None:
            missing.append({"label": label, "pattern": pattern})
            continue
        arms.append(analyse_arm(label, d))
    base = next((a for a in arms if a["label"] == "Pi"), None)
    for a in arms:
        a["paired_vs_pi"] = paired_vs(base, a) if base and a is not base else None
    return {"arms": arms, "missing": missing}


def fmt(x, nd=0):
    if x is None:
        return "-"
    return f"{x:,.{nd}f}"


def markdown(res):
    out = ["| Arm | Solvable | Impossible strict / adjudicated / refused | Refused solvable | Median s "
           "| Median prompt tok (known) | Median 1st-request tok | Median 1st agent-request tok (tools) | Median calls "
           "| Timeouts | Caps | s / solved | prompt tok / solved | Solve-rate diff vs Pi [95% CI] |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in res["arms"]:
        p = a["paired_vs_pi"]
        pd = (f"{p['rate_difference']:+.3f} [{p['ci95'][0]:+.3f}, {p['ci95'][1]:+.3f}]" if p else "reference")
        tps = fmt(a["prompt_tokens_per_solved"]) + (" (lower bound)" if a["prompt_tokens_per_solved_is_lower_bound"] else "")
        out.append(f"| {a['label']} | {a['solvable_passed']}/{a['solvable_attempts']} "
                   f"| {a['impossible_strict_passed']} / {fmt(a['impossible_adjudicated_passed'])} / "
                   f"{a['impossible_refused']} of {a['impossible_attempts']} "
                   f"| {a['refused_solvable']} | {fmt(a['median_seconds'], 1)} "
                   f"| {fmt(a['median_prompt_tokens'])} ({a['prompt_tokens_known']}/{a['attempts']}) "
                   f"| {fmt(a['median_first_request_prompt_tokens'])} "
                   f"| {fmt(a['median_first_agent_request_prompt_tokens'])} ({', '.join(map(str, a['first_agent_request_tools']))}) "
                   f"| {fmt(a['median_model_calls'], 1)} "
                   f"| {a['timeouts']} | {a['cap_hits']} | {fmt(a['seconds_per_solved'], 1)} | {tps} | {pd} |")
    out += ["", "| Arm | Solved | Refused impossible (any wording) | Timeout | Cap | Other failure | Finish reasons (relay) |",
            "|---|---|---|---|---|---|---|"]
    for a in res["arms"]:
        o = a["outcomes"]
        fr = ", ".join(f"{k} {v}" for k, v in sorted(a["finish_reasons"].items()))
        out.append(f"| {a['label']} | {o['solved']} | {o['honest refusal']} | {o['timeout']} | {o['cap']} "
                   f"| {o['other failure']} | {fr} |")
    for a in res["arms"]:
        p = a["paired_vs_pi"]
        if not p:
            continue
        out += ["", f"Paired vs Pi, {a['label']} ({p['tasks']} solvable tasks, task-clustered bootstrap, "
                f"{p['draws']} draws, seed {p['seed']}):", "", "| Task | Arm | Pi | Difference |", "|---|---|---|---|"]
        out += [f"| {t['task']} | {t['arm']} | {t['pi']} | {t['difference']:+.2f} |" for t in p["per_task"]]
    if res["missing"]:
        out += ["", "Not found (skipped): " + ", ".join(f"{m['label']} ({m['pattern']})" for m in res["missing"])]
    partial = [a["label"] for a in res["arms"] if a["attempts"] < 60]
    if partial:
        out += ["", "Partial arms (fewer than 60 attempts; may still be running): " + ", ".join(partial)]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=DEFAULT_RESULTS)
    ap.add_argument("--out", help="write the full summary as JSON to this path")
    a = ap.parse_args(argv)
    res = analyse(a.results)
    print(markdown(res))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
        print(f"\nJSON written to {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
