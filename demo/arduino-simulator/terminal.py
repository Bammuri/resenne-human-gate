"""A locally owned PTY with bounded output and Codex-session discovery on macOS."""
import base64
import fcntl
import os
from pathlib import Path
import pty
import re
import secrets
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import threading
import time

from output import OutputReader
from agent_session import AgentSession

ROOT = Path(__file__).resolve().parent
SESSION_LOCK = re.compile(r"/thread-writer-locks/([0-9a-f-]{36})\.lock$")


class WebTerminal:
    def __init__(self, codex, cwd=None, claude=None):
        self.codex = codex
        self.claude = claude or shutil.which("claude")
        self.cwd = str(cwd or ROOT.parent)
        self.lock = threading.RLock()
        self.write_lock = threading.RLock()
        self.probe_lock = threading.Lock()
        self.process = None
        self.fd = None
        self.generation = ""
        self.kind = "shell"
        self.data = bytearray()
        self.total = 0
        self.thread = ""
        self.output = OutputReader("")
        self.last_probe = 0
        self.managed = None
        self.command_results = {}

    def start(self, kind, cols=90, rows=26, effort="medium", *, managed=False):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("이미 실행 중입니다. 현재 웹 터미널을 종료한 뒤 다시 시작하세요.")
            if kind not in ("shell", "codex", "codex-yolo", "claude", "claude-yolo"):
                raise ValueError("지원하지 않는 터미널 종류입니다.")
            if effort not in ("low", "medium", "high", "xhigh"):
                raise ValueError("지원하지 않는 추론 강도입니다.")
            if kind in ("codex", "codex-yolo") and not self.codex:
                raise ValueError("Codex CLI를 찾을 수 없습니다.")
            if kind in ("claude", "claude-yolo") and not self.claude:
                raise ValueError("Claude CLI를 찾을 수 없습니다.")
            if managed and kind != "shell":
                return self._start_managed(kind, effort)
            self.managed = None
            self.command_results.clear()
            shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
            if kind in ("codex", "codex-yolo"):
                args = [self.codex, "--no-alt-screen", "-c", f'model_reasoning_effort="{effort}"']
                if kind == "codex-yolo":
                    args.append("--dangerously-bypass-approvals-and-sandbox")
                else:
                    args.extend(["--sandbox", "workspace-write", "-c", 'approval_policy="on-request"'])
            elif kind in ("claude", "claude-yolo"):
                args = [self.claude, "--effort", effort, "--permission-mode",
                        "bypassPermissions" if kind == "claude-yolo" else "default"]
                if kind == "claude-yolo":
                    args.append("--dangerously-skip-permissions")
            else:
                args = [shell, "-l"]
            if kind != "shell":
                # Let the CLI submit after its own startup/trust checks. Sending
                # timed PTY keystrokes could answer an onboarding menu instead.
                # Only a new process gets this prompt; polling never resends it.
                args.append("hi")
            master, slave = pty.openpty()
            try:
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                env = os.environ.copy()
                for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDECODE"):
                    env.pop(key, None)
                env.update(TERM="xterm-256color", COLORTERM="truecolor")
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / "pty_child.py"), *args],
                    stdin=slave, stdout=slave, stderr=slave, cwd=self.cwd, env=env,
                    close_fds=True,
                )
            except Exception:
                os.close(master)
                raise
            finally:
                os.close(slave)
            os.set_blocking(master, False)
            self.process, self.fd = process, master
            self.generation = secrets.token_hex(12)
            self.kind = kind
            self.data = bytearray()
            self.total = 0
            self.thread = ""
            self.output = OutputReader("")
            self.last_probe = 0
            threading.Thread(target=self.read, args=(master, process, self.generation), daemon=True).start()
        return self.snapshot()

    def _start_managed(self, kind, effort):
        self.generation = secrets.token_hex(12)
        generation = self.generation
        self.kind = kind
        self.data = bytearray()
        self.total = 0
        self.thread = ""
        self.fd = None
        self.output = OutputReader("")
        self.command_results.clear()

        def emit(text):
            with self.lock:
                if self.generation != generation:
                    return
                chunk = text.encode("utf-8", errors="replace")
                self.data.extend(chunk)
                self.total += len(chunk)
                if len(self.data) > 512 * 1024:
                    del self.data[:len(self.data) - 512 * 1024]

        def set_thread(thread):
            with self.lock:
                if self.generation == generation:
                    self.thread = thread
                    self.output = OutputReader(thread if kind not in ("claude", "claude-yolo") else "")

        session = AgentSession(self.claude if kind in ("claude", "claude-yolo") else self.codex,
                               kind, self.cwd, effort, self.lock, emit, set_thread)
        self.managed = session
        try:
            self.process = session.start()
        except Exception:
            session.close()
            self.managed = None
            self.process = None
            raise
        return self.snapshot()

    def read(self, fd, process, generation):
        try:
            while True:
                ready, _, _ = select.select([fd], [], [], 0.2)
                if not ready:
                    if process.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(fd, 16384)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                with self.lock:
                    if self.generation != generation:
                        break
                    self.data.extend(chunk)
                    self.total += len(chunk)
                    if len(self.data) > 512 * 1024:
                        del self.data[:len(self.data) - 512 * 1024]
        except (OSError, ValueError):
            pass
        finally:
            with self.lock:
                if self.generation == generation:
                    self.fd = None
            os.close(fd)

    def process_tree(self):
        if not self.process or self.process.poll() is not None:
            return []
        result = subprocess.run(["ps", "-axo", "pid=,ppid=,comm="], capture_output=True, text=True, timeout=2)
        rows = []
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                rows.append((int(parts[0]), int(parts[1]), parts[2]))
        selected = {self.process.pid}
        for _ in range(12):
            children = {pid for pid, parent, _ in rows if parent in selected}
            if children <= selected:
                break
            selected.update(children)
        return [row for row in rows if row[0] in selected]

    def detect_thread(self, force=False):
        if self.managed:
            return
        if not self.probe_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                if not force and time.monotonic() - self.last_probe < 2:
                    return
                self.last_probe = time.monotonic()
                generation = self.generation
            detected = ""
            try:
                processes = self.process_tree()
                # Prefer the direct Codex process, before any descendants it may own.
                candidates = [pid for pid, _, name in processes if Path(name).name == "codex"]
                if self.process and self.process.pid in candidates:
                    candidates.remove(self.process.pid)
                    candidates.insert(0, self.process.pid)
                for pid in candidates[:8]:
                    descriptors = Path(f"/proc/{pid}/fd")
                    if descriptors.is_dir():
                        paths = []
                        for descriptor in descriptors.iterdir():
                            try:
                                paths.append(os.readlink(descriptor))
                            except OSError:
                                pass
                    else:
                        files = subprocess.run(["lsof", "-a", "-p", str(pid), "-Fn"], capture_output=True, text=True, timeout=2)
                        paths = files.stdout.splitlines()
                    ids = {match.group(1) for line in paths if (match := SESSION_LOCK.search(line))}
                    if len(ids) == 1:
                        detected = ids.pop()
                        break
            except (OSError, subprocess.SubprocessError):
                pass
            with self.lock:
                if self.generation == generation and detected != self.thread:
                    self.thread = detected
                    self.output = OutputReader(detected)
        finally:
            self.probe_lock.release()

    def target_thread(self):
        self.detect_thread(force=True)
        with self.lock:
            if self.kind in ("claude", "claude-yolo") or not self.process or self.process.poll() is not None or not self.thread:
                raise ValueError("웹 터미널에서 Codex를 실행하고 세션이 연결될 때까지 기다려 주세요.")
            return self.thread

    def snapshot(self, after=0, generation=""):
        self.detect_thread()
        with self.lock:
            base = self.total - len(self.data)
            reset = generation != self.generation or after < base or after > self.total
            start = base if reset else max(base, after)
            end = min(self.total, start + 65536)
            chunk = bytes(self.data[start - base:end - base])
            return {
                "running": bool(self.process and self.process.poll() is None),
                "kind": self.kind, "generation": self.generation, "reset": reset,
                "cursor": end, "data": base64.b64encode(chunk).decode(),
                "thread": self.thread, "exitCode": self.process.poll() if self.process else None,
                "managed": bool(self.managed),
                "ready": bool(self.managed.ready) if self.managed else bool(self.process and self.process.poll() is None),
                "busy": bool(self.managed and self.managed.busy),
                "question": self.managed.question if self.managed else None,
            }

    def write(self, text, generation, expected_cursor=None):
        if not isinstance(text, str) or not 0 < len(text) <= 8192:
            raise ValueError("입력이 비어 있거나 너무 깁니다.")
        with self.write_lock, self.lock:
            if expected_cursor is not None and (type(expected_cursor) is not int or expected_cursor != self.total):
                raise ValueError("터미널 화면이 바뀌었습니다. 현재 선택지를 확인하고 다시 눌러 주세요.")
            if self.managed:
                self._validate_generation(generation)
                self.managed.write(text)
                return
            if generation != self.generation or self.fd is None or not self.process or self.process.poll() is not None:
                raise ValueError("입력 대상 터미널이 종료되었거나 변경됐습니다.")
            data = text.encode()
            deadline = time.monotonic() + 2
            while data:
                if time.monotonic() > deadline:
                    raise ValueError("터미널 입력이 지연됐습니다. 화면을 확인해 주세요.")
                if select.select([], [self.fd], [], 0.1)[1]:
                    try:
                        data = data[os.write(self.fd, data):]
                    except BlockingIOError:
                        continue

    def resize(self, cols, rows, generation):
        if not (20 <= cols <= 300 and 5 <= rows <= 100):
            raise ValueError("잘못된 터미널 크기입니다.")
        with self.lock:
            if self.managed:
                self._validate_generation(generation)
                return
            if generation != self.generation or self.fd is None:
                raise ValueError("터미널이 종료되었거나 변경됐습니다.")
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def _validate_generation(self, generation):
        if generation != self.generation or not self.process or self.process.poll() is not None:
            raise ValueError("명령 대상 터미널이 종료되었거나 변경됐습니다.")

    def command(self, action, generation, request_id, choice=None, question_id=None, text=None):
        with self.write_lock, self.lock:
            self._validate_generation(generation)
            if self.managed:
                return self.managed.command(action, request_id, choice, question_id, text)
            if action not in ("prompt", "stop"):
                raise ValueError("이 기능은 CLI 화면에서 직접 입력해 주세요.")
            if action == "stop":
                text = "\x03"
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ValueError("명령 요청 ID가 필요합니다.")
            if not isinstance(text, str) or not text.strip() or len(text) > 8191:
                raise ValueError("명령은 1~8191자로 입력하세요.")
            if request_id in self.command_results:
                previous, result = self.command_results[request_id]
                if previous != (action, text):
                    raise ValueError("같은 요청 ID에 다른 명령을 사용할 수 없습니다.")
                return {**result, "duplicate": True}
            # write_lock is reserved by write(); do not acquire it twice.
            self.write(text if action == "stop" else "\x1b[200~" + text + "\x1b[201~\r", generation)
            result = {"ok": True, "action": action, "requestId": request_id}
            self.command_results[request_id] = ((action, text), result)
            if len(self.command_results) > 512:
                self.command_results.pop(next(iter(self.command_results)))
            return result

    def stop(self, generation=None):
        with self.lock:
            if generation is not None and generation != self.generation:
                raise ValueError("종료 대상 터미널이 변경됐습니다.")
            process = self.process
            managed = self.managed
        if managed:
            managed.close()
            with self.lock:
                self.thread = ""
                self.output = OutputReader("")
            return
        if not process or process.poll() is not None:
            return
        try:
            descendants = [pid for pid, _, _ in self.process_tree() if pid != process.pid]
        except (OSError, subprocess.SubprocessError):
            descendants = []
        for pid in reversed(descendants):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        with self.lock:
            self.thread = ""
            self.output = OutputReader("")
