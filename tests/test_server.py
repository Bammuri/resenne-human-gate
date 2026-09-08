import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import SimulatorServer
from terminal import ACTIONS


class BridgeTests(unittest.TestCase):
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

    def request(self, choice="yes", request_id="press-1", headers=None, payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {"Content-Type": "application/json", "X-Simulator-Token": self.server.token}
        request_headers.update(headers or {})
        body = payload if payload is not None else json.dumps({"choice": choice, "requestId": request_id})
        conn.request("POST", "/api/press", body, request_headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    def ready(self):
        # Pretend an app-owned Claude PTY is running so presses are accepted.
        return patch.object(self.server.terminal, "claude_ready", return_value=True)

    def get(self, path, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {} if token is None else {"X-Simulator-Token": token}
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        result = response.status, response.getheader("X-Frame-Options"), response.read()
        conn.close()
        return result

    def test_press_is_sent_once_on_retry_and_is_idempotent(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice") as send:
            first = self.request("yes", "press-1")
            second = self.request("yes", "press-1")
        self.assertEqual(first, (200, {"choice": "yes", "status": "sent"}))
        self.assertEqual(first, second)
        send.assert_called_once_with("yes")

    def test_every_mapped_action_is_accepted(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice") as send:
            for index, action in enumerate(ACTIONS):
                self.server.last_sent = 0.0   # bypass the 0.5s throttle for this survey
                self.assertEqual(self.request(action, f"req-{index}"), (200, {"choice": action, "status": "sent"}))
        self.assertEqual([call.args[0] for call in send.call_args_list], list(ACTIONS))

    def test_answers_are_recorded_for_oled_but_navigation_is_not(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice"):
            self.assertEqual(self.request("no", "a1")[0], 200)
            self.assertEqual(self.server.state.snapshot()["lastAnswer"], "no")
            self.server.last_sent = 0.0
            self.assertEqual(self.request("nav_up", "a2")[0], 200)
        self.assertEqual(self.server.state.snapshot()["lastAnswer"], "no")   # nav is not an answer

    def test_rejects_cross_origin_bad_host_and_missing_token(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice") as send:
            self.assertEqual(self.request(headers={"Origin": "https://unrelated.example"})[0], 403)
            self.assertEqual(self.request(headers={"X-Simulator-Token": ""})[0], 403)
            self.assertEqual(self.request(headers={"Host": f"attacker.example:{self.server.server_port}"})[0], 403)
            send.assert_not_called()

    def test_rejects_unknown_actions_and_malformed_json(self):
        with patch.object(self.server.terminal, "send_choice") as send:
            for choice in ["yes\nrm anything", "y", "YES", "", None, ["yes"], "queue", "\r"]:
                self.assertEqual(self.request(choice)[0], 400)
            for bad_request_id in [None, "", "x" * 81, 5]:
                self.assertEqual(self.request(payload=json.dumps({"choice": "yes", "requestId": bad_request_id}))[0], 400)
            for payload in ["null", "[]", "{broken", "{}"]:
                self.assertEqual(self.request(payload=payload)[0], 400)
            send.assert_not_called()

    def test_no_claude_session_cannot_send(self):
        # claude_ready() is False (nothing started), so a valid press is refused.
        with patch.object(self.server.terminal, "send_choice") as send:
            self.assertEqual(self.request("yes")[0], 503)
            send.assert_not_called()

    def test_repeated_presses_are_throttled(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice") as send:
            self.assertEqual(self.request("yes", "p1")[0], 200)
            self.assertEqual(self.request("no", "p2")[0], 429)
            send.assert_called_once()

    def test_reused_request_id_with_a_different_choice_conflicts(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice") as send:
            self.assertEqual(self.request("yes", "dup")[0], 200)
            self.server.last_sent = 0.0
            self.assertEqual(self.request("no", "dup")[0], 409)
            send.assert_called_once()

    def test_concurrent_send_is_serialized_with_409(self):
        with self.ready():
            self.assertTrue(self.server.send_lock.acquire(blocking=False))
            try:
                self.assertEqual(self.request("yes", "busy")[0], 409)
            finally:
                self.server.send_lock.release()

    def test_send_failure_is_not_reported_as_success(self):
        with self.ready(), patch.object(self.server.terminal, "send_choice", side_effect=ValueError("대상 터미널이 변경됐습니다.")):
            status, body = self.request()
            self.assertEqual(status, 502)
            self.assertIn("error", body)
            self.assertNotIn("status", body)
        with self.ready(), patch.object(self.server.terminal, "send_choice", side_effect=OSError):
            self.server.last_sent = 0.0
            self.assertEqual(self.request("no", "p3")[0], 502)

    def test_static_files_and_session_api(self):
        for path in ["/", "/app.js", "/serial.js", "/web-terminal.js", "/vendor/xterm.js", "/vendor/xterm.css", "/vendor/addon-fit.js", "/style.css", "/favicon.svg", "/firmware.ino"]:
            status, frame, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(frame, "DENY")
            self.assertTrue(body)
        status, _, body = self.get("/api/session")
        session = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(session["claudeAvailable"])
        self.assertEqual(session["workspace"], str(self.workspace))
        self.assertEqual(session["token"], self.server.token)

    def test_state_requires_token_and_returns_snapshot(self):
        self.assertEqual(self.get("/api/state")[0], 403)
        self.assertEqual(self.get("/api/state", token="wrong")[0], 403)
        status, _, body = self.get("/api/state", token=self.server.token)
        snapshot = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(set(snapshot), {"status", "available", "lastAnswer", "source"})

    def test_terminal_snapshot_requires_token_and_valid_cursor(self):
        self.assertEqual(self.get("/api/terminal")[0], 403)
        self.assertEqual(self.get("/api/terminal?after=-1", token=self.server.token)[0], 400)
        self.assertEqual(self.get("/api/terminal?after=bad", token=self.server.token)[0], 400)
        self.assertEqual(self.get("/api/terminal?after=3&generation=x", token=self.server.token)[0], 200)

    def header(self, path, name):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        value = response.getheader(name)
        response.read()
        conn.close()
        return value

    def test_demo_bundle_is_served_under_the_same_strict_csp(self):
        from server import DEFAULT_CSP
        # The hardware-free demo is three sibling files served like any other asset.
        for path in ["/demo/", "/demo/demo.css", "/demo/demo.js"]:
            status, frame, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(frame, "DENY")
            self.assertTrue(body)
        # The demo inherits the app's strict CSP — no per-route relaxation. script-src
        # stays 'self' on BOTH pages and is never widened to 'unsafe-inline'.
        self.assertEqual(self.header("/", "Content-Security-Policy"), DEFAULT_CSP)
        self.assertEqual(self.header("/demo/", "Content-Security-Policy"), DEFAULT_CSP)
        script_src = DEFAULT_CSP.split("script-src", 1)[1].split(";", 1)[0]
        self.assertIn("'self'", script_src)
        self.assertNotIn("'unsafe-inline'", script_src)
        # The demo is a static explainer: no network, no /api, no external URLs anywhere.
        demo = Path(__file__).resolve().parents[1] / "demo"
        for name in ["binddeck-claude-demo.html", "demo.js", "demo.css"]:
            text = (demo / name).read_text(encoding="utf-8")
            for forbidden in ["fetch(", "XMLHttpRequest", "/api/", "http://", "https://"]:
                self.assertNotIn(forbidden, text, f"{name} unexpectedly references {forbidden!r}")

    def test_terminal_start_requires_token(self):
        with patch.object(self.server.terminal, "start") as start:
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            conn.request("POST", "/api/terminal/start", '{"kind":"shell"}', {"Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.close()
            start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
