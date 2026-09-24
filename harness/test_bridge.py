#!/usr/bin/env python3
"""Tests for bridge.log_call: streamed-response recording (finish_reason, n_tool_calls, stream_done, parse_error)
and unchanged non-streamed behaviour."""
import json, os, tempfile, unittest
from unittest import mock

import bridge


def chunk(choices, usage=None):
    ev = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m", "choices": choices}
    if usage is not None:
        ev["usage"] = usage
    return b"data: " + json.dumps(ev).encode() + b"\n\n"


def log_once(resp_body, req_body=b'{"model": "m", "stream": true, "messages": [], "tools": []}'):
    with tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)) as directory:
        log_file = os.path.join(directory, "bridge.LOG")
        with mock.patch.object(bridge, "LOG", log_file):
            bridge.log_call("/v1/chat/completions?x=1", req_body, resp_body, 100.0, 100.2, 100.5, 200)
        with open(log_file) as fh:
            lines = fh.read().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


class StreamedTests(unittest.TestCase):
    def test_streamed_finish_reason_tool_calls_done(self):
        body = (
            chunk([{"index": 0, "delta": {"role": "assistant", "content": "He",
                     "tool_calls": [{"index": 0, "id": "a", "function": {"name": "f"}}]}, "finish_reason": None}])
            + chunk([{"index": 0, "delta": {"content": "llo",
                     "tool_calls": [{"index": 1, "id": "b"}, {"index": 1, "id": "b2"}]}, "finish_reason": None}])
            + chunk([{"index": 0, "delta": {}, "finish_reason": "tool_calls"}])
            + chunk([], usage={"prompt_tokens": 10, "completion_tokens": 5})
            + b"data: [DONE]\n\n")
        row = log_once(body)
        self.assertEqual(row["finish_reason"], "tool_calls")
        self.assertEqual(row["n_tool_calls"], 2)          # distinct indices {0, 1}
        self.assertTrue(row["stream_done"])
        self.assertEqual(row["reasoning_chars"], 0)
        self.assertEqual(row["content_chars"], 5)
        self.assertEqual(row["prompt_tokens"], 10)
        self.assertEqual(row["completion_tokens"], 5)
        self.assertNotIn("parse_error", row)
        self.assertTrue(row["stream"])
        self.assertEqual(row["path"], "/v1/chat/completions")

    def test_no_finish_reason_no_done(self):
        body = chunk([{"index": 0, "delta": {"content": "hi"}, "finish_reason": None}])
        row = log_once(body)
        self.assertIn("finish_reason", row)
        self.assertIsNone(row["finish_reason"])
        self.assertEqual(row["n_tool_calls"], 0)
        self.assertFalse(row["stream_done"])
        self.assertNotIn("parse_error", row)

    def test_last_non_null_finish_reason_wins(self):
        body = (
            chunk([{"index": 0, "delta": {}, "finish_reason": "stop"}])
            + chunk([{"index": 0, "delta": {}, "finish_reason": None}])
            + chunk([{"index": 0, "delta": {}, "finish_reason": "tool_calls"},
                     {"index": 1, "delta": {}, "finish_reason": "length"}])
            + chunk([{"index": 0, "delta": {}, "finish_reason": None}])
            + chunk([{"index": 1, "delta": {}}]))
        row = log_once(body)
        self.assertEqual(row["finish_reason"], "length")

    def test_tool_indices_are_distinct_across_chunks_and_choices(self):
        body = (
            chunk([{"delta": {"tool_calls": [{"index": 0}, {"index": 2}]}}])
            + chunk([{"delta": {"tool_calls": [{"index": 0}, {"index": 2}]}},
                     {"delta": {"tool_calls": [{"index": 2}, {"index": 5}]}}])
            + chunk([{"delta": {"tool_calls": [{"id": "no-index"}, {"index": None}]}}]))
        row = log_once(body)
        self.assertEqual(row["n_tool_calls"], 3)
        self.assertNotIn("parse_error", row)

    def test_done_only_and_line_endings(self):
        for body in (b"data: [DONE]", b"data: [DONE]\n\n", b"data:[DONE]\r\n\r\n"):
            with self.subTest(body=body):
                row = log_once(body)
                self.assertTrue(row["stream_done"])
                self.assertIsNone(row["finish_reason"])
                self.assertEqual(row["n_tool_calls"], 0)
                self.assertEqual(row["content_chars"], 0)
                self.assertEqual(row["reasoning_chars"], 0)
                self.assertNotIn("parse_error", row)

    def test_ignores_non_data_lines_and_done_in_content(self):
        body = (chunk([{"delta": {"content": "[DONE]"}}])
                + b": keepalive\nevent: message\nid: 3\n\n")
        row = log_once(body)
        self.assertFalse(row["stream_done"])
        self.assertEqual(row["content_chars"], 6)
        self.assertNotIn("parse_error", row)

    def test_malformed_line_keeps_earlier_fields(self):
        body = (
            chunk([{"index": 0, "delta": {"reasoning": "abc", "content": "hi",
                     "tool_calls": [{"index": 0}]}, "finish_reason": None}])
            + b"data: {not json\n\n"
            + chunk([{"index": 0, "delta": {"content": "yo"}, "finish_reason": "stop"}])
            + chunk([], usage={"prompt_tokens": 1, "completion_tokens": 2})
            + b"data: [DONE]\n\n")
        row = log_once(body)
        self.assertTrue(row["parse_error"])
        # fields parsed before AND after the bad line are retained
        self.assertEqual(row["reasoning_chars"], 3)
        self.assertEqual(row["content_chars"], 4)
        self.assertEqual(row["n_tool_calls"], 1)
        self.assertEqual(row["finish_reason"], "stop")
        self.assertTrue(row["stream_done"])
        self.assertEqual(row["prompt_tokens"], 1)

    def test_malformed_line_only(self):
        row = log_once(b"data: oops\n\n")
        self.assertTrue(row["parse_error"])
        self.assertIsNone(row["finish_reason"])
        self.assertEqual(row["n_tool_calls"], 0)
        self.assertFalse(row["stream_done"])
        self.assertEqual(row["resp_bytes"], len(b"data: oops\n\n"))

    def test_malformed_data_keeps_accumulated_fields_and_continues(self):
        prefix = chunk([{
            "delta": {"reasoning": "a", "reasoning_content": "bc", "thinking": "def",
                      "content": "hi", "tool_calls": [{"index": 0}]},
            "finish_reason": "tool_calls",
        }], usage={"prompt_tokens": 7, "completion_tokens": 3,
                   "completion_tokens_details": {"reasoning_tokens": 2}})
        malformed_lines = (
            b"data: {broken", b"data: \xff", b"data:", b"data: null", b"data: []",
            b'data: {"choices": 1}', b'data: {"choices": [null]}',
            b'data: {"choices": [{"delta": 1}]}',
            b'data: {"choices": [{"delta": {"tool_calls": 1}}]}',
            b'data: {"choices": [{"delta": {"tool_calls": [{"index": []}]}}]}',
            b'data: {"usage": {"completion_tokens_details": 1}}',
        )
        for bad_line in malformed_lines:
            for continue_stream in (False, True):
                with self.subTest(line=bad_line, continue_stream=continue_stream):
                    suffix = (chunk([{"delta": {"content": "!"}}]) + b"data: [DONE]\n\n"
                              if continue_stream else b"")
                    row = log_once(prefix + bad_line + b"\n\n" + suffix)
                    self.assertTrue(row["parse_error"])
                    self.assertEqual(row["finish_reason"], "tool_calls")
                    self.assertEqual(row["n_tool_calls"], 1)
                    self.assertEqual(row["stream_done"], continue_stream)
                    self.assertEqual(row["content_chars"], 3 if continue_stream else 2)
                    self.assertEqual(row["reasoning_chars"], 6)
                    self.assertEqual(row["prompt_tokens"], 7)
                    self.assertEqual(row["completion_tokens"], 3)
                    self.assertEqual(row["reasoning_tokens"], 2)


class NonStreamedTests(unittest.TestCase):
    def test_non_streamed_unchanged(self):
        resp = json.dumps({
            "id": "x", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": "hello", "reasoning": "think!" ,
                            "tool_calls": [{"index": 0, "id": "1"}, {"index": 1, "id": "2"}]},
                "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 12,
                      "completion_tokens_details": {"reasoning_tokens": 4}},
        }).encode()
        req = b'{"model": "m", "stream": false, "messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}], "reasoning_effort": "high"}'
        row = log_once(resp, req)
        expected = {
            "t": 100.0, "path": "/v1/chat/completions", "status": 200,
            "req_bytes": len(req), "resp_bytes": len(resp), "ttft_s": 0.2, "total_s": 0.5,
            "model": "m", "stream": False, "n_messages": 1, "n_tools": 1, "reasoning_effort": "high",
            "reasoning_chars": 6, "content_chars": 5, "finish_reason": "tool_calls", "n_tool_calls": 2,
            "prompt_tokens": 30, "completion_tokens": 12, "reasoning_tokens": 4,
        }
        self.assertEqual(row, expected)

    def test_non_streamed_error_keeps_status(self):
        row = log_once(b"not json at all", b"also not json")
        self.assertTrue(row["parse_error"])
        self.assertEqual(row["status"], 200)
        self.assertNotIn("stream_done", row)


if __name__ == "__main__":
    unittest.main()
