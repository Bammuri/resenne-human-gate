import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claude_state import ClaudeStateReader


NOW = 1_000_000.0   # fixed clock so freshness is deterministic


class FakeTerminal:
    def __init__(self, ready):
        self._ready = ready

    def claude_ready(self):
        return self._ready


class ClaudeStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.state_file = self.home / "binddeck-state.json"
        self.projects = self.home / "projects"
        self.projects.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def reader(self, terminal=None):
        return ClaudeStateReader(self.state_file, self.projects, terminal=terminal, now=lambda: NOW)

    def write_state(self, record, age=5):
        self.state_file.write_text(json.dumps(record), encoding="utf-8")
        os.utime(self.state_file, (NOW - age, NOW - age))

    def write_transcript(self, age):
        session = self.projects / "some-project" / "session.jsonl"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.write_text('{"note": "mtime only, never parsed"}\n', encoding="utf-8")
        os.utime(session, (NOW - age, NOW - age))

    def test_fresh_hook_state_is_authoritative(self):
        self.write_state({"status": "waiting", "ts": NOW}, age=2)
        snapshot = self.reader().snapshot()
        self.assertEqual(snapshot["status"], "waiting")
        self.assertEqual(snapshot["source"], "hook")
        self.assertTrue(snapshot["available"])

    def test_stale_hook_falls_back_to_transcript_mtime(self):
        self.write_state({"status": "waiting", "ts": NOW}, age=120)   # stale hook file
        self.write_transcript(age=5)                                  # fresh transcript
        fresh = self.reader().snapshot()
        self.assertEqual(fresh["status"], "active")
        self.assertEqual(fresh["source"], "transcript")
        self.assertTrue(fresh["available"])
        os.utime(next(self.projects.glob("**/*.jsonl")), (NOW - 300, NOW - 300))
        stale = self.reader().snapshot()
        self.assertEqual(stale["status"], "idle")
        self.assertEqual(stale["source"], "transcript")

    def test_no_signals_uses_live_pty_then_offline(self):
        offline = self.reader(terminal=FakeTerminal(False)).snapshot()
        self.assertEqual(offline["status"], "offline")
        self.assertFalse(offline["available"])
        self.assertIsNone(offline["lastAnswer"])
        live = self.reader(terminal=FakeTerminal(True)).snapshot()
        self.assertEqual(live["status"], "active")
        self.assertTrue(live["available"])

    def test_last_answer_is_reported_after_note_answer(self):
        reader = self.reader(terminal=FakeTerminal(True))
        reader.note_answer("no")
        self.assertEqual(reader.snapshot()["lastAnswer"], "no")

    def test_bad_json_or_invalid_status_never_raises_and_degrades(self):
        self.state_file.write_text("{not json", encoding="utf-8")
        os.utime(self.state_file, (NOW - 2, NOW - 2))
        self.assertEqual(self.reader().snapshot()["status"], "offline")
        self.write_state({"status": "banana", "ts": NOW}, age=2)   # invalid status value
        self.assertEqual(self.reader().snapshot()["status"], "offline")

    def test_missing_projects_root_is_safe(self):
        reader = ClaudeStateReader(self.state_file, self.home / "does-not-exist", now=lambda: NOW)
        self.assertEqual(reader.snapshot()["status"], "offline")


if __name__ == "__main__":
    unittest.main()
