"""A locally owned PTY hosting a Claude Code session, with bounded output.

The app owns the PTY, so answers are delivered by writing key sequences to it
(there is no `claude queue` equivalent). Button/encoder actions are mapped to
terminal key sequences by ACTION_KEYS below — the single source of truth for the
answer keystrokes (mirrored in the browser for reference; see serial.js/app.js).
"""
import base64
import fcntl
import os
from pathlib import Path
import pty
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

ROOT = Path(__file__).resolve().parent

# action -> key sequence written to the Claude PTY (Application Design D2).
# Claude's permission prompt is an arrow-key menu: numbers/y-n are not reliable,
# so navigation uses Up/Down + Enter; Esc declines/interrupts. Literal bytes are
# config here so a hardware smoke test can correct them without touching logic.
ACTION_KEYS = {
    "nav_up": "\x1b[A",    # Up arrow — move menu highlight up
    "nav_down": "\x1b[B",  # Down arrow — move menu highlight down
    "confirm": "\r",       # Enter — select highlighted option
    "yes": "\r",           # fast path: accept the default-focused "Yes"
    "no": "\x1b",          # decline the prompt
    "stop": "\x1b",        # interrupt a running turn
}
ACTIONS = tuple(ACTION_KEYS)
# Actions only meaningful while Claude is waiting on a prompt; "stop" is always allowed.
PROMPT_ACTIONS = frozenset({"yes", "no", "confirm", "nav_up", "nav_down"})


class WebTerminal:
    def __init__(self, claude, cwd=None):
        self.claude = claude
        self.cwd = str(cwd or ROOT.parent)
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.process = None
        self.fd = None
        self.generation = ""
        self.kind = "shell"
        self.data = bytearray()
        self.total = 0

    def start(self, kind, cols=90, rows=26):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("이미 실행 중입니다. 현재 웹 터미널을 종료한 뒤 다시 시작하세요.")
            if kind not in ("shell", "claude"):
                raise ValueError("지원하지 않는 터미널 종류입니다.")
            if kind == "claude" and not self.claude:
                raise ValueError("Claude Code CLI를 찾을 수 없습니다.")
            shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
            if kind == "claude":
                # self.claude may be a path (real CLI) or an argv list (e.g. the
                # --mock stand-in: [python, demo/fake_claude.py]).
                args = list(self.claude) if isinstance(self.claude, (list, tuple)) else [self.claude]
            else:
                args = [shell, "-l"]
            master, slave = pty.openpty()
            try:
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                env = os.environ.copy()
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
            threading.Thread(target=self.read, args=(master, process, self.generation), daemon=True).start()
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

    def claude_ready(self):
        """A Claude Code session is running in the app-owned PTY."""
        with self.lock:
            return bool(self.kind == "claude" and self.process and self.process.poll() is None and self.fd is not None)

    def send_choice(self, action, generation=None):
        """Resolve a button/encoder action to key bytes and write them to the PTY."""
        if action not in ACTION_KEYS:
            raise ValueError("지원하지 않는 동작입니다.")
        keys = ACTION_KEYS[action]
        with self.lock:
            if generation is not None and generation != self.generation:
                raise ValueError("대상 터미널이 변경됐습니다.")
            target_generation = self.generation
        self.write(keys, target_generation)
        print(f"send_choice action={action} keys={keys!r} kind={self.kind}", flush=True)
        return {"action": action, "status": "sent"}

    def snapshot(self, after=0, generation=""):
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
                "exitCode": self.process.poll() if self.process else None,
            }

    def write(self, text, generation):
        if not isinstance(text, str) or not 0 < len(text) <= 8192:
            raise ValueError("입력이 비어 있거나 너무 깁니다.")
        with self.write_lock, self.lock:
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
            if generation != self.generation or self.fd is None:
                raise ValueError("터미널이 종료되었거나 변경됐습니다.")
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def stop(self, generation=None):
        with self.lock:
            if generation is not None and generation != self.generation:
                raise ValueError("종료 대상 터미널이 변경됐습니다.")
            process = self.process
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
