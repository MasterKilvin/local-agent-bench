#!/usr/bin/env python3
"""Scripted OpenAI-compatible server for DRY RUNS ONLY (no model, no GPU).

It plays a "reference agent": it recognises the task from the prompt, then uses the agent's own `write` tool to
write the task's reference files one per turn, then says it is done. If every task passes with this mock, the
harness plumbing (container, socket bridge, provider config, tool calls, step counting, scoring) is proven.
`--mode noop` answers with text only (every task should FAIL: proves the tests are not trivially passing).
`--mode loop` calls a read tool forever (proves the step limit stops the agent).

  python3 mock_openai.py --port 18080 [--mode reference|noop|loop]
"""
import argparse, json, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TASKS = [json.loads(l) for l in (Path(__file__).parent / "tasks.jsonl").read_text().splitlines()]
ARGS = None


def text_of(msg):
    c = msg.get("content")
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def plan(body):
    """Return ('tool', name, args) or ('text', str)."""
    tools = {t["function"]["name"]: t["function"] for t in body.get("tools") or [] if t.get("type") == "function"}
    msgs = body.get("messages", [])
    user = "\n".join(text_of(m) for m in msgs if m.get("role") == "user")
    alltext = "\n".join(text_of(m) for m in msgs)
    if ARGS.mode == "loop" and "maximum steps" in alltext:  # OpenCode's last-step instruction: comply
        return ("text", "Maximum steps reached. Stopping.")
    if ARGS.mode == "loop" and "read" in tools:  # never stops: proves the step limit works
        props = tools["read"].get("parameters", {}).get("properties", {})
        pkey = next((k for k in props if "path" in k.lower()), "path")
        return ("tool", "read", {pkey: ("/work/" if pkey != "path" else "") + next(iter(TASKS[0]["files"]))})
    if ARGS.mode == "noop" or "write" not in tools:
        return ("text", "I looked at it. Done.")
    task = next((t for t in TASKS if t["prompt"] in user), None)  # verbatim: catches prompt mangling
    if not task:
        return ("text", "Unknown task. Done.")
    todo = dict(task["reference_files"])
    done = sum(1 for m in msgs if m.get("role") == "tool")
    items = sorted(todo.items())
    if done >= len(items):
        return ("text", "Wrote the fix. Done.")
    name, content = items[done]
    props = tools["write"].get("parameters", {}).get("properties", {})
    pkey = next((k for k in props if "path" in k.lower()), "path")
    path = name if pkey == "path" else f"/work/{name}"  # opencode wants absolute filePath
    return ("tool", "write", {pkey: path, "content": content})


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._json({"object": "list", "data": [{"id": "mock", "object": "model", "owned_by": "mock"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        p = plan(body)
        cid, now, model = "chatcmpl-" + uuid.uuid4().hex[:8], int(time.time()), body.get("model", "mock")
        if p[0] == "tool":
            call = {"index": 0, "id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                    "function": {"name": p[1], "arguments": json.dumps(p[2])}}
            delta, finish = {"role": "assistant", "content": None, "tool_calls": [call]}, "tool_calls"
        else:
            delta, finish = {"role": "assistant", "content": p[1]}, "stop"
        usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
        if not body.get("stream"):
            msg = {k: v for k, v in delta.items()}
            if "tool_calls" in msg:
                msg["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in msg["tool_calls"]]
            return self._json({"id": cid, "object": "chat.completion", "created": now, "model": model,
                               "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for ch in ({"index": 0, "delta": delta, "finish_reason": None}, {"index": 0, "delta": {}, "finish_reason": finish}):
            ev = {"id": cid, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [ch]}
            self.wfile.write(b"data: " + json.dumps(ev).encode() + b"\n\n")
        ev = {"id": cid, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [], "usage": usage}
        self.wfile.write(b"data: " + json.dumps(ev).encode() + b"\n\ndata: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--mode", choices=["reference", "noop", "loop"], default="reference")
    ARGS = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", ARGS.port), H).serve_forever()
