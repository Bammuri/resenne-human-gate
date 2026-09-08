# Build Instructions — `claude-binddeck-retarget`

There is **no build step for the runtime**. The host is Python 3 stdlib and the
frontend is vanilla JS with vendored libraries (`vendor/`). Only *test-only*
dependencies are installed, and both runtimes stay dependency-free in production.

## Prerequisites

| Component | Requirement | Verify |
|---|---|---|
| Python | 3.10+ (validated on 3.14.4) | `python3 --version` |
| Node.js | 18+ (validated on 24.18.0) — test runner only | `node --version` |
| Claude Code CLI | installed + logged in (runtime, user-provided) | `claude --version` |
| Arduino IDE | ESP32 board package; Adafruit SSD1306 + Adafruit GFX + Bounce2 libs (firmware only) | — |
| Browser | Desktop Chrome (Web Serial) for real BindDeck | — |

## Install test-only dependencies

Runtime is zero-dependency; the following are **dev/test only** and are gitignored.

```bash
# JS property tests (fast-check). package.json / package-lock.json are committed.
npm install

# Python property tests (hypothesis). PEP 668 externally-managed base env → local venv.
python3 -m venv .venv
./.venv/bin/pip install hypothesis
```

## Run the application

```bash
python3 server.py                          # serves http://127.0.0.1:8765
python3 server.py --cwd /path/to/project   # run the Claude session in another folder
python3 server.py --state-file /path/to/binddeck-state.json
```

## Firmware "build" (upload)

Open `firmware/binddeck_claude/binddeck_claude.ino` in Arduino IDE, select the
ESP32 board + port, and Upload. The sketch has no BLE/Wi-Fi and no credentials.
It is **not compiled in CI** (no embedded toolchain here); correctness is by
inspection + the host-side serial-protocol tests, pending a hardware smoke test.
