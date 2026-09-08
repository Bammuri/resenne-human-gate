# resenne_uno_r4 — 제출 기준 펌웨어 (Arduino UNO R4 WiFi)

Re:senne HUMAN GATE의 **제출·검증 하드웨어** 펌웨어입니다. 물리 버튼으로 실행 중인
Claude Code 세션의 승인 프롬프트에 답합니다.

- **버튼:** ✓ **APPROVE** = D2, ✕ **REJECT** = D3 (INPUT_PULLUP, 눌림=LOW, 30ms 디바운스 에지)
  - 30ms 디바운스는 실기기에서 21회 연속 1누름=1건 클린 검증(2026-09-08).
- **OLED:** 128×64 SSD1306 (I2C, SDA=A4 / SCL=A5) — "지금 누구 차례인지"를 큰 영문으로 표시.
  - `respondsAt()` I2C ACK 프로브(0x3C→0x3D) + 2-인자 `begin` — 팀 버튼 테스트 스케치로 실기기 확인.
- **내장 12×8 LED 매트릭스:** 상태 보조 표시.
- **전송:** WiFiS3 + WebSocketsClient(Links2004), `ws://` 평문. 상태 down / `user_action` up.

## 배선

| 부품 | 핀 |
|---|---|
| ✓ APPROVE 버튼 | D2 ↔ GND |
| ✕ REJECT 버튼 | D3 ↔ GND |
| OLED SDA | A4 |
| OLED SCL | A5 |
| OLED GND | GND |

> ⚠️ UNO R4의 A4/A5에는 보드 **5V 풀업**이 있습니다. **5V I2C를 견디는 OLED 모듈**을 쓰거나
> 레벨 변환하세요(VCC만 3.3V로 연결한다고 3.3V 전용 모듈이 보호되지 않습니다).

## 라이브러리

- 코어 번들: `WiFiS3`, `Arduino_LED_Matrix`, `Wire` (UNO R4 renesas_uno 코어)
- Library Manager: **WebSockets** (Links2004)
- **Adafruit SSD1306** + **Adafruit GFX** + **Adafruit BusIO** (수동 설치 시 BusIO 의존성 누락 주의)

## 업로드 전 (로컬에서만)

스케치 상단 placeholder를 로컬에서만 채웁니다 — **저장소에는 자격증명을 커밋하지 않습니다.**

```cpp
#define WIFI_SSID   "YOUR_2G4_SSID"   // UNO R4는 2.4GHz만
#define WIFI_PASS   ""                // 개방망이면 빈 문자열
#define BRIDGE_HOST "192.168.137.1"   // AP/호스트 LAN IP (netsh portproxy → WSL Node Bridge)
#define AUTO_APPROVE_MS 0             // 반드시 0 — 사람이 눌러야만 진행
```

## OLED 상태 표기

| 상태 | 큰 문구 | 작은 문구 |
|---|---|---|
| IDLE | `READY` | `Re:senne` |
| RUNNING | `AI'S TURN` | `BUILDING...` |
| **REVIEW_REQUIRED** | **`YOUR TURN`** | `PRESS TO APPROVE` / `OR PRESS X REJECT` |
| SUCCESS | `DONE` | `CHECK PASSED` |
| ERROR | `ERROR` | `CHECK SCREEN` / `ACTION NEEDED` |
| DISCONNECTED | `OFFLINE` | `CHECK LINK` |

## 검증 상태

- **실기기 확인:** 버튼 → WiFi → WebSocket → Node Bridge 왕복(2026-09-07~08), OLED + D3 REJECT 통합.
- **남은 통합:** Node Bridge ↔ 기존 Python PTY 승인(`server.py`)을 잇는 얇은 어댑터
  (`HACKATHON_EXECUTION_PLAN.md` §2). `request_id` 에코는 그 어댑터에서 처리.
- 펌웨어는 이 환경에서 컴파일하지 않았습니다(WSL에 `arduino-cli` 없음). 플래시·온디바이스 확인은 팀이 수행.
