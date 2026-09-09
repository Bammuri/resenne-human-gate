import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow import Workflow, Checkpoints, signature


FAKE_CODEX = """
import json, pathlib, sys, time
prompt = sys.stdin.read()
result = '확인 완료'
if '구현 없이 계획만 작성하라.' in prompt:
    result = '계획: app.txt만 수정하고 결과를 검사한다.'
if '승인된 계획만 구현하라.' in prompt:
    pathlib.Path('app.txt').write_text('built')
    result = '승인된 계획 구현·검증 완료\\nVERDICT: PASS'
if '테스트, lint, 타입 검사 및 요구사항 충족을 검사하라.' in prompt:
    result = 'app.txt 확인 완료\\nVERDICT: PASS'
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': result}}), flush=True)
"""


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "app.txt").write_text("user's existing edit")
        self.flow = Workflow("fake-codex", self.root)
        self.flow.configure("app.txt의 내용을 수정하는 목표", 1)
        self.flow.inputs["ideation"] = {"goal": "app.txt의 내용을 수정하는 목표", "decision": "approved"}

    def tearDown(self):
        self.flow.stop()
        self.wait()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 5
        while self.flow.snapshot()["running"] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.flow.snapshot()["running"], "job did not finish")

    def run_stage(self, stage):
        self.flow.start(stage)
        self.wait()
        self.assertFalse(self.flow.error, self.flow.error)

    def plan(self):
        autonomy = self.flow.autonomy
        self.flow.autonomy = 1
        self.run_stage("initialization")
        self.run_stage("inception")
        self.flow.autonomy = autonomy
        self.flow.approve(self.flow.plan)

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_human_gate_and_one_use_approval(self, command):
        with self.assertRaisesRegex(ValueError, "계획 승인"):
            self.flow.start("construction")
        with self.assertRaisesRegex(ValueError, "INITIALIZATION"):
            self.flow.start("inception")
        self.plan()
        self.assertTrue(self.flow.snapshot()["approved"])
        self.run_stage("construction")
        self.assertEqual((self.root / "app.txt").read_text(), "built")
        self.assertFalse(self.flow.snapshot()["approved"])
        with self.assertRaisesRegex(ValueError, "계획 승인"):
            self.flow.start("construction")
        preview = self.flow.preview()
        self.assertIn("user's existing edit", preview["diff"])
        result = self.flow.revert(preview["token"])
        self.assertEqual((self.root / "app.txt").read_text(), "user's existing edit")
        self.assertEqual((Path(result["backup"]) / "app.txt").read_text(), "built")

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_changed_files_require_reapproval(self, command):
        self.plan()
        (self.root / "app.txt").write_text("new human change")
        with self.assertRaisesRegex(ValueError, "변경"):
            self.flow.start("construction")
        with self.assertRaisesRegex(ValueError, "변경"):
            self.flow.approve(self.flow.plan)

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_changed_requirements_and_autonomy_invalidate_approval(self, command):
        self.plan()
        self.flow.configure(self.flow.requirements, 0)
        self.assertFalse(self.flow.approval)
        with self.assertRaisesRegex(ValueError, "계획 승인"):
            self.flow.start("construction")
        self.flow.approve(self.flow.plan)
        self.flow.configure("다른 목표", 1)
        self.assertFalse(self.flow.plan)
        self.assertFalse(self.flow.results)

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_autonomy_pipeline(self, command):
        self.flow.configure(self.flow.requirements, 5)
        self.plan()
        self.run_stage("construction")
        self.assertTrue(self.flow.results["construction"].endswith("VERDICT: PASS"))
        self.assertIn("operation", self.flow.results)

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX.replace("VERDICT: PASS", "VERDICT: FAIL")])
    def test_failed_verification_stops_pipeline(self, command):
        self.flow.configure(self.flow.requirements, 5)
        self.plan()
        self.flow.start("construction")
        self.wait()
        self.assertIn("검증", self.flow.error)
        self.assertNotIn("operation", self.flow.results)

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", "import time; time.sleep(60)"])
    def test_stop_works_while_running_and_blocks_reconfigure(self, command):
        self.flow.start("initialization")
        with self.assertRaisesRegex(ValueError, "STOP"):
            self.flow.configure("changed", 3)
        with self.assertRaises(ValueError):
            self.flow.start("ideation")
        self.flow.stop()
        self.wait()
        self.assertTrue(self.flow.cancelled)
        self.assertNotIn("initialization", self.flow.results)

    def test_sandbox_commands(self):
        for stage in ["ideation", "initialization", "ask", "inception", "operation"]:
            self.assertIn("read-only", self.flow.command(stage))
        self.assertIn("workspace-write", self.flow.command("construction"))
        self.flow.autonomy = 0
        self.assertIn("workspace-write", self.flow.command("construction"))
        for stage in ["construction", "construction", "inception"]:
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", self.flow.command(stage))

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_run_now_prepares_missing_plan_without_separate_approval_or_changing_level(self, command):
        for level in range(6):
            with self.subTest(level=level):
                self.flow.configure("app.txt의 내용을 수정하는 목표", level)
                self.flow.inputs["ideation"]["decision"] = "pending"
                self.flow.results = {}
                self.flow.plan = self.flow.plan_signature = self.flow.approval = ""
                self.flow.start("construction", immediate=True)
                self.wait()
                self.assertFalse(self.flow.error, self.flow.error)
                self.assertEqual(self.flow.autonomy, level)
                self.assertIn("initialization", self.flow.results)
                self.assertIn("inception", self.flow.results)
                self.assertTrue(self.flow.results["construction"].endswith("VERDICT: PASS"))
                self.assertEqual("operation" in self.flow.results, level in (3, 5))
                self.assertFalse(self.flow.awaiting_approval)
                self.assertIsNotNone(self.flow.checkpoints.saved)

    def test_run_now_preserves_explicit_user_hold(self):
        self.flow.inputs["ideation"]["decision"] = "hold"
        with self.assertRaisesRegex(ValueError, "보류"):
            self.flow.start("construction", immediate=True)

    def test_checkpoint_changes_preview_stale_guard_and_backup(self):
        cp = self.flow.checkpoints
        cp.capture(signature(cp.inventory()))
        (self.root / "app.txt").unlink()
        (self.root / "new.txt").write_text("created by build")
        preview = cp.preview()
        self.assertEqual([item["kind"] for item in preview["changes"]], ["deleted", "added"])
        (self.root / "new.txt").write_text("human edit after preview")
        with self.assertRaisesRegex(ValueError, "변경"):
            cp.restore(preview["token"])
        result = cp.restore(cp.preview()["token"])
        self.assertFalse((self.root / "new.txt").exists())
        self.assertEqual((Path(result["backup"]) / "new.txt").read_text(), "human edit after preview")
        self.assertEqual((self.root / "app.txt").read_text(), "user's existing edit")

    def test_symlink_cannot_redirect_restore_outside_workspace(self):
        cp = self.flow.checkpoints
        (self.root / "nested").mkdir()
        (self.root / "nested/file.txt").write_text("original")
        cp.capture(signature(cp.inventory()))
        (self.root / "nested/file.txt").unlink()
        (self.root / "nested").rmdir()
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "nested").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "심볼릭"):
                cp.preview()
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_cache_and_git_are_not_restored(self):
        for name in [".git", "node_modules", "__pycache__"]:
            (self.root / name).mkdir()
            (self.root / name / "state").write_text("unchanged")
        files = self.flow.checkpoints.inventory()
        self.assertEqual(list(files), ["app.txt"])

    def test_phase_inputs_save_distinct_markdown_and_survive_restart(self):
        self.flow.configure(None, 2, "initialization", {"environment": "UNO R4 WiFi / Serial1"})
        self.flow.configure(None, 2, "ideation", {"goal": "버튼으로 AI를 제어", "users": "개발자"})
        self.flow.configure(None, 2, "inception", {"decisions": "버튼 6은 START"})
        docs = self.root / "aidlc-docs"
        self.assertEqual(len(list(docs.glob("*.md"))), 5)
        self.assertIn("Serial1", (docs / "01-initialization.md").read_text())
        self.assertNotIn("Serial1", (docs / "02-ideation.md").read_text())
        self.assertIn("버튼 6은 START", (docs / "03-inception.md").read_text())
        restored = Workflow("fake-codex", self.root)
        self.assertEqual(restored.inputs, self.flow.inputs)
        self.assertEqual(restored.autonomy, 2)
        self.assertFalse(restored.approval)
        self.assertEqual(len(restored.snapshot()["schema"]), 5)
        with self.assertRaises(ValueError): self.flow.configure(None, 2, "operation", {"goal": "wrong field"})

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_full_auto_runs_five_phases_without_human_approval(self, command):
        self.flow.configure(self.flow.requirements, 5)
        self.run_stage("initialization")
        self.assertEqual(list(self.flow.results), ["initialization", "ideation", "inception", "construction", "operation"])
        self.assertEqual((self.root / "app.txt").read_text(), "built")
        self.assertFalse(self.flow.snapshot()["awaitingApproval"])
        self.assertIn("VERDICT: PASS", (self.root / "aidlc-docs/04-construction.md").read_text())

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_gated_auto_waits_before_construction_and_resumes_after_approval(self, command):
        self.flow.configure(self.flow.requirements, 3)
        self.run_stage("initialization")
        self.assertEqual(list(self.flow.results), ["initialization", "ideation", "inception"])
        self.assertTrue(self.flow.snapshot()["awaitingApproval"])
        self.assertEqual((self.root / "app.txt").read_text(), "user's existing edit")
        self.flow.approve(self.flow.plan)
        self.run_stage("construction")
        self.assertNotIn("operation", self.flow.results)
        self.assertIn("CONSTRUCTION", self.flow.snapshot()["humanGate"])
        self.flow.configure(None, 3, "construction", {"decision": "approved"})
        self.run_stage("operation")
        self.assertIn("operation", self.flow.results)

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_auto_build_stops_before_operation_and_upstream_edits_invalidate_results(self, command):
        self.flow.configure(self.flow.requirements, 4)
        self.run_stage("initialization")
        self.assertIn("construction", self.flow.results)
        self.assertNotIn("operation", self.flow.results)
        self.flow.configure(None, 4, "ideation", {"goal": "새 목표"})
        self.assertEqual(list(self.flow.results), ["initialization"])
        self.assertFalse(self.flow.plan)
        self.assertNotIn("VERDICT: PASS", (self.root / "aidlc-docs/04-construction.md").read_text())

    def test_document_symlinks_cannot_write_outside_workspace(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "original.md"
            target.write_text("keep")
            doc = self.root / "aidlc-docs/03-inception.md"
            doc.unlink(); doc.symlink_to(target)
            with self.assertRaises(ValueError): self.flow.configure(None, 1, "inception", {"design": "changed"})
            self.assertEqual(target.read_text(), "keep")

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_explicit_question_does_not_execute_phase_or_overwrite_result_in_full_auto(self, command):
        self.flow.configure(self.flow.requirements, 5)
        self.flow.results["construction"] = "previous build result"
        docs = self.root / "aidlc-docs"
        before = {p.name: p.read_bytes() for p in docs.iterdir()}
        self.flow.start("construction", question_only=True, drafts={"construction": {"commands": "unsaved ASK input"}})
        self.wait()
        self.assertFalse(self.flow.error)
        self.assertTrue(self.flow.snapshot()["questionOnly"])
        self.assertEqual(self.flow.results, {"construction": "previous build result"})
        self.assertEqual(command.call_count, 1)
        self.assertEqual((self.root / "app.txt").read_text(), "user's existing edit")
        self.assertIn("construction", self.flow.question_results)
        self.assertEqual(before, {p.name: p.read_bytes() for p in docs.iterdir()})
        self.assertIn("unsaved ASK input", self.flow.prompt("construction"))
        self.assertNotEqual(self.flow.inputs["construction"].get("commands"), "unsaved ASK input")
        requirements = self.flow.requirements
        self.flow.questions = [{"id": "ask-choice", "prompt": "어느 방식?", "options": [{"id": "1", "label": "첫 방식"}]}]
        self.flow.answer(self.flow.run_id, "ask-choice", "1")
        self.assertIn("첫 방식", self.flow.ask_answers["construction"])
        self.assertEqual(self.flow.requirements, requirements)
        self.assertEqual(before, {p.name: p.read_bytes() for p in docs.iterdir()})
        self.assertEqual(Workflow("fake-codex", self.root).question_results, {})
        self.assertNotIn("승인된 계획만 구현하라", self.flow.prompt("construction"))

    def test_human_instructions_are_durable_and_binding(self):
        self.flow.configure(None, 1, "inception", {"instruction": "기존 API 호환성을 유지"})
        self.assertIn("기존 API 호환성을 유지", (self.root / "aidlc-docs/03-inception.md").read_text())
        restored = Workflow("fake-codex", self.root)
        self.assertIn("기존 API 호환성을 유지", restored.prompt("construction"))
        self.assertIn("are binding", restored.prompt("construction"))

    @patch.object(Workflow, "command", return_value=[sys.executable, "-c", FAKE_CODEX])
    def test_human_gates_cannot_be_bypassed_by_full_auto(self, command):
        self.flow.configure(None, 5, "ideation", {"decision": "hold"})
        with self.assertRaisesRegex(ValueError, "보류"):
            self.flow.start("inception")
        self.run_stage("initialization")
        self.assertEqual(list(self.flow.results), ["initialization"])
        self.assertIn("보류", self.flow.snapshot()["humanGate"])
        self.assertEqual((self.root / "app.txt").read_text(), "user's existing edit")

    def test_decision_only_save_preserves_reviewed_result_and_changed_rules_invalidate_it(self):
        self.flow.results["construction"] = "reviewed result"
        self.flow.configure(None, 1, "construction", {"decision": "approved"})
        self.assertEqual(self.flow.results["construction"], "reviewed result")
        self.flow.configure(None, 1, "inception", {"instruction": "new constraint"})
        self.assertNotIn("construction", self.flow.results)
        self.assertEqual(self.flow.inputs["construction"]["decision"], "pending")

    def test_pending_intent_does_not_authorize_manual_design(self):
        self.flow.inputs["ideation"]["decision"] = "pending"
        with self.assertRaisesRegex(ValueError, "IDEATION"):
            self.flow.start("inception")

    def test_single_brief_replaces_legacy_fields_and_drives_goal_and_markdown(self):
        self.flow.configure(None, 1, "ideation", {"brief": "배송 전에 주문 취소. 부분 취소 제외."})
        self.assertEqual(self.flow.requirements, "배송 전에 주문 취소. 부분 취소 제외.")
        self.assertFalse(self.flow.inputs["ideation"]["goal"])
        md = (self.root / "aidlc-docs/02-ideation.md").read_text()
        self.assertIn("부분 취소 제외", md)
        self.assertNotIn("### 사용자 · 사용 시나리오", md)
        self.flow.configure(None, 1, "ideation", {"decision": "approved"})
        self.assertIn("부분 취소 제외", Workflow("fake-codex", self.root).prompt("inception"))


if __name__ == "__main__":
    unittest.main()
