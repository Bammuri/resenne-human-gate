# AI-DLC State

## Project
- **Name**: Button Lab · UNO R4 WiFi — Codex → Claude Code retargeting
- **Workspace**: `/home/hj/aidlc-workshop/hackerthon/arduino-simulator-aidlc/` (git worktree, branch `aidlc-retarget`)
- **Project Type**: **Brownfield** (existing application code present)
- **Objective**: Retarget the physical/simulated YES/NO button bridge so it drives a running **Claude Code** session instead of Codex.
- **Hardware surface (submission, updated 2026-09-08)**: **Arduino UNO R4 WiFi** + 128×64 SSD1306 OLED + two physical buttons (✓ APPROVE = D2, ✕ REJECT = D3). Transport: button → WiFi 2.4GHz → WebSocket → Node Bridge (`ws://…:8080`) → app PTY approval seam. Firmware `firmware/resenne_uno_r4/`; button→bridge round-trip verified on real hardware 2026-09-07~08 (30ms debounce, 21 clean presses); OLED + D3 REJECT confirmed on-device via the team button-test sketch, then integrated. Node Bridge ↔ Python(PTY) thin adapter = remaining integration (`HACKATHON_EXECUTION_PLAN.md` §2). **Earlier exploration paths (retained as docs):** BindDeck ESP32 USB-serial (`firmware/binddeck_claude/`, `inception/reverse-engineering/external-binddeck-reference.md`) and the initial UNO R4 two-button USB-serial sketch (`firmware/yes_no/`).

## Current Phase
- **Phase**: CONSTRUCTION
- **Active Stage**: Build & Test — complete (auto-proceeding per user instruction "자동진행해"). Ready for OPERATIONS (placeholder) / final commit.
- **Unit**: `claude-binddeck-retarget` (single unit)
- **Verification (re-measured 2026-09-08)**: **45 tests pass** (33 Python via `.venv` unittest incl. Hypothesis PBT; 12 JS via `node --test` incl. fast-check PBT). Syntax gates (`node --check`, `py_compile`) pass. **Real-hardware (UNO R4 WiFi):** physical button → WebSocket → Node Bridge round-trip confirmed on device (2026-09-07~08); OLED + D3 REJECT confirmed via the team button-test sketch. Deferred: live-`claude` keystroke smoke + the Node Bridge↔PTY adapter end-to-end integration — see build-and-test docs and `HACKATHON_EXECUTION_PLAN.md` §2.

## Extension Configuration
| Extension | Enabled | Mode | Decided At | Notes |
|---|---|---|---|---|
| Security Baseline | No | — | Requirements Analysis | Q8=B skip. localhost single-dev PoC. Non-rule good practices still applied: strip hardcoded Wi-Fi creds, validate serial input. |
| Resiliency Baseline | Yes (scoped) | Applicable-subset | Requirements Analysis | Q9=A. Cloud/DR/multi-zone/CI-CD/incident rules = **N/A** (no deployment infra, single local process, no persistent data). Enforced subset: RESILIENCY-06 (liveness/health of serial+PTY+Claude), RESILIENCY-10 (timeouts, graceful degradation on disconnect), RESILIENCY-05 (structured logging). |
| Property-Based Testing | Yes | Partial (PBT-02/03/07/08/09) | Requirements Analysis | Q10=B. Enforced for pure mapping functions (BTN:/ENC:→choice) and serial/telemetry serialization round-trips. Other PBT rules advisory. |

### Decision provenance
All 10 requirement decisions were auto-confirmed via installed GPT (Codex CLI, medium reasoning) consultation + AI recommendation, per user instruction "애매한건 정리해서 GPT arsta mid에게 물어보고 자동진행해". See `inception/requirements/gpt-astra-consultation.md` and `inception/requirements/requirement-verification-questions.md`.

## Workspace Detection Status
- [x] Workspace Detection — Completed on 2026-09-08T02:23:18Z
- **Detected**: Brownfield. Python 3 stdlib HTTP server (`server.py`, `terminal.py`, `output.py`, `pty_child.py`) + vanilla JS/xterm.js frontend (`app.js`, `serial.js`, `web-terminal.js`, `index.html`, `style.css`) + Arduino firmware (`firmware/yes_no/yes_no.ino`) + tests (`tests/`). No package manager / build system beyond `unittest` (Python) and `node --test` (JS). Zero external runtime dependencies (xterm/addon-fit vendored).
- **No pre-existing reverse-engineering artifacts** → Reverse Engineering must execute.

## Reverse Engineering Status
- [x] Reverse Engineering — Completed on 2026-09-08T02:23:18Z (awaiting user approval at gate)
- **Artifacts Location**: aidlc-docs/inception/reverse-engineering/
- **Artifacts**: business-overview, architecture, code-structure, api-documentation, component-inventory, interaction-diagrams, technology-stack, dependencies, code-quality-assessment (+ timestamp)
- **Key finding**: Codex→Claude answer-delivery seam partially exists (`send_choice`/`claude_ready`/`start(kind="claude")`); state-reading, session discovery, and UI are Codex-only and must be retargeted. No `claude queue` equivalent → app-owned PTY is the robust send path.

## Phase Ledger
| Phase | Stage | Status |
|-------|-------|--------|
| INCEPTION | Workspace Detection | ✅ Completed |
| INCEPTION | Reverse Engineering | ✅ Completed |
| INCEPTION | Requirements Analysis | ✅ Completed |
| INCEPTION | User Stories | ⏭️ Skipped (single-dev localhost tool; scenarios cover UX) |
| INCEPTION | Workflow Planning | ✅ Completed |
| INCEPTION | Application Design | ✅ Completed (folds Functional Design + NFR) |
| INCEPTION | Units Generation | ⏭️ Skipped (one cohesive unit) |
| CONSTRUCTION | Functional Design / NFR | ⏭️ Folded into Application Design |
| CONSTRUCTION | Infrastructure Design | ⏭️ Skipped (no cloud/deploy) |
| CONSTRUCTION | Code Generation | ✅ Completed |
| CONSTRUCTION | Build & Test | ✅ Completed (45 tests pass; docs in construction/build-and-test/) |
| OPERATIONS | — | ⬜ Placeholder (out of scope) |
