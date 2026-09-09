# AI-DLC State

> **What this folder is (orientation).** `aidlc-docs/` is the AI-DLC **process trail** for the **root HUMAN GATE gate app** (this repo's `server.py` / `terminal.py` / `hooks/` / `firmware/resenne_uno_r4/` — the two-button ✓/✕ approval gate). The reverse-engineering artifacts under `inception/reverse-engineering/` are an **as-found snapshot of the pre-retargeting code** (the original Codex-based "Button Lab"); they intentionally describe the *starting* state, not the shipped product, and are kept for provenance — expect old names there (`Button Lab`, `codex queue`, `firmware/yes_no`). The **shipped submission** is *Re:senne HUMAN GATE* for **Claude Code** (canonical path USB serial → PTY; submission firmware `firmware/resenne_uno_r4/`); the authoritative positioning and claims live in the root [`README.md`](../README.md) and [`CONCEPT_FINAL.md`](../CONCEPT_FINAL.md). The separate **8-key AI-DLC controller** (real Codex·Claude driven in a PTY + physical-key AI-DLC stage control; team-confirmed on the real board) is a **different app** under [`demo/arduino-simulator/`](../demo/arduino-simulator/) with its own AI-DLC docs and its own test suite (116). The "77 tests" and workspace path below refer to **this** (root gate) app; the workspace path is the local git worktree where this AI-DLC run happened — the submission repository is `resenne-human-gate`.

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
- **Verification (re-measured 2026-09-09)**: **77 tests pass** (54 Python via `.venv` unittest incl. Hypothesis PBT + the approval-gate broker unit tests, 3 subprocess-E2E hook-process tests, and 5 decision-audit-log tests in `tests/test_approval.py` + the gate-panel serving test in `test_server.py`; 23 JS via `node --test` incl. fast-check PBT + 11 gate-panel tests incl. the recent-decisions view in `tests/gate.test.js`). Syntax gates (`node --check` incl. `gate.js`, `py_compile`) pass. **Real-hardware (UNO R4 WiFi):** physical button → WebSocket → Node Bridge round-trip confirmed on device (2026-09-07~08); OLED + D3 REJECT confirmed via the team button-test sketch. **allow/deny gate (unit `approval-gate`):** code-integrated + unit-tested + **software-E2E-verified** in the submission repo — the real `hooks/hook_bridge.py` process ↔ broker (`server.py` `/api/approval*`) ↔ browser (ui-token) resolver chain passes via subprocess tests and a live `python3 server.py` curl smoke, and a standalone browser panel (`/gate.html` + `gate.js`) lets a human submit allow/deny to a pending request. **Decision audit log (RESILIENCY-05 increment):** resolved decisions are appended to `.claude/approval-log.jsonl` (mode 0600, outside the web root, gitignored) recording only `tool_name`/`input_hash`/`decision`/`role`/timestamps — no summary, no tool input, no token — and surfaced via `GET /api/approval/log` (ui/device tokens only); a log-write failure withholds the decision (fail-safe "ask"). This is verified in software (unit + curl smoke); it records only that a resolver submitted a decision — `role` is the credential role, not a person's identity or proof of a physical button, and the log does not prove the tool actually ran. Gate activation is opt-in via `hooks/hook-gate.settings.example.json`; design in `construction/approval-gate/design.md`. **Not yet verified (human/live):** the real `claude` binary honouring the gate's `permissionDecision` to allow/deny an actual tool run — plus live-`claude` keystroke smoke and the Node Bridge↔PTY adapter integration (`HACKATHON_EXECUTION_PLAN.md` §2). **The PTY key path (`/api/press`) remains the sole *complete* E2E-verified submission path.**

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
| CONSTRUCTION | Unit `approval-gate` (allow/deny gate) | ✅ Code-integrated + unit-tested + software-E2E (subprocess + live curl); browser panel `/gate.html`. Increment 2 (2026-09-09): persistent decision audit log (`.claude/approval-log.jsonl`, 0600) + recent-decisions view (`GET /api/approval/log`, ui/device only), record-before-deliver, log excludes summary/tool-input/token. Live-`claude`-honours-decision = human/live step. Design in construction/approval-gate/design.md |
| CONSTRUCTION | Build & Test | ✅ Completed (77 tests pass; docs in construction/build-and-test/) |
| OPERATIONS | — | ⬜ Placeholder (out of scope) |
