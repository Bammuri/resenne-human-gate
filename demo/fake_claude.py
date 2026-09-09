#!/usr/bin/env python3
"""A scripted stand-in for the `claude` CLI, used by the server's --mock mode.

This is NOT Claude and runs no tools. It renders a *real* arrow-key permission
menu in the PTY and reacts to the exact byte sequences the app writes via
terminal.py::ACTION_KEYS:

    Up   = \\x1b[A   (nav_up)      Enter = \\r     (yes / confirm)
    Down = \\x1b[B   (nav_down)    Esc   = \\x1b   (no / stop)

So the whole real pipeline exercises hardware-free: BindDeck/web button ->
/api/press -> send_choice -> these bytes -> this menu -> /api/terminal stream ->
xterm.js. Enter selects the *currently highlighted* option (which is why the
encoder navigation matters); Esc declines. Approvals here approve nothing real.
"""
import os
import select
import sys
import termios
import time
import tty

RST = "\x1b[0m"; BOLD = "\x1b[1m"; DIM = "\x1b[90m"
GREEN = "\x1b[32m"; YEL = "\x1b[33m"; CYAN = "\x1b[36m"; RED = "\x1b[31m"

# Scripted gates — mirrors demo/binddeck-claude-demo.html for a consistent story.
GATES = [
    {
        "think": "server.py에 /health 핸들러를 추가할게요.",
        "tool": "Edit", "target": "server.py",
        "summary": "server.py 에 GET /health 핸들러 추가",
        "options": [
            ("Yes", True),
            ("Yes, and don't ask again for Edit this session", True),
            ("No, tell Claude what to do differently", False),
        ],
        "approve": ["✔ server.py 수정 완료 — /health 핸들러 추가", "이제 테스트를 실행해 볼게요."],
        "deny": ["↩ 편집을 취소했어요. 어떻게 바꿀지 알려주면 다시 시도할게요.", "그래도 다음 단계(테스트)를 제안합니다."],
    },
    {
        "think": "테스트 스위트를 실행할게요.",
        "tool": "Bash", "target": "npm test",
        "summary": "테스트 실행: npm test",
        "options": [
            ("Yes", True),
            ("Yes, and don't ask again for Bash this session", True),
            ("No, tell Claude what to do differently", False),
        ],
        "approve": ["$ npm test", "✔ 77 passing (54 python + 23 js)", "통과했어요. 변경을 커밋하고 푸시할까요?"],
        "deny": ["↩ 테스트 실행을 건너뜁니다.", "변경을 커밋하고 푸시할까요?"],
    },
    {
        "think": "원격 저장소로 푸시하려고 합니다.",
        "tool": "Bash", "target": "git push origin main",
        "summary": "git push origin main (되돌리기 어려움)",
        "options": [
            ("Yes", True),
            ("Yes, and don't ask again for Bash this session", True),
            ("No, tell Claude what to do differently", False),
        ],
        "approve": ["$ git push origin main", "✔ pushed."],
        "deny": ["↩ 푸시를 거절했습니다 — 원격은 그대로예요.", "로컬 변경만 남겨둘게요."],
    },
]


def out(text):
    os.write(1, text.encode())


def read_key():
    """Block for one logical key, decoding the app's escape sequences."""
    ch = os.read(0, 1)
    if not ch:
        return "EOF"
    if ch == b"\x1b":
        # Distinguish a lone Esc (no/stop) from an arrow (\x1b[A / \x1b[B):
        # the app writes the whole sequence atomically, so any continuation
        # is already buffered.
        if select.select([0], [], [], 0.06)[0]:
            seq = os.read(0, 2)
            if seq == b"[A":
                return "UP"
            if seq == b"[B":
                return "DOWN"
            return "OTHER"
        return "ESC"
    if ch in (b"\r", b"\n"):
        return "ENTER"
    if ch == b"\x03":
        return "CTRLC"
    return "CH"


def say(lines, color):
    for line in lines:
        out("\r\n" + color + "  " + line + RST)
    out("\r\n")


def run_gate(gate):
    """Draw the menu and return True (approve) / False (decline)."""
    opts = gate["options"]
    out("\r\n" + YEL + "● Claude가 " + gate["tool"] + " 실행 권한을 요청합니다 — " + BOLD + gate["target"] + RST + "\r\n")
    out(DIM + "  " + gate["summary"] + RST + "\r\n")
    out(DIM + "  ↑/↓ 이동 · Enter 확정 · Esc 거절" + RST + "\r\n")
    sel = 0

    def draw(first):
        if not first:
            out("\x1b[%dA" % len(opts))  # move cursor up to the first option
        for i, (label, _approve) in enumerate(opts):
            marker = "❯" if i == sel else " "
            color = (GREEN + BOLD) if i == sel else DIM
            out("\r\x1b[K" + color + " %s %d. %s" % (marker, i + 1, label) + RST + "\r\n")

    # Discard any keystrokes buffered while Claude was "working".
    termios.tcflush(0, termios.TCIFLUSH)
    draw(first=True)
    while True:
        key = read_key()
        if key in ("EOF", "CTRLC"):
            raise SystemExit(0)
        if key == "UP":
            sel = (sel - 1) % len(opts); draw(first=False)
        elif key == "DOWN":
            sel = (sel + 1) % len(opts); draw(first=False)
        elif key == "ENTER":
            return opts[sel][1]      # approve flag of the highlighted option
        elif key == "ESC":
            return False             # decline / interrupt
        # any other key is ignored while a prompt is open


def main():
    fd = 0
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        old = None
    if old is not None:
        tty.setcbreak(fd)  # immediate byte reads, no echo
    try:
        out("\x1b[2J\x1b[H")
        out(BOLD + CYAN + "Claude Code" + RST + DIM + "  (mock 세션 · 실제 도구는 실행되지 않습니다)" + RST + "\r\n")
        out(DIM + "BindDeck 버튼/엔코더 또는 키보드로 아래 승인 프롬프트에 답해 보세요." + RST + "\r\n")
        out("\r\n" + "› /health 엔드포인트를 추가하고 테스트를 돌려줘. 이상 없으면 커밋까지." + "\r\n")
        for gate in GATES:
            time.sleep(0.5)
            out("\r\n" + DIM + "● " + gate["think"] + RST + "\r\n")
            approved = run_gate(gate)
            say(gate["approve"] if approved else gate["deny"], GREEN if approved else YEL)
        out("\r\n" + BOLD + GREEN + "● 세션 종료 (mock)." + RST +
            DIM + " 다시 보려면 웹 터미널에서 종료 후 Claude를 다시 시작하세요." + RST + "\r\n")
        # Stay alive so the app keeps reading the PTY (claude_ready stays true)
        # until the user stops the session; Esc/keys are harmless here.
        while True:
            if read_key() == "EOF":
                break
    except SystemExit:
        pass
    finally:
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
