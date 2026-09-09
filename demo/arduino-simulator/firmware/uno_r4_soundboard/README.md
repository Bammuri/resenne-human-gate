# UNO R4 WiFi 사운드보드

`uno_r4_soundboard.ino`를 Arduino IDE에서 엽니다. 보드는 **Arduino UNO R4 WiFi**를 선택합니다.
기존 `firmware/yes_no`의 AI 제어 펌웨어와는 별도 스케치입니다. 이 스케치는 음원 재생용이며
시뮬레이터의 AI 버튼 신호 프로토콜(`/events`, `BUTTON_LAB_*`)을 구현하지 않습니다.
Wi-Fi 조작은 보드 IP에서 제공하는 전용 웹 리모컨으로 합니다.

## 준비와 업로드

1. 보드 매니저의 Arduino UNO R4 Boards를 설치합니다.
2. 라이브러리: Adafruit SSD1306, Adafruit GFX Library, Adafruit BusIO, Adafruit NeoPixel.
   WiFiS3와 Wire는 UNO R4 보드 패키지에 포함됩니다. DFPlayer 별도 라이브러리는 필요 없습니다.
3. DFPlayer 자체 USB로 `/sound1.mp3`~`/sound4.mp3`를 내부 저장장치 최상위에 복사합니다.
   안전하게 제거하고 DFPlayer USB를 분리한 다음 회로를 켭니다.
4. UNO의 USB-C를 PC에 연결하고 해당 포트를 선택해 업로드합니다.
5. 시리얼 모니터를 115200 baud로 열고 `?`를 전송합니다. `[DFPlayer] OK` 및
   `communication OK`를 확인합니다. 명령은 줄바꿈 없음/CR/LF/CRLF 모두 사용할 수 있습니다.

OLED는 **SSD1306 128×64 I2C** 기준입니다. 0x3C/0x3D를 탐색합니다.
SH1106 등 다른 컨트롤러나 다른 해상도라면 라이브러리와 표시 코드를 변경해야 합니다.
OLED에는 기본 글꼴이 지원하는 영문 음원명과 IP를, 웹에는 한국어 음원명을 표시합니다.

## Wi-Fi: API 토큰 없이 IP로 조작

### 기본: 공유기 없이 직접 연결

1. 휴대폰 또는 PC의 Wi-Fi 목록에서 **UNO-R4-Sound**를 선택합니다.
2. 기본 설정에서는 Wi-Fi 비밀번호도 없습니다. ‘인터넷 없음’이 나와도 연결을 유지합니다.
3. 브라우저에서 **http://192.168.4.1/** 을 엽니다. HTTPS가 아닙니다.
4. 웹의 8개 버튼이 실물 버튼과 같은 기능을 수행합니다. 상태는 1초마다 갱신됩니다.

### 공유기 Wi-Fi에 연결

`config.h`의 `WIFI_SSID`와 `WIFI_PASSWORD`에 2.4GHz Wi-Fi 정보를 적고 다시 업로드합니다.
PC/휴대폰을 같은 네트워크에 연결한 뒤 OLED 또는 시리얼에 나온 **실제 IP**로 접속합니다.
공유기 연결 실패·연결 끊김 시 직접 연결용 AP로 전환합니다. AP는 동시에 운영하지 않습니다.

AP 비밀번호가 필요하면 `AP_PASSWORD`를 8자 이상으로 설정할 수 있습니다.
이는 Wi-Fi 접속 비밀번호이며 보드 제어 API 토큰은 없습니다. 같은 네트워크 사용자가
조작할 수 있으므로 신뢰하는 로컬 네트워크에서 사용하고 인터넷 포트 포워딩은 하지 마세요.

### HTTP API

| 요청 | 기능 |
|---|---|
| `GET /` | 한국어 웹 리모컨 |
| `GET /status` | 선택 음원·볼륨·앰프 확인 상태·최근 응답·오류 JSON |
| `POST /command` | 본문에 시리얼 명령 한 글자 (`1`~`4`, `p`, `s`, `n`, `b`, `0`, `?`) |

```sh
curl http://192.168.4.1/status
curl -H 'Content-Type: text/plain' --data-binary '1' http://192.168.4.1/command
curl -H 'Content-Type: text/plain' --data-binary 's' http://192.168.4.1/command
```

`202 Accepted`는 UNO가 명령을 접수했다는 뜻입니다. DFPlayer가 실제로 처리했는지는
`/status`의 `busy`, `error`, `reply`, `ampKnown`, `ampOn`으로 확인합니다.
`ampOn`은 앰프 상태이지 파일 재생 중/재생 완료 상태가 아닙니다.

## 배선과 조작

| 부품 | 연결 |
|---|---|
| DFPlayer TX / RX | UNO D0/RX / D1/TX (`Serial1`, 115200) |
| DFPlayer VIN / GND | 외부 +5V / 공통 GND |
| 스피커 | DFPlayer L+ / L− 사이 (L−는 GND가 아님) |
| 버튼 1~8 | D2~D9 / 공통 GND, `INPUT_PULLUP`, 30ms 디바운싱 |
| OLED SDA / SCL | A4 / A5 (기본 `Wire`) |
| 가변저항 와이퍼 / 양 끝 | A0 / UNO 5V와 GND |
| LED IN | D10 → 330~470Ω 저항 → IN |
| LED VCC / GND | 외부 +5V / 공통 GND (OUT 미연결) |

| 버튼 | 핀 | USB/API 명령 | 기능 |
|---|---|---|---|
| 1 | D2 | `1` | 오이쉬 `/sound1.mp3` |
| 2 | D3 | `2` | 거제야호 `/sound2.mp3` |
| 3 | D4 | `3` | 러브어택 `/sound3.mp3` |
| 4 | D5 | `4` | 데자뷰 `/sound4.mp3` |
| 5 | D6 | `p` | 선택 음원 처음부터 재생 |
| 6 | D7 | `s` | 앰프 OFF: 디코더는 정지시키지 않음 |
| 7 | D8 | `n` | 다음 음원 선택 후 처음부터 재생 (4→1) |
| 8 | D9 | `b` | 이전 음원 선택 후 처음부터 재생 (1→4) |
| — | — | `0` | 출력 정지 / 선택 음원 처음부터 재생 전환 |
| — | — | `?` | `AT` 통신 검사, `OK` 확인 |

A0는 `analogReadResolution(10)`과 `1023 - analogRead(A0)`를 사용합니다.
초기 필터값도 같은 방향으로 반전합니다. 10ms 샘플링, 평활 필터와 히스테리시스를 사용하며
물리 노브가 볼륨 0~30의 기준입니다. 웹에는 볼륨을 표시하며 별도 볼륨 슬라이더는 없습니다.

재생 순서: 앰프 OFF → 단일 재생 모드 → 지정 파일 → 재생 위치 0초 → 볼륨 → 앰프 ON.
각 명령의 `OK`를 확인하며 실패하면 남은 재생 순서를 취소하고 무음 처리를 시도합니다.
통신이 끊긴 상태에서는 앰프가 실제로 꺼졌다고 보장할 수 없어 `OUTPUT UNKNOWN`으로 표시합니다.
오류가 나면 전원·배선·파일 이름을 확인하고 `?`로 재검사한 뒤 다시 재생하세요.

LED 기본 동작: 앞 4개 중 선택한 음원 위치가 켜집니다. 앰프 ON은 초록, 무음/미확인은 파랑,
통신 오류는 빨강입니다. 뒤 4개는 볼륨 막대입니다. 기본 밝기는 20/255입니다.
`config.h`에서 `ENABLE_STATUS_LEDS=false`로 끄거나 `LED_BRIGHTNESS`를 조절할 수 있습니다.

## 전원·OLED 확인

- 배선 변경은 전원을 끄고 합니다. 모든 부품과 UNO의 GND를 공유합니다.
- 외부 +5V는 DFPlayer와 LED에 공급합니다. USB 전원 사용 중인 UNO 5V 핀에 추가 연결하지 않습니다.
- 스피커는 L+와 L−에만 연결합니다. R+/R−, DACL/DACR, KEY/PLAY는 미연결입니다.
- LED VCC–GND에 1000µF·10V 커패시터를 권장합니다. 극성을 맞추세요.
- LED 외부 전원을 먼저 켠 뒤 UNO를 켭니다. 종료할 때는 UNO를 먼저 끕니다.
- OLED 전원과 신호가 5V 호환인지 확인하세요. 코드 설정으로 전압 호환성이 생기지는 않습니다.
  3.3V 전용이면 레벨 변환 또는 실제 Qwiic 배선이 필요합니다. Qwiic에 연결했을 때만
  `OLED_USE_QWIIC=true`로 설정합니다. OLED가 탐색되지 않아도 버튼·음원·Wi-Fi는 계속 동작합니다.

## 실물 확인 순서

컴파일 성공은 실물 검증을 의미하지 않습니다. 다음을 확인하세요.

1. `?`의 OK 응답, OLED의 IP, 웹 `/status` 응답을 확인합니다.
2. 버튼 1~4와 USB `1`~`4`에서 정확한 파일이 처음부터 재생되는지 확인합니다.
3. 재생 중 버튼 5가 처음부터 다시 시작하고, 버튼 6이 무음 처리하는지 확인합니다.
4. 7번의 4→1, 8번의 1→4 순환과 `0` 토글을 확인합니다.
5. 버튼을 길게 눌렀을 때 1회만 동작하고 떨림으로 중복 실행되지 않는지 확인합니다.
6. 노브 양 끝이 0과 30인지, 원하는 방향인지, 고정했을 때 음량이 떨리지 않는지 확인합니다.
7. 웹 버튼과 실물 버튼을 번갈아 눌러 선택 음원·무음 상태가 맞는지 확인합니다.
8. 파일 누락/DFPlayer 단절 시 오류가 표시되는지, 복구 후 `?`와 재생이 동작하는지 확인합니다.
9. OLED 전압·모델과 LED 순서·색상이 맞는지 확인합니다.

## 참고한 공식 자료

- [DFRobot DFPlayer Pro AT 명령](https://wiki.dfrobot.com/dfr0768/docs/20422): AMP, PLAYFILE, TIME, VOL, PLAYMODE, AT.
- [Arduino UNO R4 WiFi AP 예제](https://github.com/arduino/ArduinoCore-renesas/blob/main/libraries/WiFiS3/examples/AP_SimpleWebServer/AP_SimpleWebServer.ino)
- [Adafruit NeoPixel](https://github.com/adafruit/Adafruit_NeoPixel)
