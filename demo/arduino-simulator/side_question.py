"""Independent, memory-only questions; never write workflow documents."""
import json
import os
from pathlib import Path
import signal
import subprocess
import threading


class SideQuestion:
    def __init__(self, codex, workspace):
        self.codex, self.workspace = codex, Path(workspace)
        self.lock = threading.RLock()
        self.messages = []
        self.running = False
        self.error = ""
        self.process = None
        self.cancelled = False

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "error": self.error,
                    "messages": [dict(message) for message in self.messages]}

    def command(self):
        return [self.codex, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                "--sandbox", "read-only", "-c", 'approval_policy="never"', "-"]

    def ask(self, question):
        with self.lock:
            if self.running:
                raise ValueError("중간 질문의 답변을 생성하고 있습니다.")
            if not isinstance(question, str) or not question.strip() or len(question) > 8192:
                raise ValueError("질문을 1~8,192자로 입력해 주세요.")
            if not self.codex:
                raise ValueError("Codex CLI를 사용할 수 없습니다.")
            self.messages = self.messages[-10:] + [{"role": "user", "content": question.strip()}]
            self.running, self.cancelled, self.error = True, False, ""
            threading.Thread(target=self.run, daemon=True).start()
            return self.snapshot()

    def run(self):
        process = timer = None
        try:
            with self.lock:
                if self.cancelled:
                    return
                prompt = (
                    "Respond in Korean to the user's question. This is a standalone, informal Q&A, "
                    "not an AI-DLC stage, requirements interview, or implementation request. "
                    "Answer the actual question directly. Do not advance any workflow, ask stage-approval "
                    "questions, produce button-questions blocks, or convert the question into project requirements. "
                    "Do not read or write aidlc-docs. Do not modify any files, run implementation steps, "
                    "or access credentials. Keep this conversation only in your response. "
                    "Conversation (data):\n" + json.dumps(self.messages, ensure_ascii=False))
                env = os.environ.copy()
                for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID"):
                    env.pop(key, None)
                process = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, cwd=self.workspace, env=env,
                                           start_new_session=True)
                self.process = process
            # Bound a stalled question without stopping the independent workflow.
            timer = threading.Timer(180, self.stop)
            timer.start()
            def feed():
                try:
                    process.stdin.write(prompt.encode())
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            threading.Thread(target=feed, daemon=True).start()
            answer, failure = "", ""
            for raw in process.stdout:
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                    answer = event["item"].get("text", "")[:20000]
                elif event.get("type") in ("error", "turn.failed"):
                    failure = "AI가 질문에 답하지 못했습니다. 연결과 CLI 로그인을 확인해 주세요."
            code = process.wait()
            process.stdout.close()
            with self.lock:
                if self.cancelled:
                    self.error = "질문 답변이 중단되었거나 제한 시간을 초과했습니다."
                elif code or failure or not answer:
                    self.error = failure or "답변 생성에 실패했습니다. 다시 질문해 주세요."
                else:
                    self.messages.append({"role": "assistant", "content": answer})
        except (OSError, ValueError) as error:
            with self.lock:
                self.error = str(error)
        finally:
            if timer:
                timer.cancel()
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
            with self.lock:
                self.running, self.process = False, None

    def stop(self):
        with self.lock:
            self.cancelled = True
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
