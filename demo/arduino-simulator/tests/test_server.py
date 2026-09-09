import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import SimulatorServer


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.server = SimulatorServer(("127.0.0.1", 0), "test-thread", "/fake/codex")
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.terminal.stop()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def request(self, choice="yes", request_id="press-1", headers=None, payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {
            "Content-Type": "application/json",
            "X-Simulator-Token": self.server.token,
        }
        request_headers.update(headers or {})
        body = payload if payload is not None else json.dumps({"choice": choice, "requestId": request_id})
        conn.request("POST", "/api/press", body, request_headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    @patch("server.subprocess.run")
    def test_yes_is_sent_to_fixed_thread_once_on_retry(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "queued", "")
        first = self.request()
        second = self.request()
        self.assertEqual(first, (200, {"choice": "yes", "status": "queued"}))
        self.assertEqual(first, second)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["/fake/codex", "queue", "--thread", "test-thread", "--message", "yes"])
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch("server.subprocess.run")
    def test_no_is_forwarded_without_mapping_to_approval(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "queued", "")
        self.assertEqual(self.request("no")[0], 200)
        self.assertEqual(run.call_args.args[0][-1], "no")
        self.assertEqual(self.request("yes")[0], 409)
        run.assert_called_once()

    @patch("server.subprocess.run")
    def test_rejects_cross_origin_and_missing_token(self, run):
        self.assertEqual(self.request(headers={"Origin": "https://unrelated.example"})[0], 403)
        self.assertEqual(self.request(headers={"X-Simulator-Token": ""})[0], 403)
        self.assertEqual(self.request(headers={"Host": f"attacker.example:{self.server.server_port}"})[0], 403)
        run.assert_not_called()

    @patch("server.subprocess.run")
    def test_rejects_arbitrary_commands_and_malformed_data(self, run):
        for choice in ["yes\nrm anything", "y", "YES", "", None, ["yes"]]:
            self.assertEqual(self.request(choice)[0], 400)
        for payload in ["null", "[]", "{broken", "{}"]:
            self.assertEqual(self.request(payload=payload)[0], 400)
        run.assert_not_called()

    @patch("server.subprocess.run")
    def test_missing_codex_session_cannot_send(self, run):
        self.server.thread = ""
        self.assertEqual(self.request()[0], 503)
        run.assert_not_called()

    @patch("server.subprocess.run")
    def test_repeated_presses_are_throttled(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "queued", "")
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(request_id="press-2")[0], 429)
        run.assert_called_once()

    @patch("server.subprocess.run")
    def test_queue_failure_is_not_reported_as_success(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "session unavailable")
        status, body = self.request()
        self.assertEqual(status, 502)
        self.assertIn("error", body)
        self.assertNotIn("status", body)

    @patch("server.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 20))
    def test_uncertain_timeout_is_not_automatically_retried(self, run):
        self.assertEqual(self.request()[0], 504)
        self.assertEqual(self.request()[0], 504)
        run.assert_called_once()

    @patch("server.subprocess.run")
    def test_new_session_without_rollout_explains_how_to_connect(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "no rollout found for thread id test-thread")
        status, body = self.request()
        self.assertEqual(status, 502)
        self.assertIn("첫 요청", body["error"])
        self.assertIn("Enter", body["error"])
        self.assertEqual(self.request(), (status, body))
        run.assert_called_once()

    def test_static_files_and_session_api(self):
        for path in ["/", "/app.js", "/serial.js", "/web-terminal.js", "/vendor/xterm.js", "/vendor/xterm.css", "/vendor/addon-fit.js", "/style.css", "/favicon.svg", "/firmware.ino", "/api/session"]:
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
            conn.request("GET", path)
            response = conn.getresponse()
            self.assertEqual(response.status, 200, path)
            self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
            self.assertTrue(response.read())
            conn.close()

    def test_output_requires_token_and_valid_cursor(self):
        with patch.object(self.server.output, "snapshot", return_value={"events": [], "cursor": 7}) as snapshot:
            for path, token, expected in [
                ("/api/output", "", 403),
                ("/api/output?after=-1", self.server.token, 400),
                ("/api/output?after=bad", self.server.token, 400),
                ("/api/output?after=3&generation=test", self.server.token, 200),
            ]:
                conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
                conn.request("GET", path, headers={"X-Simulator-Token": token})
                response = conn.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                conn.close()
            snapshot.assert_called_once_with(3, "test")

    @patch("server.subprocess.run")
    def test_terminal_target_uses_its_detected_session(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, 'queued', '')
        with patch.object(self.server.terminal, 'target_thread', return_value='web-thread'):
            result = self.request(payload=json.dumps({'choice':'no','requestId':'web-1','target':'terminal'}))
        self.assertEqual(result[0],200)
        self.assertEqual(run.call_args.args[0], ['/fake/codex','queue','--thread','web-thread','--message','no'])

    def test_terminal_start_requires_token(self):
        with patch.object(self.server.terminal, 'start') as start:
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
            conn.request('POST','/api/terminal/start','{"kind":"shell"}',{'Content-Type':'application/json'})
            response=conn.getresponse()
            self.assertEqual(response.status,403)
            response.read(); conn.close()
            start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
