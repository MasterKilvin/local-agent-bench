#!/usr/bin/env python3
"""Copy the working bench harness into harness/ with the standalone adjustments and scrubs of the published copy.

Re-runnable: every file is regenerated from the source tree, so running it twice gives the same bytes.

  python3 tools/sync_harness.py --source <bench dir> [--workroom <workroom.sh>]     (or BENCH_SOURCE=<bench dir>)
  python3 tools/sync_harness.py --source <bench dir> --results v2-20260923-13-dsh-min-27b [...]
  python3 tools/sync_harness.py --source <bench dir> --results-only --results <dir> ...

Harness adjustments (the same ones the first published copy carries, see harness/FREEZE.md "Published copy"):
  * paths point inside this repository: workroom.sh sits next to run.py; task files live in ../tasks/
    (tasks-v2.jsonl -> tasks-v2-frozen.jsonl, tasks-v2/anchors.jsonl -> tasks-anchors.jsonl, scorer cases likewise);
  * shell scripts run from their own folder instead of a fixed checkout path, and without the local GPU-lock wrapper;
  * the KV-cache arm, which restarts a local system service, is replaced by a note;
  * the container image with extra libraries is called bench-agentroom-deps; its recipe is Containerfile.deps;
  * reviewer and assistant names in comments become neutral wording.
Scrubs applied to everything copied (harness and results): the local model-blob path -> <ollama-blobs>, the image
name above, and timestamps with a local UTC offset -> UTC "Z" (results metadata only; task code may hold offsets).
Anything a rule does not cover is left for tools/scan.py, which fails the run if an identifier remains.

Not copied on purpose: test_arms_v2.py (drives arms-v2.sh against the private layout: GPU-lock wrapper, system
service, private task paths), *.bak-* backups, logs, agent transcripts (*.agent.jsonl, *.agent.stderr, *.claude.json)
and working notes (SUMMARY-*.md) in results.
"""
import argparse, datetime, hashlib, os, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "harness"
REVIEWER = [None]   # the external reviewer's name, read from the source test file name at run time

# ---- scrubs shared by harness and results ---------------------------------------------------------------------
HOME_BLOBS = re.compile(r"/home/(?!worker\b)[^/\s\"']+/\.ollama/models/blobs")
OFFSET_TS = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:\d{2})\b")


def to_utc(m):
    base = datetime.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{m.group(4)}")
    return base.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + (m.group(3) or "") + "Z"


def scrub(text, timestamps=False):
    text = HOME_BLOBS.sub("<ollama-blobs>", text)
    text = re.sub(r"bench-agentroom-(?!deps\b)[a-z0-9]+", "bench-agentroom-deps", text)   # extra-library image
    if timestamps:
        text = OFFSET_TS.sub(to_utc, text)
    return text


# ---- per-file standalone adjustments ---------------------------------------------------------------------------
TASKS_FROZEN = '../tasks/tasks-v2-frozen.jsonl'
KVQ4_NOTE = ('  5|kvq4)      echo "KV Q4 arm: needs OLLAMA_KV_CACHE_TYPE=q4_0 on the Ollama SERVICE (a restart), same '
             'flash-attention setting as the control; not runnable from here" ; exit 2 ;;\n')


def sub1(pattern, repl, text, name, count=1, flags=0):
    """Apply a required substitution; a missing anchor means the source moved and the rule needs a look."""
    new, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if n == 0:
        sys.exit(f"sync: rule for {name} did not match: {pattern!r}")
    return new


def adj_run(t, n):
    t = sub1(r"\([\w-]+/workroom/workroom\.sh\)", "(harness/workroom.sh)", t, n)
    t = sub1(r'WORKROOM = HERE\.parents\[1\] / "workroom" / "workroom\.sh"', 'WORKROOM = HERE / "workroom.sh"', t, n)
    t = sub1(r'TASKS = HERE / "tasks\.jsonl"', 'TASKS = HERE.parent / "tasks" / "tasks-v2-frozen.jsonl"', t, n)
    t = sub1(r"Mirrors [\w-]+/eval/run_eval\.py and", "Mirrors harness/workroom.sh and", t, n)
    return t


def adj_shell_common(t, n):
    t = re.sub(r'cd "\$\{BENCH_DIR:-/home/[^}]+\}" \|\| exit 1', 'cd "${BENCH_DIR:-$(dirname "$0")}" || exit 1', t)
    t = sub1(r"^cd /home/\S+$", 'cd "$(dirname "$0")"', t, n, flags=re.M) if re.search(r"^cd /home/", t, re.M) else t
    t = re.sub(r"(?<![\w/-])tasks-v2/anchors\.jsonl", "../tasks/tasks-anchors.jsonl", t)
    t = re.sub(r"(?<![\w/.-])tasks-v2\.jsonl", TASKS_FROZEN, t)
    return t


def adj_arms(t, n):
    t = sub1(r"# tools/gpu_run\.py \+ eval/gpu_window\.sh, records", "# the GPU lock wrapper, records", t, n)
    t = adj_shell_common(t, n)
    # KV-cache arm: from its case label up to the first line ending in ';;'
    t = sub1(r"^  5\|kvq4\).*?;;[ \t]*\n", KVQ4_NOTE, t, n, flags=re.M | re.S)
    return t


def adj_overnight(t, n):
    t = sub1(r"\([^()\n]*gpu_slot\)", "(the shared GPU lock)", t, n)
    t = adj_shell_common(t, n)
    t = sub1(r"\.\./\.\./tools/gpu_run\.py \.\./\.\./eval/gpu_window\.sh \./arms-v2\.sh", "./arms-v2.sh", t, n)
    t = sub1(r'(^cd [^\n]*\n)', r'\1mkdir -p logs results\n', t, n, flags=re.M)
    return t


def adj_containerfile_deps(t, n):
    t = sub1(r"\A# Agent room image for [^\n]*",
             "# Agent room image with extra libraries: the benchmark image plus the library versions some task code imports,",
             t, n)
    t = sub1(r"Containerfile\.(?!deps\b)[a-z0-9]+", "Containerfile.deps", t, n, count=0)
    return t


def adj_claude_arm(t, n):
    t = sub1(r'default=str\(HERE / "tasks-v2\.jsonl"\)',
             'default=str(HERE / str(HERE.parent / "tasks" / "tasks-v2-frozen.jsonl"))', t, n)
    t = sub1(r'dir="/home/[^"]+"', "dir=None", t, n)
    return t


def adj_rescore(t, n):
    return sub1(r'os\.path\.dirname\(__file__\), "tasks-v2\.jsonl"',
                'os.path.dirname(__file__), "..", "tasks", "tasks-v2-frozen.jsonl"', t, n)


def adj_test_run(t, n):
    # temporary directories in the system temp dir, not inside the checkout
    t = t.replace(', dir=HERE)', ')').replace('TemporaryDirectory(dir=HERE)', 'TemporaryDirectory()')
    return t


def reviewer_name():
    if REVIEWER[0] is None:
        sys.exit("sync: reviewer name unknown (source test_refusal_<name>_cases.py not found)")
    return re.escape(REVIEWER[0].capitalize())


def adj_test_refusal(t, n):
    return re.sub(rf"# {reviewer_name()}'s case:", "# independent reviewer's case:", t)


def adj_adversarial(t, n):
    r = reviewer_name()
    t = sub1(rf"{r}'s 17 adversarial scorer cases, replayed",
             "17 adversarial scorer cases written by an independent reviewer, replayed", t, n)
    t = re.sub(rf"\b{r}'s", "the independent reviewer's", t)
    t = re.sub(rf"\b{r}Cases\b", "AdversarialCases", t)
    t = sub1(r'Path\(__file__\)\.with_name\("tasks-v2"\) / "scorer-cases" / "refusal-scorer-cases\.json"',
             'Path(__file__).resolve().parent.parent / "tasks" / "refusal-scorer-cases.json"', t, n)
    return t


def ident(t, n):
    return t


# published name -> (source path relative to --source, adjustment)
FILES = {
    "run.py": ("run.py", adj_run),
    "bridge.py": ("bridge.py", ident),
    "refusal.py": ("refusal.py", ident),
    "assemble_v2.py": ("assemble_v2.py", ident),
    "claude_arm.py": ("claude_arm.py", adj_claude_arm),
    "mock_openai.py": ("mock_openai.py", ident),
    "rescore_refusals.py": ("rescore_refusals.py", adj_rescore),
    "review_minutes.py": ("review_minutes.py", ident),
    "pi-maxturns.ts": ("pi-maxturns.ts", ident),
    "arms-v2.sh": ("arms-v2.sh", adj_arms),
    "overnight-v2.sh": ("overnight-v2.sh", adj_overnight),
    "Containerfile": ("Containerfile", ident),
    "Containerfile.deps": ("Containerfile.*", adj_containerfile_deps),   # the one extra-library recipe
    "Modelfile.qwen3.8-27b-64k": ("Modelfile.qwen3.8-27b-64k", ident),
    "Modelfile.qwen3.8-27b-q4-24k": ("Modelfile.qwen3.8-27b-q4-24k", ident),
    "Modelfile.qwen3.8-27b-q8-24k": ("Modelfile.qwen3.8-27b-q8-24k", ident),
    "Modelfile.qwen3-coder-30b-64k": ("Modelfile.qwen3-coder-30b-64k", ident),
    "test_run.py": ("test_run.py", adj_test_run),
    "test_refusal.py": ("test_refusal.py", adj_test_refusal),
    "test_refusal_adversarial_cases.py": ("test_refusal_*_cases.py", adj_adversarial),
    "test_bridge.py": ("test_bridge.py", ident),
    "dsh/driver.py": ("dsh/driver.py", ident),
    "dsh/minimal.patch.yml": ("dsh/minimal.patch.yml", ident),
    "dsh/standard.patch.yml": ("dsh/standard.patch.yml", ident),
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(dst, text, mode_from):
    dst.parent.mkdir(parents=True, exist_ok=True)
    changed = not dst.exists() or dst.read_text() != text
    dst.write_text(text)
    shutil.copymode(mode_from, dst)
    return changed


def find(src, rel):
    """A plain relative path, or a glob that must match exactly one non-backup file."""
    if "*" not in rel:
        return src / rel
    hits = [p for p in src.glob(rel) if ".bak" not in p.name]
    if len(hits) != 1:
        sys.exit(f"sync: {rel} matched {len(hits)} files in the source, expected one")
    return hits[0]


def sync_harness(src, workroom):
    m = re.fullmatch(r"test_refusal_([a-z]+)_cases\.py", find(src, "test_refusal_*_cases.py").name)
    REVIEWER[0] = m.group(1) if m else None
    rows = []
    for pub, (rel, fn) in FILES.items():
        s = find(src, rel)
        text = scrub(fn(s.read_text(), pub))
        changed = write(HARNESS / pub, text, s)
        rows.append((pub, rel, sha(s), sha(HARNESS / pub), changed))
    changed = write(HARNESS / "workroom.sh", scrub(workroom.read_text()), workroom)
    rows.append(("workroom.sh", "../../workroom/workroom.sh", sha(workroom), sha(HARNESS / "workroom.sh"), changed))
    try:
        rev = subprocess.run(["git", "-C", str(src), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True).stdout.strip() or "unknown"
        dirty = subprocess.run(["git", "-C", str(src), "status", "--porcelain", "--"] + [r for _, (r, _f) in FILES.items()],
                               capture_output=True, text=True).stdout.strip()
    except OSError:
        rev, dirty = "unknown", ""
    lines = ["# Harness sync manifest", "",
             f"Written by `tools/sync_harness.py` from the working bench at commit `{rev}`"
             + (" with uncommitted changes" if dirty else "") + ".",
             "Published file | source sha256 (first 16) | published sha256 (first 16)", "--- | --- | ---"]
    lines += [f"`{p}` | `{a[:16]}` | `{b[:16]}`" for p, _r, a, b, _ in rows]
    (HARNESS / "SYNC.md").write_text("\n".join(lines) + "\n")
    for p, _r, _a, _b, ch in rows:
        print(("updated  " if ch else "same     ") + "harness/" + p)


RESULT_SKIP = re.compile(r"(\.agent\.(jsonl|stderr)|\.claude\.json)$|^SUMMARY-.*\.md$")   # agent transcripts stay private;
# SUMMARY-*.md are working notes written during a run, superseded by the reports
RESULT_TS_FILES = {"MANIFEST.txt", "config.json"}


def sync_results(src, names, dest_root):
    for name in names:
        s = (src / "results" / name) if not Path(name).is_absolute() else Path(name)
        if not s.is_dir():
            sys.exit(f"sync: no result dir {s}")
        m = re.fullmatch(r"v2-\d{8}-(.+)", s.name)
        if not m:
            sys.exit(f"sync: {s.name} is not a v2-YYYYMMDD-<arm> result dir")
        d = dest_root / m.group(1)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        n = 0
        for f in sorted(s.rglob("*")):
            if f.is_dir() or RESULT_SKIP.search(f.name):
                continue
            out = d / f.relative_to(s)
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = f.read_text()
            except UnicodeDecodeError:
                shutil.copy2(f, out); n += 1
                continue
            out.write_text(scrub(text, timestamps=f.name in RESULT_TS_FILES))
            n += 1
        print(f"results  {s.name} -> {d.relative_to(REPO) if d.is_relative_to(REPO) else d} ({n} files)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=os.environ.get("BENCH_SOURCE"), required="BENCH_SOURCE" not in os.environ,
                    help="the working bench directory (or set BENCH_SOURCE)")
    ap.add_argument("--workroom", type=Path, help="sandbox script (default: <source>/../../workroom/workroom.sh)")
    ap.add_argument("--results", nargs="*", default=[], help="result dirs under <source>/results to publish (v2-*)")
    ap.add_argument("--results-dest", type=Path, default=REPO / "results" / "v2")
    ap.add_argument("--results-only", action="store_true", help="copy results, leave harness/ alone")
    a = ap.parse_args()
    src = a.source.resolve()
    if not a.results_only:
        sync_harness(src, (a.workroom or src.parents[1] / "workroom" / "workroom.sh").resolve())
    if a.results:
        sync_results(src, a.results, a.results_dest)
    print("next: python3 tools/scan.py")


if __name__ == "__main__":
    main()
