#!/usr/bin/env python3
"""Re-judge every saved attempt on the impossible tasks with an ADJUDICATED accepted-code list (the frozen codes plus
the synonyms accepted by a blind, rubric-first adjudication), from the saved final trees. Prints strict vs adjudicated
per arm. Never overwrites results.jsonl: writes <run>/refusals-adjudicated.json beside it.
Usage: rescore_refusals.py ADJUDICATION.json RESULTS_DIR..."""
import json, sys, os, glob
import refusal
adj = json.load(open(sys.argv[1]))          # {"accepted": {task: [codes...]}, ...}
tasks = {t["id"]: t for t in (json.loads(l) for l in open(os.path.join(os.path.dirname(__file__), "..", "tasks", "tasks-v2-frozen.jsonl")))}
print(f"{'run':44} {'strict':>7} {'adjudicated':>12}  changed attempts")
for d in sys.argv[2:]:
    if not os.path.exists(d + "/results.jsonl"): continue
    strict = adjud = 0; changed = []; out = []
    for l in open(d + "/results.jsonl"):
        r = json.loads(l)
        if r["kind"] != "blocked": continue
        strict += r["passed"]
        t = dict(tasks[r["task"]]); t["blocker"] = {"codes": sorted(set(t["blocker"]["codes"]) | set(adj["accepted"].get(r["task"], [])))}
        fp = f"{d}/{r['task']}-r{r['repeat']}.final.json"
        fin = json.load(open(fp))["files"] if os.path.exists(fp) else {}
        ok, note, info = refusal.judge_refusal(t, tasks[r["task"]]["files"], fin)
        adjud += ok
        if ok != r["passed"]: changed.append(f"{r['task'][:22]}-r{r['repeat']}:{'strict-fail→adj-pass' if ok else 'strict-pass→adj-fail'}")
        out.append({"task": r["task"], "repeat": r["repeat"], "strict_passed": r["passed"], "adjudicated_passed": ok, "note": note, "blocker": info.get("blocker")})
    json.dump({"adjudication": os.path.basename(sys.argv[1]), "rows": out}, open(d + "/refusals-adjudicated.json", "w"), indent=1)
    print(f"{os.path.basename(d):44} {strict:>4}/12 {adjud:>9}/12  {', '.join(changed) if changed else '-'}")
