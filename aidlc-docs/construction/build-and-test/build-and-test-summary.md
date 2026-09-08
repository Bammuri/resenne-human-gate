# Build & Test Summary — `claude-binddeck-retarget`

Single unit retargeting the Button Lab bridge from Codex → **Claude Code**. The **submission
hardware is Arduino UNO R4 WiFi** (`firmware/resenne_uno_r4/`, ✓ D2 / ✕ D3 buttons + SSD1306 OLED
over WiFi/WebSocket); the BindDeck ESP32 USB-serial fork is retained as an earlier exploration path.
Runtime stays zero-dependency; test-only deps are `fast-check` (npm, gitignored `node_modules/`)
and `hypothesis` (local `.venv/`, gitignored — PEP 668 base env).

## Commands

```bash
npm install && python3 -m venv .venv && ./.venv/bin/pip install hypothesis   # once
npm test                                                                     # 19 JS tests
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v           # 49 Python tests
python3 server.py                                                            # run app
```

## Result (re-measured 2026-09-09)

| Suite | Command | Result |
|---|---|---|
| Python unit + property | `unittest discover` (venv) | **49 passed** (incl. approval-gate broker + hook-process subprocess-E2E tests in `tests/test_approval.py`, gate-panel serving test in `test_server.py`) |
| JS unit + property | `node --test tests/*.test.js` | **19 passed** (incl. 7 gate-panel tests in `tests/gate.test.js`) |
| **Total** | | **68 passed, 0 failed** |

Syntax gates: `node --check` on `app.js`/`web-terminal.js`/`serial.js`/`gate.js` and
`py_compile` on `server.py`/`terminal.py`/`claude_state.py`/`hooks/claude_state_hook.py`/`hooks/hook_bridge.py`
all pass. `index.html`/`gate.html` element IDs referenced by the JS were verified present;
all Codex/UNO artifacts (`terminal-codex`, `terminal-yolo`, `button-target`,
`codex-step`, `codexAvailable`, "UNO R4") removed.

## Extension compliance (enabled subset)

- **Security Baseline**: disabled (Q8=B). Good-practice guards retained anyway:
  localhost Host allow-list, `X-Simulator-Token` `compare_digest`, Origin check,
  CSP + `X-Frame-Options: DENY`, inbound serial whitelisting, no credentials in the
  firmware fork, `send_choice` action allow-list.
- **Resiliency (RESILIENCY-05/06/10)**: verified — see performance-test-instructions.md.
- **PBT (PBT-02/03/07/08/09)**: implemented in `tests/mapping.pbt.test.js` and
  `tests/test_mapping_pbt.py` (totality, purity, table consistency for the pure
  mappings; send_choice totality/consistency for the action→keys table).

## Verified on hardware / not yet verified

- **Verified (UNO R4 WiFi, 2026-09-07~08):** physical button → WiFi → WebSocket → Node Bridge
  round-trip on real hardware (30ms debounce, 21 clean presses); OLED + D3 REJECT confirmed via the
  team button-test sketch and integrated into `firmware/resenne_uno_r4/`.
- **Verified (software, approval gate, 2026-09-09):** the real `hooks/hook_bridge.py` process ↔ broker
  ↔ browser (ui-token) resolver chain, end-to-end — subprocess tests (allow / deny / fail-safe-ask)
  plus a live `python3 server.py --mock --show-gate-token` curl smoke: `/gate.html`+`/gate.js` served →
  a hook long-poll creates a pending request → the browser panel polls `/api/approval` and a human
  APPROVE resolves it → the hook receives `{decision: allow}`; the hook token cannot self-resolve (403).
  No hardware or browser automation required. This proves the software chain up to — but not including —
  the real `claude` binary honouring the decision.
- **Not yet verified:**
  1. Live `claude` honouring the gate's `permissionDecision` on the submission build (opt-in
     `claude --settings hooks/hook-gate.settings.example.json`) — the only remaining gate link,
     confirmed in a running Claude session (live demo). The PTY key path (`/api/press`) remains the
     sole **complete** E2E-verified submission path.
  2. Live `claude` permission-menu key-sequence smoke test — may adjust `ACTION_KEYS` literal bytes
     only (no logic/test change).
  3. Node Bridge ↔ Python(PTY) thin adapter end-to-end (remaining integration, plan §2).
  4. Firmware not compiled in this env (no `arduino-cli`/toolchain) — correctness by inspection;
     flash / on-device confirmation performed by the team.
  5. BindDeck (ESP32, USB serial) upload — earlier exploration path, not the submission hardware.

## Provenance / licensing note

Firmware forks SanX18/BindDeck, which has **no LICENSE** upstream; redistribution is
deferred until clarified (NFR-6). The fork strips BLE/Wi-Fi and carries no credentials.
