# Interaction Diagrams

How each business transaction is realized across components.

## BT-1: Answer the agent (YES/NO)

```mermaid
sequenceDiagram
    participant U as Developer
    participant B as Board (firmware)
    participant Ser as serial.js
    participant UI as app.js
    participant S as server.py
    participant WT as terminal.py
    participant CX as Codex CLI / Agent PTY

    alt Hardware source
        U->>B: press physical button
        B->>Ser: "yes\n" / "no\n" (115200, debounced)
        Ser->>UI: onChoice(choice)
    else Web source
        U->>UI: click YES/NO or press Y/N
    end
    UI->>UI: canSend() && !busy && debounce(250ms)
    UI->>S: POST /api/press {choice, target, requestId}
    S->>S: host/token/Origin guards, send_lock, idempotency, rate limit
    alt target=terminal AND claude_ready()
        S->>WT: send_choice(choice)
        WT->>CX: write "choice\n" to PTY
        S-->>UI: 200 {status:"sent"}
    else Codex thread
        S->>WT: target_thread() (discover)
        S->>CX: codex queue --thread <id> --message choice
        S-->>UI: 200 {status:"queued"}
    end
    UI->>U: animate board + serial-monitor log + status
```

## BT-2: Run an agent/shell session in the browser

```mermaid
sequenceDiagram
    participant U as Developer
    participant BT as web-terminal.js
    participant S as server.py
    participant WT as terminal.py
    participant PC as pty_child.py
    participant P as shell/codex/claude

    U->>BT: click "Shell/Codex/Codex-YOLO 시작"
    BT->>S: POST /api/terminal/start {kind, cols, rows}
    S->>WT: start(kind)
    WT->>PC: spawn (stdin/out/err = PTY slave)
    PC->>P: setsid + TIOCSCTTY + execv
    WT-->>BT: snapshot {generation, ...}
    loop poll ~180ms
        BT->>S: GET /api/terminal?after&generation
        S->>WT: snapshot()
        WT-->>BT: {data(base64), running, thread, ...}
        BT->>BT: xterm.write(bytes)
    end
    U->>BT: type keys
    BT->>S: POST /api/terminal/input {data, generation}
    S->>WT: write(data, generation) -> PTY
```

## BT-3 + BT-4: Attach to session and observe activity

```mermaid
sequenceDiagram
    participant BT as web-terminal.js
    participant S as server.py
    participant WT as terminal.py
    participant OR as output.py
    participant FS as ~/.codex (sqlite + jsonl + locks)

    BT->>S: GET /api/terminal (each poll)
    S->>WT: snapshot() -> detect_thread()
    WT->>WT: process_tree() -> /proc/<pid>/fd or lsof
    WT->>FS: match thread-writer-locks/<uuid>.lock
    WT->>WT: thread discovered -> new OutputReader(thread)
    BT->>S: GET /api/output?target=terminal (checkButtonReady)
    S->>OR: snapshot()
    OR->>FS: locate() via state_5.sqlite / sessions glob
    OR->>FS: tail jsonl, parse event_msg
    OR-->>BT: {available, status(active/idle/waiting), events[]}
    BT->>BT: enable buttons once available
```

## BT-5: Pair a physical board (Web Serial handshake)

```mermaid
sequenceDiagram
    participant U as Developer
    participant Ser as serial.js
    participant B as Board (yes_no.ino)

    U->>Ser: click "USB 보드 연결"
    Ser->>B: open port 115200; write "BUTTON_LAB_HELLO\n" (every 700ms)
    B->>Ser: "BUTTON_LAB_READY:1\n"
    Ser->>Ser: state = connected (clear handshake timeout)
    loop while connected
        U->>B: press button
        B->>Ser: "yes\n" / "no\n"
        Ser->>Ser: onChoice -> BT-1 (web press with source=hardware)
    end
```
