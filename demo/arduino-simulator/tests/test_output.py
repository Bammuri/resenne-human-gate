import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from output import MAX_TEXT, OutputReader


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.path = self.home / "rollout.jsonl"
        self.path.touch()
        db = sqlite3.connect(self.home / "state_5.sqlite")
        db.execute("CREATE TABLE threads (id TEXT, name TEXT, rollout_path TEXT)")
        db.execute("INSERT INTO threads VALUES (?, ?, ?)", ("thread-1", "test chat", str(self.path)))
        db.commit()
        db.close()
        self.reader = OutputReader("thread-1", self.home)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, record):
        with self.path.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def item(self, kind, item_id="item-1", **fields):
        record = {
            "type": "event_msg", "timestamp": "2026-09-07T10:00:00Z",
            "payload": {"type": "item_completed", "thread_id": "thread-1", "item": {"type": kind, "id": item_id, **fields}},
        }
        self.write(record)
        return record

    def test_only_visible_message_phases_are_exposed(self):
        self.item("UserMessage", "user", content=[{"type": "text", "text": "yes"}])
        self.item("AgentMessage", "progress", phase="commentary", content=[{"type": "Text", "text": "작업 중"}])
        self.item("AgentMessage", "final", phase="final_answer", content=[{"type": "Text", "text": "완료"}])
        self.item("AgentMessage", "private", phase="analysis", content=[{"type": "Text", "text": "PRIVATE_SENTINEL"}])
        self.item("AgentMessage", "unknown-phase", content=[{"type": "Text", "text": "PRIVATE_SENTINEL"}])
        self.item("Reasoning", "reasoning", summary_text="PRIVATE_SENTINEL", raw_content="PRIVATE_SENTINEL")
        self.item("Extension", "unknown", data="PRIVATE_SENTINEL")
        self.write({"type": "session_meta", "payload": {"base_instructions": "PRIVATE_SENTINEL"}})
        self.write({"type": "response_item", "payload": {"type": "message", "role": "system", "text": "PRIVATE_SENTINEL"}})
        snapshot = self.reader.snapshot()
        self.assertEqual([event["text"] for event in snapshot["events"]], ["yes", "작업 중", "완료"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(snapshot))
        self.assertNotIn(str(self.path), json.dumps(snapshot))

    def test_command_output_is_plain_text_and_bounded(self):
        self.item("CommandExecution", command=["/bin/zsh", "-lc", "printf ready"], aggregated_output="\x1b[32mready\x1b[0m", exit_code=0)
        event = self.reader.snapshot()["events"][0]
        self.assertEqual(event["command"], "printf ready")
        self.assertEqual(event["text"], "ready")
        self.assertEqual(event["exitCode"], 0)
        self.item("CommandExecution", "long", command=["echo", "long"], stdout="x" * (MAX_TEXT + 100), stderr="error", exit_code=1)
        event = self.reader.snapshot()["events"][-1]
        self.assertLess(len(event["text"]), MAX_TEXT + 100)
        self.assertIn("나머지는 터미널", event["text"])

    def test_partial_utf8_record_is_not_lost_or_duplicated(self):
        record = {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "UserMessage", "id": "u", "content": [{"type": "text", "text": "안녕"}]}}}
        data = (json.dumps(record, ensure_ascii=False) + "\n").encode()
        split = data.index("안".encode()) + 1
        self.path.write_bytes(data[:split])
        first = self.reader.snapshot()
        self.assertEqual(first["events"], [])
        with self.path.open("ab") as stream:
            stream.write(data[split:])
        second = self.reader.snapshot(first["cursor"], first["generation"])
        self.assertEqual(second["events"][0]["text"], "안녕")
        self.assertEqual(self.reader.snapshot(second["cursor"], second["generation"])["events"], [])
        self.write(record)
        self.assertEqual(self.reader.snapshot(second["cursor"], second["generation"])["events"], [])

    def test_replaced_log_resets_the_cursor(self):
        self.item("UserMessage", content=[{"type": "text", "text": "old"}])
        before = self.reader.snapshot()
        replacement = self.home / "replacement.jsonl"
        replacement.write_text("")
        replacement.replace(self.path)
        self.item("UserMessage", content=[{"type": "text", "text": "new"}])
        after = self.reader.snapshot(before["cursor"], before["generation"])
        self.assertTrue(after["reset"])
        self.assertNotEqual(before["generation"], after["generation"])
        self.assertEqual(after["events"][0]["text"], "new")

    def test_history_window_resets_a_client_that_fell_behind(self):
        self.item("UserMessage", "zero", content=[{"type": "text", "text": "0"}])
        before = self.reader.snapshot()
        for i in range(130):
            self.item("UserMessage", str(i), content=[{"type": "text", "text": str(i)}])
        after = self.reader.snapshot(before["cursor"], before["generation"])
        self.assertTrue(after["reset"])
        self.assertEqual(len(after["events"]), 120)
        self.assertEqual(after["events"][-1]["text"], "129")

    def test_lifecycle_status_and_invalid_rows(self):
        self.path.write_text("invalid json\n[]\n")
        self.write({"type": "event_msg", "payload": {"type": "task_started"}})
        self.assertEqual(self.reader.snapshot()["status"], "active")
        self.write({"type": "event_msg", "payload": {"type": "task_complete"}})
        self.assertEqual(self.reader.snapshot()["status"], "idle")

    def test_another_thread_is_never_displayed(self):
        self.write({"type": "event_msg", "payload": {"type": "item_completed", "thread_id": "another-thread", "item": {"type": "UserMessage", "id": "foreign", "content": [{"type": "text", "text": "FOREIGN"}]}}})
        self.assertEqual(self.reader.snapshot()["events"], [])
        self.assertFalse(OutputReader("unknown-thread", self.home).snapshot()["available"])
        self.assertEqual(OutputReader("", self.home).snapshot()["status"], "offline")

    def test_exact_session_name_resolves_to_correct_thread(self):
        self.item("UserMessage", content=[{"type": "text", "text": "yes"}])
        self.assertEqual(OutputReader("test chat", self.home).snapshot()["events"][0]["text"], "yes")


if __name__ == "__main__":
    unittest.main()
