#!/usr/bin/env python3
"""Assemble bench v2 task JSON files into one frozen tasks jsonl, with shape checks. Usage: assemble_v2.py OUT.jsonl DIR..."""
import json, sys
from pathlib import Path

REQ = {"unittest": ("id", "group", "prompt", "files", "hidden_tests", "reference_files"),
       "blocked": ("id", "group", "prompt", "files", "blocker")}
out = Path(sys.argv[1]); rows, seen, problems = [], set(), []
for d in sys.argv[2:]:
    for p in sorted(Path(d).glob("*.json")):
        try:
            t = json.loads(p.read_text())
        except ValueError as e:
            problems.append(f"{p}: bad json {e}"); continue
        kind = t.get("kind")
        for k in REQ.get(kind, ()):
            if k not in t: problems.append(f"{p}: missing {k}")
        if kind not in REQ: problems.append(f"{p}: kind {kind!r}")
        if t.get("id") in seen: problems.append(f"{p}: duplicate id {t.get('id')}")
        seen.add(t.get("id"))
        n = len(t.get("files", {}))
        if not 3 <= n <= 7: problems.append(f"{p}: {n} files")
        if kind == "unittest":
            if set(t["reference_files"]) - set(t["files"]) and t.get("group") != "build":
                problems.append(f"{p}: reference file not in files")
            if "test_hidden.py" not in t["hidden_tests"]: problems.append(f"{p}: hidden test must be test_hidden.py")
        if kind == "blocked" and not (t.get("blocker") or {}).get("codes"): problems.append(f"{p}: no blocker codes")
        size = sum(len(v) for v in t.get("files", {}).values())
        if size > 60000: problems.append(f"{p}: {size} bytes of files")
        t["source"] = f"tasks-v2/{Path(d).name}/{p.name}"
        rows.append(t)
out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
print(f"{len(rows)} tasks -> {out}; {len(problems)} problems")
for x in problems: print("  ", x)
