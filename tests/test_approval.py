"""Unit tests for the allow/deny PreToolUse approval broker (unit = approval-gate).

Scope: SW unit verification only — the broker's dedup/atomic-resolve/deadline/token-role
behaviour and the /api/approval endpoints. The end-to-end path (physical button -> broker ->
real Claude tool gate) is NOT exercised here; that is a human re-verification step on the
submission build. The PTY key path (/api/press, tests/test_server.py) is the sole E2E-verified
submission path.
"""

import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import SimulatorServer, summarize_tool


class ApprovalBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        state_file = self.workspace / ".claude" / "binddeck-state.json"
        self.server = SimulatorServer(("127.0.0.1", 0), "claude", self.workspace, state_file)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.terminal.stop()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def post(self, path, body, token=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {"Content-Type": "application/json"}
        if token is not None:
            request_headers["X-Simulator-Token"] = token
        request_headers.update(headers or {})
        conn.request("POST", path, json.dumps(body), request_headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    def get(self, path, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"X-Simulator-Token": token} if token is not None else {}
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    # --- broker semantics (in-process) ---------------------------------

    def test_create_dedups_by_tool_use_id_while_pending(self):
        first = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        second = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        self.assertEqual(first, second)
        self.assertEqual(self.server.list_pending()["count"], 1)

    def test_resolve_is_atomic_and_a_second_resolve_conflicts(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "rm -rf x"})
        self.assertIsNotNone(self.server.resolve_approval(approval_id, "allow"))
        # A late or duplicate resolve finds nothing pending: the first decision stands.
        self.assertIsNone(self.server.resolve_approval(approval_id, "deny"))
        self.assertEqual(self.server.wait_for_decision(approval_id), "allow")

    def test_wait_returns_decision_set_concurrently(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Write", {"file_path": "/tmp/x"})

        def resolver():
            time.sleep(0.05)
            self.server.resolve_approval(approval_id, "deny")

        threading.Thread(target=resolver, daemon=True).start()
        self.assertEqual(self.server.wait_for_decision(approval_id), "deny")

    def test_wait_on_unknown_approval_falls_back_to_ask(self):
        self.assertEqual(self.server.wait_for_decision("does-not-exist"), "ask")

    def test_end_session_expires_its_pending_approvals(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        self.server.register_session("b1", "s1")
        self.server.end_session("b1", "s1")
        self.assertEqual(self.server.list_pending()["count"], 0)
        self.assertEqual(self.server.wait_for_decision(approval_id), "ask")

    def test_summarize_tool_is_human_readable_and_bounded(self):
        self.assertEqual(summarize_tool("Bash", {"command": "ls -la"}), "ls -la")
        self.assertEqual(summarize_tool("Write", {"file_path": "/tmp/x"}), "file_path: /tmp/x")
        self.assertLessEqual(len(summarize_tool("Bash", {"command": "x" * 500})), 240)
        self.assertEqual(summarize_tool("Read", "not-a-dict"), "Read")

    # --- endpoints and token roles -------------------------------------

    def test_approval_list_requires_ui_or_device_token(self):
        self.assertEqual(self.get("/api/approval", token="")[0], 403)
        self.assertEqual(self.get("/api/approval", token=self.server.hook_token)[0], 403)
        status, body = self.get("/api/approval", token=self.server.ui_token)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 0)

    def test_wait_endpoint_requires_hook_token_and_validates_payload(self):
        good = {"bridge_id": "b1", "tool_name": "Bash", "tool_use_id": "tu1", "tool_input": {"command": "ls"}}
        self.assertEqual(self.post("/api/approval/wait", good, token=self.server.ui_token)[0], 403)
        self.assertEqual(self.post("/api/approval/wait", {"tool_name": "Bash"}, token=self.server.hook_token)[0], 400)
        self.assertEqual(self.post("/api/approval/wait", {"bridge_id": "b1"}, token=self.server.hook_token)[0], 400)
        self.assertEqual(self.server.list_pending()["count"], 0)

    def test_wait_endpoint_end_to_end_hook_cannot_self_approve(self):
        result = {}

        def waiter():
            result["value"] = self.post(
                "/api/approval/wait",
                {"bridge_id": "b1", "session_id": "s1", "tool_use_id": "tu1",
                 "tool_name": "Bash", "tool_input": {"command": "ls"}},
                token=self.server.hook_token,
            )

        worker = threading.Thread(target=waiter, daemon=True)
        worker.start()
        approval_id = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            pending = self.get("/api/approval", token=self.server.ui_token)[1]["pending"]
            if pending:
                approval_id = pending[0]["id"]
                break
            time.sleep(0.02)
        self.assertIsNotNone(approval_id, "hook wait never registered a pending approval")
        # The hook token registered the request but must NOT be able to resolve it.
        self.assertEqual(self.post("/api/approval/resolve",
                                   {"approval_id": approval_id, "decision": "allow"},
                                   token=self.server.hook_token)[0], 403)
        # The browser (ui token) resolves it.
        status, body = self.post("/api/approval/resolve",
                                 {"approval_id": approval_id, "decision": "allow"},
                                 token=self.server.ui_token)
        self.assertEqual(status, 200)
        self.assertEqual(body["tool_name"], "Bash")
        worker.join(timeout=5)
        self.assertEqual(result["value"][0], 200)
        self.assertEqual(result["value"][1]["decision"], "allow")
        # A second resolve conflicts.
        self.assertEqual(self.post("/api/approval/resolve",
                                   {"approval_id": approval_id, "decision": "deny"},
                                   token=self.server.ui_token)[0], 409)

    def test_device_token_may_resolve(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        status, body = self.post("/api/approval/resolve",
                                 {"approval_id": approval_id, "decision": "deny"},
                                 token=self.server.device_token)
        self.assertEqual(status, 200)
        self.assertEqual(self.server.wait_for_decision(approval_id), "deny")

    def test_resolve_rejects_bad_input(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        self.assertEqual(self.post("/api/approval/resolve",
                                   {"approval_id": approval_id, "decision": "maybe"},
                                   token=self.server.ui_token)[0], 400)
        self.assertEqual(self.post("/api/approval/resolve", {"decision": "allow"},
                                   token=self.server.ui_token)[0], 400)

    def test_session_lifecycle_requires_hook_token(self):
        registration = {"bridge_id": "b1", "session_id": "s1"}
        self.assertEqual(self.post("/api/session/register", registration, token=self.server.ui_token)[0], 403)
        self.assertEqual(self.post("/api/session/register", registration, token=self.server.hook_token)[0], 200)
        self.assertEqual(self.get("/api/approval", token=self.server.ui_token)[1]["sessions"], 1)
        self.assertEqual(self.post("/api/session/end", registration, token=self.server.hook_token)[0], 200)
        self.assertEqual(self.get("/api/approval", token=self.server.ui_token)[1]["sessions"], 0)

    # --- decision audit log (persistent) -------------------------------
    #
    # Scope: the broker records only that a resolver *submitted* a decision — tool name,
    # the short input hash, the decision, the resolver credential role, and timestamps.
    # It stores no summary, no full tool input, and no token, and it proves neither a
    # person's identity nor that the tool actually ran.

    SAFE_LOG_KEYS = {"id", "tool_name", "input_hash", "decision", "role", "created_at", "resolved_at"}

    def test_resolve_records_decision_with_resolver_role(self):
        ui_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        self.assertEqual(self.post("/api/approval/resolve", {"approval_id": ui_id, "decision": "allow"},
                                   token=self.server.ui_token)[0], 200)
        dev_id = self.server.create_approval("b1", "s1", "tu2", "Write", {"file_path": "/tmp/x"})
        self.assertEqual(self.post("/api/approval/resolve", {"approval_id": dev_id, "decision": "deny"},
                                   token=self.server.device_token)[0], 200)
        status, body = self.get("/api/approval/log", token=self.server.ui_token)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)
        newest, older = body["decisions"]  # most-recent-first
        self.assertEqual((newest["tool_name"], newest["decision"], newest["role"]), ("Write", "deny", "device"))
        self.assertEqual((older["tool_name"], older["decision"], older["role"]), ("Bash", "allow", "ui"))
        # Never leaks the summary, the full tool input, or any token.
        for entry in body["decisions"]:
            self.assertEqual(set(entry), self.SAFE_LOG_KEYS)

    def test_decision_log_requires_ui_or_device_token(self):
        self.assertEqual(self.get("/api/approval/log", token="")[0], 403)
        self.assertEqual(self.get("/api/approval/log", token=self.server.hook_token)[0], 403)
        self.assertEqual(self.get("/api/approval/log", token=self.server.ui_token)[0], 200)
        self.assertEqual(self.get("/api/approval/log", token=self.server.device_token)[0], 200)

    def test_duplicate_resolve_logs_exactly_once(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        self.assertEqual(self.post("/api/approval/resolve", {"approval_id": approval_id, "decision": "allow"},
                                   token=self.server.ui_token)[0], 200)
        # A conflicting late resolve is rejected and must NOT add a second record.
        self.assertEqual(self.post("/api/approval/resolve", {"approval_id": approval_id, "decision": "deny"},
                                   token=self.server.ui_token)[0], 409)
        body = self.get("/api/approval/log", token=self.server.ui_token)[1]
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["decisions"][0]["decision"], "allow")

    def test_decision_log_file_is_owner_only_and_survives_restart(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})
        self.assertEqual(self.post("/api/approval/resolve", {"approval_id": approval_id, "decision": "allow"},
                                   token=self.server.ui_token)[0], 200)
        log_path = self.workspace / ".claude" / "approval-log.jsonl"
        self.assertTrue(log_path.exists())
        self.assertEqual(oct(os.stat(log_path).st_mode & 0o777), oct(0o600))
        # A fresh server over the same workspace warms its panel view from disk.
        restarted = SimulatorServer(("127.0.0.1", 0), "claude", self.workspace,
                                    self.workspace / ".claude" / "binddeck-state.json")
        try:
            view = restarted.recent_decisions()
            self.assertEqual(view["count"], 1)
            self.assertEqual(view["decisions"][0]["tool_name"], "Bash")
        finally:
            restarted.terminal.stop()
            restarted.server_close()

    def test_log_write_failure_withholds_the_decision(self):
        approval_id = self.server.create_approval("b1", "s1", "tu1", "Bash", {"command": "ls"})

        def boom(_entry):
            raise OSError("disk full")

        self.server._append_decision_log = boom
        # The resolve must not deliver an unlogged decision: 500, request stays pending.
        self.assertEqual(self.post("/api/approval/resolve", {"approval_id": approval_id, "decision": "allow"},
                                   token=self.server.ui_token)[0], 500)
        self.assertEqual(self.server.list_pending()["count"], 1)
        self.assertEqual(self.get("/api/approval/log", token=self.server.ui_token)[1]["count"], 0)

    # --- hook_bridge.py process, end-to-end (software-only, no hardware) ------
    #
    # These drive the REAL hooks/hook_bridge.py binary exactly as Claude Code's
    # PreToolUse hook would: a PreToolUse event on stdin, BUTTONLAB_* in the
    # environment, and the permissionDecision contract expected back on stdout.
    # A web resolver holding the ui token (the same token the browser already
    # gets from /api/session) approves/denies over HTTP. This exercises the whole
    # chain — hook process -> broker -> web resolver -> hook process -> stdout —
    # without any hardware or browser. The only piece left for a live demo is
    # Claude Code itself honouring the emitted decision (its documented contract).

    HOOK_BRIDGE = Path(__file__).resolve().parents[1] / "hooks" / "hook_bridge.py"

    def _run_hook_process(self, stdin_payload, env, timeout=30):
        proc = subprocess.run(
            [sys.executable, str(self.HOOK_BRIDGE)],
            input=json.dumps(stdin_payload),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, f"hook exited nonzero; stderr={proc.stderr!r}")
        return json.loads(proc.stdout)

    def _gate_env(self, bridge_id):
        env = dict(os.environ)
        env["BUTTONLAB_URL"] = f"http://127.0.0.1:{self.server.server_port}"
        env["BUTTONLAB_HOOK_TOKEN"] = self.server.hook_token
        env["BUTTONLAB_BRIDGE_ID"] = bridge_id
        return env

    def _resolve_next_pending(self, decision, resolved, deadline_s=8):
        """Poll /api/approval as the browser (ui token) would and resolve the
        first pending request, recording the resolve HTTP status in `resolved`."""
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            pending = self.get("/api/approval", token=self.server.ui_token)[1]["pending"]
            if pending:
                approval_id = pending[0]["id"]
                status, _ = self.post(
                    "/api/approval/resolve",
                    {"approval_id": approval_id, "decision": decision},
                    token=self.server.ui_token,
                )
                resolved["status"] = status
                return
            time.sleep(0.02)

    def test_hook_process_e2e_returns_web_allow(self):
        resolved = {}
        threading.Thread(target=self._resolve_next_pending, args=("allow", resolved), daemon=True).start()
        out = self._run_hook_process(
            {"hook_event_name": "PreToolUse", "session_id": "s-e2e", "tool_use_id": "tu-allow",
             "tool_name": "Bash", "tool_input": {"command": "npm test"}},
            self._gate_env("b-e2e-allow"),
        )
        self.assertEqual(resolved.get("status"), 200, "web resolver never approved")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_hook_process_e2e_returns_web_deny(self):
        resolved = {}
        threading.Thread(target=self._resolve_next_pending, args=("deny", resolved), daemon=True).start()
        out = self._run_hook_process(
            {"hook_event_name": "PreToolUse", "session_id": "s-e2e", "tool_use_id": "tu-deny",
             "tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/scratch"}},
            self._gate_env("b-e2e-deny"),
        )
        self.assertEqual(resolved.get("status"), 200, "web resolver never denied")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_hook_process_without_broker_env_fails_safe_to_ask(self):
        # No BUTTONLAB_* configured: the hook must never block or crash the tool;
        # it fails safe by deferring to Claude Code's normal prompt ("ask").
        env = {k: v for k, v in os.environ.items() if not k.startswith("BUTTONLAB_")}
        out = self._run_hook_process(
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}},
            env,
            timeout=10,
        )
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")


if __name__ == "__main__":
    unittest.main()
