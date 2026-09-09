# 시뮬레이터 연동용 UNO R4 WiFi

`simulator_r4.ino`, `board_config.h`, `wifi_credentials.h`, `oled_text_frame.h`,
`oled_transport.h`가 한 폴더에 있어야 합니다.
보드 AP 이름은 `DM`이며 접속 비밀번호는 로컬 `wifi_credentials.h`에서 관리합니다.
웹 다운로드에는 실제 비밀번호가 없는 `board_config.example.h`만 제공합니다.
이 스케치는 `arduino-simulator`의 실물 탭용입니다. 앞서 만든 `uno_r4_soundboard`와 다릅니다.
음원 이름/파일을 버튼에 고정하지 않으며 모드와 버튼의 의미는 시뮬레이터가 결정합니다.

## 기능

- D2~D9: INPUT_PULLUP, 30ms 디바운싱. 버튼 1~8 이벤트를 전송합니다.
- 8번 MODE: AI 제어 → AI-DLC → 커스텀. 모드 상태는 PC에서 관리합니다.
- 모드 1: MODEL / PLAN / BUILD / CHECK / ACCEPT / DENIED / STOP.
- 모드 2: 1~5 단계 입력 / 6 중간 질문(메모리 전용, MD 저장 없음) / 7 RUN NOW.
- 모드 3: 시뮬레이터의 커스텀 매핑.
- A0: 10kΩ 가변저항, 10비트 ADC. AI 수준·자율성·스크롤 등 현재 문맥의 기능입니다.
  음량 전용 노브가 아니며 3핀 가변저항에는 누름 스위치가 없습니다.
  AI 수준·자율성은 웹에서 현재 ADC 위치를 기준으로 조절합니다. 시계방향은 증가,
  반시계방향은 감소입니다. 유효 범위 192–832를 단계별 균등 구간으로 나누며 양 끝은 포화됩니다.
  모델의 기준 경계는 352 / 512 / 672이며, 미디움 구간은 160 ADC 폭입니다.
  경계 여유 16 ADC, 안정 확인 120ms, 단계 유지 최소 400ms로 흔들림·연속 변경을 억제합니다.
  USB 연결 완료 시 현재 ADC도 전송하며, 모드 3의 음량은 기존처럼 보드에서 직접 조절합니다.
- OLED: SSD1306 128×64, A4/A5 Wire, 0x3C/0x3D 탐색. 모드·단계·수준·상태를 표시합니다.
  전원을 켜면 제품명 `Re:senne`와 `STARTING...`을 표시하며, 연결 대기 중에도 제품명을 유지합니다.
  대기 화면은 기본 6×8 글꼴, 최대 20자×4줄, 가장자리 4픽셀 여백을 사용합니다.
  작업 중에는 전체 화면에 2배 크기 `RUNNING`, 250ms 간격으로 이동하는 블록과 경과 시간(분:초)을 표시합니다.
  모든 모드에서 실행 화면이 우선하며, 질문 대기에는 답변 안내로, 완료·중단 시에는 기존 화면으로 전환합니다.
  데이터는 16바이트씩 전송하고 각 전송의 I2C 응답을 확인합니다.
  실패 시 2초 간격으로 재초기화하며, 정상일 때도 5초마다 화면 설정과 내용을 복원합니다.
- D10 WS2812B 8개: 낮은 밝기(20/255), 키 입력 흰색, 모드/진행 상태 표시.
- DFPlayer Pro: Serial1 115200, 웹 연결 설정의 음원 제어 명령을 전달합니다.
  6번·7번 버튼을 음원 정지/다음 곡에 연결하지 않습니다.
- USB Serial 115200과 Wi-Fi HTTP 모두 Button Lab protocol 3을 지원합니다.

## 배선

| 부품 | UNO 또는 전원 |
|---|---|
| DFPlayer TX / RX | D0/RX / D1/TX |
| DFPlayer VIN / GND | 외부 +5V / 공통 GND |
| 스피커 | DFPlayer L+와 L− 사이 (L−는 GND 아님) |
| 버튼 1~8 | D2~D9 / 공통 GND |
| OLED SDA / SCL | A4 / A5 |
| 가변저항 와이퍼 / 양 끝 | A0 / UNO 5V와 GND |
| WS2812B IN | D10 → 330~470Ω → IN |
| WS2812B VCC / GND | 외부 +5V / 공통 GND |

OLED 전원·신호의 5V 호환 여부는 실제 모듈 사양을 확인해야 합니다. 3.3V 전용이면
레벨 변환 또는 Qwiic 배선을 사용하며, Qwiic으로 옮겼을 때만 `OLED_USE_QWIIC=true`로 설정합니다.
외부 +5V를 USB 전원 사용 중인 UNO 5V 핀에 추가 연결하지 않습니다.
LED 외부 전원을 먼저 켜고 UNO를 켜며, 끌 때는 UNO부터 끕니다. 배선 변경은 전원을 끄고 합니다.

## 연결

1. Arduino IDE에서 `simulator_r4.ino`를 열고 UNO R4 WiFi와 해당 USB 포트를 선택해 업로드합니다.
2. 시리얼 모니터를 닫고 시뮬레이터의 **실물 → USB 연결**에서 보드를 선택합니다.
3. Wi-Fi는 PC를 **DM** AP에 설정한 비밀번호로 연결한 뒤 **실물 → Wi-Fi → 연결 설정**에서
   `192.168.4.1`을 입력합니다. Wi-Fi 접속 비밀번호와 별개로 보드 API 토큰은 없습니다.
4. 공유기를 쓰려면 AP에 연결한 상태로 `http://192.168.4.1/`을 열어 공유기 SSID/비밀번호를 저장합니다.
   이후 PC도 같은 공유기에 연결하고 OLED에 표시되는 새 IP를 입력합니다. 실패 시 AP로 돌아옵니다.
5. 같은 네트워크에서 접근한 사용자가 제어할 수 있으므로 신뢰하는 네트워크에서 사용합니다.

## 확인 명령 (USB, 줄바꿈 LF)

```text
BUTTON_LAB_HELLO
wifi:info
oled:info
oled:refresh
audio:status
```

준비 응답은 `BUTTON_LAB_READY:3:slots=8:knob=analog`입니다.
음원 통신 확인 응답은 `BUTTON_LAB_AUDIO:OK`입니다.
`oled:info`는 주소·전송 오류·완료 프레임·실패 횟수를 반환합니다.
`bus=전>후`는 복구 전후 SDA/SCL 상태입니다(3=둘 다 HIGH, 1=SDA LOW, 2=SCL LOW, 0=둘 다 LOW).
초기화 실패 시 SDA가 LOW에 걸렸다면 최대 9개의 클록과 STOP으로 버스 복구를 시도합니다.
출력을 HIGH로 강제하지 않고 LOW/입력 해제로만 동작합니다.
`oled:refresh`는 모드나 음원을 바꾸지 않고 화면만 다시 전송합니다.
`/status`의 `oled`는 마지막 전체 프레임 전송 성공 여부이며, `oledFrames`,
`oledFailures`, `oledError`, `oledFrameAgeMs`로 갱신을 확인할 수 있습니다.
I2C 응답 성공이 실제 패널의 발광·육안 표시까지 검증하는 것은 아닙니다.
실물 버튼은 `BUTTON_LAB_KEY:1`~`:8`, 웹에서 보드로 보낸 키는 `BUTTON_LAB_SIMULATED_KEY:n`으로 응답합니다.
Wi-Fi `/status`, `/events?after=N`, `/command`는 토큰 없이 시뮬레이터의 로컬 서버를 통해 사용합니다.
보드만 켜 두면 AI 작업이 실행되는 것은 아니며, 시뮬레이터 서버와 웹 화면이 연결되어 있어야 합니다.
