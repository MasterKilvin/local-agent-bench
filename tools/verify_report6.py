#!/usr/bin/env python3
"""Recompute every number in reports/06-seven-agent-tools.md from the published result rows; exit 1 on any mismatch.

  python3 tools/verify_report6.py            check the report
  python3 tools/verify_report6.py --print    print the recomputed tables and figures (for writing the report)

Inputs, per arm under results/v2/<arm>/: results.jsonl (one row per attempt), relay-calls.jsonl (one row per engine
call, logged by the shared relay) and refusals-adjudicated.json (written by harness/rescore_refusals.py with
analysis/refusal-adjudication-20260923b.json). Standard library only; independent of analysis/seven_arms.py.

Two checks:
  1. every recomputed table row and figure below appears verbatim in the report;
  2. every number written in the report is either one of the recomputed figures or a listed constant (task counts,
     settings, versions, dates, citations). A number that is neither fails the check.
"""
import json, os, random, re, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RES = REPO / "results" / "v2"
REPORT = REPO / "reports" / "06-seven-agent-tools.md"
ARMS = [("Pi 0.87.0", "1-baseline-pi-27b"), ("Goose 1.51.0", "2-goose-27b"), ("OpenCode 1.18.32", "3-opencode-27b"),
        ("Oh My Pi 18.2.11", "11-omp-27b"), ("Qwen Code 0.24.4", "12-qwencode-27b"),
        ("DSH Minimal", "13-dsh-min-27b"), ("DSH Standard", "14-dsh-std-27b")]
CHAT = "/v1/chat/completions"
CAP, TIMEOUT = 30, 900
DRAWS, SEED = 10000, 20260923
LONG_GAP = 200          # seconds between one model call's end and the next call's start (or the attempt's end)


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def med(xs):
    return statistics.median(xs)


def n0(x):
    return f"{x:,.0f}"


def n1(x):
    return f"{x:,.1f}"


def arm_stats(d):
    rows = jl(RES / d / "results.jsonl")
    relay = jl(RES / d / "relay-calls.jsonl")
    chat = sorted((c for c in relay if c.get("path") == CHAT), key=lambda c: c["t"])
    adj = json.load(open(RES / d / "refusals-adjudicated.json"))["rows"]
    solv = [r for r in rows if r["kind"] == "unittest"]
    imp = [r for r in rows if r["kind"] == "blocked"]
    s = {"attempts": len(rows), "solved": sum(bool(r["passed"]) for r in solv), "solvable": len(solv),
         "strict": sum(bool(r["passed"]) for r in imp), "adjudicated": sum(bool(x["adjudicated_passed"]) for x in adj),
         "impossible": len(imp), "refused_any": sum(bool(r["refused"]) for r in imp),
         "refused_solvable": sum(bool(r["refused_solvable"]) for r in rows),
         "median_s": med([r["seconds"] for r in rows]), "total_s": sum(r["seconds"] for r in rows),
         "max_s": max(r["seconds"] for r in rows), "http_not_200": sum(c["status"] != 200 for c in relay),
         "timeouts": sum(r["ended"] == "timeout" for r in rows)}
    assert len(adj) == len(imp)
    ptok, first, tools, calls, gaps, model_s, match = [], [], set(), [], [], 0.0, 0
    per_task, gap_attempts, known_tok = {}, set(), 0
    for r in rows:
        mine = [c for c in chat if r["t_start"] <= c["t"] <= r["t_end"]]
        calls.append(len(mine))
        model_s += sum(c["total_s"] for c in mine)
        known_tok += sum(c["prompt_tokens"] for c in mine if isinstance(c.get("prompt_tokens"), int))   # every reported call
        if mine and all(isinstance(c.get("prompt_tokens"), int) for c in mine):
            ptok.append(sum(c["prompt_tokens"] for c in mine))
        agent = [c for c in mine if c.get("n_tools")]
        first.append(agent[0]["prompt_tokens"])
        tools.add(agent[0]["n_tools"])
        pts = [r["t_start"]] + [p for c in mine for p in (c["t"], c["t"] + c["total_s"])] + [r["t_end"]]
        gaps += [pts[i + 1] - pts[i] for i in range(0, len(pts) - 1, 2) if pts[i + 1] - pts[i] > LONG_GAP]
        match += sum(c.get("prompt_tokens") or 0 for c in mine) == r["tokens_in"]
        if any(pts[i + 1] - pts[i] > LONG_GAP for i in range(0, len(pts) - 1, 2)):
            gap_attempts.add((r["task"], r["repeat"]))
        if r["kind"] == "unittest":
            p = per_task.setdefault(r["task"], [0, 0])
            p[0] += bool(r["passed"]); p[1] += 1
    s.update(median_ptok=med(ptok), ptok_known=len(ptok), first=med(first), tools=sorted(tools),
             median_calls=med(calls), max_calls=max(calls), caps=sum(n >= CAP for n in calls),
             s_per_solved=s["total_s"] / s["solved"], ptok_per_solved=known_tok / s["solved"],
             ptok_lower_bound=len(ptok) < len(rows), gaps=gaps, gap_attempts=len(gap_attempts), model_s=model_s, tok_match=match,
             per_task=per_task)
    return s


def paired(base, arm):
    tasks = sorted(base["per_task"])
    assert tasks == sorted(arm["per_task"]) and len(tasks) == 16
    b = [base["per_task"][t] for t in tasks]
    a = [arm["per_task"][t] for t in tasks]

    def diff(idx):
        return sum(a[i][0] for i in idx) / sum(a[i][1] for i in idx) - sum(b[i][0] for i in idx) / sum(b[i][1] for i in idx)

    rng = random.Random(SEED)
    n = len(tasks)
    boots = sorted(diff([rng.randrange(n) for _ in range(n)]) for _ in range(DRAWS))
    return diff(range(n)), boots[int(0.025 * DRAWS)], boots[int(0.975 * DRAWS) - 1]


def pts(x):
    """A rate difference in percentage points, signed; minus sign as in the report."""
    v = round(100 * x, 1)
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.1f}"


def compute():
    st = {label: arm_stats(d) for label, d in ARMS}
    pi = st["Pi 0.87.0"]
    rows, figs = [], {}
    for label, _d in ARMS:
        s = st[label]
        if s is pi:
            dcol = "reference"
        else:
            d, lo, hi = paired(pi, s)
            dcol = f"{pts(d)} [{pts(lo)}, {pts(hi)}]"
        tok = n0(s["median_ptok"]) + ("" if s["ptok_known"] == s["attempts"] else f" ({s['ptok_known']} of {s['attempts']})")
        tps = ("≥ " if s["ptok_lower_bound"] else "") + n0(s["ptok_per_solved"])
        rows.append(f"| {label} | {s['solved']} of {s['solvable']} | {s['strict']} → {s['adjudicated']} of {s['impossible']} "
                    f"| {s['refused_solvable']} | {n1(s['median_s'])} | {tok} | {n0(s['first'])} "
                    f"| {n1(s['s_per_solved'])} | {tps} | {dcol} |")
    tool_rows = [f"| {label} | {', '.join(map(str, st[label]['tools']))} | {n0(st[label]['first'])} "
                 f"| {st[label]['median_calls']:g} | {st[label]['max_calls']} | {n1(st[label]['max_s'])} |" for label, _ in ARMS]
    m, sd = st["DSH Minimal"], st["DSH Standard"]
    q, o = st["Qwen Code 0.24.4"], st["Oh My Pi 18.2.11"]
    solved = [st[l]["solved"] for l, _ in ARMS]
    figs.update({
        "solved range": f"{min(solved)} to {max(solved)} of 48",
        "dsh min solved": f"{m['solved']} of 48", "dsh std solved": f"{sd['solved']} of 48",
        "std/min prompt": f"{sd['median_ptok'] / m['median_ptok']:.1f} times",
        "min/pi prompt": f"{n0(m['median_ptok'])} against {n0(pi['median_ptok'])}",
        "qwen/pi prompt": f"{q['median_ptok'] / pi['median_ptok']:.1f} times",
        "std first/min first": f"{sd['first'] / m['first']:.0f} times",
        "min gaps": f"{len(m['gaps'])} pauses",
        "min gaps s": f"{n0(sum(m['gaps']))} of its {n0(m['total_s'])} seconds",
        "min gap attempts share": f"{n1((m['total_s'] - sum(m['gaps'])) / m['solved'])} seconds per solved task",
        "other arms gaps": "none" if all(not st[l]["gaps"] for l, _ in ARMS if l != "DSH Minimal") else "SOME",
        "min model s": f"{n0(m['model_s'])} seconds",
        "dsh tok match": f"{m['tok_match']} of 60 and {sd['tok_match']} of 60",
        "max calls all": f"{max(st[l]['max_calls'] for l, _ in ARMS)} model calls",
        "max s all": f"{n1(max(st[l]['max_s'] for l, _ in ARMS))} seconds",
        "timeouts caps": "no" if all(st[l]["timeouts"] == 0 and st[l]["caps"] == 0 for l, _ in ARMS) else "SOME",
        "http": "every" if all(st[l]["http_not_200"] == 0 for l, _ in ARMS) else "NOT every",
        "adj all but std": all(st[l]["adjudicated"] == 12 for l, _ in ARMS if l != "DSH Standard") and sd["adjudicated"] == 11,
        "refused any": all(st[l]["refused_any"] == 12 for l, _ in ARMS),
        "strict range": f"{min(st[l]['strict'] for l, _ in ARMS)} to {max(st[l]['strict'] for l, _ in ARMS)} of 12",
        "pi s/solved": n1(pi["s_per_solved"]), "min s/solved": n1(m["s_per_solved"]),
        "min median s": n1(m["median_s"]), "pi median s": n1(pi["median_s"]),
        "min tok/solved": n0(m["ptok_per_solved"]), "pi tok/solved": n0(pi["ptok_per_solved"]),
        "std tok/solved": n0(sd["ptok_per_solved"]), "qwen tok/solved": n0(q["ptok_per_solved"]),
        "omp first": n0(o["first"]), "qwen first": n0(q["first"]), "pi first": n0(pi["first"]),
        "min first": n0(m["first"]), "std first": n0(sd["first"]),
    })
    tps = [st[l]["ptok_per_solved"] for l, _ in ARMS]
    figs["tok/solved spread"] = f"{max(tps) / min(tps):.1f} times"
    figs["min gap attempts"] = {1: "in one attempt", 2: "in two attempts", 3: "in three attempts"}.get(
        m["gap_attempts"], "MANY")
    figs["min 300s gaps"] = {3: "three of them lasted"}.get(sum(295 <= g <= 310 for g in m["gaps"]), "OTHER")
    figs["min 300s gap len"] = f"about {max(m['gaps']):.0f} seconds"
    # Peak prompt and output sizes come from the relay (what the engine saw), not from agent-reported result fields
    calls = [c for _l, d in ARMS for c in jl(RES / d / "relay-calls.jsonl")]
    figs["peak"] = f"largest single prompt was {n0(max(c.get('prompt_tokens') or 0 for c in calls))} tokens"
    over = {l: sum((c.get("completion_tokens") or 0) > 8192 for c in jl(RES / d / "relay-calls.jsonl")) for l, d in ARMS}
    figs["over 8192"] = f"{sum(over.values())} model calls returned more than 8192 output"
    figs["max output"] = f"the largest was {n0(max(c.get('completion_tokens') or 0 for c in calls))}"
    # Tighter lower bounds for the arms with one incomplete attempt: every call that did report usage, over solved
    for l, d, label in ((ARMS[1][0], ARMS[1][1], "tight goose"), (ARMS[3][0], ARMS[3][1], "tight omp")):
        res_rows = jl(RES / d / "results.jsonl")
        chat = [c for c in jl(RES / d / "relay-calls.jsonl") if c.get("path") == CHAT]
        tot = sum(c.get("prompt_tokens") or 0 for c in chat if any(r["t_start"] <= c["t"] <= r["t_end"] for r in res_rows))
        figs[label] = f"{n0(round(tot / st[l]['solved']))}"
    figs["differing tasks"] = f"Solve counts differ on {len([t for t in st[ARMS[0][0]]['per_task'] if len({st[l]['per_task'][t][0] for l, _ in ARMS}) > 1])} of the 16 tasks"
    ci = [paired(pi, st[l]) for l, _ in ARMS if l != "Pi 0.87.0"]
    figs["all intervals include zero"] = all(lo <= 0 <= hi for _d, lo, hi in ci)
    rs = {l: [(r["task"]) for r in jl(RES / d / "results.jsonl") if r["refused_solvable"]] for l, d in ARMS}
    figs["refused solvable only retry"] = all(set(v) <= {"build-retry-regression"} for v in rs.values())
    counts = [str(len(rs[l])) for l, _ in ARMS if rs[l]]
    figs["refused solvable counts"] = f"({', '.join(counts[:-1])} and {counts[-1]} attempts)"
    # per-task notes quoted in the report
    pt = {l: st[l]["per_task"] for l, _ in ARMS}
    figs["csv"] = ", ".join(f"{l.split(' 0')[0].split(' 1')[0]} {pt[l]['build-csv-dry-run'][0]}" for l, _ in ARMS)
    figs["retry"] = ", ".join(f"{l.split(' 0')[0].split(' 1')[0]} {pt[l]['build-retry-regression'][0]}" for l, _ in ARMS)
    return st, rows, tool_rows, figs


# Numbers in the report that are settings, counts of the design, versions, dates or citations, not results.
CONSTANTS = {
    "0.87.0", "1.51.0", "1.18.32", "18.2.11", "0.24.4", "0.1.5", "0.1.7", "0.33.3", "3.8", "27", "27B", "32", "0.1.1", "0.73.1", "127.0.0.1", "11435", "90.6", "86.1", "4.1",
    "20", "16", "4", "3", "48", "12", "60", "30", "900", "300", "65536", "64", "8192", "10000", "10,000", "20260923",
    "95", "2026", "22", "23", "1", "2", "5", "6", "7", "8", "9", "10", "11", "13", "14", "19", "4283", "11.9", "1200",
    "1,200", "0.6", "0.95", "1.0", "500", "V4.1", "200", "1M", "2-2", "1", "3.8-27B", "24",
}


def main():
    st, rows, tool_rows, figs = compute()
    if "--print" in sys.argv:
        print("\n".join(rows)); print(); print("\n".join(tool_rows)); print()
        for k, v in figs.items():
            print(f"{k}: {v}")
        return
    text = REPORT.read_text()
    flat = re.sub(r"\s*\n\s*", " ", text)          # table rows and figures may wrap across lines
    bad = []
    expected = rows + tool_rows + [v for v in figs.values() if isinstance(v, str)]
    for e in expected:
        if e not in text and e not in flat:
            bad.append(f"missing or different: {e}")
    for k, v in figs.items():
        if v is False or (isinstance(v, str) and v.isupper()):
            bad.append(f"claim not supported by the rows: {k}")
    allowed = set(CONSTANTS)
    for e in expected:
        allowed.update(re.findall(r"\d[\d,]*(?:\.\d+)?", e))
    for i, line in enumerate(text.splitlines(), 1):
        clean = re.sub(r"`[^`]*`|\(https?://[^)]*\)|\[[^\]]*\]\(https?://[^)]*\)|RTX \d+", "", line)   # code, links, GPU
        for num in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)*", clean):
            num = num.rstrip(",")
            if num not in allowed:
                bad.append(f"line {i}: number {num} is neither recomputed nor a listed constant")
    for b in bad:
        print("FAIL", b)
    print(f"verify_report6: {len(expected)} recomputed items, {'FAIL' if bad else 'all match'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
