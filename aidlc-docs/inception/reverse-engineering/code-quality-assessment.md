# Code Quality Assessment

## Test Coverage
- **Overall**: **Good** for a project this size — the security-critical and parsing-critical paths are unit tested; hardware and end-to-end agent behavior are (necessarily) not.
- **Unit Tests**:
  - `tests/test_server.py` (156 lines) — routing, host/token/Origin guards, `/api/press` validation, idempotency/rate limiting; Codex send is mocked.
  - `tests/test_output.py` (122 lines) — `OutputReader` JSONL/`event_msg` parsing and status transitions.
  - `tests/test_terminal.py` (67 lines) — `WebTerminal` behavior.
  - `tests/serial.test.js` (83 lines) — `SerialLineParser`/`ButtonSerial` over a fake Web Serial stream.
- **Integration/E2E Tests**: **None automated.** README explicitly states physical board upload/wiring/press and real agent delivery must be verified manually with hardware; run environment validated on macOS + desktop Chrome, Linux/WSL "not yet verified."

## Code Quality Indicators
- **Linting**: No linter config present (no ESLint/ruff/flake8 config files).
- **Code Style**: **Consistent.** Python is idiomatic stdlib with clear docstrings; JS is uniform `"use strict"` classes with terse, purposeful comments. Naming is coherent across the stack (`thread`, `generation`, `choice`, `target`).
- **Documentation**: **Good.** `README.md` is thorough (setup, terminal, hardware wiring, serial protocol, troubleshooting, verification); code comments explain non-obvious intent (PTY control tty, partial-line handling, idempotency).
- **Security posture**: **Strong for a local tool** — loopback-only bind, per-process random token with `compare_digest`, Origin check, strict CSP + `nosniff` + `X-Frame-Options`, read-only sqlite (`mode=ro`), bounded request/record sizes, ANSI stripping before display. The README is candid that web-terminal commands run as the invoking user.

## Technical Debt
- **Codex-format coupling** (`output.py`, `terminal.py::detect_thread`): depends on undocumented, version-specific on-disk Codex formats; README notes it targets `codex-cli 0.153.4` and may need adjustment on Codex updates. This is the brittle core the retarget must replace.
- **Partial Claude scaffolding, incomplete end-to-end** (see below): the send path exists but discovery, state, and UI do not — a half-migrated seam.
- **Answer semantics vs. permission prompts**: `send_choice()` writes a literal `"yes\n"`/`"no\n"` to the PTY. This matches a chat-style prompt, but interactive agents (both Codex and Claude Code) often present **numbered permission menus** where "yes" is not a valid keystroke — mapping YES/NO to the correct selection is unspecified and untested for Claude.
- **Single-session by design**: one web terminal + one "current" target per server; documented, not a bug, but a scaling limit.
- **No CI**: tests exist but there is no pipeline to run them.

## Patterns and Anti-patterns
- **Good Patterns**:
  - App-owned PTY broker with a proper controlling terminal (`pty_child.py`).
  - Incremental tailing with `generation`/`reset` + inode identity (robust to rotation/restart).
  - Idempotent, rate-limited, single-flight command dispatch (`requestId` cache, `send_lock`).
  - Defense-in-depth local origin control (host + token + Origin + CSP).
  - Handshake-gated serial bridge; bounded buffers everywhere (512 KiB PTY, 20 000-char text cap, 50 000-byte request cap).
- **Anti-patterns / risks**:
  - Reading another tool's private on-disk state as an integration contract (inherently fragile; the retarget should prefer a supported mechanism such as Claude Code hooks).
  - Frontend gates the terminal target on `codexAvailable` even though the terminal answer path can be Claude — an availability check that does not match the retarget's intent.

## Brownfield Retarget Readiness — Key Findings
- **Already in place (reusable seam):** `terminal.py` exposes `start(kind="claude")`, `send_choice()`, and `claude_ready()`; `server.py` routes `target=terminal` answers through the Claude PTY when ready; `/api/session` already reports `claudeAvailable`. So the **answer-delivery path to a terminal-hosted Claude partially exists.**
- **Missing / Codex-only (must change for the retarget):**
  1. **No UI to launch Claude** — `web-terminal.js`/`index.html` offer only `shell`/`codex`/`codex-yolo` buttons; there is no "Claude 시작" control, so `kind="claude"` is unreachable from the UI.
  2. **State reading is Codex-only** (`output.py` parses `~/.codex` sqlite/JSONL) — Claude Code has no equivalent `event_msg` store; needs hooks (`Notification`/`PostToolUse`/`Stop`) or `~/.claude/projects/**/*.jsonl` transcript parsing.
  3. **Session discovery is Codex-only** (`thread-writer-locks/<uuid>.lock`) — no analog for Claude.
  4. **Availability/UX gating is Codex-worded** — `canSend()`, hint text, and labels assume Codex.
  5. **No `claude queue` equivalent exists** — Codex's inject-into-running-session command has no Claude counterpart, so the "current" (external existing session) target has no clean Claude path; the robust path is the app-owned PTY (Claude launched inside the web terminal).
- **Confirmed by prior gpt-astra consultation**: recommended approach = **hooks for state + app-owned PTY for YES/NO + `.jsonl` as fallback**, with AgentDeck used as **reference only** (not adopted).
