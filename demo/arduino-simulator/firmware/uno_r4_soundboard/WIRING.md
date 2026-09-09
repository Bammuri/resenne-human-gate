# UNO R4 WiFi · 부품 연결도

> **버전 안내(두 버전 모두 보존).** 이 문서는 팀 하드웨어·펌웨어 담당자의 **부품 연결도**로,
> **통합 작업본** 기준입니다 — 현재 통합 코드는 OLED·MP3·버튼·A0를 제어하며 **D10 LED 통합은 진행 중**입니다.
> 반면 저장소에 커밋된 [`uno_r4_soundboard.ino`](./uno_r4_soundboard.ino)·[`README.md`](./README.md)는
> 이미 **D10 WS2812B LED를 구동**합니다(상태 색상·볼륨 막대, `ENABLE_STATUS_LEDS=true`). 두 버전을 모두 남깁니다.
> 이 문서는 연결 요약이며 **실물 검증 완료를 뜻하지 않습니다.**

구성: OLED + DFPlayer Pro + 4Ω 3W 스피커 + 버튼 8개 + 10kΩ 가변저항 + WS2812B LED 8개.

## 1. 핀 연결표

| 부품 | 부품 단자 | 연결 대상 |
|---|---|---|
| DFPlayer Pro | TX | UNO D0 / RX |
| DFPlayer Pro | RX | UNO D1 / TX |
| DFPlayer Pro | VIN | 외부 5V 전원 + |
| DFPlayer Pro | GND | 공통 GND |
| 스피커 | + / − | DFPlayer L+ / L− |
| 버튼 1~8 | 한쪽 접점 | 순서대로 UNO D2~D9 |
| 버튼 1~8 | 나머지 접점 | 공통 GND |
| OLED | SDA | UNO A4 / SDA |
| OLED | SCK 또는 SCL | UNO A5 / SCL |
| OLED | GND | 공통 GND |
| OLED | VDD | 모듈 허용 전압에 맞는 전원 ※ 아래 참고 |
| 10kΩ 가변저항 | 가운데 단자(와이퍼) | UNO A0 |
| 10kΩ 가변저항 | 바깥쪽 두 단자 | UNO 5V / GND 각각 |
| WS2812B-8 LED | IN | UNO D10 → 330~470Ω 저항 → IN |
| WS2812B-8 LED | VCC / GND | 외부 5V 전원 + / 공통 GND |
| WS2812B-8 LED | OUT | 연결하지 않음 |
| UNO | USB-C | PC: 전원·업로드·시리얼 명령 |

## 2. 전원 연결

```text
PC USB ─────────── UNO R4 WiFi

외부 +5V ──┬────── DFPlayer VIN
           └────── LED VCC

외부 GND ──┬────── UNO GND
           ├────── DFPlayer GND
           └────── LED GND
```

- 배선 변경은 전원을 끄고 작업합니다. 버튼·OLED·가변저항도 UNO와 GND를 공유합니다.
- 외부 +5V를 USB로 공급 중인 UNO 5V 핀에 추가 연결하지 않습니다.
- **스피커 L−는 GND가 아닙니다.** 스피커는 L+와 L− 사이에만 연결합니다.
- DFPlayer의 R+/R−, DACL/DACR, KEY/PLAY는 연결하지 않습니다.
- LED 입력의 VCC–GND 사이에 1000µF·10V 전해 커패시터 권장: +는 VCC, −는 GND.
- LED 외부 전원을 먼저 켜고 UNO를 켭니다. 끌 때는 UNO를 먼저 끕니다.
- **OLED는 사진만으로 전원·신호의 5V 호환이 확인되지 않았습니다.** 5V 호환 모듈일 때 위 일반 I2C 헤더에 직접 연결합니다. 3.3V 전용이면 신호 레벨 변환 또는 3.3V Qwiic(`Wire1`) 연결이 필요합니다.

## 3. 버튼 기능과 음원

모든 버튼은 `INPUT_PULLUP`, 30ms 디바운싱 사용. 외부 풀업·풀다운 저항은 필요 없습니다. 누르면 LOW입니다.

| 버튼 | UNO 핀 | 현재 기능 / 파일 |
|---|---|---|
| 1 | D2 | 오이쉬 · `/sound1.mp3` |
| 2 | D3 | 거제야호 · `/sound2.mp3` |
| 3 | D4 | 러브어택 · `/sound3.mp3` |
| 4 | D5 | 데자뷰 · `/sound4.mp3` |
| 5 | D6 | 선택한 음원 처음부터 재생 |
| 6 | D7 | 출력 정지: 앰프 OFF |
| 7 | D8 | 다음 음원: sound1~4 순환 |
| 8 | D9 | 이전 음원: sound1~4 순환 |

출력 정지는 내부 디코딩 정지가 아닌 무음 처리입니다. 다음 재생은 파일 처음부터 시작합니다.

## 4. A0 볼륨 노브

현재 배선은 유지하고 코드에서 방향을 반전합니다. ADC는 `analogReadResolution(10)`으로 설정하며 볼륨은 0~30입니다.

```cpp
// readVolumeKnob() 안
int raw = 1023 - analogRead(A0);

// setup() 안
filteredADC = 1023 - analogRead(A0);
```

## 5. PC 시리얼

PC USB는 `Serial`, DFPlayer D0·D1은 `Serial1`이며 모두 115200 baud입니다.

| 입력 | 기능 |
|---|---|
| `1`~`4` | 해당 음원 재생 |
| `p` | 선택 음원 처음부터 재생 |
| `s` | 출력 정지 |
| `n` / `b` | 다음 / 이전 음원 |
| `0` | 출력 정지 / 처음부터 재생 전환 |
| `?` | DFPlayer 통신 확인: OK 응답 확인 |

음원은 DFPlayer 자체 USB로 내부 저장장치 최상위에 복사합니다. 복사 후 안전하게 제거하고 DFPlayer USB를 분리한 뒤 회로 전원을 켭니다.

**현재 최신 통합 코드는 OLED·MP3·버튼·A0를 제어하며, D10 LED 제어는 아직 포함하지 않습니다.** 이 문서는 연결 요약이며 실제 하드웨어 검증 완료를 뜻하지 않습니다.
