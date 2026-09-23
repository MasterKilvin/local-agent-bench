#!/usr/bin/env python3
"""Owner review minutes: how long does a person need to check an agent's work before trusting it?

Blind, randomized, timestamped. Shows each attempt's task and diff WITHOUT the scorer's verdict; records active reading
time, the decision (merge / reject / unsure), confidence, and only afterwards reveals the verdict so 'wrongly trusted'
can be counted. One rater's burden on this set - an observation, not a claim (PLAN-v2 §6b).

Usage: review_minutes.py RESULTS_DIR [--repeat 0] [--seed 7] [--out RESULTS_DIR/review-minutes.jsonl]
The clock starts when the diff is shown and stops at Enter; you can correct the number if you were interrupted.
"""
import argparse, json, random, sys, time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results"); ap.add_argument("--repeat", type=int, default=0); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out"); ap.add_argument("--taskfile", default=str(Path(__file__).with_name("tasks-v2.jsonl")))
    a = ap.parse_args()
    R = Path(a.results); out = Path(a.out) if a.out else R / "review-minutes.jsonl"
    tasks = {t["id"]: t for t in (json.loads(l) for l in open(a.taskfile) if l.strip())}
    rows = [json.loads(l) for l in open(R / "results.jsonl") if l.strip()]
    rows = [r for r in rows if r["repeat"] == a.repeat]
    done = {json.loads(l)["task"] for l in open(out)} if out.exists() else set()
    rows = [r for r in rows if r["task"] not in done]
    random.Random(a.seed).shuffle(rows)
    print(f"{len(rows)} attempts to review, blind. Verdicts are revealed at the end.\n")
    for i, r in enumerate(rows, 1):
        t = tasks[r["task"]]
        tag = f"{r['task'].replace(':', '_')}-r{r['repeat']}"
        diff = (R / f"{tag}.diff.patch").read_text() if (R / f"{tag}.diff.patch").exists() else "<no diff saved>"
        final = json.loads((R / f"{tag}.final.json").read_text())["files"] if (R / f"{tag}.final.json").exists() else {}
        print("=" * 100); print(f"[{i}/{len(rows)}] TASK {r['task']} ({t.get('group')})\n"); print(t["prompt"]); print("-" * 100)
        if "BLOCKED.json" in final:
            print("The agent REFUSED. BLOCKED.json:\n" + final["BLOCKED.json"])
        print(diff if diff.strip() else "<the agent changed nothing>")
        print("-" * 100)
        t0 = time.time()
        input("The clock is running from now. Read, decide, then press Enter (stops the clock). ")
        secs = round(time.time() - t0, 1)
        fix = input(f"Recorded {secs:.0f} s. Enter to keep, or type the honest number of seconds if you were interrupted: ").strip()
        if fix:
            try:
                secs = float(fix)
            except ValueError:
                pass
        decision = ""
        while decision not in ("merge", "reject", "unsure"):
            decision = input("Decision [merge / reject / unsure]: ").strip().lower()
        conf = ""
        while conf not in ("1", "2", "3", "4", "5"):
            conf = input("Confidence 1-5: ").strip()
        notes = input("One line of notes (optional): ").strip()
        rec = {"task": r["task"], "repeat": r["repeat"], "group": t.get("group"), "kind": t["kind"], "order": i,
               "active_seconds": secs, "decision": decision, "confidence": int(conf), "notes": notes,
               "scorer_passed": r["passed"], "scorer_note": r["note"], "recorded_at": time.strftime("%F %T")}
        with open(out, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    print("\nDone. Verdicts:")
    for l in open(out):
        x = json.loads(l)
        wrong = (x["decision"] == "merge" and not x["scorer_passed"]) or (x["decision"] == "reject" and x["scorer_passed"])
        print(f"  {x['task']:34} you: {x['decision']:6} ({x['confidence']})  scorer: {'PASS' if x['scorer_passed'] else 'FAIL'}  {'<-- wrongly trusted/rejected' if wrong else ''}  {x['active_seconds']:.0f}s")


if __name__ == "__main__":
    main()
