# Integration & Manual Test Instructions — `claude-binddeck-retarget`

The single unit spans host (Python) ↔ browser (JS) ↔ device (firmware). Automated
integration coverage lives in `tests/test_server.py` (real HTTP server + PTY) and
`tests/serial.test.js` (fake Web Serial stream). The device and a live Claude
session require **manual** smoke tests below.

## Automated seam coverage

- **HTTP ↔ PTY**: `test_server.py` starts a real `SimulatorServer` and drives
  `/api/press`, `/api/state`, `/api/terminal/*` over `http.client`, asserting the
  security guards, idempotency, throttling and status codes end to end.
- **Browser serial ↔ device framing**: `serial.test.js` feeds a fake
  `ReadableStream`/`WritableStream`, asserting handshake-gated input, the
  `BTN:`/`ENC:` → action mapping, and `CMD:MSG:` OLED output.

## Manual smoke test A — Claude keystrokes (no hardware)

1. `claude --version` succeeds and you are logged in.
2. `python3 server.py --cwd <a test project>`; open `http://127.0.0.1:8765`.
3. Click **Claude 시작**. Confirm the badge shows "Claude 실행 중" and buttons enable.
4. In the terminal, prompt Claude to do something needing a permission approval.
5. When the arrow-key permission menu appears, click **YES** — confirm Claude
   accepts (Enter). Repeat for **NO**/**STOP** (Esc), **▲/▼** (menu moves), **ENTER**.
6. **If a keystroke is wrong** for your Claude version, adjust only the literal
   bytes in `terminal.py::ACTION_KEYS` — logic and tests do not change (they assert
   consistency, not literal bytes). Re-run the unit tests.

## Manual smoke test B — real BindDeck (Chrome + hardware)

1. Upload `firmware/binddeck_claude/binddeck_claude.ino` (see build-instructions).
2. Close other serial monitors. In Chrome, choose **실물 BindDeck · USB → USB BindDeck 연결**.
3. Confirm handshake: status becomes "BindDeck 연결됨".
4. Start Claude (smoke test A) and press physical buttons/encoder:
   `BTN:0`=YES, `BTN:1`=NO, `BTN:2`=STOP, encoder rotate=menu, encoder push=ENTER.
5. Confirm the OLED shows the Claude state and last answer (host → `/api/state` →
   browser poll → `CMD:MSG:`).

## State-feedback check (hooks)

- With `.claude/settings.json` hooks active, `/api/state` `source` should read
  `hook` while Claude is active/waiting. Kill the session and confirm it degrades
  to `transcript` (mtime) or `offline` without errors.
