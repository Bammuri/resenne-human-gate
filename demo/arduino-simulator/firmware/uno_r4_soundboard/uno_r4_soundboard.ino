/* UNO R4 WiFi 전용 사운드보드
 * D0/RX <- DFPlayer TX, D1/TX -> DFPlayer RX (Serial1 115200)
 * D2~D9: 버튼 1~8 -> GND (INPUT_PULLUP, 30ms debounce)
 * A0: 10k potentiometer, ADC 10-bit, 반전 볼륨 0~30
 * A4/A5: SSD1306 OLED, D10: WS2812B x8
 * PC USB Serial: 115200, 1 2 3 4 p s n b 0 ? (줄바꿈 없어도 동작)
 * Wi-Fi: 보드 IP의 / 에 웹 리모컨, GET /status, POST /command
 * API 토큰 없음. 기존 Button Lab AI 제어 프로토콜과는 별도 펌웨어입니다.
 */
#include <WiFiS3.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>
#include "config.h"
#include "web_page.h"

struct ButtonState { uint8_t pin; bool reading; bool stable; uint32_t changedAt; };
ButtonState buttons[8];
const char BUTTON_COMMANDS[] = "1234psnb";
const char* TRACK_NAMES[] = {"OISHI", "GEOJE YAHO", "LOVE ATTACK", "DEJA VU"};
TwoWire& oledWire = OLED_USE_QWIIC ? Wire1 : Wire;
Adafruit_SSD1306 oled(128, 64, &oledWire, -1);
Adafruit_NeoPixel leds(8, 10, NEO_GRB + NEO_KHZ800);
WiFiServer server(80);
WiFiClient client;

uint8_t selectedTrack = 1;
int filteredADC = 0, knobVolume = 0, sentVolume = -1;
bool wantedMute = true, ampOn = false, ampKnown = false, oledReady = false;
bool networkReady = false, apMode = false, audioInitialized = false;
bool awaitingReply = false, replyOverflow = false;
String ipAddress = "USB ONLY", lastReply, audioError, incomingReply, pendingCommand;
String commandQueue[8];
uint8_t queueSize = 0;
uint32_t sentAt = 0, completedAt = 0, knobAt = 0, displayAt = 0, networkAt = 0;
String httpRequest;
uint32_t clientAt = 0;

void queueCommand(const String& command) {
  if (queueSize < 8) commandQueue[queueSize++] = command;
}

// 새 조작은 아직 전송하지 않은 재생 순서를 교체합니다. 전송 중인 명령은 응답을 기다립니다.
void stopOutput() {
  wantedMute = true;
  queueSize = 0;
  queueCommand("AT+AMP=OFF");
}

void playSelected() {
  wantedMute = false;
  audioError = "";
  queueSize = 0;
  // 파일 전환 중에는 무음 처리하고, 파일 처음으로 이동한 뒤 출력을 켭니다.
  queueCommand("AT+AMP=OFF");
  queueCommand("AT+PLAYMODE=3");
  queueCommand("AT+PLAYFILE=/sound" + String(selectedTrack) + ".mp3");
  queueCommand("AT+TIME=0");
  queueCommand("AT+VOL=" + String(knobVolume));
  queueCommand("AT+AMP=ON");
}

bool commandAllowed(char command) {
  return command != '\0' && strchr("1234psnb0?", command) != nullptr;
}

void dispatchCommand(char command) {
  if (!commandAllowed(command)) return;
  Serial.print("[COMMAND] "); Serial.println(command);
  if (command >= '1' && command <= '4') { selectedTrack = command - '0'; playSelected(); }
  else if (command == 'p') playSelected();
  else if (command == 's') stopOutput();
  else if (command == 'n') { selectedTrack = selectedTrack % 4 + 1; playSelected(); }
  else if (command == 'b') { selectedTrack = (selectedTrack + 2) % 4 + 1; playSelected(); }
  else if (command == '0') { if (wantedMute) playSelected(); else stopOutput(); }
  else if (command == '?') queueCommand("AT");
}

void readButtons() {
  uint32_t now = millis();
  for (uint8_t i = 0; i < 8; ++i) {
    bool value = digitalRead(buttons[i].pin);
    if (value != buttons[i].reading) { buttons[i].reading = value; buttons[i].changedAt = now; }
    if (now - buttons[i].changedAt >= 30 && value != buttons[i].stable) {
      buttons[i].stable = value;
      if (value == LOW) dispatchCommand(BUTTON_COMMANDS[i]);
    }
  }
}

void readVolumeKnob() {
  if (millis() - knobAt < 10) return;
  knobAt = millis();
  int raw = 1023 - analogRead(A0);
  filteredADC = (filteredADC * 3 + raw + 2) / 4;
  // 필터와 히스테리시스로 경계 부근에서 볼륨이 반복해서 바뀌는 것을 억제합니다.
  int candidate = constrain((filteredADC * 30 + 511) / 1023, 0, 30);
  int center = knobVolume * 1023 / 30;
  if (candidate != knobVolume && (abs(filteredADC - center) >= 23 || filteredADC <= 5 || filteredADC >= 1018))
    knobVolume = candidate;
}

void finishAudioCommand(bool ok, const String& reason) {
  awaitingReply = false;
  completedAt = millis();
  if (ok) {
    if (pendingCommand == "AT+AMP=ON" || pendingCommand == "AT+AMP=OFF") {
      ampOn = pendingCommand.endsWith("ON"); ampKnown = true;
    }
    if (pendingCommand.startsWith("AT+VOL=")) sentVolume = pendingCommand.substring(7).toInt();
    if (pendingCommand == "AT") { audioError = ""; Serial.println("[DFPlayer] communication OK"); }
  } else {
    audioError = reason + ": " + pendingCommand;
    Serial.println("[DFPlayer ERROR] " + audioError);
    queueSize = 0; wantedMute = true; ampKnown = false;
    // 실패하면 뒤에 남은 AMP=ON을 취소하고 무음 처리를 한 번 시도합니다.
    if (pendingCommand != "AT+AMP=OFF") queueCommand("AT+AMP=OFF");
  }
}

void serviceAudio() {
  for (uint8_t n = 0; n < 96 && Serial1.available(); ++n) {
    char c = Serial1.read();
    if (c == '\n' || c == '\r') {
      if (!replyOverflow && incomingReply.length()) {
        incomingReply.trim(); lastReply = incomingReply;
        Serial.println("[DFPlayer] " + incomingReply);
        if (awaitingReply && incomingReply == "OK") finishAudioCommand(true, "");
        else if (awaitingReply && (incomingReply.startsWith("ERROR") || incomingReply.startsWith("ERR")))
          finishAudioCommand(false, incomingReply);
      }
      incomingReply = ""; replyOverflow = false;
    } else if (incomingReply.length() < 160) incomingReply += c;
    else replyOverflow = true;
  }
  if (awaitingReply && millis() - sentAt >= 1500) finishAudioCommand(false, "No OK response");
  if (!audioInitialized) {
    if (millis() < 2000) return;
    audioInitialized = true;
    // 이미 대기 중인 사용자 조작이 있으면 해당 순서를 유지합니다.
    if (!queueSize) { queueCommand("AT"); queueCommand("AT+AMP=OFF"); queueCommand("AT+PROMPT=OFF"); queueCommand("AT+PLAYMODE=3"); }
  }
  if (awaitingReply || millis() - completedAt < 120) return;
  // No retries for a changing knob while the module is unresponsive.
  if (!queueSize && sentVolume != knobVolume && !audioError.length()) queueCommand("AT+VOL=" + String(knobVolume));
  if (!queueSize) return;
  pendingCommand = commandQueue[0];
  for (uint8_t i = 1; i < queueSize; ++i) commandQueue[i - 1] = commandQueue[i];
  --queueSize;
  Serial1.print(pendingCommand); Serial1.print("\r\n");
  Serial.println("[AT] " + pendingCommand);
  awaitingReply = true; sentAt = millis();
}

void serviceUsb() {
  for (uint8_t n = 0; n < 32 && Serial.available(); ++n) {
    char c = Serial.read();
    if (commandAllowed(c)) dispatchCommand(c);
    else if (c != '\r' && c != '\n' && c != ' ') Serial.println("Use: 1 2 3 4 p s n b 0 ?");
  }
}

void drawIndicators() {
  if (millis() - displayAt < 200) return;
  displayAt = millis();
  if (oledReady) {
    oled.clearDisplay(); oled.setTextColor(SSD1306_WHITE); oled.setTextWrap(false);
    oled.setTextSize(1); oled.setCursor(0, 0); oled.print("SOUND "); oled.print(selectedTrack);
    oled.setCursor(0, 12); oled.print(TRACK_NAMES[selectedTrack - 1]);
    oled.setCursor(0, 25); oled.print(audioError.length() ? "DFPLAYER ERROR" : !ampKnown ? "OUTPUT UNKNOWN" : ampOn ? "OUTPUT ON" : "MUTED");
    oled.setCursor(0, 37); oled.print("VOL "); oled.print(knobVolume); oled.print("/30");
    oled.setCursor(0, 48); oled.print(networkReady ? (apMode ? "AP: UNO-R4-Sound" : "ROUTER WI-FI") : "WI-FI UNAVAILABLE");
    oled.setCursor(0, 56); oled.print(ipAddress); oled.display();
  }
  if (ENABLE_STATUS_LEDS) {
    leds.clear();
    leds.setPixelColor(selectedTrack - 1, audioError.length() ? leds.Color(255, 0, 0) : ampKnown && ampOn ? leds.Color(0, 170, 70) : leds.Color(0, 40, 180));
    uint8_t bars = (knobVolume * 4 + 29) / 30;
    for (uint8_t i = 0; i < bars; ++i) leds.setPixelColor(i + 4, leds.Color(100, 80, 0));
    leds.show();
  }
}

String jsonString(const String& value) {
  String out = "\"";
  for (unsigned int i = 0; i < value.length(); ++i) {
    char c = value[i];
    if (c == '"' || c == '\\') { out += '\\'; out += c; }
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else if ((uint8_t)c >= 32) out += c;
  }
  return out + '"';
}

String statusJson() {
  return "{\"track\":" + String(selectedTrack) + ",\"volume\":" + String(knobVolume) +
    ",\"ampOn\":" + (ampOn ? "true" : "false") + ",\"ampKnown\":" + (ampKnown ? "true" : "false") +
    ",\"busy\":" + (awaitingReply || queueSize ? "true" : "false") +
    ",\"mode\":" + jsonString(apMode ? "AP" : "Wi-Fi") + ",\"ip\":" + jsonString(ipAddress) +
    ",\"reply\":" + jsonString(lastReply) + ",\"error\":" + jsonString(audioError) + "}";
}

void respond(int code, const String& body, const char* type = "application/json") {
  client.print("HTTP/1.1 "); client.print(code);
  client.println(code == 200 ? " OK" : code == 202 ? " Accepted" : " Error");
  client.print("Content-Type: "); client.println(type);
  client.print("Content-Length: "); client.println(body.length());
  client.println("Cache-Control: no-store\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\n");
  client.print(body); client.stop(); httpRequest = "";
}

void handleRequest() {
  int split = httpRequest.indexOf("\r\n\r\n");
  if (split < 0) return;
  int firstEnd = httpRequest.indexOf("\r\n");
  String first = httpRequest.substring(0, firstEnd);
  if (first == "GET / HTTP/1.1" || first == "GET / HTTP/1.0") { respond(200, WEB_PAGE, "text/html; charset=utf-8"); return; }
  if (first == "GET /status HTTP/1.1" || first == "GET /status HTTP/1.0") { respond(200, statusJson()); return; }
  if (first != "POST /command HTTP/1.1" && first != "POST /command HTTP/1.0") { respond(404, "{\"error\":\"Not found\"}"); return; }
  String headers = httpRequest.substring(firstEnd, split); headers.toLowerCase();
  int start = headers.indexOf("\r\ncontent-length:");
  if (start < 0 || headers.indexOf("transfer-encoding:") >= 0) { respond(400, "{\"error\":\"Use Content-Length: 1\"}"); return; }
  start += 17;
  int end = headers.indexOf("\r\n", start);
  String length = headers.substring(start, end < 0 ? headers.length() : end); length.trim();
  if (length != "1") { respond(400, "{\"error\":\"Send one character\"}"); return; }
  if (httpRequest.length() < (unsigned int)(split + 5)) return;
  char command = httpRequest[split + 4];
  if (!commandAllowed(command)) { respond(400, "{\"error\":\"Invalid command\"}"); return; }
  dispatchCommand(command);
  respond(202, "{\"accepted\":true}"); // DFPlayer ACK is reported separately in /status.
}

void startAccessPoint() {
  apMode = true;
  WiFi.config(IPAddress(192, 168, 4, 1));
  int result = AP_PASSWORD[0] ? WiFi.beginAP(AP_SSID, AP_PASSWORD) : WiFi.beginAP(AP_SSID);
  networkReady = result == WL_AP_LISTENING || result == WL_AP_CONNECTED;
}

void startNetwork() {
  WiFi.setTimeout(5000);
  if (WiFi.status() == WL_NO_MODULE) { Serial.println("[WiFi] Module unavailable; USB/buttons still work."); return; }
  if (WIFI_SSID[0]) {
    int result = WIFI_PASSWORD[0] ? WiFi.begin(WIFI_SSID, WIFI_PASSWORD) : WiFi.begin(WIFI_SSID);
    networkReady = result == WL_CONNECTED;
  }
  if (!networkReady) { WiFi.disconnect(); startAccessPoint(); }
  if (networkReady) {
    ipAddress = WiFi.localIP().toString(); server.begin();
    Serial.println("[WiFi] " + String(apMode ? AP_SSID : WIFI_SSID) + " -> http://" + ipAddress);
  } else Serial.println("[WiFi] Start failed; USB/buttons still work.");
}

void serviceNetwork() {
  if (!networkReady) return;
  if (millis() - networkAt >= 5000) {
    networkAt = millis();
    if (!apMode && WiFi.status() != WL_CONNECTED) {
      client.stop(); WiFi.disconnect(); startAccessPoint();
      ipAddress = networkReady ? WiFi.localIP().toString() : "USB ONLY";
      if (networkReady) { server.begin(); Serial.println("[WiFi] Fallback AP: http://" + ipAddress); }
    }
  }
  if (!client) {
    client = server.available();
    if (!client) return;
    httpRequest = ""; clientAt = millis();
  }
  for (uint8_t n = 0; n < 128 && client.available(); ++n) {
    httpRequest += (char)client.read();
    if (httpRequest.length() > 1536) { respond(413, "{\"error\":\"Request too large\"}"); return; }
  }
  if (millis() - clientAt > 2000) { client.stop(); httpRequest = ""; return; }
  handleRequest();
}

void setup() {
  Serial.begin(115200); Serial1.begin(115200);
  analogReadResolution(10);
  filteredADC = 1023 - analogRead(A0);
  knobVolume = constrain((filteredADC * 30 + 511) / 1023, 0, 30);
  for (uint8_t i = 0; i < 8; ++i) {
    pinMode(i + 2, INPUT_PULLUP);
    bool reading = digitalRead(i + 2);
    buttons[i] = {uint8_t(i + 2), reading, reading, millis()};
  }
  // LED 기능을 끄면 데이터 신호를 보내지 않습니다. 전원 순서는 README를 참고하세요.
  if (ENABLE_STATUS_LEDS) { leds.begin(); leds.setBrightness(LED_BRIGHTNESS); leds.clear(); leds.show(); }
  oledWire.begin();
  for (uint8_t address = 0x3C; address <= 0x3D && !oledReady; ++address) {
    oledWire.beginTransmission(address);
    if (oledWire.endTransmission() == 0) oledReady = oled.begin(SSD1306_SWITCHCAPVCC, address);
  }
  incomingReply.reserve(161); httpRequest.reserve(1537);
  startNetwork();
  Serial.println("UNO R4 Soundboard. Serial 115200. Commands: 1 2 3 4 p s n b 0 ?");
  Serial.println("OLED: " + String(oledReady ? "OK" : "not detected (check model, voltage and I2C)"));
}

void loop() {
  readButtons(); readVolumeKnob(); serviceUsb(); serviceAudio(); serviceNetwork(); drawIndicators();
}
