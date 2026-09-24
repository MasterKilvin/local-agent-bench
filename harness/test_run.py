#!/usr/bin/env python3
"""Offline unit tests for run.py's task selection and context resolution.

Standard library only, no network, no podman, no model: subprocess.Popen/run and
urllib are replaced by stand-ins that raise if anything external is started, so a
selection that slips past the new check (and proceeds to container/model work) fails
the test. Run with: python3 -m unittest test_run
"""
import argparse, contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


_TMP_RUNTIME = None


def tearDownModule():
    # only remove a directory this test made (reviewers: the original leaked one on every run)
    if _TMP_RUNTIME:
        shutil.rmtree(_TMP_RUNTIME, ignore_errors=True)
        os.environ.pop("XDG_RUNTIME_DIR", None)


def _load_run():
    # run.py reads this at import time; keep it out of the real runtime dir.
    global _TMP_RUNTIME
    if not os.environ.get("XDG_RUNTIME_DIR"):
        _TMP_RUNTIME = tempfile.mkdtemp(prefix="run-test-")
        os.environ["XDG_RUNTIME_DIR"] = _TMP_RUNTIME
    spec = importlib.util.spec_from_file_location("run_under_test", HERE / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runmod = _load_run()


class SelectionTests(unittest.TestCase):
    def setUp(self):
        # Small synthetic task file.
        self.tmp = tempfile.TemporaryDirectory()
        self.tasks_file = Path(self.tmp.name) / "tasks.jsonl"
        tasks = [{"id": i, "kind": "unittest", "files": {"a.py": "x = 1"}, "prompt": "p"}
                 for i in ("A1", "B2", "C3")]
        self.tasks_file.write_text("\n".join(json.dumps(t) for t in tasks) + "\n")

        self._old_tasks = runmod.TASKS
        runmod.TASKS = self.tasks_file

        # Stand-ins: any attempt to start a container/process or hit the network fails hard.
        def explode(*a, **k):
            raise AssertionError(f"unexpected external call: {a[:1] if a else k}")

        self._old_run, self._old_popen = subprocess.run, subprocess.Popen
        self._old_urlopen = runmod.urllib.request.urlopen
        subprocess.run = explode
        subprocess.Popen = explode
        runmod.urllib.request.urlopen = explode

        self._argv = sys.argv

    def tearDown(self):
        subprocess.run, subprocess.Popen = self._old_run, self._old_popen
        runmod.urllib.request.urlopen = self._old_urlopen
        runmod.TASKS = self._old_tasks
        sys.argv = self._argv
        self.tmp.cleanup()

    def call_main(self, *argv):
        """Run run.py's main(); must stop on its own (SystemExit) before any external call.

        If the selection check were bypassed, the stand-ins raise AssertionError and
        the test fails with an error instead of a clean SystemExit.
        """
        sys.argv = ["run.py", "--agent", "pi", "--model", "fake-model"] + list(argv)
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                runmod.main()
        code = cm.exception.code
        # sys.exit("message") carries the message in .code; the interpreter turns that into
        # an stderr message plus exit status 1, so we check it the same way here.
        status = 1 if isinstance(code, str) else code
        message = (code if isinstance(code, str) else "") + err.getvalue()
        return status, message

    def test_unknown_id_stops_with_message_and_nonzero_exit(self):
        code, msg = self.call_main("--only", "NOPE")
        self.assertNotEqual(code, 0)
        self.assertIn("unknown", msg.lower())
        self.assertIn("NOPE", msg)

    def test_mixed_valid_and_invalid_stops(self):
        code, msg = self.call_main("--only", "A1,NOPE")
        self.assertNotEqual(code, 0)
        self.assertIn("unknown", msg.lower())
        self.assertIn("NOPE", msg)

    def test_empty_selection_stops(self):
        code, msg = self.call_main("--only", "")
        self.assertNotEqual(code, 0)
        self.assertIn("--only", msg)

    def test_blank_selection_stops(self):
        code, msg = self.call_main("--only", " , ,")
        self.assertNotEqual(code, 0)
        self.assertIn("--only", msg)

    def test_valid_selection_keeps_file_order(self):
        all_t = runmod.load_tasks()
        self.assertEqual([t["id"] for t in all_t], ["A1", "B2", "C3"])
        for spec in ("B2,A1", "A1,B2,C3", "A1,B2,C3,A1"):
            got = [t["id"] for t in runmod.select_only(all_t, spec)]
            # Same result as the old set-filter: task-file order, duplicates ignored.
            want = [t["id"] for t in all_t if t["id"] in set(spec.split(","))]
            self.assertEqual(got, want, spec)

    def test_valid_selection_strips_whitespace(self):
        got = [t["id"] for t in runmod.select_only(runmod.load_tasks(), " A1 , B2")]
        self.assertEqual(got, ["A1", "B2"])


class ModelTestCase(unittest.TestCase):
    """Synthetic Ollama responses and files; all external calls are intercepted."""
    EP = "http://127.0.0.1:11435/v1"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.info = {"parameters": "num_ctx 8192\nnum_predict 4096", "capabilities": ["completion", "tools"],
                     "modified_at": "2026-01-01T00:00:00Z", "details": {"family": "fake"}}
        self.mock_patch(Path, "home", return_value=self.root / "home")
        self.urlopen = self.mock_patch(runmod.urllib.request, "urlopen", side_effect=self.show_response)
        self.process_run = self.mock_patch(subprocess, "run", side_effect=AssertionError("unexpected process"))
        self.mock_patch(subprocess, "Popen", side_effect=AssertionError("unexpected process"))

    def mock_patch(self, obj, name, **kwargs):
        p = patch.object(obj, name, **kwargs)
        result = p.start()
        self.addCleanup(p.stop)
        return result

    def show_response(self, req, timeout):
        self.assertEqual(req.full_url, "http://127.0.0.1:11435/api/show")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data), {"model": "fake-model"})
        self.assertEqual(timeout, 30)
        return io.BytesIO(json.dumps(self.info).encode())


class ResolveCtxTests(ModelTestCase):
    """The resolver shares check_context's validation and preserves its public result."""

    def test_auto_returns_model_num_ctx(self):
        for size in (4096, 65536, 131072):
            with self.subTest(size=size):
                self.info["parameters"] = f"num_predict 1024\nnum_ctx {size}"
                self.assertEqual(runmod.resolve_ctx(self.EP, "fake-model", "auto"), size)

    def test_auto_uses_same_api_show_request(self):
        for endpoint in (self.EP, self.EP + "/", self.EP.removesuffix("/v1")):
            with self.subTest(endpoint=endpoint):
                self.urlopen.reset_mock()
                runmod.resolve_ctx(endpoint, "fake-model", "auto")
                self.urlopen.assert_called_once()

    def test_int_equal_or_smaller_returns_that_int(self):
        for need in (8192, 4096):
            with self.subTest(need=need):
                self.assertEqual(runmod.resolve_ctx(self.EP, "fake-model", need), need)

    def test_int_larger_exits_like_check_context(self):
        # A context failure must take precedence even when tool calling is also absent.
        for caps in (["tools"], ["vision"]):
            with self.subTest(capabilities=caps):
                self.info["capabilities"] = caps
                for fn in (runmod.check_context, runmod.resolve_ctx):
                    with self.assertRaises(SystemExit) as cm:
                        fn(self.EP, "fake-model", 65536)
                    self.assertEqual(cm.exception.code,
                                     "model fake-model has num_ctx=8192; need >= 65536. "
                                     "Create a 64K variant first (BASELINE-TODO.md).")

    def test_model_without_tool_calling_exits(self):
        for caps in (["vision"], [], None):
            self.info["capabilities"] = caps
            for fn, need in ((runmod.resolve_ctx, "auto"), (runmod.resolve_ctx, 4096),
                             (runmod.check_context, 4096)):
                with self.subTest(fn=fn.__name__, need=need, caps=caps):
                    with self.assertRaises(SystemExit) as cm:
                        fn(self.EP, "fake-model", need)
                    self.assertEqual(cm.exception.code,
                                     f"model fake-model does not report tool calling (capabilities={caps or []}); "
                                     "agents need it.")

    def test_auto_without_num_ctx_exits(self):
        for params in ("num_predict 8192", "", None):
            with self.subTest(parameters=params):
                self.info["parameters"] = params
                with self.assertRaisesRegex(SystemExit, "num_ctx"):
                    runmod.resolve_ctx(self.EP, "fake-model", "auto")
        del self.info["parameters"]
        with self.assertRaisesRegex(SystemExit, "num_ctx"):
            runmod.resolve_ctx(self.EP, "fake-model", "auto")

    def test_int_without_num_ctx_exits_like_check_context(self):
        del self.info["parameters"]
        self.info["capabilities"] = []
        for fn in (runmod.check_context, runmod.resolve_ctx):
            with self.subTest(fn=fn.__name__):
                with self.assertRaises(SystemExit) as cm:
                    fn(self.EP, "fake-model", 4096)
                self.assertEqual(cm.exception.code,
                                 "model fake-model has num_ctx=None; need >= 4096. "
                                 "Create a 64K variant first (BASELINE-TODO.md).")

    def test_check_context_keeps_same_behaviour(self):
        self.info["parameters"] = "num_ctx 131072"
        self.assertEqual(runmod.check_context(self.EP, "fake-model", 65536),
                         {"num_ctx": 131072, "manifest_sha256": None,
                          "modified_at": self.info["modified_at"], "details": self.info["details"],
                          "capabilities": self.info["capabilities"]})
        self.urlopen.assert_called_once()

    def test_check_context_keeps_manifest_hash(self):
        for tag in ("", ":small"):
            with self.subTest(tag=tag):
                mf = Path.home() / ".ollama/models/manifests/registry.ollama.ai/library/fake-model" / (tag[1:] or "latest")
                mf.parent.mkdir(parents=True, exist_ok=True)
                mf.write_text("synthetic manifest")
                self.urlopen.side_effect = lambda *a, **k: io.BytesIO(json.dumps(self.info).encode())
                info = runmod.check_context(self.EP, "fake-model" + tag, 4096)
                self.assertEqual(info["manifest_sha256"], runmod.sha(mf))

    def test_ctx_argument_accepts_auto_or_int(self):
        self.assertEqual(runmod.ctx_value("auto"), "auto")
        self.assertEqual(runmod.ctx_value("4096"), 4096)
        with self.assertRaises(argparse.ArgumentTypeError):
            runmod.ctx_value("big")


class BeforeRelay(Exception):
    """Stop a main() test after the real configuration files have been written."""


class MainCtxTests(ModelTestCase):
    """Exercise argument parsing, validation and real config writes without starting a run."""

    def setUp(self):
        super().setUp()
        tasks_file = self.root / "tasks.jsonl"
        tasks_file.write_text(json.dumps({"id": "A1", "kind": "unittest", "files": {"a.py": "x = 1"}, "prompt": "p"}) + "\n")
        self.mock_patch(runmod, "TASKS", new=tasks_file)
        self.mock_patch(runmod, "WORKROOM", new=tasks_file)
        self.mock_patch(runmod, "RUNROOT", new=self.root / "runtime")
        self.mock_patch(runmod, "THINKING", new=None)
        self.mock_patch(runmod, "RELAY_LOG", new=None)
        self.mock_patch(sys, "argv", new=["run.py"])
        self.resolve = self.mock_patch(runmod, "resolve_ctx", wraps=runmod.resolve_ctx)
        self.relay = self.mock_patch(runmod, "start_relay", side_effect=BeforeRelay)
        self.process_run.side_effect = self.fake_run

    def fake_run(self, cmd, *args, **kwargs):
        allowed = [["podman", "image", "exists", runmod.IMAGE],
                   ["podman", "image", "inspect", runmod.IMAGE, "--format", "{{.Id}}"]]
        allowed += [[str(runmod.AGENT_DIRS[agent] / runmod.AGENT_BIN[agent]), "--version"]
                    for agent in runmod.AGENT_DIRS]
        self.assertIn(cmd, allowed)
        return subprocess.CompletedProcess(cmd, 0, stdout="fake-version", stderr="")

    def call_main(self, *argv):
        sys.argv = ["run.py", "--agent", "pi", "--model", "fake-model", "--out", str(self.root / "out")] + list(argv)
        with contextlib.redirect_stderr(io.StringIO()):
            runmod.main()

    def assert_context(self, expected, *argv):
        with self.assertRaises(BeforeRelay):
            self.call_main(*argv)
        config = json.loads((self.root / "out/config.json").read_text())
        self.assertEqual(config["ctx"], expected)
        if config["agent"] == "pi":
            model = config["agent_config"]["providers"]["ollama"]["models"][0]
            self.assertEqual(model["contextWindow"], expected)
        elif config["agent"] == "opencode":
            model = config["agent_config"]["provider"]["ollama"]["models"]["fake-model"]
            self.assertEqual(model["limit"]["context"], expected)
        if "--skip-ctx-check" in argv:
            self.resolve.assert_not_called()
            self.urlopen.assert_not_called()
            self.assertIsNone(config["model_info"])
        else:
            self.assertEqual(config["model_info"]["num_ctx"], 8192)
            self.assertEqual(config["model_info"]["details"], self.info["details"])
            self.assertEqual(config["model_info"]["capabilities"], self.info["capabilities"])

    def test_default_auto_resolves_model_ctx(self):
        self.assert_context(8192)
        self.resolve.assert_called_once_with(self.EP, "fake-model", "auto")

    def test_explicit_auto_resolves_model_ctx(self):
        self.assert_context(8192, "--ctx", "auto")

    def test_opencode_uses_resolved_ctx(self):
        self.assert_context(8192, "--agent", "opencode")

    def test_goose_records_resolved_ctx(self):
        self.assert_context(8192, "--agent", "goose")

    def test_int_ctx_is_used_as_declared(self):
        self.assert_context(4096, "--ctx", "4096")
        self.resolve.assert_called_once_with(self.EP, "fake-model", 4096)

    def test_int_larger_than_model_stops(self):
        with self.assertRaisesRegex(SystemExit, "num_ctx=8192; need >= 65536"):
            self.call_main("--ctx", "65536")
        self.relay.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_invalid_ctx_is_an_argument_error(self):
        with self.assertRaises(SystemExit) as cm:
            self.call_main("--ctx", "big")
        self.assertEqual(cm.exception.code, 2)
        self.process_run.assert_not_called()
        self.urlopen.assert_not_called()

    def test_skip_ctx_check_auto_is_65536_with_no_request(self):
        self.assert_context(65536, "--skip-ctx-check")

    def test_skip_ctx_check_explicit_auto_is_65536(self):
        self.assert_context(65536, "--skip-ctx-check", "--ctx", "auto")

    def test_skip_ctx_check_int_kept(self):
        self.assert_context(32768, "--skip-ctx-check", "--ctx", "32768")


if __name__ == "__main__":
    unittest.main()
