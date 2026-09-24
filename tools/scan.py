#!/usr/bin/env python3
"""Identifier scan over the whole repository; exits 1 on any hit, 0 when clean.

  python3 tools/scan.py [root]

Looks for: absolute home paths (other than the container's /home/worker; Path.home()-based code is fine), the
owner's account name or name fragments, the private assistant project, agent teammate names, the machine's hostname
(the GPU name "RTX 5090" is fine), local or tailnet IP addresses, private image names, and timestamps carrying a
local UTC offset (-04:00 / -05:00; published timestamps are UTC "Z"). Third-party task sources under tasks/upstream
are skipped, as are .git and this file's own pattern table.
"""
import re, sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__"}
SKIP_PREFIXES = ("tasks/upstream/",)
SELF = Path(__file__).resolve()

# Owner-specific patterns (real name, account names) live in tools/scan-private.txt, one regex per line, which is
# gitignored so the scanner itself never carries them; the scan refuses to run without it.
PRIVATE = Path(__file__).resolve().parent / "scan-private.txt"   # skipped by the walk below
if not PRIVATE.exists():
    sys.exit("scan: tools/scan-private.txt is missing (one regex per line, kept out of git); refusing to scan without it")
RULES = [("private pattern", re.compile(line.strip(), re.I)) for line in PRIVATE.read_text().splitlines() if line.strip()] + [
    ("home path", re.compile(r"/home/(?!worker\b)[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+|~/Work\b")),
    ("private project", re.compile(r"\bmy[ _-]?ai\b|private-assistant|agent-loops|agent-handoffs", re.I)),
    ("agent name", re.compile(r"\b(Bishop|Joshua|Whisper|Devin|Gemini|Codex|Jev)\b", re.I)),
    ("hostname", re.compile(r"(?<!RTX )(?<![\d.,])\b5090\b(?![\d.,])")),
    ("local address", re.compile(r"\b(192\.168|10\.\d{1,3}|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.\d{1,3}\.\d{1,3}\b")),
    ("local-offset time", re.compile(r"\d{2}:\d{2}:\d{2}(\.\d+)?-0[45]:00\b")),
]


# Third-party names that match a rule by coincidence, allowed only in the exact form given.
ALLOW = [re.compile(r"@deepseek-ai/dsh-hooks-codex\b|dsh-hooks-codex-\d")]   # a DSH package in its npm lockfile


def files():
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_dir() or set(p.relative_to(ROOT).parts) & SKIP_DIRS or rel.startswith(SKIP_PREFIXES) or p == SELF or p == PRIVATE:
            continue
        yield p, rel


def main():
    hits = n = 0
    for p, rel in files():
        n += 1
        for label, rx in RULES:           # the path itself
            if rx.search(rel):
                print(f"{rel}: [{label}] in file name"); hits += 1
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for label, rx in RULES:
                m = rx.search(line)
                if m and label == "agent name" and any(a.search(line) for a in ALLOW):
                    continue
                if m:
                    hits += 1
                    if hits <= 200:
                        print(f"{rel}:{i}: [{label}] {line[max(0, m.start() - 40):m.end() + 40].strip()}")
    print(f"scan: {n} files, {hits} hit(s)" + ("" if hits <= 200 else " (first 200 shown)"))
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
