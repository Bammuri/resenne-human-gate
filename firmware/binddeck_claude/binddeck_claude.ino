// binddeck_claude.ino — Button Lab firmware for a slimmed BindDeck (ESP32) that
// drives a Claude Code permission prompt over USB serial.
//
// Provenance: forked from SanX18/BindDeck (https://github.com/SanX18/BindDeck).
// Upstream has NO LICENSE file; redistribution is deferred until clarified (NFR-6).
//
// This fork deliberately DROPS: BLE HID keyboard macros, Wi-Fi/UDP transport,
// hardware-monitor telemetry (C:/U:/G:/V:), the battery gauge and idle stat
// screens — and carries NO hardcoded credentials (FR-6.2, NFR-3). It keeps only
// what the agent-answer bridge needs: 8 switches + a rotary encoder over USB
// serial, an OLED "Claude state" screen, and a Button-Lab handshake.
//
// Wire protocol (115200 baud, newline-delimited):
//   Device -> PC : BTN:0..7 (switch), BTN:8 (encoder push),
//                  ENC:CW / ENC:CCW (encoder rotate),
//                  BUTTON_LAB_READY:1 (reply to the handshake below)
//   PC -> Device : BUTTON_LAB_HELLO   (liveness/handshake request)
//                  CMD:MSG:<text>     (show <text> on the OLED)
//
// Host mapping (serial.js): BTN:0=yes, BTN:1=no, BTN:2=stop, BTN:8=confirm,
//   ENC:CW=nav_down, ENC:CCW=nav_up.  BTN:3..7 are reserved (ignored by host).
//
// Libraries (Arduino/PlatformIO): Adafruit SSD1306, Adafruit GFX, Bounce2.

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Bounce2.h>

// ---- Pins (BindDeck hardware; firmware array is source of truth) ----
static const uint8_t SWITCH_PINS[8] = {13, 12, 14, 27, 32, 33, 25, 26};
static const uint8_t ENC_CLK = 18;
static const uint8_t ENC_DT  = 19;
static const uint8_t ENC_SW  = 5;

// ---- OLED (SSD1306 128x64 @ I2C 0x3C, SDA=21, SCL=22) ----
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
bool haveDisplay = false;

Bounce switches[8];
Bounce encoderButton = Bounce();

int lastClk = HIGH;
String rxLine;
String oledMessage = "waiting for host";

void drawScreen() {
  if (!haveDisplay) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("Claude . BindDeck"));
  display.drawFastHLine(0, 12, OLED_WIDTH, SSD1306_WHITE);
  display.setCursor(0, 20);
  display.setTextSize(2);
  // Show the host-pushed message (Claude state + last answer), wrapping is automatic.
  display.println(oledMessage);
  display.display();
}

void showMessage(const String &text) {
  oledMessage = text.length() ? text : String("--");
  drawScreen();
}

void emit(const String &line) {
  Serial.print(line);
  Serial.print('\n');
}

void handleCommand(const String &line) {
  if (line == "BUTTON_LAB_HELLO") {
    emit("BUTTON_LAB_READY:1");
  } else if (line.startsWith("CMD:MSG:")) {
    showMessage(line.substring(8));
  }
  // All other PC->Device commands from stock BindDeck are intentionally ignored.
}

void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      rxLine.trim();
      if (rxLine.length()) handleCommand(rxLine);
      rxLine = "";
    } else if (c != '\r' && rxLine.length() < 160) {
      rxLine += c;
    }
  }
}

void pollEncoder() {
  int clk = digitalRead(ENC_CLK);
  if (clk != lastClk && clk == LOW) {
    // Falling edge on CLK: DT level selects direction.
    if (digitalRead(ENC_DT) != clk) {
      emit("ENC:CW");
    } else {
      emit("ENC:CCW");
    }
  }
  lastClk = clk;
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < 8; i++) {
    switches[i].attach(SWITCH_PINS[i], INPUT_PULLUP);
    switches[i].interval(15);
  }
  pinMode(ENC_CLK, INPUT_PULLUP);
  pinMode(ENC_DT, INPUT_PULLUP);
  encoderButton.attach(ENC_SW, INPUT_PULLUP);
  encoderButton.interval(15);
  lastClk = digitalRead(ENC_CLK);

  Wire.begin(21, 22);
  haveDisplay = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  drawScreen();
}

void loop() {
  pollSerial();

  for (uint8_t i = 0; i < 8; i++) {
    switches[i].update();
    if (switches[i].fell()) {         // INPUT_PULLUP: press pulls the line LOW
      emit(String("BTN:") + i);
    }
  }

  encoderButton.update();
  if (encoderButton.fell()) {
    emit("BTN:8");                     // encoder push == confirm
  }

  pollEncoder();
}
