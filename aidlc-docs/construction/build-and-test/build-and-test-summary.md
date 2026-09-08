# Build & Test Summary — `claude-binddeck-retarget`

Single unit retargeting the Button Lab bridge from Codex → **Claude Code** and from
UNO R4 → **BindDeck** (ESP32). Runtime stays zero-dependency; test-only deps are
`fast-check` (npm, gitignored `node_modules/`) and `hypothesis` (local `.venv/`,
gitignored — PEP 668 base env).

## Commands

```bash
npm install && python3 -m venv .venv && ./.venv/bin/pip install hypothesis   # once
npm test                                                                     # 12 JS tests
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v           # 31 Python tests
python3 server.py                                                            # run app
```

## Result (this run, 2026-09-08)

| Suite | Command | Result |
|---|---|---|
| Python unit + property | `unittest discover` (venv) | **31 passed** |
| JS unit + property | `node --test tests/*.test.js` | **12 passed** |
| **Total** | | **43 passed, 0 failed** |

Syntax gates: `node --check` on `app.js`/`web-terminal.js`/`serial.js` and
`py_compile` on `server.py`/`terminal.py`/`claude_state.py`/`hooks/claude_state_hook.py`
all pass. `index.html` element IDs referenced by the JS were verified present;
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

## Not yet verified (requires environment/hardware)

1. Real key-sequence smoke test against a live `claude` permission menu — may adjust
   `ACTION_KEYS` literal bytes only (no logic/test change).
2. Real BindDeck upload + button/encoder/OLED behavior over USB.
3. Firmware is not compiled here (no embedded toolchain) — correctness by inspection.

## Provenance / licensing note

Firmware forks SanX18/BindDeck, which has **no LICENSE** upstream; redistribution is
deferred until clarified (NFR-6). The fork strips BLE/Wi-Fi and carries no credentials.
