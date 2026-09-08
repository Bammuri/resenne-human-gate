/*
 * Re:senne HUMAN GATE — Arduino UNO R4 WiFi 펌웨어 (APPROVE + REJECT + OLED)
 *
 * 검증된 연결 테스트 스케치(resenne_conn_test.ino, 2026-09-07 실기기 E2E 통과)를 기반으로:
 *   - 물리 버튼 2개: D2 = ✓ APPROVE, D3 = ✕ REJECT (INPUT_PULLUP, 눌림=LOW, 30ms 디바운스)
 *     · 30ms 디바운스는 실기기에서 21회 연속 1누름=1건 클린 검증(2026-09-08) — 더블파이어 없음.
 *   - 128x64 SSD1306 OLED(I2C) 상태 표시 — "지금 누구 차례인지"
 *     · I2C 프로브(respondsAt) + 2-인자 begin은 팀 버튼 테스트 스케치로 실기기 확인(2026-09-08).
 *   - 내장 12x8 LED 매트릭스 보조 표시 유지
 *   - 자동 APPROVE OFF (사람이 눌러야만 진행 — 컨셉 핵심). AUTO_APPROVE_MS는 하드웨어 없는 테스트 전용.
 *
 * 라이브러리(Arduino IDE 설치):
 *   - WiFiS3, Arduino_LED_Matrix, Wire  → renesas_uno 코어 번들
 *   - WebSockets (Links2004)            → Library Manager "WebSockets"
 *   - Adafruit SSD1306 + Adafruit GFX + Adafruit BusIO  → 수동 설치 시 BusIO 의존성 누락 주의
 *
 * 배선: 버튼 D2/D3 ↔ GND (외부저항 불필요).
 *       OLED: SDA=A4, SCL=A5 (UNO R4 하드웨어 I2C). GND 공통.
 *       ⚠️ UNO R4의 A4/A5에는 보드 5V 풀업이 있음 → 5V I2C를 견디는 OLED 모듈을 쓰거나 레벨 변환.
 *          (VCC만 3.3V로 연결한다고 3.3V 전용 모듈이 보호되지 않음.)
 *
 * 공개 저장소 정책: WiFi 자격증명/브리지 주소는 placeholder. 실제 값은 로컬에서만 채운다(커밋 금지).
 *   실측 네트워크 경로(참고): 게스트망 client isolation 회피용 Windows 모바일 핫스팟(2.4GHz),
 *   보드 → AP(예: 192.168.137.1) → netsh portproxy → WSL Node Bridge(ws://…:8080).
 */
#include "WiFiS3.h"
#include <WebSocketsClient.h>
#include "Arduino_LED_Matrix.h"
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ===== 사용자 설정 (로컬에서만 채우기, 커밋 금지) =====
#define WIFI_SSID   "YOUR_2G4_SSID"    // UNO R4는 2.4GHz만 지원
#define WIFI_PASS   ""                 // 개방망이면 빈 문자열
#define BRIDGE_HOST "192.168.137.1"    // AP/호스트 LAN IP (netsh portproxy → WSL Node Bridge)
#define BRIDGE_PORT 8080
#define BRIDGE_PATH "/"
#define BTN_APPROVE 2                  // ✓ D2 ↔ GND
#define BTN_REJECT  3                  // ✕ D3 ↔ GND
#define AUTO_APPROVE_MS 0              // 0 = 자동승인 끔(반드시 0으로 제출). >0이면 REVIEW 후 자동 APPROVE(테스트 전용)
// ======================================================

// ----- OLED -----
#define OLED_W 128
#define OLED_H 64
Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);
bool oledOK = false;

// ----- LED matrix + WebSocket -----
WebSocketsClient webSocket;
ArduinoLEDMatrix matrix;
const uint32_t FRAME_OFF[]     = { 0x00000000, 0x00000000, 0x00000000 };
const uint32_t FRAME_RUNNING[] = { 0xAAAAAAAA, 0x55555555, 0xAAAAAAAA }; // 체커(작동중)
const uint32_t FRAME_REVIEW[]  = { 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF }; // 전체점등(승인필요)
const uint32_t FRAME_SUCCESS[] = { 0x00000000, 0x0FFFFFF0, 0x00000000 }; // 중앙밴드(성공)
const uint32_t FRAME_ERROR[]   = { 0x81420024, 0x00240042, 0x81000000 }; // 흩뿌림(에러)

bool wsConnected = false;
char currentState[20] = "DISCONNECTED";
char lastRendered[20] = "";
unsigned long lastBeat = 0;
unsigned long autoApproveAt = 0;
const unsigned long DEBOUNCE_MS = 30;   // 실기기 검증값(2026-09-08). 튜닝 불필요.

struct Button {
  uint8_t pin;
  const char* action;   // "APPROVE" / "REJECT"
  int reading;
  int stable;
  unsigned long changedAt;
};
Button buttons[] = {
  { BTN_APPROVE, "APPROVE", HIGH, HIGH, 0 },  // 배열 순서 = 우선순위(동시 누름 시 APPROVE 우선)
  { BTN_REJECT,  "REJECT",  HIGH, HIGH, 0 },
};

// I2C 주소 ACK 프로브(팀 검증 버튼 테스트 스케치 respondsAt()와 동일 패턴, 2026-09-08 실기기 확인).
bool respondsAt(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

// 큰 글자 1줄 + 작은 글자 2줄 + 하단 연결표시. 상태 변경 시에만 호출(루프 부담↓).
void renderOLED(const char* big, const char* small1, const char* small2) {
  if (!oledOK) return;
  oled.clearDisplay();
  oled.setTextWrap(false);        // 128px 폭 초과 시 줄바꿈 대신 잘라 표시(레이아웃 안정)
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(2);            // 12x16 px/char — 큰 문구는 ≤9자로 유지
  oled.setCursor(0, 4);
  oled.println(big);
  oled.setTextSize(1);            // 6x8 px/char
  if (small1 && small1[0]) { oled.setCursor(0, 30); oled.println(small1); }
  if (small2 && small2[0]) { oled.setCursor(0, 42); oled.println(small2); }
  oled.setCursor(0, 56);
  oled.print(wsConnected ? "LINK: up" : "LINK: down");
  oled.display();
}

void applyState(const char* s) {
  strncpy(currentState, s, sizeof(currentState) - 1);
  currentState[sizeof(currentState) - 1] = '\0';
  if (!strcmp(currentState, lastRendered)) return;   // 변경 시에만 갱신
  strncpy(lastRendered, currentState, sizeof(lastRendered) - 1);
  lastRendered[sizeof(lastRendered) - 1] = '\0';

  if (!strcmp(s, "REVIEW_REQUIRED")) {
    matrix.loadFrame(FRAME_REVIEW);
    renderOLED("YOUR TURN", "PRESS TO APPROVE", "OR PRESS X REJECT");
  } else if (!strcmp(s, "RUNNING")) {
    matrix.loadFrame(FRAME_RUNNING);
    renderOLED("AI'S TURN", "BUILDING...", "");
  } else if (!strcmp(s, "SUCCESS")) {
    matrix.loadFrame(FRAME_SUCCESS);
    renderOLED("DONE", "CHECK PASSED", "");
  } else if (!strcmp(s, "ERROR")) {
    matrix.loadFrame(FRAME_ERROR);
    renderOLED("ERROR", "CHECK SCREEN", "ACTION NEEDED");
  } else if (!strcmp(s, "IDLE")) {
    matrix.loadFrame(FRAME_OFF);
    renderOLED("READY", "Re:senne", "");
  } else { // DISCONNECTED / 기타
    matrix.loadFrame(FRAME_OFF);
    renderOLED("OFFLINE", "CHECK LINK", "");
  }
  Serial.print("[state] "); Serial.println(currentState);
}

void onWsEvent(WStype_t type, uint8_t* payload, size_t len) {
  switch (type) {
    case WStype_CONNECTED:
      wsConnected = true;
      Serial.println("[ws] CONNECTED");
      webSocket.sendTXT("{\"type\":\"hello\",\"client\":\"uno-r4\"}");
      applyState("IDLE");
      break;
    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("[ws] DISCONNECTED");
      applyState("DISCONNECTED");
      break;
    case WStype_TEXT: {
      if (payload == nullptr || len == 0) break;   // 빈 프레임 → strstr(nullptr) UB 방지
      Serial.print("[ws] RX: "); Serial.write(payload, len); Serial.println();
      const char* p = (const char*)payload;
      // 경량 문자열 매칭(테스트용). 다른 필드에 상태명이 섞이면 오인식 가능 →
      // 실제 펌웨어는 ArduinoJson으로 "state" 필드만 파싱 권장.
      if      (strstr(p, "REVIEW_REQUIRED")) { applyState("REVIEW_REQUIRED"); if (AUTO_APPROVE_MS) autoApproveAt = millis() + AUTO_APPROVE_MS; }
      else if (strstr(p, "SUCCESS"))         { applyState("SUCCESS");         autoApproveAt = 0; }
      else if (strstr(p, "RUNNING"))         { applyState("RUNNING");         autoApproveAt = 0; }
      else if (strstr(p, "ERROR"))           { applyState("ERROR");           autoApproveAt = 0; }
      else if (strstr(p, "IDLE"))            { applyState("IDLE");            autoApproveAt = 0; }
      break;
    }
    default: break;
  }
}

// 승인/거절 전송. 대기 요청이 있을 때(REVIEW_REQUIRED)만 보낸다.
// 대상 판정(대기 요청·request_id 최초 1회 채택)은 서버/Node Bridge가 진실의 기준.
// TODO(통합): 서버가 request_id를 방송하면 여기서 그대로 echo해 오도착 입력을 서버가 걸러내도록 한다(계획서 §2).
void sendAction(const char* action) {
  if (!wsConnected || strcmp(currentState, "REVIEW_REQUIRED") != 0) return;
  char buf[56];
  snprintf(buf, sizeof(buf), "{\"type\":\"user_action\",\"action\":\"%s\"}", action);
  const bool sent = webSocket.sendTXT(buf);
  Serial.print("[btn] "); Serial.print(action);
  Serial.println(sent ? " -> TX OK" : " -> TX FAILED");   // TX OK도 서버 승인 접수 ACK는 아님
}

void setup() {
  Serial.begin(115200);
  // while(!Serial){} 넣지 않음 — 전원만 연결해도 동작해야 함.
  for (Button& b : buttons) {
    pinMode(b.pin, INPUT_PULLUP);
    b.reading = b.stable = digitalRead(b.pin);   // 부팅 시 눌린 버튼은 떼야 전송
  }

  matrix.begin();
  matrix.loadFrame(FRAME_OFF);

  // OLED: I2C ACK 프로브로 실제 응답 확인(begin()만으로는 미연결도 true일 수 있음). 0x3C 우선, 0x3D 대비.
  Wire.begin();
  uint8_t oledAddr = respondsAt(0x3C) ? 0x3C : (respondsAt(0x3D) ? 0x3D : 0);
  oledOK = oledAddr != 0 && oled.begin(SSD1306_SWITCHCAPVCC, oledAddr);  // 2-인자 폼: 팀 검증(2026-09-08)
  Serial.println(oledOK ? "[oled] ACK + begin OK" : "[oled] unavailable; matrix only");
  applyState("DISCONNECTED");

  Serial.print("\n[wifi] connecting to "); Serial.println(WIFI_SSID);
  if (strlen(WIFI_PASS) == 0) WiFi.begin(WIFI_SSID);
  else                        WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) { delay(300); Serial.print("."); }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) { Serial.print("[wifi] connected, IP="); Serial.println(WiFi.localIP()); }
  else                               { Serial.println("[wifi] FAILED — 2.4GHz SSID/PASS 확인"); }

  webSocket.begin(BRIDGE_HOST, BRIDGE_PORT, BRIDGE_PATH); // 평문 ws://
  webSocket.onEvent(onWsEvent);
  webSocket.setReconnectInterval(2000);
  Serial.print("[ws] target ws://"); Serial.print(BRIDGE_HOST);
  Serial.print(":"); Serial.print(BRIDGE_PORT); Serial.println(BRIDGE_PATH);
}

void loop() {
  webSocket.loop();  // 매 루프 필수(논블로킹). loop()에 긴 delay 금지.

  const unsigned long now = millis();
  for (Button& b : buttons) {
    const int reading = digitalRead(b.pin);
    if (reading != b.reading) { b.reading = reading; b.changedAt = now; }
    if (now - b.changedAt >= DEBOUNCE_MS && reading != b.stable) {
      b.stable = reading;
      if (reading == LOW) { sendAction(b.action); break; }   // 눌림 에지 1회, 한 틱에 하나만
    }
  }

  if (autoApproveAt && now >= autoApproveAt && wsConnected) {
    autoApproveAt = 0;
    Serial.println("[auto] APPROVE -> sendTXT (test-only)");
    sendAction("APPROVE");
  }

  if (now - lastBeat > 5000) {
    lastBeat = now;
    Serial.print("[hb] wifi="); Serial.print(WiFi.status() == WL_CONNECTED ? "up" : "down");
    Serial.print(" ws="); Serial.print(wsConnected ? "up" : "down");
    Serial.print(" oled="); Serial.print(oledOK ? "ok" : "off");
    Serial.print(" state="); Serial.println(currentState);
  }
}
