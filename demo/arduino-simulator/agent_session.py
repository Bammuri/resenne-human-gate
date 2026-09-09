"""Local CLI protocol adapters. No model requests are made until a prompt is sent.

Codex uses app-server JSON-RPC; Claude uses the Agent SDK's stream-json control
protocol. Approvals are responses to pending tool requests, never chat messages.
"""
from collections import OrderedDict
import copy
import json
import os
import secrets
import signal
import subprocess
import threading
import uuid

from output import visible_text
from questions import parse_numbered_question


BUTTON_INSTRUCTIONS = (
    "The user controls this session with seven numbered answer buttons and a mode button. "
    "When a decision is needed, use the structured user question tool when available. "
    "Otherwise ask one clear question with consecutive numbered choices starting at 1. "
    "Text choices must occupy separate lines with literal prefixes '1. ', '2. ', etc.; "
    "unnumbered bullet choices cannot be answered by this controller. "
    "Prefer no more than seven choices. Do not number ordinary explanatory lists as questions."
)


class AgentSession:
    def __init__(self, executable, kind, cwd, effort, lock, emit, set_thread):
        self.kind, self.cwd, self.effort = kind, cwd, effort
        self.lock, self.emit, self.set_thread = lock, emit, set_thread
        self.claude = kind in ("claude", "claude-yolo")
        self.ready = False
        self.busy = False
        self.thread = str(uuid.uuid4()) if self.claude else ""
        self.turn = ""
        self.pending = []
        self.prose_question = None
        self.requests = {}
        self.results = OrderedDict()
        self.last_prompt = ""
        self.last_agent_text = ""
        self.items = {}
        self.completed_items = set()
        self.input_line = ""
        self.input_escape = ""
        self.closed = False
        self.process = None
        self.executable = executable
        self.approval_items = {}
        self.startup_timer = None

    def start(self):
        if self.claude:
            args = [self.executable, "--print", "--verbose", "--input-format", "stream-json",
                    "--output-format", "stream-json", "--include-partial-messages",
                    "--permission-prompt-tool", "stdio",
                    "--permission-mode", "bypassPermissions" if self.kind == "claude-yolo" else "default",
                    "--session-id", self.thread, "--effort", self.effort,
                    "--append-system-prompt", BUTTON_INSTRUCTIONS]
            if self.kind == "claude-yolo":
                args.append("--dangerously-skip-permissions")
        else:
            args = [self.executable, "app-server", "-c", f'model_reasoning_effort="{self.effort}"']
        env = os.environ.copy()
        for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDECODE"):
            env.pop(key, None)
        self.process = subprocess.Popen(args, cwd=self.cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", errors="replace", bufsize=1,
                                        start_new_session=True)
        self.startup_timer = threading.Timer(45, self._startup_timeout)
        self.startup_timer.daemon = True
        self.startup_timer.start()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()
        if self.claude:
            # Force the question through the host callback even in bypass mode.
            self._request("initialize", {"hooks": {"PreToolUse": [
                {"matcher": "AskUserQuestion", "hookCallbackIds": ["ddt-question"]}
            ]}}, self._initialized)
        else:
            self._request("initialize", {"clientInfo": {"name": "ddt_controller", "version": "1.0.0"},
                                         "capabilities": {"experimentalApi": True}}, self._initialized)
        self.emit(f"\r\n[{self.kind}] 연결 중…\r\n")
        return self.process

    def _startup_timeout(self):
        with self.lock:
            if self.closed or self.ready:
                return
            self.emit("\r\nAI 연결 시간이 초과됐습니다. CLI 로그인과 버전을 확인한 뒤 다시 실행하세요.\r\n")
        self.close()

    def _send(self, message):
        if self.closed or not self.process or self.process.poll() is not None:
            raise ValueError("AI 세션이 종료됐습니다.")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ValueError("AI 세션 연결이 끊겼습니다.") from exc

    def _request(self, method, params, callback=None):
        request_id = "ddt-" + secrets.token_hex(8)
        self.requests[request_id] = (method, callback)
        if self.claude:
            self._send({"type": "control_request", "request_id": request_id,
                        "request": {"subtype": method, **params}})
        else:
            self._send({"id": request_id, "method": method, "params": params})

    def _reply(self, request_id, result):
        if self.claude:
            self._send({"type": "control_response", "response": {
                "subtype": "success", "request_id": request_id, "response": result}})
        else:
            self._send({"id": request_id, "result": result})

    def _initialized(self, result):
        if self.claude:
            self._thread_ready({"thread": {"id": self.thread}})
        else:
            self._send({"method": "initialized", "params": {}})
            self._request("thread/start", {
                "cwd": self.cwd, "approvalPolicy": "never" if self.kind.endswith("yolo") else "on-request",
                "sandbox": "danger-full-access" if self.kind.endswith("yolo") else "workspace-write",
                "developerInstructions": BUTTON_INSTRUCTIONS,
            }, self._thread_ready)

    def _thread_ready(self, result):
        self.thread = result["thread"]["id"]
        self.set_thread(self.thread)
        self.ready = True
        if self.startup_timer:
            self.startup_timer.cancel()
        self.emit("연결 완료. 명령을 입력하거나 버튼을 누르세요.\r\n> ")

    def _read(self):
        try:
            while not self.closed:
                line = self.process.stdout.readline(4 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 4 * 1024 * 1024:
                    raise ValueError("CLI output too large")
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        continue
                    with self.lock:
                        if not self.closed:
                            (self._claude_event if self.claude else self._codex_event)(message)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # Raw transport records can contain credentials or internal reasoning.
                    continue
        except (OSError, ValueError):
            with self.lock:
                if not self.closed:
                    self.emit("\r\nAI 연결 오류. CLI 로그인과 버전을 확인해 주세요.\r\n")
        finally:
            with self.lock:
                self.ready = self.busy = False
                self.pending.clear()
                self.prose_question = None
                if not self.closed:
                    self.emit("\r\nAI 세션 연결이 종료됐습니다.\r\n")

    def _stderr(self):
        # Drain to avoid deadlock; never publish unfiltered provider diagnostics.
        try:
            while self.process.stderr.read(4096):
                pass
        except (OSError, ValueError):
            pass

    def _response(self, request_id, result, error=None):
        method, callback = self.requests.pop(request_id, (None, None))
        if error:
            if method in ("initialize", "thread/start"):
                self.ready = False
                threading.Thread(target=self.close, daemon=True).start()
            if method in ("turn/start", "turn/interrupt", "interrupt"):
                self.busy = False
            self.emit("\r\nAI 요청 실패. CLI 로그인·설정·버전을 확인한 뒤 다시 시도하세요.\r\n")
        elif callback:
            callback(result or {})

    def _codex_event(self, message):
        method, params = message.get("method"), message.get("params") or {}
        if not method:
            self._response(message.get("id"), message.get("result"), message.get("error"))
            return
        if params.get("threadId") and self.thread and params["threadId"] != self.thread:
            return
        if "id" in message:
            if method in ("item/tool/requestUserInput", "tool/requestUserInput"):
                self._queue(message["id"], method, params, params.get("questions", []))
            elif method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval",
                            "item/permissions/requestApproval"):
                item = self.approval_items.get(params.get("itemId"), {})
                details = params.get("command") or item.get("command") or item.get("changes") or params.get("permissions") or params.get("grantRoot") or ""
                prompt = str(params.get("reason") or "이 작업을 승인할까요?")
                if details:
                    prompt += "\n" + (details if isinstance(details, str) else json.dumps(details, ensure_ascii=False))
                self._queue(message["id"], method, params, [self._approval(prompt, params.get("availableDecisions"))])
            else:
                self._send({"id": message["id"], "error": {"code": -32601, "message": "Unsupported host request"}})
            return
        if method == "serverRequest/resolved":
            self.pending = [p for p in self.pending if p["request_id"] != params.get("requestId")]
        elif method == "turn/started":
            self.turn = params["turn"]["id"]
            self.busy = True
            self.prose_question = None
        elif method == "item/agentMessage/delta":
            key = params.get("itemId", "agent")
            delta = params.get("delta", "")
            self.items[key] = self.items.get(key, "") + delta
            self.emit(visible_text(delta).replace("\n", "\r\n"))
        elif method == "item/commandExecution/outputDelta":
            self.emit(visible_text(params.get("delta", "")).replace("\n", "\r\n"))
        elif method == "item/started":
            item = params.get("item", {})
            if item.get("type") in ("commandExecution", "fileChange"):
                self.approval_items[item.get("id")] = item
            if item.get("type") == "commandExecution":
                self.emit("\r\n$ " + visible_text(item.get("command", "")) + "\r\n")
        elif method == "item/completed":
            item = params.get("item", {})
            self.approval_items.pop(item.get("id"), None)
            if item.get("type") == "agentMessage" and item.get("id") not in self.completed_items:
                key = item.get("id")
                final = item.get("text", "")
                streamed = self.items.pop(key, "")
                if not streamed:
                    self.emit(visible_text(final).replace("\n", "\r\n"))
                elif final.startswith(streamed) and len(final) > len(streamed):
                    self.emit(visible_text(final[len(streamed):]).replace("\n", "\r\n"))
                self.completed_items.add(key)
                if item.get("phase") in (None, "final_answer", "final"):
                    self.last_agent_text = final or streamed
                self.emit("\r\n")
        elif method == "turn/completed":
            status = params.get("turn", {}).get("status")
            self._finished(status not in ("interrupted", "failed"))
            if status == "failed":
                self.emit("작업이 실패했습니다. CLI 로그인과 설정을 확인하거나 RETRY를 사용하세요.\r\n")
        elif method == "error":
            self.emit("\r\nAI 작업 오류가 발생했습니다.\r\n")

    def _claude_event(self, message):
        kind = message.get("type")
        if kind == "control_response":
            response = message.get("response", {})
            self._response(response.get("request_id"), response.get("response"),
                           response.get("error") if response.get("subtype") == "error" else None)
        elif kind == "control_cancel_request":
            self.pending = [p for p in self.pending if p["request_id"] != message.get("request_id")]
        elif kind == "control_request":
            request = message.get("request", {})
            request_id = message.get("request_id")
            if request.get("subtype") == "hook_callback" and request.get("callback_id") == "ddt-question":
                self._reply(request_id, {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "permissionDecision": "ask"}})
            elif request.get("subtype") == "can_use_tool":
                tool_input = request.get("input") or {}
                if request.get("tool_name") == "AskUserQuestion":
                    self._queue(request_id, "claude-question", request, tool_input.get("questions", []))
                else:
                    prompt = str(request.get("title") or request.get("tool_name") or "도구 실행 승인")
                    prompt += "\n" + json.dumps(tool_input, ensure_ascii=False)
                    self._queue(request_id, "claude-approval", request, [self._approval(prompt)])
            else:
                self._send({"type": "control_response", "response": {"subtype": "error",
                            "request_id": request_id, "error": "Unsupported host request"}})
        elif kind == "stream_event" and not message.get("parent_tool_use_id"):
            event = message.get("event", {})
            if event.get("type") == "message_start":
                self.items["claude-current"] = ""
            elif event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                text = event["delta"].get("text", "")
                self.items["claude-current"] = self.items.get("claude-current", "") + text
                self.emit(visible_text(text).replace("\n", "\r\n"))
        elif kind == "assistant" and not message.get("parent_tool_use_id"):
            content = message.get("message", {}).get("content", [])
            text = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
            key = message.get("message", {}).get("id") or message.get("uuid")
            if key and key in self.completed_items:
                return
            if key:
                self.completed_items.add(key)
            streamed = self.items.pop("claude-current", "")
            if text and not streamed:
                self.emit(visible_text(text).replace("\n", "\r\n"))
            if text or streamed:
                self.last_agent_text = text or streamed
                self.emit("\r\n")
        elif kind == "result":
            if not self.last_agent_text and isinstance(message.get("result"), str):
                self.last_agent_text = message["result"]
                self.emit(visible_text(self.last_agent_text).replace("\n", "\r\n"))
            self._finished(not message.get("is_error"))
            if message.get("is_error"):
                self.emit("작업이 실패했습니다. CLI 로그인과 설정을 확인하거나 RETRY를 사용하세요.\r\n")

    def _finished(self, detect_question=True):
        self.busy = False
        self.turn = ""
        self.pending.clear()
        self.prose_question = parse_numbered_question(self.last_agent_text, self.thread + secrets.token_hex(8)) if detect_question else None
        self.items.clear()
        self.completed_items.clear()
        self.approval_items.clear()
        self.emit("\r\n> ")

    @staticmethod
    def _approval(prompt, decisions=None):
        labels = {"accept": "ACCEPT · 이번 작업 승인", "acceptForSession": "이 세션 동안 승인",
                  "decline": "DENIED · 거절", "cancel": "거절하고 작업 중단"}
        choices = []
        for i, decision in enumerate(decisions if decisions is not None else ["accept", "decline"]):
            if isinstance(decision, str):
                choices.append({"id": "denied" if decision == "decline" else decision,
                                "label": labels.get(decision, decision), "decision": decision})
            else:
                choices.append({"id": f"policy-{i + 1}", "label": "정책 변경: " + json.dumps(decision, ensure_ascii=False),
                                "decision": decision})
        return {"question": prompt, "kind": "approval", "options": choices}

    def _queue(self, request_id, method, params, questions):
        if any(p["request_id"] == request_id for p in self.pending):
            return
        normalized = []
        for index, question in enumerate(questions):
            options = [{"id": str(option.get("id", i + 1)), "label": option["label"],
                        "description": option.get("description", "")}
                       for i, option in enumerate(question.get("options") or [])]
            normalized.append({"id": "request-" + secrets.token_hex(12), "prompt": question.get("question", ""),
                               "kind": question.get("kind", "choice"), "options": options,
                               "index": index + 1, "total": len(questions),
                               "multiSelect": bool(question.get("multiSelect")),
                               "isSecret": bool(question.get("isSecret"))})
        if not normalized:
            if self.claude:
                self._reply(request_id, {"behavior": "deny", "message": "No questions supplied"})
            else:
                self._reply(request_id, {"answers": {}})
            return
        self.pending.append({"request_id": request_id, "method": method, "params": params,
                             "questions": normalized, "original": questions, "index": 0, "answers": {}})
        self.prose_question = None
        self.emit("\r\n[답변 대기] " + visible_text(normalized[0]["prompt"]).replace("\n", "\r\n") + "\r\n")

    @property
    def question(self):
        if self.pending:
            pending = self.pending[0]
            return copy.deepcopy(pending["questions"][pending["index"]])
        return copy.deepcopy(self.prose_question)

    def prompt(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 32000:
            raise ValueError("명령은 1~32000자로 입력하세요.")
        if not self.ready:
            raise ValueError("AI 세션 연결을 기다려 주세요.")
        if self.pending:
            raise ValueError("먼저 대기 중인 질문에 답변해 주세요.")
        if self.busy:
            raise ValueError("작업이 실행 중입니다. STOP으로 중단한 뒤 명령을 보내세요.")
        self.last_prompt = text
        self.last_agent_text = ""
        self.prose_question = None
        self.items.clear()
        self.completed_items.clear()
        self.busy = True
        self.emit("\r\n사용자: " + visible_text(text).replace("\n", "\r\n") + "\r\n")
        try:
            if self.claude:
                self._send({"type": "user", "session_id": self.thread, "parent_tool_use_id": None,
                            "message": {"role": "user", "content": text}})
            else:
                self._request("turn/start", {"threadId": self.thread, "effort": self.effort,
                                             "input": [{"type": "text", "text": text}]}, self._turn_started)
        except ValueError:
            self.busy = False
            raise

    def _turn_started(self, result):
        self.turn = result.get("turn", {}).get("id", self.turn)

    def answer(self, question_id, choice=None, text=None):
        question = self.question
        if not question or question_id != question["id"]:
            raise ValueError("답변 대상 질문이 종료되었거나 변경됐습니다.")
        selected = None
        multiple = None
        if isinstance(choice, list):
            if not question.get("multiSelect") or question["kind"] == "approval" or not choice:
                raise ValueError("현재 질문은 여러 선택지를 받을 수 없습니다.")
            if not all(isinstance(value, str) for value in choice) or len(choice) != len(set(choice)):
                raise ValueError("여러 답변의 선택지 ID를 확인하세요.")
            by_id = {option["id"]: option for option in question["options"]}
            if any(value not in by_id for value in choice):
                raise ValueError("현재 질문에 없는 선택지입니다.")
            multiple = [by_id[value]["label"] for value in choice]
        elif type(choice) is int and 1 <= choice <= len(question["options"]):
            selected = question["options"][choice - 1]
        elif isinstance(choice, str):
            selected = next((o for o in question["options"] if o["id"] == choice), None)
        if choice is not None and selected is None and multiple is None:
            raise ValueError("현재 질문에 없는 선택지입니다.")
        if question["kind"] == "approval" and selected is None:
            raise ValueError("승인 또는 거절 버튼을 선택하세요.")
        answer = ", ".join(multiple) if multiple else selected["label"] if selected else text
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 8192:
            raise ValueError("답변을 선택하거나 입력하세요.")
        if not self.pending:
            # Preserve the number as well as the text for ordinary prose menus.
            self.prompt(f"{selected['id']}. {answer}" if selected else answer)
            return
        pending = self.pending[0]
        method, params = pending["method"], pending["params"]
        if question["kind"] == "approval":
            allow = selected["id"] == "accept"
            if method == "claude-approval":
                result = {"behavior": "allow", "updatedInput": params.get("input", {})} if allow else {
                    "behavior": "deny", "message": "User denied this request."}
            elif method == "item/permissions/requestApproval":
                result = {"permissions": params.get("permissions", {}) if allow else {}, "scope": "turn"}
            else:
                original_options = pending["original"][pending["index"]]["options"]
                decision = next(option["decision"] for option in original_options if option["id"] == selected["id"])
                result = {"decision": decision}
            self._reply(pending["request_id"], result)
            self.pending.pop(0)
        else:
            original = pending["original"][pending["index"]]
            key = original.get("id", original.get("question", "")) if not self.claude else original.get("question", "")
            pending["answers"][key] = answer if self.claude else {"answers": multiple or [answer]}
            if pending["index"] + 1 < len(pending["questions"]):
                pending["index"] += 1
            else:
                if self.claude:
                    updated = {**params.get("input", {}), "answers": pending["answers"]}
                    result = {"behavior": "allow", "updatedInput": updated}
                else:
                    result = {"answers": pending["answers"]}
                self._reply(pending["request_id"], result)
                self.pending.pop(0)
        self.emit("\r\n[답변] " + ("입력 완료" if question.get("isSecret") else visible_text(answer)) + "\r\n")

    def interrupt(self):
        if not self.ready:
            raise ValueError("AI 세션 연결을 기다려 주세요.")
        if not self.busy and not self.pending:
            self.prose_question = None
            return
        if self.claude:
            self._request("interrupt", {})
        elif self.turn:
            self._request("turn/interrupt", {"threadId": self.thread, "turnId": self.turn})
        else:
            raise ValueError("작업이 시작되는 중입니다. 잠시 뒤 STOP을 다시 누르세요.")
        self.pending.clear()
        self.prose_question = None
        self.emit("\r\n[중단 요청]\r\n")

    def command(self, action, request_id, choice=None, question_id=None, text=None):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("명령 요청 ID가 필요합니다.")
        signature = (action, tuple(choice) if isinstance(choice, list) else choice, question_id, text)
        if request_id in self.results:
            previous, result = self.results[request_id]
            if previous != signature:
                raise ValueError("같은 요청 ID에 다른 명령을 사용할 수 없습니다.")
            return {**result, "duplicate": True}
        if not self.ready:
            raise ValueError("AI 세션 연결을 기다려 주세요.")
        if action == "answer":
            self.answer(question_id, choice, text)
        elif action in ("accept", "denied"):
            question = self.question
            if not question or question["kind"] != "approval":
                raise ValueError("현재 승인 대기 중인 요청이 없습니다.")
            self.answer(question_id, action)
        elif action == "stop":
            self.interrupt()
        elif action == "prompt":
            self.prompt(text)
        elif action == "continue":
            self.prompt("이전 작업을 이어서 진행해 주세요.")
        elif action == "retry":
            if not self.last_prompt:
                raise ValueError("다시 시도할 이전 명령이 없습니다.")
            self.prompt(self.last_prompt)
        else:
            raise ValueError("지원하지 않는 AI 명령입니다.")
        result = {"ok": True, "action": action, "requestId": request_id}
        self.results[request_id] = (signature, result)
        while len(self.results) > 512:
            self.results.popitem(last=False)
        return result

    def write(self, text):
        # Minimal line editor for the existing xterm view. Browser IME input is
        # Unicode; ANSI cursor/control sequences must not become model prompts.
        for char in text:
            if self.input_escape:
                self.input_escape += char
                if len(self.input_escape) > 2 and (char.isalpha() or char == "~"):
                    self.input_escape = ""
                continue
            if char == "\x1b":
                self.input_escape = char
            elif char == "\x03":
                self.input_line = ""
                self.interrupt()
            elif char in ("\x7f", "\b"):
                if self.input_line:
                    self.input_line = self.input_line[:-1]
                    self.emit("\b \b")
            elif char in ("\r", "\n"):
                if self.input_line.strip():
                    line, self.input_line = self.input_line.strip(), ""
                    question = self.question
                    if question:
                        if line.isdigit():
                            self.answer(question["id"], int(line))
                        else:
                            self.answer(question["id"], text=line)
                    else:
                        self.prompt(line)
            elif ord(char) >= 32:
                if len(self.input_line) >= 8192:
                    raise ValueError("입력이 너무 깁니다.")
                self.input_line += char
                self.emit("*" if (self.question or {}).get("isSecret") else char)

    def close(self):
        with self.lock:
            if self.startup_timer:
                self.startup_timer.cancel()
            self.closed = True
            self.ready = self.busy = False
            self.pending.clear()
            self.prose_question = None
        process = self.process
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1)
            except ProcessLookupError:
                pass
        if process:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
