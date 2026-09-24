#!/usr/bin/env python3
"""Drive one DeepSeek Harness (DSH) task over its SDK JSON-RPC stdio protocol, inside the sealed workroom.

Usage (inside the container): driver.py <profile: sdk|sdk-minimal> <model> <max_model_steps>   (prompt on stdin)
Protocol (@deepseek-ai/dsh-sdk-protocol 0.1.5-rc.3): newline-delimited JSON-RPC 2.0; initialize {cwd, provider, model}
-> session/prompt {sessionId, contentBlocks} -> notifications session.event / session.status until the session is idle
-> shutdown. Every notification is echoed to stdout as one JSON line for the bench's step counter. The step cap counts
assistant messages that carry model usage; after the cap no new prompt is sent and the run is shut down.
"""
import json, os, subprocess, sys, threading, time, uuid

profile, model, cap = sys.argv[1], sys.argv[2], int(sys.argv[3])
prompt = sys.stdin.read()
patch = "standard" if profile == "sdk" else "minimal"
env = dict(os.environ, DSH_HOME="/home/worker/.dsh", DSH_TELEMETRY_MODE="DISABLED", DSH_BENCH_MODEL=model,
           DSH_BENCH_API_KEY="ollama", HOME="/home/worker")
os.makedirs("/home/worker/.dsh", exist_ok=True)
cmd = ["/opt/node/bin/node", "/opt/agent/node_modules/@deepseek-ai/dsh/lib/bin.js", "--profile", profile,
       "--patch", f"/bench/dsh/{patch}.patch.yml"]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, env=env, cwd="/work")
out = sys.stdout
pending, lock, next_id = {}, threading.Lock(), [0]
state = {"running_seen": False, "idle": threading.Event(), "steps": 0, "capped": False}


def send(method, params=None):
    with lock:
        next_id[0] += 1
        i = next_id[0]
        ev = threading.Event()
        pending[i] = {"ev": ev, "resp": None}
    frame = {"jsonrpc": "2.0", "id": i, "method": method}
    if params is not None:
        frame["params"] = params
    proc.stdin.write(json.dumps(frame) + "\n")
    proc.stdin.flush()
    return pending[i]


def reader():
    for line in proc.stdout:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" in msg and ("result" in msg or "error" in msg):
            p = pending.get(msg["id"])
            if p:
                p["resp"] = msg
                p["ev"].set()
            if "error" in msg:
                out.write(json.dumps({"driver": "rpc-error", "error": msg["error"]}) + "\n"); out.flush()
            continue
        method, params = msg.get("method"), msg.get("params") or {}
        out.write(json.dumps({"method": method, "params": params}) + "\n"); out.flush()
        if method == "session.event":
            e = params.get("event") or {}
            blob = json.dumps(e)
            if '"usage"' in blob and ('"assistant"' in blob):
                state["steps"] += 1
                if state["steps"] >= cap and not state["capped"]:
                    state["capped"] = True
                    out.write(json.dumps({"driver": "step-cap", "steps": state["steps"]}) + "\n"); out.flush()
                    state["idle"].set()
        elif method == "session.status":
            if params.get("status") == "running":
                state["running_seen"] = True
            elif params.get("status") == "idle" and state["running_seen"]:
                state["idle"].set()
    state["idle"].set()


threading.Thread(target=reader, daemon=True).start()
init = send("initialize", {"cwd": "/work", "provider": "local-ollama", "model": model})
if not init["ev"].wait(120) or "error" in (init["resp"] or {}):
    out.write(json.dumps({"driver": "initialize-failed", "resp": init["resp"]}) + "\n")
    proc.kill(); sys.exit(2)
sid = str(uuid.uuid4())
send("session/prompt", {"sessionId": sid, "contentBlocks": [{"type": "text", "text": prompt}]})
state["idle"].wait()
out.write(json.dumps({"driver": "done", "steps": state["steps"], "capped": state["capped"]}) + "\n"); out.flush()
try:
    sd = send("shutdown")
    sd["ev"].wait(30)
    proc.wait(timeout=30)
except Exception:  # noqa: BLE001
    proc.kill()
sys.exit(0)
