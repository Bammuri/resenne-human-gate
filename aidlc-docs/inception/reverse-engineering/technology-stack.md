# Technology Stack

## Programming Languages
- **Python** — ≥ 3.10 — entire backend (`server.py`, `terminal.py`, `output.py`, `pty_child.py`).
- **JavaScript** (ES2020+, browser, `"use strict"`) — frontend SPA (`app.js`, `web-terminal.js`, `serial.js`).
- **C++ (Arduino)** — firmware (`firmware/yes_no/yes_no.ino`).
- **HTML/CSS** — `index.html`, `style.css` (inline SVG virtual board).

## Frameworks
- **None server-side** — Python standard library only (`http.server.ThreadingHTTPServer`, `BaseHTTPRequestHandler`).
- **None frontend-side** — vanilla JS + DOM; no React/Vue/build framework.
- **xterm.js** (+ `@xterm/addon-fit`) — vendored — in-browser terminal emulator.
- **Arduino core (UNO R4 / Renesas RA4M1)** — firmware runtime.

## Browser Platform APIs
- **Web Serial API** — USB board connection (desktop Chrome).
- **Fetch / AbortSignal.timeout / crypto.randomUUID** — API calls and request ids.

## Infrastructure
- **None** — runs as a single local process bound to `127.0.0.1`; no cloud, containers, or orchestration.

## Build Tools
- **None for app** — Python run directly; frontend served static; libraries pre-vendored.
- **Arduino IDE** — compile/upload firmware (UNO R4 Boards board package).

## Testing Tools
- **Python `unittest`** — `python3 -m unittest discover -s tests -v` (server/output/terminal; Codex send mocked).
- **Node.js built-in test runner** — `node --test tests/serial.test.js` (fake Web Serial stream).

## External CLIs / OS tools (runtime integration)
- **Codex CLI** — `codex queue --thread <id> --message <choice>`; local session store at `~/.codex/`.
- **Claude Code CLI** — detected at startup (`shutil.which("claude")`); launchable in the PTY as `kind="claude"` (partial integration today).
- **`ps`, `lsof`, `/proc`** — process-tree + open-fd inspection for session discovery.
