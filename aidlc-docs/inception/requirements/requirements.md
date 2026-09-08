# Requirements — Button Lab: Codex → Claude Code retarget on BindDeck hardware

## 1. Intent Analysis Summary
- **User request (raw)**: "HW는 https://github.com/SanX18/BindDeck 이거쓸꺼야 분석해서 다시 만들어보자" (preceded by: retarget the YES/NO button bridge from Codex to Claude Code).
- **Request type**: Migration (Codex → Claude Code target; UNO R4 → BindDeck hardware) + Enhancement (richer input surface: encoder-driven menu navigation, OLED state feedback).
- **Scope estimate**: Multiple Components — Arduino/ESP32 firmware, browser Web Serial layer (`serial.js` + UI), Python host (send path + Claude state reader).
- **Complexity estimate**: Moderate → Complex (semantic gap between literal `yes/no` and Claude's numbered permission menus; new hardware protocol; new state-reading mechanism).
- **Depth**: Standard/Comprehensive (brownfield migration touching every layer).
- **Decision provenance**: All clarifying answers auto-confirmed via GPT arsta mid (Codex CLI, medium) + AI recommendation per user instruction. See `gpt-astra-consultation.md`.

## 2. Confirmed Decisions (from requirement-verification-questions.md)
| # | Decision | Answer |
|---|---|---|
| Q1 | Rebuild scope | **A** — fork+slim BindDeck firmware AND adapt host `serial.js` |
| Q2 | Button→action mapping | **A+C** — YES/NO + STOP; ALWAYS excluded by default |
| Q3 | Encoder for numbered menus | **A** — rotate = move selection (↑/↓), push (BTN:8) = confirm (Enter) |
| Q4 | OLED feedback | **A** — show Claude state (waiting/active/idle) + last answer |
| Q5 | BLE/Wi-Fi | **A** — USB serial only; strip BLE + Wi-Fi + hardcoded creds |
| Q6 | Claude state-reading | **A** — Hooks first + `.jsonl` transcript fallback |
| Q7 | Host transport | **A** — browser Web Serial (USB) |
| Q8 | Security extension | **B** — skip (PoC); still strip creds + validate serial input |
| Q9 | Resiliency extension | **A** — apply the *applicable subset* (see §6) |
| Q10 | PBT extension | **B** — partial (pure mapping + serialization round-trips) |

## 3. Functional Requirements

### FR-1 — Physical/virtual answer input via BindDeck
- **FR-1.1**: A press of BindDeck switch `BTN:0` SHALL be interpreted as **YES**; `BTN:1` as **NO**; `BTN:2` as **STOP** (interrupt / Esc).
- **FR-1.2**: The virtual on-screen board SHALL continue to offer the same YES/NO/STOP actions so the app is usable without hardware.
- **FR-1.3**: Duplicate/bounced events for the same logical press SHALL be de-duplicated (idempotent dispatch) — a single physical press produces exactly one delivered choice.
- **FR-1.4**: `ALWAYS` (approve-all) is **not** wired by default; it is a documented future option the user can enable (user-discretion item).

### FR-2 — Encoder-driven navigation of Claude's numbered permission menus
- **FR-2.1**: When Claude presents a **numbered permission menu**, encoder rotation SHALL move the highlighted selection up/down (emit ↑/↓ arrow keys to the PTY), and the encoder push (`BTN:8`) SHALL confirm the selection (Enter).
- **FR-2.2**: For a simple binary `y/n` prompt, YES/NO buttons SHALL provide a fast path that sends the correct token directly (option `1`/`3` for a standard 3-item menu, or `y`/`n` where applicable). The exact token set SHALL be defined in Application Design.
- **FR-2.3**: The mapping between a button/encoder event and the emitted key sequence SHALL be a **pure, table-driven function** (testable per PBT — see §6).

### FR-3 — Deliver answers to a running Claude Code session
- **FR-3.1**: The app SHALL write the resolved key sequence to an **app-owned PTY** that hosts the Claude Code session (reuse `terminal.send_choice()` / `start(kind="claude")`).
- **FR-3.2**: There SHALL be **no dependency** on any `claude queue` CLI (none exists); PTY write is the sole send path.
- **FR-3.3**: The send path SHALL only be enabled when a Claude session is detected ready (`claude_ready()` / `/api/session` reports `claudeAvailable`).

### FR-4 — Read Claude session state
- **FR-4.1**: The app SHALL determine Claude session state — **waiting-for-approval / active / idle** — primarily from **Claude hooks** (Notification / PostToolUse / Stop).
- **FR-4.2**: When hooks are unavailable or miss an event, the app SHALL fall back to tailing the Claude transcript at `~/.claude/projects/**/*.jsonl`.
- **FR-4.3**: All Codex-specific state reading (`state_5.sqlite`, `sessions/**.jsonl` `event_msg` parsing, `thread-writer-locks/*.lock` discovery) SHALL be removed or replaced by the Claude equivalents. `codex queue` subprocess send SHALL be removed.

### FR-5 — OLED state feedback (reverse channel)
- **FR-5.1**: The host SHALL push the current Claude state (waiting / active / idle) and the last delivered answer to the BindDeck OLED using `CMD:MSG:<text>` (and/or a repurposed telemetry line).
- **FR-5.2**: OLED display format is a user-discretion item; a compact default (state word + last answer) SHALL be provided.

### FR-6 — Firmware fork (slimmed BindDeck sketch)
- **FR-6.1**: A forked firmware sketch SHALL retain the `BTN:<i>` / `ENC:<...>` USB-serial event protocol and OLED, and SHALL drop or gate BLE HID, Wi-Fi UDP, hardware-monitor telemetry, and the battery/idle-stats screens.
- **FR-6.2**: The forked firmware SHALL contain **no hardcoded Wi-Fi credentials**.
- **FR-6.3**: The forked firmware SHOULD add a Button-Lab-style handshake (or a `CMD:GET_WIFI`→`WIFI_INFO:`-equivalent liveness reply) so the host can robustly detect a connected board.

### FR-7 — Web Serial host integration
- **FR-7.1**: The browser `serial.js` / `SerialLineParser` SHALL be adapted to parse BindDeck framing (`BTN:<i>`, `ENC:<...>`) and map events to logical actions, replacing the current `yes`/`no` line parsing.
- **FR-7.2**: Connection SHALL use the browser Web Serial API at 115200 baud; no extra host install required.

## 4. Non-Functional Requirements
- **NFR-1 (Locality/Privacy)**: The app SHALL remain localhost-only, retaining existing guards (Host allow-list, `X-Simulator-Token`, Origin/CSP checks). No new network egress. (Security extension skipped, but these existing controls are retained.)
- **NFR-2 (Zero external runtime deps)**: No new runtime dependency on the Python/JS host beyond the standard library + already-vendored xterm.js. Firmware may use its existing Arduino libs (Adafruit SSD1306/GFX, Bounce2); BLE lib removed.
- **NFR-3 (Credential hygiene)**: No secrets committed. Hardcoded BindDeck Wi-Fi creds SHALL be removed in the fork.
- **NFR-4 (Robustness)**: See §6 resiliency subset — serial/PTY calls have timeouts; graceful degradation when the device or Claude session is absent; idempotent press handling; safe initial state.
- **NFR-5 (Testability)**: Pure mapping functions and serialization round-trips SHALL be covered by property-based tests (see §6). Existing example-based tests SHALL be retained/updated.
- **NFR-6 (Licensing)**: BindDeck has no LICENSE file. The fork SHALL note provenance and the unresolved license question; redistribution deferred until clarified.

## 5. User Scenarios (key)
- **S-1 Approve via hardware**: Claude prompts a numbered permission menu → OLED shows "WAITING" → user rotates encoder to the desired option and pushes to confirm → app writes ↑/↓ + Enter to the PTY → Claude proceeds → OLED shows "ACTIVE" then "IDLE".
- **S-2 Quick yes/no**: Simple y/n prompt → user taps YES (`BTN:0`) → app sends the correct token → answer reflected; OLED shows last answer = YES.
- **S-3 Stop**: Runaway/unwanted action → user taps STOP (`BTN:2`) → app sends interrupt (Esc) to the PTY.
- **S-4 No hardware**: User clicks the virtual YES/NO/STOP on the SPA → same delivery path.
- **S-5 Device disconnect**: BindDeck unplugged mid-session → host detects loss of liveness → UI/`/api/session` reflects "hardware disconnected"; virtual board still works (graceful degradation).
- **S-6 Claude not running**: No ready Claude PTY → send path disabled; UI indicates Claude unavailable.

## 6. Extension Compliance Scope

### Resiliency (Q9=A — applicable subset only)
This is a single-process localhost developer tool with **no deployment infrastructure and no persistent business data**, so most RESILIENCY rules are **N/A**:
- **N/A**: RESILIENCY-01/02 (workload criticality, RTO/RPO — no production SLA), 03/04 (change mgmt, CI/CD, rollback, deploy style — no pipeline; runs from source locally), 07 (resiliency assessment tooling), 08 (multi-zone/region — single local process), 09 (auto-scaling/quota — none), 11/12/13 (DR strategy, backups, failover — no persistent state), 14 (chaos/DR testing — no infra), 15 (incident response — personal tool). Rationale documented per rule's N/A allowance.
- **Enforced (applicable)**:
  - **RESILIENCY-06 (health/liveness)**: serial handshake/liveness detection, `claude_ready()`, and `/api/session` availability reporting act as health checks for the three moving parts (device, PTY, Claude).
  - **RESILIENCY-10 (timeouts + graceful degradation)**: all serial reads, PTY writes, and transcript-tail reads have explicit timeouts / non-blocking behavior; the app degrades gracefully (virtual board still functions) when the device or Claude session is absent.
  - **RESILIENCY-05 (observability)**: structured logging of press → mapping → delivery and state transitions.
- These are treated as **design-time directional guidance**, not production certification.

### Property-Based Testing (Q10=B — Partial: PBT-02, 03, 07, 08, 09)
- **PBT-02 (round-trip)**: `SerialLineParser` framing ↔ event structure round-trips (parse(format(e)) == e for valid events).
- **PBT-03 (invariant)**: the event→choice mapping is total over the valid event domain and never emits an unmapped/illegal key sequence; YES always maps to the affirmative token, NO to the negative token.
- **PBT-07 (generators)**: domain generators for BindDeck lines (`BTN:0..8`, `ENC:<known verbs>`) and menu-state fixtures, not raw strings.
- **PBT-08 (shrinking/repro)**: PBT runs with shrinking enabled and seed logging in CI/test output.
- **PBT-09 (framework)**: JS uses **fast-check** (with `node --test`); Python uses **Hypothesis** (with `unittest`). Documented in tech-stack decisions; added as dev deps.
- Other PBT rules (01, 04, 05, 06, 10) are advisory (non-blocking) in partial mode.

### Security (Q8=B — skipped as blocking rules)
- Not enforced as AI-DLC blocking constraints. However, two concrete good-practice items from the request are still implemented: (a) remove hardcoded Wi-Fi credentials in the firmware fork; (b) validate/whitelist inbound serial lines before mapping.

## 7. Out of Scope (this iteration)
- BLE HID keyboard macros, Wi-Fi UDP transport, hardware-monitor/battery idle screens (dropped from the fork).
- `ALWAYS`/approve-all button (documented future option).
- Redistribution/packaging of the firmware fork (blocked on BindDeck license clarification).
- Production deployment, multi-user, cloud, or DR concerns.

## 8. Key Requirements Summary
Retarget the YES/NO bridge from Codex to **Claude Code**, driven by a **slimmed BindDeck ESP32 fork** over **USB Web Serial**: two buttons for YES/NO, one for STOP, and a **rotary encoder to navigate Claude's numbered permission menus** (rotate = move, push = confirm). Claude **state** comes from **hooks with a `.jsonl` fallback**, surfaced back to the user on the **OLED**. All Codex coupling (queue subprocess, sqlite/jsonl-event parsing, lock-file discovery) is removed. Robustness (timeouts, graceful degradation, idempotent presses, liveness), plus partial property-based testing of the pure mapping/parsing layer, are enforced; heavier cloud/DR/security gates are out of scope for this localhost PoC.
