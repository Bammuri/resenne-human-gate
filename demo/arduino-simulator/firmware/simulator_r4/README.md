# 시뮬레이터 연동용 UNO R4 WiFi

`simulator_r4.ino`, `board_config.h`, `wifi_credentials.h`가 한 폴더에 있어야 합니다.
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
  AI 수준·자율성은 작은 회전마다 한 단계씩 상대적으로 조절합니다. 시계방향은 증가,
  반시계방향은 감소입니다. 웹에서 ADC 변화량 48을 한 단계 기준으로 사용하며 작은 떨림은 무시합니다.
- OLED: SSD1306 128×64, A4/A5 Wire, 0x3C/0x3D 탐색. 모드·단계·수준·상태를 표시합니다.
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
audio:status
```

준비 응답은 `BUTTON_LAB_READY:3:slots=8:knob=analog`입니다.
음원 통신 확인 응답은 `BUTTON_LAB_AUDIO:OK`입니다.
실물 버튼은 `BUTTON_LAB_KEY:1`~`:8`, 웹에서 보드로 보낸 키는 `BUTTON_LAB_SIMULATED_KEY:n`으로 응답합니다.
Wi-Fi `/status`, `/events?after=N`, `/command`는 토큰 없이 시뮬레이터의 로컬 서버를 통해 사용합니다.
보드만 켜 두면 AI 작업이 실행되는 것은 아니며, 시뮬레이터 서버와 웹 화면이 연결되어 있어야 합니다.
