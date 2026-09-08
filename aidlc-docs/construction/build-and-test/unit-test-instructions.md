# Unit & Property Test Instructions — `claude-binddeck-retarget`

Run all Python tests under the venv (it has `hypothesis`; the base env is PEP 668
externally-managed), and JS tests with the Node test runner.

```bash
# Python (unit + property). 31 tests.
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v

# JavaScript (unit + property). 12 tests.
npm test        # == node --test tests/*.test.js
```

## Test inventory

| File | Kind | Covers |
|---|---|---|
| `tests/test_terminal.py` | unit | PTY lifecycle, `shell`/`claude` allow-list, `claude_ready()`, `send_choice` maps every action → `ACTION_KEYS`, rejects unknown/stale, table consistency |
| `tests/test_server.py` | unit | `/api/press` for all 6 actions, idempotency, throttle (429), send-lock (409), reused request-id (409), 503 when no Claude session, 502 on send failure, origin/host/token guards, `/api/state` + `/api/session` + static assets, cursor validation |
| `tests/test_claude_state.py` | unit | hook-file primary source, transcript **mtime** fallback (active/idle), pty-live vs offline, `note_answer`, bad-JSON/invalid-status never raises |
| `tests/test_mapping_pbt.py` | property (Hypothesis) | **PBT-08** send_choice totality (only mapped actions accepted), **PBT-09** every mapped action writes exactly its keys; non-string rejection; tables are single source of truth |
| `tests/serial.test.js` | unit | `parseDeviceLine` table, line framing/overflow, handshake-before-input, OLED `sendMessage`, reconnect, unplug, unsupported browser |
| `tests/mapping.pbt.test.js` | property (fast-check) | **PBT-02** totality, **PBT-03** purity/determinism, **PBT-07** consistency with button/encoder tables and exact framing |

## Notes

- `send_choice` PTY delivery is mocked in `test_server.py`; the real key-sequence
  mapping is asserted directly in `test_terminal.py` / `test_mapping_pbt.py`.
- `test_terminal.py` uses `cat` as a long-lived stand-in for `claude` to exercise a
  real PTY and `claude_ready()` without requiring the CLI.
- Expected result: **45 passed, 0 failed** (33 Python + 12 Node).
