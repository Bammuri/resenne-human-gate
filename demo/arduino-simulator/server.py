#!/usr/bin/env python3
"""Local Arduino button simulator and an optional bridge to one Codex thread."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from board_wifi import BoardWifi
from output import OutputReader
from terminal import WebTerminal
from workflow import Workflow
from controls import ControlSettings, ConversationQuestions, ACTIONS


ROOT = Path(__file__).resolve().parent
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/serial.js": ("serial.js", "text/javascript; charset=utf-8"),
    "/web-terminal.js": ("web-terminal.js", "text/javascript; charset=utf-8"),
    "/workflow.js": ("workflow.js", "text/javascript; charset=utf-8"),
    "/controls.js": ("controls.js", "text/javascript; charset=utf-8"),
    "/vendor/xterm.js": ("vendor/xterm.js", "text/javascript; charset=utf-8"),
    "/vendor/addon-fit.js": ("vendor/addon-fit.js", "text/javascript; charset=utf-8"),
    "/vendor/xterm.css": ("vendor/xterm.css", "text/css; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/board-config.example.h": ("firmware/simulator_r4/board_config.example.h", "text/plain; charset=utf-8"),
    "/firmware.ino": ("firmware/simulator_r4/simulator_r4.ino", "text/plain; charset=utf-8"),
}


class SimulatorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, thread, codex, workspace=None, settings_directory=None):
        super().__init__(address, Handler)
        self.thread = thread
        self.codex = codex
        self.claude = shutil.which("claude")
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.token = secrets.token_urlsafe(32)
        self.send_lock = threading.Lock()
        self.last_sent = 0.0
        self.replies = {}
        self.output = OutputReader(thread)
        self.terminal = WebTerminal(codex, self.workspace)
        self.workflow = Workflow(codex, self.workspace)
        self.control_lock = threading.Lock()
        self.command_lock = threading.Lock()
        self.command_replies = {}
        self.controls = ControlSettings(self.workspace, settings_directory)
        self.questions = ConversationQuestions(self.output)
        self.board = BoardWifi()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if self.path.startswith(("/api/output", "/api/terminal", "/api/workflow", "/api/questions", "/api/board/events")) and len(args) > 1 and str(args[1]) == "200":
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
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
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
                "thread": self.server.thread,
                "available": bool(self.server.thread and self.server.codex),
                "codexAvailable": bool(self.server.codex),
                "claudeAvailable": bool(self.server.claude),
                "workspace": str(self.server.workspace),
                "token": self.server.token,
            })
        if path in ("/api/output", "/api/terminal", "/api/workflow", "/api/controls", "/api/questions", "/api/board/events"):
            if not secrets.compare_digest(self.headers.get("X-Simulator-Token", ""), self.server.token):
                return self.respond(403, {"error": "페이지를 새로고침해 주세요."})
            if path == "/api/board/events":
                try: return self.respond(200, self.server.board.poll())
                except ValueError as error: return self.respond(409, {"error": str(error)})
            if path == "/api/workflow":
                return self.respond(200, self.server.workflow.snapshot())
            if path == "/api/controls":
                return self.respond(200, self.server.controls.snapshot())
            query = parse_qs(parsed.query)
            if path == "/api/questions":
                if query.get("target", ["current"])[0] != "current":
                    return self.respond(400, {"error": "이 경로는 기존 Codex 세션의 질문을 제공합니다."})
                return self.respond(200, self.server.questions.snapshot(bool(self.server.thread and self.server.codex)))
            try:
                after = int(query.get("after", ["0"])[0])
                if after < 0:
                    raise ValueError
            except ValueError:
                return self.respond(400, {"error": "잘못된 출력 위치입니다."})
            generation = query.get("generation", [""])[0]
            if path == "/api/terminal":
                return self.respond(200, self.server.terminal.snapshot(after, generation))
            target = query.get("target", ["current"])[0]
            if target not in ("current", "terminal"):
                return self.respond(400, {"error": "잘못된 세션 대상입니다."})
            if target == "terminal":
                self.server.terminal.detect_thread()
            output = self.server.terminal.output if target == "terminal" else self.server.output
            return self.respond(200, output.snapshot(after, generation))
        if path not in ASSETS:
            return self.respond(404, {"error": "페이지를 찾을 수 없습니다."})
        filename, content_type = ASSETS[path]
        self.respond(200, (ROOT / filename).read_bytes(), content_type)

    def do_POST(self):
        if not self.valid_host():
            return self.respond(403, {"error": "로컬 주소로 접속해 주세요."})
        if self.path not in ("/api/board/connect", "/api/board/disconnect", "/api/board/command", "/api/press", "/api/command", "/api/controls", "/api/terminal/start", "/api/terminal/input", "/api/terminal/resize", "/api/terminal/stop",
                             "/api/workflow/configure", "/api/workflow/start", "/api/workflow/ask", "/api/workflow/approve", "/api/workflow/stop", "/api/workflow/preview", "/api/workflow/revert"):
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
            limit = 256 * 1024 if self.path == "/api/controls" else 128 * 1024
            if not 0 < size <= limit:
                raise ValueError
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, OSError):
            return self.respond(400, {"error": "올바른 JSON 입력이 필요합니다."})
        if self.path.startswith("/api/board/"):
            try:
                if self.path.endswith("/connect"):
                    return self.respond(200, self.server.board.connect(payload.get("host"), payload.get("token", "")))
                if self.path.endswith("/command"):
                    return self.respond(200, self.server.board.command(payload.get("command")))
                self.server.board.disconnect()
                return self.respond(200, {"ok": True})
            except ValueError as error:
                return self.respond(409, {"error": str(error)})
        if self.path == "/api/controls":
            try:
                return self.respond(200, self.server.controls.save(payload))
            except ValueError as error:
                return self.respond(400, {"error": str(error)})
            except OSError:
                return self.respond(500, {"error": "버튼 설정을 저장하지 못했습니다."})
        if self.path == "/api/command":
            return self.handle_command(payload)
        if self.path.startswith("/api/terminal/"):
            return self.handle_terminal(payload)
        if self.path.startswith("/api/workflow/"):
            return self.handle_workflow(payload)
        try:
            choice, request_id = payload.get("choice"), payload.get("requestId")
            if choice not in ("yes", "no"):
                raise ValueError
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
                raise ValueError
        except (ValueError, OSError):
            return self.respond(400, {"error": "yes 또는 no 입력이 필요합니다."})
        target = payload.get("target", "current")
        if target not in ("current", "terminal"):
            return self.respond(400, {"error": "잘못된 세션 대상입니다."})
        try:
            thread = self.server.terminal.target_thread() if target == "terminal" else self.server.thread
        except ValueError as error:
            return self.respond(503, {"error": str(error)})
        if not thread or not self.server.codex:
            return self.respond(503, {"error": "연결할 Codex 세션이 없습니다. Codex를 시작하고 첫 요청을 입력해 주세요."})
        if not self.server.send_lock.acquire(blocking=False):
            return self.respond(409, {"error": "이전 답변을 전송 중입니다. 잠시 기다려 주세요."})
        try:
            cache_key = (thread, request_id)
            if cache_key in self.server.replies:
                previous_choice, status, reply = self.server.replies[cache_key]
                if previous_choice != choice:
                    return self.respond(409, {"error": "이미 사용한 요청 ID입니다."})
                return self.respond(status, reply)
            if time.monotonic() - self.server.last_sent < 0.5:
                return self.respond(429, {"error": "잠시 후 다시 눌러 주세요."})
            self.server.last_sent = time.monotonic()
            try:
                result = subprocess.run(
                    [self.server.codex, "queue", "--thread", thread, "--message", choice],
                    capture_output=True, text=True, timeout=20, cwd=self.server.workspace,
                )
                if result.returncode:
                    print(f"Codex queue failed: {result.stderr.strip()}", flush=True)
                    message = "Codex에 전달하지 못했습니다. 서버 로그와 세션 상태를 확인해 주세요."
                    if "no rollout found for thread id" in result.stderr:
                        message = "Codex 세션 기록이 아직 없습니다. 해당 Codex 터미널에 첫 요청을 입력하고 Enter를 누른 뒤 다시 전송해 주세요."
                    status, reply = 502, {"error": message}
                else:
                    status, reply = 200, {"choice": choice, "status": "queued"}
            except subprocess.TimeoutExpired:
                status, reply = 504, {"error": "전송 결과를 확인하지 못했습니다. 다시 누르기 전에 Codex 대화를 확인해 주세요."}
            except OSError:
                status, reply = 502, {"error": "Codex 명령을 실행할 수 없습니다."}
            self.server.replies[cache_key] = (choice, status, reply)
            # Bound memory while retaining recent request IDs to prevent duplicate sends.
            if len(self.server.replies) > 1000:
                del self.server.replies[next(iter(self.server.replies))]
            return self.respond(status, reply)
        finally:
            self.server.send_lock.release()

    def handle_command(self, payload):
        action, target = payload.get("action"), payload.get("target", "terminal")
        generation, request_id = payload.get("generation"), payload.get("requestId")
        if action not in (*ACTIONS, "answer") or target not in ("terminal", "current", "workflow"):
            return self.respond(400, {"error": "지원하지 않는 명령 또는 대상입니다."})
        if not all(isinstance(v, str) and 1 <= len(v) <= 128 for v in (generation, request_id)):
            return self.respond(400, {"error": "세션과 요청 ID가 필요합니다. 연결 상태를 확인해 주세요."})
        if action == "answer" and (not isinstance(payload.get("questionId"), str) or not payload["questionId"]):
            return self.respond(400, {"error": "응답할 질문 ID가 필요합니다."})
        multiple = payload.get("choice")
        multi_answer = target == "terminal" and isinstance(multiple, list) and 1 <= len(multiple) <= 30 and all(
            isinstance(item, str) and 1 <= len(item) <= 128 for item in multiple)
        if action == "answer" and type(payload.get("choice")) not in (str, int) and not multi_answer and not (
                target == "terminal" and isinstance(payload.get("text"), str) and 0 < len(payload["text"].strip()) <= 8192):
            return self.respond(400, {"error": "선택지 번호 또는 답변이 필요합니다."})
        if action == "prompt" and (not isinstance(payload.get("text"), str) or not 0 < len(payload["text"].strip()) <= 8192 or "\0" in payload["text"]):
            return self.respond(400, {"error": "보낼 명령·프롬프트는 1~8,192자여야 합니다."})
        if not self.server.command_lock.acquire(blocking=False):
            return self.respond(409, {"error": "이전 명령을 처리 중입니다. 잠시 기다려 주세요."})
        try:
            fingerprint = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            key = (target, generation, request_id)
            cached = self.server.command_replies.get(key)
            if cached:
                if cached[0] != fingerprint:
                    return self.respond(409, {"error": "이미 사용한 요청 ID입니다."})
                return self.respond(cached[1], cached[2])
            try:
                if target == "terminal":
                    result = self.server.terminal.command(action=action, generation=generation, request_id=request_id,
                        choice=payload.get("choice"), question_id=payload.get("questionId"), text=payload.get("text"))
                elif target == "workflow":
                    if action != "answer":
                        raise ValueError("워크플로 질문에는 번호 응답을 사용해 주세요.")
                    result = {"ok": True, "workflow": self.server.workflow.answer(generation, payload["questionId"], payload["choice"])}
                else:
                    result = self.command_current(payload)
                status = 200
            except ValueError as error:
                status, result = 409, {"error": str(error)}
            except subprocess.TimeoutExpired:
                status, result = 504, {"error": "전송 결과를 확인하지 못했습니다. 대화를 확인한 뒤 다시 입력해 주세요."}
            except (OSError, subprocess.SubprocessError):
                status, result = 502, {"error": "AI 명령을 처리하지 못했습니다. 연결과 서버 로그를 확인해 주세요."}
            self.server.command_replies[key] = (fingerprint, status, result)
            if len(self.server.command_replies) > 1000:
                del self.server.command_replies[next(iter(self.server.command_replies))]
            return self.respond(status, result)
        finally:
            self.server.command_lock.release()

    def command_current(self, payload):
        snap = self.server.questions.snapshot(bool(self.server.thread and self.server.codex))
        if not snap["ready"] or payload["generation"] != snap["generation"]:
            raise ValueError("기존 Codex 세션이 준비되지 않았거나 변경됐습니다.")
        action = payload["action"]
        question = snap["question"]
        if action == "stop":
            raise ValueError("외부에서 실행한 Codex는 해당 창에서 중단해 주세요. 이 서비스는 웹에서 시작한 AI를 중단할 수 있습니다.")
        if action == "answer":
            if not question or question["id"] != payload["questionId"]:
                raise ValueError("질문이 이미 처리됐거나 변경됐습니다.")
            option = next((item for item in question["options"] if item["id"] == str(payload["choice"])), None)
            if not option:
                raise ValueError("표시된 선택지 번호를 눌러 주세요.")
            message = f"{question['prompt']}\n답변: {option['id']}. {option['label']}"
        else:
            if question:
                raise ValueError("먼저 표시된 질문에 번호로 답변해 주세요.")
            message = {"accept": "yes", "denied": "no", "continue": "계속 진행해 주세요.",
                       "retry": "직전 요청을 다시 시도해 주세요.", "prompt": payload.get("text", "")}[action]
        result = subprocess.run([self.server.codex, "queue", "--thread", self.server.thread, "--message", message],
                                capture_output=True, text=True, timeout=20, cwd=self.server.workspace)
        if result.returncode:
            raise ValueError("기존 Codex 세션에 메시지를 전달하지 못했습니다. 해당 대화의 연결 상태를 확인해 주세요.")
        if action == "answer":
            self.server.questions.resolve(question["id"])
        return {"ok": True, "action": action, "status": "queued"}

    def handle_terminal(self, payload):
        terminal = self.server.terminal
        try:
            action = self.path.rsplit("/", 1)[-1]
            if action in ("start", "resize"):
                cols, rows = payload.get("cols", 90), payload.get("rows", 26)
                if type(cols) is not int or type(rows) is not int or not (20 <= cols <= 300 and 5 <= rows <= 100):
                    raise ValueError("잘못된 터미널 크기입니다.")
            if action == "start":
                with self.server.control_lock:
                    if self.server.workflow.snapshot()["running"]:
                        raise ValueError("워크플로 작업을 STOP으로 중단한 뒤 터미널을 시작해 주세요.")
                    return self.respond(200, terminal.start(payload.get("kind", "shell"), cols, rows, payload.get("effort", "medium")))
            generation = payload.get("generation", "")
            if action == "input":
                terminal.write(payload.get("data"), generation, expected_cursor=payload.get("expectedCursor"))
            elif action == "resize":
                terminal.resize(cols, rows, generation)
            elif action == "stop":
                terminal.stop(generation)
            return self.respond(200, {"ok": True})
        except ValueError as error:
            return self.respond(409, {"error": str(error)})
        except (OSError, subprocess.SubprocessError):
            return self.respond(502, {"error": "웹 터미널을 처리하지 못했습니다. 서버 로그를 확인해 주세요."})

    def handle_workflow(self, payload):
        workflow = self.server.workflow
        action = self.path.rsplit("/", 1)[-1]
        try:
            # STOP deliberately does not wait for checkpoint creation or the general control lock.
            if action == "stop":
                result = workflow.stop()
                self.server.terminal.stop()
                return self.respond(200, result)
            if action == "ask":
                # Independent Q&A is allowed while the workflow or terminal is running.
                workflow.side_question.ask(payload.get("question"))
                return self.respond(200, workflow.snapshot())
            with self.server.control_lock:
                if action in ("start", "ask", "approve", "preview", "revert") and self.server.terminal.snapshot()["running"]:
                    raise ValueError("웹 터미널을 종료한 뒤 워크플로를 실행해 주세요. 워크플로는 이 프로젝트의 별도 작업으로 실행됩니다.")
                if action == "configure":
                    result = workflow.configure(payload.get("requirements"), payload.get("autonomy"), payload.get("stage"), payload.get("fields"))
                elif action == "start":
                    result = workflow.start(payload.get("stage"), immediate=True)
                elif action == "approve":
                    result = workflow.approve(payload.get("plan"))
                elif action == "preview":
                    result = workflow.preview()
                elif action == "revert":
                    result = workflow.revert(payload.get("token"))
                return self.respond(200, result)
        except (ValueError, OSError) as error:
            return self.respond(409, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--thread", default=os.environ.get("CODEX_THREAD_ID", ""))
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Working directory for the web terminal")
    args = parser.parse_args()
    thread = args.thread
    server = SimulatorServer(("127.0.0.1", args.port), thread, shutil.which("codex"), args.cwd)
    print(f"Button Lab: http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Existing Codex thread: {thread or '(not assigned)'}", flush=True)
    print(f"Workspace: {server.workspace}", flush=True)
    def stop_server(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.workflow.stop()
        server.terminal.stop()
        server.server_close()


if __name__ == "__main__":
    main()
