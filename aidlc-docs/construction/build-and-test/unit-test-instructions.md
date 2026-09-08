# Unit & Property Test Instructions — `claude-binddeck-retarget`

Run all Python tests under the venv (it has `hypothesis`; the base env is PEP 668
externally-managed), and JS tests with the Node test runner.

```bash
# Python (unit + property). 49 tests.
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v

# JavaScript (unit + property). 19 tests.
npm test        # == node --test tests/*.test.js
```

## Test inventory

| File | Kind | Covers |
|---|---|---|
| `tests/test_terminal.py` | unit | PTY lifecycle, `shell`/`claude` allow-list, `claude_ready()`, `send_choice` maps every action → `ACTION_KEYS`, rejects unknown/stale, table consistency |
| `tests/test_server.py` | unit | `/api/press` for all 6 actions, idempotency, throttle (429), send-lock (409), reused request-id (409), 503 when no Claude session, 502 on send failure, origin/host/token guards, `/api/state` + `/api/session` + static assets, cursor validation; **gate panel served under the same strict CSP and `gate.js` never calls the PTY/terminal paths (isolation)** |
| `tests/test_claude_state.py` | unit | hook-file primary source, transcript **mtime** fallback (active/idle), pty-live vs offline, `note_answer`, bad-JSON/invalid-status never raises |
| `tests/test_mapping_pbt.py` | property (Hypothesis) | **PBT-08** send_choice totality (only mapped actions accepted), **PBT-09** every mapped action writes exactly its keys; non-string rejection; tables are single source of truth |
| `tests/test_approval.py` | unit + subprocess-E2E (approval-gate) | allow/deny broker: dedup by tool_use_id, atomic resolve + 409 on second resolve, concurrent wait wakes, unknown→ask, session-end expiry, `summarize_tool` bound; `/api/approval*` token roles (ui\|device list/resolve, hook register/wait only, hook cannot self-approve, device may resolve, bad-input 400). **Plus 3 subprocess-E2E tests** that run the real `hooks/hook_bridge.py` process with a PreToolUse stdin + `BUTTONLAB_*` env against a web (ui-token) resolver: allow / deny / no-env→fail-safe-ask. **Software E2E only — the live `claude`-honours-decision link is a human/live step.** |
| `tests/gate.test.js` | unit (approval-gate panel) | `gate.js`: `describePending` (pure), `GateApi` connect/listPending/resolve incl. 409 (fake fetch models the broker endpoints), `initGatePanel` renders pending rows + wires approve/reject buttons (fake DOM) |
| `tests/serial.test.js` | unit | `parseDeviceLine` table, line framing/overflow, handshake-before-input, OLED `sendMessage`, reconnect, unplug, unsupported browser |
| `tests/mapping.pbt.test.js` | property (fast-check) | **PBT-02** totality, **PBT-03** purity/determinism, **PBT-07** consistency with button/encoder tables and exact framing |

## Notes

- `send_choice` PTY delivery is mocked in `test_server.py`; the real key-sequence
  mapping is asserted directly in `test_terminal.py` / `test_mapping_pbt.py`.
- `test_terminal.py` uses `cat` as a long-lived stand-in for `claude` to exercise a
  real PTY and `claude_ready()` without requiring the CLI.
- Expected result: **68 passed, 0 failed** (49 Python + 19 Node).
