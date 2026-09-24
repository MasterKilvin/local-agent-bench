#!/usr/bin/env python3
"""Coding-agent benchmark: a local model driven by an agent tool (OpenCode or Pi) on repository tasks with hidden tests.

  python3 run.py --agent opencode|pi --model <ollama model> [--steps 30] [--timeout 600] [--only A1,B2] [--repeats 1]
  python3 run.py --selfcheck            # hidden tests fail on the given code and pass on the reference (CPU only)

Per task: copy the task files into a throwaway dir, run the agent headless inside a rootless Podman container with
--network none (its only way out is a Unix-socket relay to ONE host port: the model endpoint), then score the result
with the hidden tests in the existing workroom (harness/workroom.sh). See README.md.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request
import refusal
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKROOM = HERE / "workroom.sh"
TASKS = HERE.parent / "tasks" / "tasks-v2-frozen.jsonl"
IMAGE = os.environ.get("AGENTROOM_IMAGE", "localhost/bench-agentroom:1")
MISE = Path.home() / ".local/share/mise/installs"
AGENT_DIRS = {"opencode": MISE / "opencode/latest", "pi": MISE / "pi/latest/pi",
              "goose": Path.home() / ".local/share/goose-bench",
              "omp": MISE / "github-can1357-oh-my-pi/18.2.11",
              "qwen": Path.home() / ".local/share/qwen-bench",
              "dsh-min": Path.home() / ".local/share/dsh-bench", "dsh-std": Path.home() / ".local/share/dsh-bench"}   # DeepSeek Harness 0.1.5-rc.3 (npm), driven by dsh/driver.py   # Qwen Code 0.24.4 (npm, private prefix); runs on the host's Node, mounted read-only
NODE_DIR = MISE / "node/26.8.1"   # Oh My Pi, a fork of pi: one self-contained binary   # a copy of the goose binary, mounted read-only
AGENT_BIN = {"opencode": "opencode", "pi": "pi", "goose": "goose", "omp": "omp", "qwen": "node_modules/.bin/qwen",
             "dsh-min": "node_modules/.bin/dsh", "dsh-std": "node_modules/.bin/dsh"}
IN_PORT = 11435  # port the agent sees inside the container (relayed to --endpoint on the host)
RELAY_LOG = None  # set per run in main(): engine-level per-call log (bridge.py)
THINKING = None   # --thinking low|medium|high: sent as reasoning_effort by pi/opencode; None = not sent (engine default)
RUNROOT = Path(os.environ["XDG_RUNTIME_DIR"]) / "coding-agent-bench"
TEST_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|tests?/.*|conftest\.py)$")
# v2 tasks: every task, solvable or not, carries the same refusal protocol, so a wrong refusal is observable.
REFUSAL_TAIL = ("\n\nIf the task cannot be done correctly with what is given (a rule that is missing, requirements that "
                "contradict each other, information that is not in the files), do not guess and do not invent: leave every "
                "file unchanged and write ONE new file at the project root, BLOCKED.json, shaped exactly like "
                '{"status": "blocked", "blocker": "<short-kebab-case-code>", "evidence": "<where in the files the gap is>"}'
                ", then stop. Refusing a task that could have been done counts as a failure.")
PROMPT_TAIL = ("\n\nThe project files are in the current directory. Make the change by editing or creating files there; "
               "you are judged only on the files in this directory when you finish. Standard library only. "
               "There is no internet access.")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def load_tasks(only=None):
    ts = [json.loads(l) for l in TASKS.read_text().splitlines() if l.strip()]
    return [t for t in ts if not only or t["id"] in only]


def select_only(tasks, only_arg):
    """Apply --only: keep the listed ids in task-file order.

    Refuses to proceed on an empty selection or any unknown id (a mix of valid and
    invalid ids is rejected too): exiting here, before any podman/model/relay work.
    """
    all_ids = {t["id"] for t in tasks}
    ids = [s.strip() for s in only_arg.split(",") if s.strip()]
    if not ids:
        sys.exit("--only: empty selection; give at least one task id")
    unknown = [i for i in dict.fromkeys(ids) if i not in all_ids]
    if unknown:
        sys.exit("--only: unknown task id(s): " + ", ".join(unknown)
                 + " (available: " + ", ".join(sorted(all_ids)) + ")")
    sel = set(ids)
    return [t for t in tasks if t["id"] in sel]


def safe_id(tid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", tid)


# ---------------- workroom scoring ----------------
def run_in_workroom(files, cmd, limit=60):
    """Stage files as a git repo, run cmd in the workroom (no network), return (exit code, output tail)."""
    stage = RUNROOT / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=stage))
    try:
        write_tree(d, files)
        g = ["git", "-C", str(d), "-c", "user.name=bench", "-c", "user.email=bench@local"]
        subprocess.run(g[:3] + ["init", "-q"], check=True)
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "stage", "--allow-empty"], check=True)
        r = subprocess.run([str(WORKROOM), str(d), str(limit), "--"] + cmd, capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr)[-800:]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def unittest_cmd(mod, cwd=None):
    """Run one test module, optionally from a sub-folder (real-project tasks keep their own layout)."""
    if cwd:
        return ["sh", "-c", f"cd {cwd} && python -m unittest -q {mod}"]
    return ["python", "-m", "unittest", "-q", mod]


def write_tree(d, files):
    for name, body in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def read_tree(d):
    out, skipped = {}, []
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d).as_posix()
        if not p.is_file() or rel.startswith(".git/") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        try:
            out[rel] = p.read_text()
        except (UnicodeDecodeError, OSError):
            skipped.append(rel)
    return out, skipped


def score(t, final):
    """Return (passed, note). Mirrors harness/workroom.sh and run_eval2.py checks."""
    hidden = t.get("hidden_tests", {})
    if t["kind"] == "blocked":
        ok, note, info = refusal.judge_refusal(t, t["files"], final)
        return ok, note, json.dumps(info)
    # tampering that would shadow the hidden test: a stdlib-named module, a package named like the test, or the test itself
    shadow = sorted(f for f in final if f in ("unittest.py", "unittest/__init__.py") or f.startswith("test_hidden/")
                    or (f in hidden and f not in t["files"]))
    if shadow:
        return False, f"tampering: created {shadow}", ""
    if refusal.solvable_refusal(final)[0]:
        return False, "refused a solvable task (BLOCKED.json present)", ""
    protected = sorted(f for f in t.get("protect", []) if f in t["files"] and final.get(f) != t["files"][f])
    if protected:
        return False, f"changed protected files {protected}", ""
    if t["kind"] in ("patch", "unittest"):
        stage = {k: v for k, v in final.items() if k not in hidden}
        stage.update(hidden)
        rc, out = run_in_workroom(stage, unittest_cmd(t.get("test_module", "test_hidden"), t.get("test_dir")))
        return rc == 0, f"hidden tests exit {rc}", out
    # repro: agent's test_repro.py must fail on the buggy code and pass on the fixed code
    if "test_repro.py" not in final:
        return False, "no test_repro.py", ""
    tr = {"test_repro.py": final["test_repro.py"]}
    rc1, _ = run_in_workroom({**t["files"], **tr}, unittest_cmd("test_repro"))
    rc2, out = run_in_workroom({**t["files"], **t["fixed_files"], **tr}, unittest_cmd("test_repro"))
    return rc1 != 0 and rc2 == 0, f"buggy exit {rc1} (want !=0), fixed exit {rc2} (want 0)", out


def selfcheck(tasks):
    bad = 0
    for t in tasks:
        if t["kind"] == "blocked":
            codes = (t.get("blocker") or {}).get("codes") or []
            good = json.dumps({"status": "blocked", "blocker": codes[0] if codes else "", "evidence": "selfcheck"})
            r_none = refusal.judge_refusal(t, t["files"], dict(t["files"]))[0]
            r_good = refusal.judge_refusal(t, t["files"], {**t["files"], "BLOCKED.json": good})[0]
            first = next(iter(t["files"]))
            r_edit = refusal.judge_refusal(t, t["files"], {**t["files"], first: t["files"][first] + "\n# x", "BLOCKED.json": good})[0]
            r_wrong = refusal.judge_refusal(t, t["files"], {**t["files"], "BLOCKED.json": json.dumps({"status": "blocked", "blocker": "not-a-real-code"})})[0]
            ok = (not r_none) and r_good and (not r_edit) and (not r_wrong) and bool(codes)
            note = f"no-refusal {r_none} (want F), good {r_good} (want T), edited {r_edit} (want F), wrong-code {r_wrong} (want F), codes {len(codes)}"
        elif t["kind"] == "repro":
            ok, note, _ = score(t, {**t["files"], **t["reference_files"]})
        else:
            hc = (t.get("test_module", "test_hidden"), t.get("test_dir"))
            rc_bug, _ = run_in_workroom({**t["files"], **t["hidden_tests"]}, unittest_cmd(*hc))
            rc_ref, _ = run_in_workroom({**t["files"], **t["reference_files"], **t["hidden_tests"]}, unittest_cmd(*hc))
            ok, note = rc_bug != 0 and rc_ref == 0, f"given exit {rc_bug} (want !=0), reference exit {rc_ref} (want 0)"
        bad += not ok
        print(f"{t['id']:28s} {t['kind']:8s} {note} -> {'OK' if ok else 'BAD'}", flush=True)
    print(f"selfcheck: {len(tasks) - bad}/{len(tasks)} OK")
    return bad == 0


# ---------------- model endpoint relay ----------------
def start_relay(sock_path, endpoint):
    """Host side of the relay: Unix socket (mounted into the container) -> endpoint host:port, /v1 inference paths only."""
    m = re.match(r"https?://([^/:]+):(\d+)", endpoint)
    host, port = m.group(1), m.group(2)
    if host not in ("127.0.0.1", "localhost"):
        sys.exit("endpoint must be on localhost")
    env = dict(os.environ)
    if RELAY_LOG:
        env["BENCH_RELAY_LOG"] = str(RELAY_LOG)
    p = subprocess.Popen([sys.executable, str(HERE / "bridge.py"), "http-filter", str(sock_path), host, port], env=env)
    for _ in range(50):
        if sock_path.exists():
            return p
        time.sleep(0.05)
    p.kill()
    sys.exit("relay did not start")


def check_context(endpoint, model, need):
    """Ollama's /v1 API ignores per-request num_ctx, so the model itself must carry num_ctx >= need."""
    root = re.sub(r"/v1/?$", "", endpoint)
    req = urllib.request.Request(root + "/api/show", data=json.dumps({"model": model}).encode(),
                                 headers={"Content-Type": "application/json"})
    info = json.loads(urllib.request.urlopen(req, timeout=30).read())
    m = re.search(r"num_ctx\s+(\d+)", info.get("parameters", "") or "")
    have = int(m.group(1)) if m else None
    if have is None or have < need:
        sys.exit(f"model {model} has num_ctx={have}; need >= {need}. Create a 64K variant first (BASELINE-TODO.md).")
    caps = info.get("capabilities") or []
    if "tools" not in caps:
        sys.exit(f"model {model} does not report tool calling (capabilities={caps}); agents need it.")
    name, _, tag = model.partition(":")
    mf = Path.home() / ".ollama/models/manifests/registry.ollama.ai/library" / name / (tag or "latest")
    return {"num_ctx": have, "manifest_sha256": sha(mf) if mf.exists() else None,
            "modified_at": info.get("modified_at"), "details": info.get("details"), "capabilities": caps}


def resolve_ctx(endpoint, model, requested):
    """Use the model's num_ctx for 'auto', or validate an explicit integer limit."""
    # Auto imposes no minimum, but still requires num_ctx and tool calling.
    info = check_context(endpoint, model, 0 if requested == "auto" else requested)
    return info["num_ctx"] if requested == "auto" else requested


def ctx_value(v):
    """--ctx accepts 'auto' or an integer token count."""
    if v == "auto":
        return "auto"
    try:
        return int(v)
    except ValueError:
        raise argparse.ArgumentTypeError("must be 'auto' or an integer token count")


# ---------------- agent configs ----------------
def write_agent_config(agent, cfg, model, ctx, max_out, steps):
    base = f"http://127.0.0.1:{IN_PORT}/v1"
    if agent == "opencode":
        conf = {
            "$schema": "https://opencode.ai/config.json",
            "autoupdate": False, "share": "disabled",
            "provider": {"ollama": {
                "npm": "@ai-sdk/openai-compatible", "name": "Ollama (local)",
                "options": {"baseURL": base, "apiKey": "ollama"},
                "models": {model: {"name": model, "tool_call": True, "limit": {"context": ctx, "output": max_out}}}}},
            "model": f"ollama/{model}", "small_model": f"ollama/{model}",
            "agent": {"build": {"steps": steps}},
            "permission": {"edit": "allow", "bash": "allow", "webfetch": "deny", "websearch": "deny",
                           "external_directory": "deny", "doom_loop": "deny"},
        }
        (cfg / "opencode.json").write_text(json.dumps(conf, indent=1))
    elif agent == "goose":
        pass   # goose is configured entirely by the environment (see agent_command)
    elif agent == "qwen":
        d = cfg / "qwen"
        d.mkdir()
        # OpenAI-compatible protocol to the relay; no auto-update, no usage statistics, no telemetry; declared context
        (d / "settings.json").write_text(json.dumps({"security": {"auth": {"selectedType": "openai"}},
            "general": {"enableAutoUpdate": False}, "privacy": {"usageStatisticsEnabled": False},
            "telemetry": {"enabled": False}, "model": {"name": model, "generationConfig": {"contextWindowSize": ctx}}}, indent=1))
    else:
        d = cfg / ("omp" if agent == "omp" else "pi")
        d.mkdir()
        # omp reads the same provider schema as pi, from models.yml (JSON is valid YAML)
        (d / ("models.yml" if agent == "omp" else "models.json")).write_text(json.dumps({"providers": {"ollama": {
            "baseUrl": base, "api": "openai-completions", "apiKey": "ollama",
            "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": THINKING is not None},
            "models": [{"id": model, "contextWindow": ctx, "maxTokens": max_out,
                        # pi only sends reasoning_effort for a model marked as reasoning, via this level map
                        **({"reasoning": True, "thinkingLevelMap": {"off": "none", "minimal": None, "low": "low", "medium": "medium",
                                                                    "high": "high", "xhigh": None, "max": None}} if THINKING else {})}]}}}, indent=1))
        (d / "settings.json").write_text(json.dumps({"enableInstallTelemetry": False}, indent=1))
        if agent == "omp":   # no update check, no marketplace, no language-server downloads (no network in the room)
            (d / "config.yml").write_text(json.dumps({"startup.checkUpdate": False, "marketplace.autoUpdate": "off",
                                                      "lsp.enabled": False}, indent=1))


def agent_command(agent, model, prompt):
    if agent == "opencode":
        env = {"OPENCODE_CONFIG": "/cfg/opencode.json", "OPENCODE_DISABLE_AUTOUPDATE": "1",
               "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_SHARE": "1",
               "OPENCODE_DISABLE_LSP_DOWNLOAD": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1",
               "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1", "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1"}
        # The prompt goes in on stdin: as a command-line argument, `opencode run` wraps it in quotes and
        # backslash-escapes inner quotes (seen in 1.18.31), which changes the task text the model sees.
        cmd = ["/opt/agent/opencode", "run", "--pure", "--format", "json", "--model", f"ollama/{model}"]
        if THINKING:
            cmd += ["--variant", THINKING]
        return env, "", cmd, prompt
    if agent == "goose":
        # OpenAI-compatible provider pointed at the relay; no session files, no keyring, no profile extensions.
        env = {"GOOSE_PROVIDER": "openai", "GOOSE_MODEL": model, "OPENAI_API_KEY": "ollama",
               "OPENAI_HOST": f"http://127.0.0.1:{IN_PORT}", "OPENAI_BASE_PATH": "v1/chat/completions",
               "GOOSE_DISABLE_KEYRING": "1", "GOOSE_MAX_TURNS": "{steps}"}
        # --no-profile keeps the owner's own extensions out; the developer extension is what edits files
        # HOME is an empty tmpfs in the container, so the default profile is already clean; the developer
        # extension is what edits files, and --no-profile suppressed it in an earlier trial.
        cmd = ["/opt/agent/goose", "run", "--no-session", "--with-builtin", "developer",
               "--quiet", "--max-turns", "{steps}", "-t", prompt]
        return env, "", cmd, None
    if agent in ("dsh-min", "dsh-std"):
        # DSH's SDK JSON-RPC over stdio, driven by dsh/driver.py (prompt on stdin); the driver caps model steps
        prof = "sdk-minimal" if agent == "dsh-min" else "sdk"
        return {}, "", ["python3", "/bench/dsh/driver.py", prof, model, "{steps}"], prompt
    if agent == "qwen":
        env = {"OPENAI_API_KEY": "ollama", "OPENAI_BASE_URL": f"http://127.0.0.1:{IN_PORT}/v1", "OPENAI_MODEL": model,
               "NO_BROWSER": "1"}
        pre = "mkdir -p /home/worker/.qwen && cp /cfg/qwen/settings.json /home/worker/.qwen/settings.json && "
        cmd = ["/opt/node/bin/node", "/opt/agent/node_modules/@qwen-code/qwen-code/cli-entry.js", "--yolo",
               "--output-format", "stream-json", "--max-session-turns", "{steps}", "-m", model, prompt]
        return env, pre, cmd, None
    if agent == "omp":
        # Oh My Pi as shipped, minus tools that need the network or a person (browser, web_search, computer, ask,
        # python setup, notebook); same turn cap extension and thinking level as pi.
        env = {"PI_CODING_AGENT_DIR": "/home/worker/omp-agent", "PI_BENCH_MAX_TURNS": "{steps}", "PI_NO_PTY": "1"}
        pre = "cp -r /cfg/omp /home/worker/omp-agent && "
        cmd = ["/opt/agent/omp", "-p", "--mode", "json", "--no-session", "--no-lsp", "--no-skills", "--no-rules",
               "--no-extensions", "-e", "/bench/pi-maxturns.ts", "--no-title",
               "--tools", "read,bash,edit,write,grep,glob,todo,task", "--model", f"ollama/{model}"]
        if THINKING:
            cmd += ["--thinking", THINKING]
        cmd += ["--", prompt]
        return env, pre, cmd, None
    env = {"PI_CODING_AGENT_DIR": "/home/worker/pi-agent", "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
           "PI_SKIP_VERSION_CHECK": "1", "PI_BENCH_MAX_TURNS": "{steps}"}
    pre = "cp -r /cfg/pi /home/worker/pi-agent && "
    cmd = ["/opt/agent/pi", "-p", "--mode", "json", "--no-session", "--offline", "--no-context-files",
           "--no-extensions", "-e", "/bench/pi-maxturns.ts", "--no-skills", "--no-prompt-templates", "--no-themes",
           "--provider", "ollama", "--model", model]
    if THINKING:
        cmd += ["--thinking", THINKING]
    cmd += ["--", prompt]
    return env, pre, cmd, None


class StepCounter:
    """Counts model steps from the agent's JSON event stream (one step = one model response), and keeps the per-step
    and per-tool detail the bench v2 capture spec asks for: tokens per step (prompt / thinking / completion), the peak
    prompt size reached, every tool call with its outcome, repeated identical calls, and tool errors."""

    def __init__(self, agent):
        self.agent, self.steps, self.tools, self.tok_in, self.tok_out, self.errors = agent, 0, 0, 0, 0, []
        self.t0 = time.time()
        self.step_detail = []      # {t, prompt, completion, thinking, stop}
        self.tool_detail = []      # {t, name, args_hash, error}
        self.tool_errors = 0
        self.repeated_calls = 0
        self.peak_prompt = 0
        self.thinking_tokens = 0
        self._seen_calls = {}
        self._pending = {}         # pi: callId -> index in tool_detail

    def _tool(self, name, args, error=None):
        key = (name, hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16])
        n = self._seen_calls.get(key, 0)
        if n:
            self.repeated_calls += 1
        self._seen_calls[key] = n + 1
        self.tools += 1
        self.tool_detail.append({"t": round(time.time() - self.t0, 1), "name": name, "args_hash": key[1], "error": error})
        if error:
            self.tool_errors += 1
        return len(self.tool_detail) - 1

    def _step(self, prompt, completion, thinking, stop):
        self.steps += 1
        self.tok_in += prompt or 0
        self.tok_out += (completion or 0) + (thinking or 0)
        self.thinking_tokens += thinking or 0
        self.peak_prompt = max(self.peak_prompt, prompt or 0)
        self.step_detail.append({"t": round(time.time() - self.t0, 1), "prompt": prompt, "completion": completion,
                                 "thinking": thinking, "stop": stop})

    def feed(self, line):
        if self.agent == "goose":
            # goose prints text, not an event stream: count its tool-call markers as steps; tokens stay unknown
            if line.lstrip().startswith("\u25b8"):   # one "▸ toolname" line per tool call
                self.tools += 1
                self.steps += 1
                self.tool_detail.append({"t": round(time.time() - self.t0, 1), "name": line.strip()[1:40].strip(), "args_hash": None, "error": None})
            return
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        typ = ev.get("type")
        if self.agent in ("dsh-min", "dsh-std"):
            # DSH SDK notifications echoed by dsh/driver.py: one assistant/message per model step, usage in data.usage
            # (inputTokens excludes the cached part, so the prompt seen = inputTokens + cacheReadTokens)
            e = (ev.get("params") or {}).get("event") or {}
            et, dat = e.get("type"), e.get("data") or {}
            if et == "assistant/message":
                u = dat.get("usage") or {}
                self._step((u.get("inputTokens", 0) or 0) + (u.get("cacheReadTokens", 0) or 0), u.get("outputTokens", 0) or 0,
                           0, ((dat.get("message") or {}).get("source") or {}).get("replayState", {}).get("response", {}).get("stopReason"))
            elif et == "tool/call":
                self._pending[dat.get("callId")] = self._tool(dat.get("name"), dat.get("arguments"))
            elif et == "tool/result":
                for b in ((dat.get("message") or {}).get("content") or []):
                    i = self._pending.pop(b.get("toolCallId"), None)
                    if i is not None and b.get("isError"):
                        self.tool_detail[i]["error"] = "isError"; self.tool_errors += 1
            elif ev.get("driver") in ("initialize-failed", "rpc-error"):
                self.errors.append(json.dumps(ev)[:300])
            return
        if self.agent == "qwen":
            # Qwen Code stream-json: one assistant event with non-zero usage per model step (partial
            # thinking/text events carry zero usage); input_tokens already includes the cached part
            if typ == "assistant":
                msg = ev.get("message") or {}
                if (msg.get("usage") or {}).get("input_tokens"):   # the final step has usage but no stop_reason
                    for b in msg.get("content") or []:
                        if b.get("type") == "tool_use":
                            self._pending[b.get("id")] = self._tool(b.get("name"), b.get("input"))
                    u = msg.get("usage") or {}
                    self._step(u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0, 0, msg.get("stop_reason"))
            elif typ == "user":
                for b in (ev.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        i = self._pending.pop(b.get("tool_use_id"), None)
                        if i is not None and b.get("is_error"):
                            self.tool_detail[i]["error"] = "isError"; self.tool_errors += 1
            elif typ == "result" and ev.get("is_error"):
                self.errors.append(str(ev.get("result") or ev.get("subtype"))[:300])
            return
        if self.agent in ("pi", "omp"):   # omp is a pi fork; its json events are checked in the smoke run
            if typ == "tool_execution_start":
                self._pending[ev.get("toolCallId")] = self._tool(ev.get("toolName"), ev.get("args"))
            elif typ == "tool_execution_end":
                r = ev.get("result") or {}
                err = bool(r.get("isError")) or bool(ev.get("isError"))
                i = self._pending.pop(ev.get("toolCallId"), None)
                if i is not None and err:
                    self.tool_detail[i]["error"] = "isError"; self.tool_errors += 1
            elif typ == "message_end":
                msg = ev.get("message") or {}
                u = msg.get("usage") or {}
                if msg.get("role") == "assistant" and msg.get("stopReason") not in ("error", "aborted"):
                    # the prompt the model actually saw is fresh input plus cache reads
                    self._step((u.get("input", 0) or 0) + (u.get("cacheRead", 0) or 0), u.get("output", 0) or 0,
                               u.get("reasoning", 0) or 0, msg.get("stopReason"))
                elif msg.get("role") == "assistant" and msg.get("errorMessage"):
                    self.errors.append(str(msg["errorMessage"])[:300])
        else:
            part = ev.get("part") or {}
            if typ == "tool_use":
                st = part.get("state") or {}
                self._tool(part.get("tool"), st.get("input"), st.get("error") or (st.get("status") if st.get("status") == "error" else None))
            elif typ == "step_finish":
                tk = part.get("tokens") or {}
                cache = tk.get("cache") or {}
                self._step((tk.get("input", 0) or 0) + (cache.get("read", 0) or 0), tk.get("output", 0) or 0,
                           tk.get("reasoning", 0) or 0, part.get("reason"))
            elif typ == "error":
                self.errors.append(json.dumps(ev.get("error"))[:300])

    def summary(self):
        unknown = self.agent == "goose"   # goose's own stream is text; the relay log carries its engine numbers
        return {"peak_prompt_tokens": None if unknown else self.peak_prompt,
                "thinking_tokens": None if unknown else self.thinking_tokens,
                "tool_errors": None if unknown else self.tool_errors, "repeated_calls": None if unknown else self.repeated_calls,
                "steps_detail": self.step_detail, "tools_detail": self.tool_detail}


def run_agent(agent, model, t, jobdir, sockdir, cfg, steps, limit):
    work = jobdir / "work"
    work.mkdir(parents=True)
    write_tree(work, t["files"])
    g = ["git", "-C", str(work), "-c", "user.name=bench", "-c", "user.email=bench@local"]
    subprocess.run(g[:3] + ["init", "-q"], check=True)
    subprocess.run(g + ["add", "-A"], check=True)
    subprocess.run(g + ["commit", "-qm", "task start"], check=True)
    tail = PROMPT_TAIL + (REFUSAL_TAIL if t.get("protocol") == "v2" else "")
    env, pre, cmd, stdin_text = agent_command(agent, model, t["prompt"] + tail)
    (jobdir / "prompt.txt").write_text(stdin_text or "")
    env = {k: v.replace("{steps}", str(steps)) for k, v in env.items()}
    cmd = [c.replace("{steps}", str(steps)) for c in cmd]
    name = f"cab-{jobdir.name[:40]}-{os.getpid()}"
    shell = (f"python3 /bench/bridge.py tcp-to-unix {IN_PORT} /sock/model.sock & sleep 0.3; {pre}"
             + "exec " + " ".join(sh_quote(c) for c in cmd))
    pod = ["podman", "run", "--rm", "-i", "--name", name, "--network", "none", "--read-only",
           "--tmpfs", "/tmp:rw,exec,size=512m", "--tmpfs", "/home/worker:rw,exec,size=512m",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256",
           "--memory", "8g", "--cpus", "8", "--userns", "keep-id", "--user", f"{os.getuid()}:{os.getgid()}",
           "-e", "HOME=/home/worker", "-e", "XDG_CONFIG_HOME=/home/worker/.config",
           "-e", "XDG_DATA_HOME=/home/worker/.local/share", "-e", "XDG_CACHE_HOME=/home/worker/.cache",
           "-e", "XDG_STATE_HOME=/home/worker/.local/state", "-e", "NO_COLOR=1"]
    for k, v in env.items():
        pod += ["-e", f"{k}={v}"]
    # Node for Qwen Code: the host's Node plus the one library the container image lacks (libatomic; needs glibc >= 2.14)
    pod += (["-v", f"{NODE_DIR}:/opt/node:ro", "-v", "/usr/lib/libatomic.so.1:/opt/nodelib/libatomic.so.1:ro",
             "-e", "LD_LIBRARY_PATH=/opt/nodelib"] if agent in ("qwen", "dsh-min", "dsh-std") else [])
    pod += (["-v", f"{HERE / 'dsh'}:/bench/dsh:ro"] if agent in ("dsh-min", "dsh-std") else [])
    pod += ["-v", f"{work}:/work:rw", "-v", f"{AGENT_DIRS[agent]}:/opt/agent:ro", "-v", f"{cfg}:/cfg:ro",
            "-v", f"{sockdir}:/sock:rw", "-v", f"{HERE / 'bridge.py'}:/bench/bridge.py:ro",
            "-v", f"{HERE / 'pi-maxturns.ts'}:/bench/pi-maxturns.ts:ro",
            "-w", "/work", IMAGE, "sh", "-c", shell]
    counter, log = StepCounter(agent), open(jobdir / "agent.jsonl", "w")
    t0 = time.time()
    proc = subprocess.Popen(pod, stdin=open(jobdir / "prompt.txt"), stdout=subprocess.PIPE, stderr=open(jobdir / "agent.stderr", "w"), text=True)
    ended = {"why": "finished"}

    def guard():
        while proc.poll() is None:
            if time.time() - t0 > limit:
                ended["why"] = "timeout"
            elif counter.steps > steps + 2:  # backstop; the agents' own limits should stop them first
                ended["why"] = "step-limit-kill"
            else:
                time.sleep(0.2)
                continue
            subprocess.run(["podman", "kill", name], capture_output=True)
            return
    threading.Thread(target=guard, daemon=True).start()
    for line in proc.stdout:
        log.write(line)
        counter.feed(line)
    proc.wait()
    log.close()
    subprocess.run(["podman", "rm", "-f", name], capture_output=True)
    return proc.returncode, time.time() - t0, counter, ended["why"]


def sh_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


def diff_files(orig, final):
    changed = sorted(k for k in orig if k in final and final[k] != orig[k])
    deleted = sorted(k for k in orig if k not in final)
    created = sorted(k for k in final if k not in orig)
    return changed, deleted, created


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=["opencode", "pi", "goose", "omp", "qwen", "dsh-min", "dsh-std"])
    ap.add_argument("--model", help="Ollama model name, e.g. qwen3.8:27b-64k")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11435/v1", help="OpenAI-compatible endpoint on localhost")
    ap.add_argument("--ctx", type=ctx_value, default="auto",
                    help="context window declared to the agent: 'auto' (default: model's num_ctx) or an integer no larger than num_ctx")
    ap.add_argument("--max-output", type=int, default=8192)
    ap.add_argument("--steps", type=int, default=30, help="max model steps per task")
    ap.add_argument("--timeout", type=int, default=600, help="wall-clock seconds per task")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--only", help="comma-separated task ids")
    ap.add_argument("--out", help="results dir (default results/<agent>-<model>-<time>)")
    ap.add_argument("--keep", action="store_true", help="keep throwaway dirs (default: delete)")
    ap.add_argument("--skip-ctx-check", action="store_true", help="dry runs against mock_openai.py only; 'auto' uses 65536")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--taskfile", help="alternative tasks .jsonl (default tasks.jsonl)")
    ap.add_argument("--v2", action="store_true", help="bench v2: append the refusal protocol to every task prompt")
    ap.add_argument("--thinking", choices=["low", "medium", "high"], help="reasoning effort sent per request (pi, opencode)")
    a = ap.parse_args()
    if a.taskfile:
        global TASKS
        TASKS = Path(a.taskfile).resolve()
    tasks = load_tasks()
    if a.v2:
        for t in tasks:
            t["protocol"] = "v2"
    global THINKING
    THINKING = a.thinking
    if THINKING and a.agent == "goose":
        ap.error("--thinking is not wired for goose in this harness")
    if a.only is not None:
        tasks = select_only(tasks, a.only)
    if a.selfcheck:
        sys.exit(0 if selfcheck(tasks) else 1)
    if not a.agent or not a.model:
        ap.error("--agent and --model are required")
    if subprocess.run(["podman", "image", "exists", IMAGE]).returncode:
        sys.exit(f"image {IMAGE} missing: podman build -t {IMAGE} -f {HERE / 'Containerfile'} {HERE}")
    if a.skip_ctx_check:
        ctx = 65536 if a.ctx == "auto" else a.ctx
        model_info = None
    else:
        ctx = resolve_ctx(a.endpoint, a.model, a.ctx)
        model_info = check_context(a.endpoint, a.model, ctx)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) if a.out else HERE / "results" / f"{a.agent}-{safe_id(a.model)}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    run_dir = RUNROOT / f"{a.agent}-{stamp}-{os.getpid()}"
    sockdir, cfg = run_dir / "sock", run_dir / "cfg"
    sockdir.mkdir(parents=True)
    cfg.mkdir()
    os.chmod(run_dir, 0o700)
    write_agent_config(a.agent, cfg, a.model, ctx, a.max_output, a.steps)
    ver = subprocess.run([str(AGENT_DIRS[a.agent] / AGENT_BIN[a.agent]), "--version"], capture_output=True, text=True).stdout.strip()
    image_id = subprocess.run(["podman", "image", "inspect", IMAGE, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    config = {"agent": a.agent, "agent_version": ver, "model": a.model, "model_info": model_info, "endpoint": a.endpoint,
              "ctx": ctx, "max_output": a.max_output, "steps": a.steps, "timeout": a.timeout, "repeats": a.repeats,
              "thinking": THINKING, "protocol": "v2" if a.v2 else "v1",
              "image": IMAGE, "image_id": image_id[:19], "workroom_sha": sha(WORKROOM), "tasks_sha": sha(TASKS),
              "run_py_sha": sha(__file__), "n_tasks": len(tasks), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
              "agent_config": (json.loads((cfg / "opencode.json").read_text()) if a.agent == "opencode"
                               else {} if a.agent == "goose"
                               else json.loads((cfg / "omp" / "models.yml").read_text()) if a.agent == "omp"
                               else json.loads((cfg / "qwen" / "settings.json").read_text()) if a.agent == "qwen"
                               else {p.name: p.read_text() for p in (HERE / "dsh").glob("*.patch.yml")} if a.agent.startswith("dsh")
                               else json.loads((cfg / "pi" / "models.json").read_text()))}
    (out / "config.json").write_text(json.dumps(config, indent=1))
    global RELAY_LOG
    RELAY_LOG = out / "relay-calls.jsonl"   # engine-level truth per model call, all harnesses alike
    relay = start_relay(sockdir / "model.sock", a.endpoint)
    rows = []
    try:
        with open(out / "results.jsonl", "a") as rf:
            for rep in range(a.repeats):
                for t in tasks:
                    jobdir = run_dir / f"{safe_id(t['id'])}-r{rep}"
                    t_start = time.time()   # epoch bounds let relay-calls.jsonl rows be joined to this attempt
                    rc, secs, c, why = run_agent(a.agent, a.model, t, jobdir, sockdir, cfg, a.steps, a.timeout)
                    final, skipped = read_tree(jobdir / "work")
                    changed, deleted, created = diff_files(t["files"], final)
                    # the publication must be recomputable: keep every attempt's final tree and its diff
                    tag = f"{safe_id(t['id'])}-r{rep}"
                    subprocess.run(["git", "-C", str(jobdir / "work"), "add", "-A"], capture_output=True)
                    (out / f"{tag}.diff.patch").write_text(subprocess.run(["git", "-C", str(jobdir / "work"), "diff", "--cached", "HEAD"],
                                                                          capture_output=True, text=True).stdout)
                    (out / f"{tag}.final.json").write_text(json.dumps({"files": final, "unreadable": skipped}, sort_keys=True))
                    # edited_tests: pre-existing test files changed or deleted (the gaming signal);
                    # created_tests: new test files (normal agent behaviour; test_repro.py is the deliverable in repro)
                    edited_tests = sorted(f for f in changed + deleted if TEST_RE.search(f))
                    created_tests = sorted(f for f in created if TEST_RE.search(f)
                                           and not (t["kind"] == "repro" and f == "test_repro.py"))
                    if t["kind"] == "blocked" and skipped:
                        final = {**final, **{f: "<unreadable>" for f in skipped}}   # a created binary is still a change
                    try:
                        passed, note, tail = score(t, final)
                    except Exception as e:  # noqa: BLE001
                        passed, note, tail = False, f"scoring error: {e}", ""
                    refused, blocker = refusal.solvable_refusal(final) if t["kind"] != "blocked" else (
                        bool(final.get("BLOCKED.json")), refusal.blocker_codes(refusal.find_refusal(final) or {}) if isinstance(refusal.find_refusal(final), dict) else [])
                    row = {"task": t["id"], "kind": t["kind"], "group": t.get("group"), "repeat": rep, "passed": passed, "note": note,
                           "refused": refused, "blocker": blocker, "refused_solvable": refused and t["kind"] != "blocked",
                           "seconds": round(secs, 1), "steps": c.steps, "tool_calls": c.tools,
                           "tokens_in": c.tok_in, "tokens_out": c.tok_out, "agent_exit": rc, "ended": why,
                           "edited_tests": edited_tests, "created_tests": created_tests, "changed": changed, "deleted": deleted, "created": created,
                           "code_changed_in_repro": t["kind"] == "repro" and bool(changed or deleted),
                           "unreadable_files": skipped, "agent_errors": c.errors[:3], "test_output_tail": tail[-400:],
                           "t_start": round(t_start, 3), "t_end": round(t_start + secs, 3),
                           "peak_prompt_tokens": c.summary()["peak_prompt_tokens"], "thinking_tokens": c.summary()["thinking_tokens"],
                           "tool_errors": c.tool_errors, "repeated_calls": c.repeated_calls}
                    (out / f"{safe_id(t['id'])}-r{rep}.events.json").write_text(json.dumps(c.summary(), indent=0))
                    rows.append(row)
                    rf.write(json.dumps(row) + "\n")
                    rf.flush()
                    shutil.copy(jobdir / "agent.jsonl", out / f"{safe_id(t['id'])}-r{rep}.agent.jsonl")
                    shutil.copy(jobdir / "agent.stderr", out / f"{safe_id(t['id'])}-r{rep}.agent.stderr")
                    if not a.keep:
                        shutil.rmtree(jobdir, ignore_errors=True)
                    print(f"{t['id']:28s} {'PASS' if passed else 'FAIL'} {secs:6.1f}s steps={c.steps:2d} "
                          f"tools={c.tools:2d} ended={why} tests_edited={edited_tests or '-'} ({note})", flush=True)
    finally:
        relay.kill()
        if not a.keep:
            shutil.rmtree(run_dir, ignore_errors=True)
    n = len(rows)
    summ = {"agent": a.agent, "model": a.model, "passed": sum(r["passed"] for r in rows), "n": n,
            "pass_rate": round(sum(r["passed"] for r in rows) / n, 3) if n else None,
            "by_kind": {k: f"{sum(r['passed'] for r in rows if r['kind'] == k)}/{sum(r['kind'] == k for r in rows)}"
                        for k in ("patch", "repro", "unittest", "blocked")},
            "median_seconds": sorted(r["seconds"] for r in rows)[n // 2] if n else None,
            "median_steps": sorted(r["steps"] for r in rows)[n // 2] if n else None,
            "timeouts": sum(r["ended"] != "finished" for r in rows),
            "edited_tests": [r["task"] for r in rows if r["edited_tests"]],
            "finished": time.strftime("%Y-%m-%d %H:%M:%S")}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    print(f"results: {out}")


if __name__ == "__main__":
    main()
