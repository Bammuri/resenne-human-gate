# External Hardware Reference — BindDeck (SanX18/BindDeck)

> Added at the RE review gate after the user chose **BindDeck as the hardware surface** ("HW는 BindDeck 이거쓸꺼야 분석해서 다시 만들어보자"). This documents the *external* project so the retarget can integrate/rebuild against it. Source analyzed: shallow clone of `https://github.com/SanX18/BindDeck` (firmware `src/main.cpp` @ 866 lines, `platformio.ini`, `README.md`, `pc_script/`, dev patch scripts).

## What BindDeck Is
An open-source **ESP32 macro pad** ("smart macro pad") with a PC companion app (Windows). It is *not* a YES/NO answer device out of the box — it is a Stream-Deck-style productivity controller. Hardware:
- **MCU**: ESP32-WROOM-32 Dev Kit (`platformio.ini`: `board = esp32dev`, Arduino framework, `monitor_speed = 115200`, `huge_app` partitions).
- **Display**: 0.96" SSD1306 OLED, 128×64, I2C addr `0x3C` (SDA=GPIO21, SCL=GPIO22).
- **Rotary encoder**: KY-040 — CLK=GPIO18, DT=GPIO19, SW(push)=GPIO5.
- **8 mechanical switches** — firmware `SWITCH_PINS[8] = {13, 12, 14, 27, 32, 33, 25, 26}` (indices 0..7). ⚠️ README's "Switch 5–8" pin list (26,25,33,32) differs from the firmware array order for 5–8; **firmware is source of truth**.
- **Menu button**: GPIO4 (local only — cycles idle screens; not sent to PC).
- **Battery**: LiPo + TP4056; ADC on GPIO35 (voltage divider).
- **Libraries** (`lib_deps`): `ESP32 BLE Keyboard`, `Adafruit SSD1306`, `Adafruit GFX`, `Bounce2`.

## Connectivity (three simultaneous channels)
1. **USB serial** — 115200 baud, newline-framed text. Primary for a wired host.
2. **BLE HID keyboard** (name "BindDeck") — buttons also emit HID function keys (F13–F21, F23, F24) directly to the OS.
3. **Wi-Fi UDP** — listens on port **4210**, sends telemetry/events to the PC on port **4211** (broadcast until it learns the PC IP). Wi-Fi creds are **hardcoded in `main.cpp`** (see Risks).

`sendDataToPC(msg)` writes `msg` to **both** Serial (`Serial.println`) **and** UDP — so the same event stream is available over USB or Wi-Fi.

## Serial / UDP Protocol

### Device → PC (events)
| Message | Meaning |
|---|---|
| `BTN:0` … `BTN:7` | Mechanical switch 0–7 pressed |
| `BTN:8` | Encoder push-button pressed |
| `ENC:VUP` / `ENC:VDN` | Encoder rotate (mode 0: volume up/down) |
| `ENC:ZIN` / `ENC:ZOUT` | Encoder rotate (mode 1: zoom) |
| `ENC:TFWD` / `ENC:TBCK` | Encoder rotate (mode 2: browser tabs) |
| `ENC:REDO` / `ENC:UNDO` | Encoder rotate (mode 3: undo/redo) |
| `ENC:APPVUP` / `ENC:APPVDN` | Encoder rotate (mode 5: app volume) |
| `WIFI_INFO:<ssid>,<ip>` | Reply to `CMD:GET_WIFI` |

(Buttons also fire BLE keys `MACRO_KEYS = {F13..F20}` for switches, `F21` for encoder button, `F23/F24` for app-volume — independent of the serial line.)

### PC → Device (commands, newline-terminated)
| Command | Effect |
|---|---|
| `CFG:ANIM:<n>` | Global press animation mode |
| `CFG:ENC:<n>` | Encoder mode (0 vol,1 zoom,2 tabs,3 undo/redo,5 app-vol) |
| `CFG:BRIGHT:<n>` | OLED contrast/brightness (0–255) |
| `CFG:KB_ANIM:<csv>` | Per-key animation overrides (8 CSV values) |
| `CFG:TXT:<idx>:<text>` | Set per-button OLED label (idx 0–7) |
| `CFG:WIFI:<ssid>\|<pwd>` | Set + persist Wi-Fi creds, reconnect |
| `CMD:GET_WIFI` | Ask for `WIFI_INFO:` reply |
| `CMD:PREVIEW:<n>` | Preview animation n |
| `CMD:SIMULATE:<n>` | Simulate button n press animation |
| `CMD:MSG:<text>` | Show a custom message screen (~1.5 s, "AUDIO" + text) |
| `CMD:UPDATE` | Show "Updating… do not disconnect" spinner |
| `C:<cpu_t>,U:<cpu_u>,G:<gpu_t>,V:<gpu_u>` | Telemetry → drives the idle OLED "PC STATS" screen (parsed by `sscanf("C:%d,U:%d,G:%d,V:%d")`) |

**No handshake** equivalent to Button Lab's `BUTTON_LAB_HELLO`/`READY:1`. Liveness can be confirmed by sending `CMD:GET_WIFI` and awaiting `WIFI_INFO:`, or by simply observing any `BTN:`/`ENC:` line. Idle screen shows "NO SIGNAL" if no `C:`/command received for 3 s.

## Mapping BindDeck → Button Lab (Claude YES/NO)
BindDeck gives us far more input surface than the UNO R4 two-button design:
- **YES / NO**: map two switches, e.g. `BTN:0` → `yes`, `BTN:1` → `no`.
- **Extra actions available** (optional, matches AgentDeck-style surfaces): `BTN:2` → ALWAYS/approve-all, `BTN:3` → STOP/interrupt (Esc), remaining switches → custom messages.
- **Encoder**: scroll through Claude's *numbered* permission-menu options (`ENC:*` rotate) and **encoder push (`BTN:8`) = confirm selection** — this directly addresses the open "numbered permission menu vs. literal yes\n" problem flagged in `code-quality-assessment.md`.
- **OLED feedback (reverse channel)**: repurpose `CMD:MSG:<text>` and/or the telemetry line to display **Claude session state** (waiting / active / idle) and the last answer, instead of CPU/GPU stats.

## How This Differs From the Current Firmware
| Aspect | Current `firmware/yes_no.ino` (UNO R4) | BindDeck (ESP32) |
|---|---|---|
| Board | UNO R4 WiFi (Renesas RA4M1) | ESP32-WROOM-32 |
| Inputs | 2 buttons (D2/D3) | 8 switches + encoder + push + menu |
| Host transport | USB serial only | USB serial + BLE HID + Wi-Fi UDP |
| Handshake | `BUTTON_LAB_HELLO`→`READY:1` | none (use `CMD:GET_WIFI`→`WIFI_INFO:`) |
| Wire format | `yes\n` / `no\n` | `BTN:<i>` / `ENC:<...>` |
| Display | none | SSD1306 OLED (feedback channel) |

Both are **line-based USB serial**, so Button Lab's browser Web Serial layer (`serial.js`, `SerialLineParser`) is structurally reusable — only the framing/handshake logic changes.

## Risks / Cleanup Needed for a Rebuild
- **Hardcoded Wi-Fi SSID/password in `main.cpp`** (lines 12–13) — must be stripped/redacted before reuse.
- **No LICENSE file** in the repo tree (README shows sponsor badges and calls it "open-source," but there is no explicit license). ⚠️ Confirm license before redistributing a fork.
- **Repo hygiene**: the repo ships prebuilt Windows binaries (LibreHardwareMonitor, many DLLs, `BindDeck.exe`, `firmware.bin`) and ~40 ad-hoc `fix_*.py` / `patch_*.py` dev scripts — **not** something to vendor wholesale. For our purposes we only need the **firmware sketch** and the **serial protocol**.
- **Feature mismatch**: most firmware (BLE keyboard macros, Wi-Fi telemetry, hardware-monitor idle screen, battery gauge) is irrelevant to the agent-answer use case. A "다시 만들어보자" rebuild should **fork a slimmed sketch** focused on: button→choice events, encoder→menu navigation, OLED→agent-state — dropping or making optional the Windows-companion features.

## Integration Recommendation (consistent with prior gpt-astra consultation)
- **Host side**: keep Web Serial in the browser; adapt `serial.js` to BindDeck framing (`BTN:`/`ENC:`) and map events → `yes`/`no`(+ optional ALWAYS/STOP). Optionally push Claude state to the OLED via `CMD:MSG:`. The Python send path to Claude (app-owned PTY) is unchanged.
- **Firmware side**: fork a minimal BindDeck sketch — strip hardcoded Wi-Fi + BLE + telemetry (or gate them), add an OLED "agent state" screen, keep the `BTN:`/`ENC:` event protocol (optionally add a Button-Lab handshake for robust detection).
- **AgentDeck** remains **reference-only**; BindDeck replaces the UNO R4 as the physical surface.
