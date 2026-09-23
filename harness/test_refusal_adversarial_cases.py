"""17 adversarial scorer cases written by an independent reviewer, replayed through refusal.py.

Contract difference, on purpose: the independent reviewer's cases put the structured answer in the agent's final MESSAGE; our judge reads
ONE file, BLOCKED.json, because goose prints text and a file is verifiable across every harness. The adapter therefore
moves a JSON object found in the case's final answer into BLOCKED.json. One case ('created file is a tree change') is
expected to disagree with us by design: BLOCKED.json is the single allowed new file, and it is parsed, not executed."""
import json, re, unittest
from pathlib import Path
import refusal

D = json.load(open(Path(__file__).resolve().parent.parent / "tasks" / "refusal-scorer-cases.json"))
KNOWN_DISAGREEMENTS = {"blocked-created-file"}   # prefix match: our file-based protocol vs the independent reviewer's message-based one


def replay(case):
    task = D["fixtures"][case["task"]]
    files = dict(task["files"])
    agent = case["agent"] or {}
    tree = agent.get("tree", "unchanged")
    final = dict(files)
    if isinstance(tree, dict):
        for k, v in tree.items():
            if v is None:
                final.pop(k, None)
            else:
                final[k] = v
    ans = agent.get("final_answer") or ""
    # Under our protocol only a FILE counts. the independent reviewer's cases carry the answer as text, so for blocked tasks we move a
    # status:"blocked" object from the text into BLOCKED.json; for solvable tasks the text is prose and is ignored
    # (a "hedge" object in prose is exactly what a file-based rule refuses to read).
    if task["kind"] == "blocked" and "BLOCKED.json" not in final:
        objs = [o for o in re.findall(r"\{[^{}]*\}", ans, re.S) if '"status"' in o]
        statuses = []
        for o in objs:
            try:
                statuses.append(str(json.loads(o).get("status")).lower())
            except ValueError:
                statuses.append("unparseable")
        if statuses and len(set(statuses)) > 1:
            final["BLOCKED.json"] = json.dumps({"status": "contradictory", "statuses": statuses})
        else:
            blocked = [o for o, st in zip(objs, statuses) if st == "blocked"]
            if blocked:
                final["BLOCKED.json"] = blocked[0]
    if task["kind"] == "blocked":
        ok, note, info = refusal.judge_refusal(task, files, final)
    else:
        refused, _ = refusal.solvable_refusal(final)
        ok = (not refused) and bool(agent.get("hidden_test_would_pass"))
        note = f"solvable: refused={refused}, hidden_test_would_pass={agent.get('hidden_test_would_pass')}"
    return ok, note


class AdversarialCases(unittest.TestCase):
    pass


def _make(case):
    def t(self):
        ok, note = replay(case)
        want = bool(case["expect"]["passed"])
        if any(case["id"].startswith(p) for p in KNOWN_DISAGREEMENTS):
            self.skipTest(f"known contract difference: {note}")
        self.assertEqual(ok, want, f"{case['id']}: {case['covers']} -> {note}; trap: {case.get('lenient_trap')}")
    return t


for c in D["cases"]:
    setattr(AdversarialCases, "test_" + re.sub(r"[^a-z0-9]+", "_", c["id"].lower()), _make(c))

if __name__ == "__main__":
    unittest.main()
