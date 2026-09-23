#!/usr/bin/env python3
"""Cloud arm on the owner's subscription: Claude Code with its own tools, same frozen tasks, same hidden tests and
refusal judge. Runs on the HOST in a throwaway dir per task (Claude Code needs network, so the offline workroom cannot
hold the agent); scoring still happens in the workroom. One run per task (illustrative arm)."""
import argparse, json, os, shutil, subprocess, tempfile, time
from pathlib import Path
import importlib.util
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bench_run", HERE / "run.py"); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
import refusal
ap = argparse.ArgumentParser()
ap.add_argument("--taskfile", default=str(HERE / str(HERE.parent / "tasks" / "tasks-v2-frozen.jsonl"))); ap.add_argument("--out", required=True)
ap.add_argument("--model", default="claude-opus-5-5"); ap.add_argument("--only"); ap.add_argument("--timeout", type=int, default=900)
ap.add_argument("--claude", default=os.path.expanduser("~/.local/share/mise/installs/claude/latest/claude"))
a = ap.parse_args()
tasks = [json.loads(l) for l in open(a.taskfile) if l.strip()]
if a.only: tasks = [t for t in tasks if t["id"] in set(a.only.split(","))]
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
(out / "config.json").write_text(json.dumps({"agent": "claude-code", "model": a.model, "protocol": "v2", "runs": 1,
    "note": "host-side agent run; scoring in the offline workroom; illustrative arm",
    "claude_version": subprocess.run([a.claude, "--version"], capture_output=True, text=True).stdout.strip(),
    "tasks_sha": R.sha(a.taskfile)}, indent=1))
with open(out / "results.jsonl", "a") as rf:
    for t in tasks:
        work = Path(tempfile.mkdtemp(prefix="claude-arm-", dir=None))
        R.write_tree(work, t["files"])
        prompt = t["prompt"] + R.PROMPT_TAIL + R.REFUSAL_TAIL
        t0 = time.time()
        try:
            p = subprocess.run([a.claude, "-p", "--model", a.model, "--dangerously-skip-permissions", "--no-session-persistence",
                                "--setting-sources", "", "--strict-mcp-config", "--output-format", "json", prompt],
                               cwd=work, capture_output=True, text=True, timeout=a.timeout)
            why, rc = "finished", p.returncode
            try: meta = json.loads(p.stdout)
            except ValueError: meta = {"raw": (p.stdout + p.stderr)[-2000:]}
        except subprocess.TimeoutExpired:
            why, rc, meta = "timeout", -1, {}
        secs = time.time() - t0
        final, skipped = R.read_tree(work)
        changed, deleted, created = R.diff_files(t["files"], final)
        tag = R.safe_id(t["id"]) + "-r0"
        (out / f"{tag}.final.json").write_text(json.dumps({"files": final, "unreadable": skipped}, sort_keys=True))
        (out / f"{tag}.claude.json").write_text(json.dumps(meta, indent=1))
        try: passed, note, tail = R.score(t, final)
        except Exception as e: passed, note, tail = False, f"scoring error: {e}", ""
        fr = refusal.find_refusal(final)
        refused = isinstance(fr, dict); blocker = refusal.blocker_codes(fr) if refused else []
        u = meta.get("usage") or {}
        row = {"task": t["id"], "kind": t["kind"], "group": t.get("group"), "repeat": 0, "passed": passed, "note": note,
               "refused": refused, "blocker": blocker, "refused_solvable": refused and t["kind"] != "blocked",
               "seconds": round(secs, 1), "ended": why, "agent_exit": rc, "changed": changed, "created": created, "deleted": deleted,
               "edited_tests": sorted(f for f in changed + deleted if R.TEST_RE.search(f)),
               "cost_usd": meta.get("total_cost_usd"), "tokens_in": u.get("input_tokens"), "tokens_out": u.get("output_tokens"),
               "model_seen": list((meta.get("modelUsage") or {}).keys()), "num_turns": meta.get("num_turns"),
               "test_output_tail": tail[-400:]}
        rf.write(json.dumps(row) + "\n"); rf.flush()
        print(f"{t['id']:30} {'PASS' if passed else 'fail'} {secs:5.0f}s turns={meta.get('num_turns')} model={row['model_seen']} {note[:50]}", flush=True)
        shutil.rmtree(work, ignore_errors=True)
rows = [json.loads(l) for l in open(out / "results.jsonl")]
s = {"agent": "claude-code", "model": a.model, "passed": sum(r["passed"] for r in rows), "n": len(rows),
     "cost_usd_equiv": round(sum((r.get("cost_usd") or 0) for r in rows), 2),
     "by_kind": {k: f"{sum(r['passed'] for r in rows if r['kind']==k)}/{sum(1 for r in rows if r['kind']==k)}" for k in ("unittest", "blocked")}}
(out / "summary.json").write_text(json.dumps(s, indent=1)); print(json.dumps(s))
