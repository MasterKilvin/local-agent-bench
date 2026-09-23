#!/usr/bin/env python3
"""Offline unit tests for run.py's --only selection checks.

Standard library only, no network, no podman, no model: subprocess.Popen/run and
urllib are replaced by stand-ins that raise if anything external is started, so a
selection that slips past the new check (and proceeds to container/model work) fails
the test. Run with: python3 -m unittest test_run
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
