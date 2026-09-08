# API Documentation

All endpoints are served by `server.py` on `http://127.0.0.1:<port>` (default 8765). **Common guards**: `Host` must be `127.0.0.1:<port>` or `localhost:<port>` (else 403); every `/api/*` call except `GET /api/session` requires header `X-Simulator-Token: <token>` (else 403); `POST` bodies must be `application/json`, ≤ 50000 bytes, and `Origin` (if present) must equal `http://<Host>`. Responses set `no-store`, `nosniff`, `X-Frame-Options: DENY`, a restrictive CSP, and `Permissions-Policy: serial=(self)`.

## REST APIs

### Get session info
- **Method**: GET
- **Path**: `/api/session`
- **Purpose**: Bootstrap the SPA; returns the token and availability flags.
- **Response**: `{ thread, available, codexAvailable, claudeAvailable, workspace, token }`
  - `available` = `bool(thread and codex)` (the pre-specified "current" target is usable).
  - `codexAvailable`/`claudeAvailable` = whether each CLI was found on `PATH` at startup.

### Poll session output / state
- **Method**: GET
- **Path**: `/api/output?target=<current|terminal>&after=<int>&generation=<str>`
- **Purpose**: Incremental visible events + status for a session.
- **Auth**: token required.
- **Response** (`OutputReader.snapshot`): `{ available, status, generation, reset, cursor, events[] }` where `status ∈ {active, idle, waiting, offline}` and each event is `{id, timestamp, kind, text, ...}` (`kind ∈ {assistant, user, command}`).
- **Note**: `target=terminal` first runs session discovery on the web terminal.

### Poll web-terminal output
- **Method**: GET
- **Path**: `/api/terminal?after=<int>&generation=<str>`
- **Purpose**: Stream bounded PTY bytes for xterm.js.
- **Auth**: token required.
- **Response** (`WebTerminal.snapshot`): `{ running, kind, generation, reset, cursor, data(base64), thread, exitCode }`.

### Send an answer
- **Method**: POST
- **Path**: `/api/press`
- **Purpose**: Deliver a YES/NO answer to the selected agent session.
- **Request**: `{ "choice": "yes"|"no", "target": "current"|"terminal", "requestId": "<1..80 chars>" }`
- **Behavior**:
  - If `target=terminal` **and** a Claude session is live in the web terminal (`claude_ready()`), the answer is written to the agent's PTY → `200 {choice, status:"sent"}`.
  - Otherwise it resolves a Codex thread (`terminal` → discovered thread; `current` → configured `--thread`) and runs `codex queue --thread <id> --message <choice>` → `200 {choice, status:"queued"}`.
  - Idempotent per `(target/thread, requestId)`; duplicate id with a different choice → 409; global 0.5 s min interval → 429; concurrent send in flight → 409.
- **Error responses**: 400 (bad choice/id/target), 503 (no connectable session), 502 (delivery failed), 504 (Codex timeout).

### Web-terminal lifecycle
- **Method**: POST
- **Paths**: `/api/terminal/start`, `/api/terminal/input`, `/api/terminal/resize`, `/api/terminal/stop`
- **Purpose**: Manage the PTY session.
- **Requests**:
  - `start`: `{ kind: "shell"|"codex"|"claude", cols(20..300), rows(5..100) }` → `WebTerminal.snapshot`.
  - `input`: `{ data: "<=8192 chars>", generation }` → `{ok:true}`.
  - `resize`: `{ cols, rows, generation }` → `{ok:true}`.
  - `stop`: `{ generation }` → `{ok:true}`.
- **Errors**: 409 (stale generation / already running / bad size), 502 (PTY failure).

## Internal APIs

### `WebTerminal` (`terminal.py`)
- `start(kind, cols=90, rows=26) -> snapshot` — spawn PTY child (`pty_child.py` → shell/codex/claude).
- `snapshot(after=0, generation="") -> dict` — bounded PTY bytes + running/thread state; also runs `detect_thread()`.
- `write(text, generation)` — forward keystrokes to the PTY (≤ 8192 chars).
- `send_choice(choice)` — write `choice + "\n"` to a **Claude** PTY (answer delivery).
- `claude_ready() -> bool` — `kind=="claude"` and PTY live.
- `detect_thread(force=False)` / `target_thread()` — discover the Codex thread via lock-file scan.
- `resize(cols, rows, generation)` / `stop(generation=None)`.

### `OutputReader` (`output.py`)
- `__init__(thread, codex_home=None)`.
- `locate() -> Path|None` — resolve the session JSONL (sqlite `threads` table, else glob).
- `snapshot(after=0, generation="") -> dict` — incremental events + status.
- (internal) `ingest(record)` / `refresh()` — parse `event_msg` records.

## Data Models

### Answer request (`/api/press` body)
- **Fields**: `choice` (`yes`|`no`), `target` (`current`|`terminal`), `requestId` (string 1..80).
- **Validation**: strict; unknown/oversized → 400.

### OutputReader event
- **Fields**: `id` (monotonic int), `timestamp`, `kind` (`assistant`|`user`|`command`), `text`; commands add `command`, `exitCode`.
- **Source**: Codex `event_msg` → `item_completed` items; ANSI-stripped and length-capped to 20000 chars.

### Terminal snapshot
- **Fields**: `running`, `kind`, `generation`, `reset`, `cursor`, `data` (base64 PTY bytes), `thread`, `exitCode`.
