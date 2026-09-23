#!/usr/bin/env python3
"""Byte-for-byte TCP <-> Unix-socket relay, so a container with NO network can still reach one host port.

  host side:       bridge.py http-filter <socket path> <host> <port>   (HTTP proxy on the socket; forwards ONLY
                   OpenAI-style inference paths to host:port, so an agent cannot call Ollama's pull/delete/create API)
                   bridge.py unix-to-tcp <socket path> <host> <port>   (raw relay, unfiltered; not used by run.py)
  container side:  bridge.py tcp-to-unix <port> <socket path>          (listen on 127.0.0.1:port, dial socket)

The container has --network none; its only way out is this socket, which reaches exactly one host address.
"""
import http.client, json, os, socket, socketserver, sys, threading, time

# Engine-level truth for every model call, whatever the agent harness: set BENCH_RELAY_LOG=<path> to append one JSON
# line per call with the engine's own usage numbers, reasoning length, and latency. This is how the bench records
# thinking tokens and prompt size for harnesses whose own streams do not expose them (goose prints text).
LOG = os.environ.get("BENCH_RELAY_LOG")
UPSTREAM_TLS = os.environ.get("BENCH_UPSTREAM_TLS") == "1"       # https to the upstream (cloud arm)
UPSTREAM_AUTH = os.environ.get("BENCH_UPSTREAM_KEY")             # bearer / x-api-key injected host-side
UPSTREAM_PREFIX = os.environ.get("BENCH_UPSTREAM_PREFIX", "")    # e.g. "" for api.anthropic.com/v1/chat/completions
LOG_LOCK = threading.Lock()


def _reasoning_len(msg):
    for k in ("reasoning", "reasoning_content", "thinking"):
        v = msg.get(k)
        if isinstance(v, str):
            return len(v)
    return None


def log_call(path, req_body, resp_body, t0, t_first, t_end, status):
    row = {"t": round(t0, 3), "path": path.split("?")[0], "status": status, "req_bytes": len(req_body or b""),
           "resp_bytes": len(resp_body), "ttft_s": round((t_first or t_end) - t0, 3), "total_s": round(t_end - t0, 3)}
    try:
        req = json.loads(req_body or b"{}")
        row["model"] = req.get("model"); row["stream"] = bool(req.get("stream"))
        row["n_messages"] = len(req.get("messages") or []); row["n_tools"] = len(req.get("tools") or [])
        row["reasoning_effort"] = req.get("reasoning_effort")
    except ValueError:
        pass
    usage, msg = None, {}
    try:
        if resp_body.startswith(b"data:"):
            # streamed: usage arrives in the final chunk; reasoning text is spread over deltas
            reasoning, content = 0, 0
            for line in resp_body.split(b"\n"):
                if not line.startswith(b"data:") or line.strip() == b"data: [DONE]":
                    continue
                d = json.loads(line[5:])
                if d.get("usage"):
                    usage = d["usage"]
                for ch in d.get("choices") or []:
                    delta = ch.get("delta") or {}
                    for k in ("reasoning", "reasoning_content", "thinking"):
                        if isinstance(delta.get(k), str):
                            reasoning += len(delta[k])
                    if isinstance(delta.get("content"), str):
                        content += len(delta["content"])
            row["reasoning_chars"], row["content_chars"] = reasoning, content
        else:
            d = json.loads(resp_body)
            usage = d.get("usage")
            ch = (d.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            row["reasoning_chars"] = _reasoning_len(msg)
            row["content_chars"] = len(msg.get("content") or "") if isinstance(msg.get("content"), str) else None
            row["finish_reason"] = ch.get("finish_reason")
            row["n_tool_calls"] = len(msg.get("tool_calls") or [])
    except (ValueError, AttributeError, IndexError):
        row["parse_error"] = True
    if isinstance(usage, dict):
        row["prompt_tokens"] = usage.get("prompt_tokens"); row["completion_tokens"] = usage.get("completion_tokens")
        det = usage.get("completion_tokens_details") or {}
        row["reasoning_tokens"] = det.get("reasoning_tokens")
    with LOG_LOCK, open(LOG, "a") as fh:
        fh.write(json.dumps(row) + "\n")
from http.server import BaseHTTPRequestHandler

ALLOWED = ("/v1/chat/completions", "/v1/completions", "/v1/models")


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve(listener, dial):
    while True:
        conn, _ = listener.accept()
        try:
            up = dial()
        except OSError:
            conn.close()
            continue
        threading.Thread(target=pipe, args=(conn, up), daemon=True).start()
        threading.Thread(target=pipe, args=(up, conn), daemon=True).start()


def unix_to_tcp(path, host, port):
    if os.path.exists(path):
        os.unlink(path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    os.chmod(path, 0o600)
    s.listen(64)
    serve(s, lambda: socket.create_connection((host, int(port))))


def tcp_to_unix(port, path):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", int(port)))
    s.listen(64)

    def dial():
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(path)
        return c
    serve(s, dial)


def http_filter(path, host, port):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def address_string(self):
            return "container"

        def _forward(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
            if not self.path.split("?")[0].startswith(ALLOWED):
                msg = b'{"error":"blocked by bench relay: only /v1 inference paths are allowed"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(msg)
                return
            up = (http.client.HTTPSConnection if UPSTREAM_TLS else http.client.HTTPConnection)(host, int(port), timeout=3600)
            hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection", "content-length")}
            if UPSTREAM_AUTH:   # cloud arm: the key stays on the host; the container never sees it
                hdrs["Authorization"] = "Bearer " + UPSTREAM_AUTH
                hdrs["x-api-key"] = UPSTREAM_AUTH
            if UPSTREAM_PREFIX and not self.path.startswith(UPSTREAM_PREFIX):
                self.path = UPSTREAM_PREFIX.rstrip("/") + self.path
            t0 = time.time()
            if UPSTREAM_TLS:
                hdrs["Host"] = host
            up.request(self.command, self.path, body=body, headers=hdrs)
            r = up.getresponse()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            self.send_header("Connection", "close")  # body ends when the socket closes: simple and stream-safe
            self.end_headers()
            first, collected = None, []
            while True:
                chunk = r.read1(65536)
                if not chunk:
                    break
                if first is None:
                    first = time.time()
                if LOG:
                    collected.append(chunk)
                self.wfile.write(chunk)
                self.wfile.flush()
            up.close()
            self.close_connection = True
            if LOG:
                log_call(self.path, body, b"".join(collected), t0, first, time.time(), r.status)

        do_GET = do_POST = _forward

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    if os.path.exists(path):
        os.unlink(path)
    srv = Server(path, Handler)
    os.chmod(path, 0o600)
    srv.serve_forever()


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    {"unix-to-tcp": unix_to_tcp, "tcp-to-unix": tcp_to_unix, "http-filter": http_filter}[mode](*args)
