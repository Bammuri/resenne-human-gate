import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow import Workflow
from side_question import SideQuestion

FAKE_ANSWER = """
import json, sys
prompt = sys.stdin.read()
assert 'PWM이 무엇인가요?' in prompt
assert 'PRIVATE_STAGE_INPUT' not in prompt
assert 'standalone, informal Q&A' in prompt
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'PWM은 펄스 폭을 조절하는 방식입니다.'}}))
"""


class SideQuestionTests(unittest.TestCase):
    def wait(self, chat):
        end = time.monotonic() + 5
        while chat.snapshot()["running"] and time.monotonic() < end:
            time.sleep(.01)
        self.assertFalse(chat.snapshot()["running"])

    @patch.object(SideQuestion, "command", return_value=[sys.executable, "-c", FAKE_ANSWER])
    def test_ask_is_independent_while_workflow_running_and_never_changes_documents(self, command):
        with tempfile.TemporaryDirectory() as directory:
            flow = Workflow("fake", directory)
            flow.configure("PRIVATE_STAGE_INPUT", 2)
            flow.stage, flow.run_id, flow.running = "construction", "ongoing-run", True
            before = {p.name: p.read_bytes() for p in flow.documents.root.iterdir()}
            flow.side_question.ask("PWM이 무엇인가요?")
            self.wait(flow.side_question)
            self.assertFalse(flow.side_question.error)
            self.assertIn("펄스", flow.side_question.messages[-1]["content"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in flow.documents.root.iterdir()})
            self.assertTrue(flow.running)
            self.assertEqual((flow.stage, flow.run_id, flow.autonomy), ("construction", "ongoing-run", 2))
            self.assertEqual(flow.questions, [])
            flow.persist()  # A later workflow save must not persist the side conversation either.
            self.assertEqual(before, {p.name: p.read_bytes() for p in flow.documents.root.iterdir()})
            restored = Workflow("fake", directory)
            self.assertEqual(restored.side_question.messages, [])
            flow.running = False
            flow.stop()

    def test_validation_and_read_only_ephemeral_command(self):
        chat = SideQuestion("fake", ".")
        for question in (None, "", "  ", "x" * 8193):
            with self.assertRaises(ValueError):
                chat.ask(question)
        self.assertIn("read-only", chat.command())
        self.assertIn("--ephemeral", chat.command())
        chat.running = True
        with self.assertRaisesRegex(ValueError, "생성"):
            chat.ask("PWM이 무엇인가요?")

    @patch.object(SideQuestion, "command", return_value=[sys.executable, "-c", "import time; time.sleep(30)"])
    def test_stop_cancels_question_without_writing_files(self, command):
        with tempfile.TemporaryDirectory() as directory:
            chat = SideQuestion("fake", directory)
            chat.ask("PWM이 무엇인가요?")
            end = time.monotonic() + 3
            while chat.process is None and time.monotonic() < end:
                time.sleep(.01)
            chat.stop()
            self.wait(chat)
            self.assertEqual(list(Path(directory).iterdir()), [])
