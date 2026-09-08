#!/usr/bin/env python3
"""Local BindDeck button simulator that drives an app-owned Claude Code session."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from claude_state import ClaudeStateReader
from terminal import ACTIONS, WebTerminal


ROOT = Path(__file__).resolve().parent
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/serial.js": ("serial.js", "text/javascript; charset=utf-8"),
    "/web-terminal.js": ("web-terminal.js", "text/javascript; charset=utf-8"),
    "/vendor/xterm.js": ("vendor/xterm.js", "text/javascript; charset=utf-8"),
    "/vendor/addon-fit.js": ("vendor/addon-fit.js", "text/javascript; charset=utf-8"),
    "/vendor/xterm.css": ("vendor/xterm.css", "text/css; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/firmware.ino": ("firmware/binddeck_claude/binddeck_claude.ino", "text/plain; charset=utf-8"),
    "/demo/fake-serial.js": ("demo/fake-serial.js", "text/javascript; charset=utf-8"),
    # The hardware-free explainer. Its <style>/<script> live in sibling files so the
    # page loads under the same strict CSP as the app (no 'unsafe-inline' anywhere) and
    # still opens standalone via file:// (relative hrefs resolve to the sibling files).
    # Served under a trailing-slash "directory" URL so those relative hrefs resolve to
    # /demo/demo.css and /demo/demo.js.
    "/demo/": ("demo/binddeck-claude-demo.html", "text/html; charset=utf-8"),
    "/demo/demo.css": ("demo/demo.css", "text/css; charset=utf-8"),
    "/demo/demo.js": ("demo/demo.js", "text/javascript; charset=utf-8"),
}

# One strict Content-Security-Policy for every response. Per project rule it is NEVER
# relaxed with script-src 'unsafe-inline' — the app page holds the session token and
# talks to /api, and the /demo page ships its script as a same-origin file, so 'self'
# is enough for both. object-src 'none' hardens against legacy plugin vectors.
DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


class SimulatorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, claude, workspace=None, state_file=None):
        super().__init__(address, Handler)
        self.claude = claude
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.state_file = Path(state_file) if state_file else (self.workspace / ".claude" / "binddeck-state.json")
        self.token = secrets.token_urlsafe(32)
        self.send_lock = threading.Lock()
        self.last_sent = 0.0
        self.replies = {}
        self.terminal = WebTerminal(claude, self.workspace)
        self.state = ClaudeStateReader(self.state_file, terminal=self.terminal)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if self.path.startswith(("/api/state", "/api/terminal")) and len(args) > 1 and str(args[1]) == "200":
            return
        print(f"{self.log_date_time_string()} {format % args}", flush=True)

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", DEFAULT_CSP)
        self.send_header("Permissions-Policy", "serial=(self)")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        port = self.server.server_port
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {"error": "로컬 주소로 접속해 주세요."})
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/api/session":
            return self.respond(200, {
                "claudeAvailable": bool(self.server.claude),
                "workspace": str(self.server.workspace),
                "token": self.server.token,
            })
        if path in ("/api/state", "/api/terminal"):
            if not secrets.compare_digest(self.headers.get("X-Simulator-Token", ""), self.server.token):
                return self.respond(403, {"error": "페이지를 새로고침해 주세요."})
            if path == "/api/state":
                return self.respond(200, self.server.state.snapshot())
            query = parse_qs(parsed.query)
            try:
                after = int(query.get("after", ["0"])[0])
                if after < 0:
                    raise ValueError
            except ValueError:
                return self.respond(400, {"error": "잘못된 출력 위치입니다."})
            generation = query.get("generation", [""])[0]
            return self.respond(200, self.server.terminal.snapshot(after, generation))
        if path not in ASSETS:
            return self.respond(404, {"error": "페이지를 찾을 수 없습니다."})
        filename, content_type = ASSETS[path]
        self.respond(200, (ROOT / filename).read_bytes(), content_type)

    def do_POST(self):
        if not self.valid_host():
            return self.respond(403, {"error": "로컬 주소로 접속해 주세요."})
        if self.path not in ("/api/press", "/api/terminal/start", "/api/terminal/input", "/api/terminal/resize", "/api/terminal/stop"):
            return self.respond(404, {"error": "경로를 찾을 수 없습니다."})
        expected_origin = f"http://{self.headers.get('Host')}"
        if self.headers.get("Origin") not in (None, expected_origin):
            return self.respond(403, {"error": "같은 페이지에서만 입력할 수 있습니다."})
        if not secrets.compare_digest(self.headers.get("X-Simulator-Token", ""), self.server.token):
            return self.respond(403, {"error": "페이지를 새로고침해 주세요."})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"error": "JSON 입력이 필요합니다."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 50000:
                raise ValueError
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, OSError):
            return self.respond(400, {"error": "올바른 JSON 입력이 필요합니다."})
        if self.path.startswith("/api/terminal/"):
            return self.handle_terminal(payload)
        return self.handle_press(payload)

    def handle_press(self, payload):
        try:
            choice, request_id = payload.get("choice"), payload.get("requestId")
            if choice not in ACTIONS:
                raise ValueError
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
                raise ValueError
        except (ValueError, OSError):
            return self.respond(400, {"error": "지원하지 않는 동작입니다."})
        if not self.server.terminal.claude_ready():
            return self.respond(503, {"error": "연결할 Claude 세션이 없습니다. 웹 터미널에서 Claude를 시작해 주세요."})
        if not self.server.send_lock.acquire(blocking=False):
            return self.respond(409, {"error": "이전 답변을 전송 중입니다. 잠시 기다려 주세요."})
        try:
            cache_key = (choice, request_id)
            if cache_key in self.server.replies:
                status, reply = self.server.replies[cache_key]
                return self.respond(status, reply)
            if any(rid == request_id for _, rid in self.server.replies):
                return self.respond(409, {"error": "이미 사용한 요청 ID입니다."})
            if time.monotonic() - self.server.last_sent < 0.5:
                return self.respond(429, {"error": "잠시 후 다시 눌러 주세요."})
            self.server.last_sent = time.monotonic()
            try:
                self.server.terminal.send_choice(choice)
                status, reply = 200, {"choice": choice, "status": "sent"}
                if choice in ("yes", "no", "stop", "confirm"):
                    self.server.state.note_answer(choice)
            except ValueError as error:
                status, reply = 502, {"error": str(error)}
            except OSError:
                status, reply = 502, {"error": "Claude 세션에 전달하지 못했습니다."}
            self.server.replies[cache_key] = (status, reply)
            # Bound memory while retaining recent request IDs to prevent duplicate sends.
            if len(self.server.replies) > 1000:
                del self.server.replies[next(iter(self.server.replies))]
            return self.respond(status, reply)
        finally:
            self.server.send_lock.release()

    def handle_terminal(self, payload):
        terminal = self.server.terminal
        try:
            action = self.path.rsplit("/", 1)[-1]
            if action in ("start", "resize"):
                cols, rows = payload.get("cols", 90), payload.get("rows", 26)
                if type(cols) is not int or type(rows) is not int or not (20 <= cols <= 300 and 5 <= rows <= 100):
                    raise ValueError("잘못된 터미널 크기입니다.")
            if action == "start":
                return self.respond(200, terminal.start(payload.get("kind", "shell"), cols, rows))
            generation = payload.get("generation", "")
            if action == "input":
                terminal.write(payload.get("data"), generation)
            elif action == "resize":
                terminal.resize(cols, rows, generation)
            elif action == "stop":
                terminal.stop(generation)
            return self.respond(200, {"ok": True})
        except ValueError as error:
            return self.respond(409, {"error": str(error)})
        except (OSError, subprocess.SubprocessError):
            return self.respond(502, {"error": "웹 터미널을 처리하지 못했습니다. 서버 로그를 확인해 주세요."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Working directory for the Claude session")
    parser.add_argument("--state-file", type=Path, default=None, help="Path the Claude hooks write session state to")
    parser.add_argument("--mock", action="store_true",
                        help="Run a scripted stand-in (demo/fake_claude.py) instead of the real Claude CLI — "
                             "lets the whole app run with no `claude` install and no hardware.")
    args = parser.parse_args()
    claude = [sys.executable, str(ROOT / "demo" / "fake_claude.py")] if args.mock else shutil.which("claude")
    server = SimulatorServer(("127.0.0.1", args.port), claude, args.cwd, args.state_file)
    print(f"Button Lab: http://127.0.0.1:{server.server_port}", flush=True)
    if args.mock:
        print("Claude CLI: MOCK (demo/fake_claude.py — scripted, no real tools run)", flush=True)
    else:
        print(f"Claude CLI: {'found' if server.claude else '(not found — install Claude Code, or use --mock)'}", flush=True)
    print(f"Workspace: {server.workspace}", flush=True)
    print(f"Hook state file: {server.state_file}", flush=True)
    def stop_server(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.terminal.stop()
        server.server_close()


if __name__ == "__main__":
    main()
