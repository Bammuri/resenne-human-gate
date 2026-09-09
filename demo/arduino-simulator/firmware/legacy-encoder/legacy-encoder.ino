// Button Lab BindDeck profile for Arduino UNO R3 / UNO R4 WiFi.
// Exactly eight deck buttons: D2--D8 = function slots 1--7; D9 = MODE.
// Optional KY-040: CLK D10, DT D11, SW D12 (reasoning/control knob only).
// Every button connects to GND (INPUT_PULLUP); no separate A0 mode button.
// Serial Monitor: 115200 baud + New Line. Commands: key:1, mode:toggle, knob:left/right/press.
// SSD1306 I2C: SDA/SCL, address below. The host owns mode and question mappings.
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <string.h>
#include <ctype.h>

// Keep protocol/display literals out of the UNO R3's 2 KiB SRAM so the
// SSD1306 can allocate its 1 KiB framebuffer with room left for the stack.
#if defined(__AVR__)
#include <avr/pgmspace.h>
#define FLASH_STORAGE PROGMEM
#define TEXT_EQUALS(value, literal) (strcmp_P((value), PSTR(literal)) == 0)
#define TEXT_STARTS(value, literal) (strncmp_P((value), PSTR(literal), sizeof(literal) - 1) == 0)
#define STORED_EQUALS(value, stored) (strcmp_P((value), (stored)) == 0)
#define COPY_STORED(destination, source, length) memcpy_P((destination), (source), (length))
#else
#define FLASH_STORAGE
#define TEXT_EQUALS(value, literal) (strcmp((value), (literal)) == 0)
#define TEXT_STARTS(value, literal) (strncmp((value), (literal), sizeof(literal) - 1) == 0)
#define STORED_EQUALS(value, stored) (strcmp((value), (stored)) == 0)
#define COPY_STORED(destination, source, length) memcpy((destination), (source), (length))
#endif

Adafruit_SSD1306 display(128, 64, &Wire, -1);
const byte OLED_ADDRESS = 0x3C; // Change to 0x3D if required by your module.
bool oledReady = false;
bool oledDirty = true;
bool workflowProfile = false;
byte autonomyIndex = 1;
byte effortIndex = 1;
char oledStage[15] = "ready";
char oledStatus[10] = "ready";
char oledProfile[9] = "agent";
unsigned long lastDisplayAt = 0;

void renderDisplay() {
  if (!oledReady) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setTextWrap(false);
  display.setCursor(0, 0);
  if (TEXT_EQUALS(oledProfile, "agent")) display.print(F("1 AI CONTROL"));
  else if (workflowProfile) display.print(F("2 AI-DLC"));
  else display.print(F("3 CUSTOM"));
  display.drawFastHLine(0, 11, 128, SSD1306_WHITE);
  display.setCursor(0, 16);
  for (byte i = 0; oledStage[i]; i++) display.write(toupper(oledStage[i]));
  display.setCursor(0, 30);
  const bool question = TEXT_EQUALS(oledStage, "question") || TEXT_EQUALS(oledStatus, "question");
  if (question) display.print(F("PICK 1-7"));
  else if (workflowProfile) {
    display.print(F("CONTROL ")); display.print(autonomyIndex); display.print(' ');
    switch (autonomyIndex) {
      case 0: display.print(F("OBSERVE")); break;
      case 1: display.print(F("STEP")); break;
      case 2: display.print(F("CHECK")); break;
      case 3: display.print(F("FLOW")); break;
    }
  } else if (TEXT_EQUALS(oledStage, "model")) {
    display.print(F("DEPTH "));
    switch (effortIndex) {
      case 0: display.print(F("LOW")); break;
      case 1: display.print(F("MEDIUM")); break;
      case 2: display.print(F("HIGH")); break;
      case 3: display.print(F("XHIGH")); break;
    }
  } else {
    if (TEXT_EQUALS(oledStage, "plan")) display.print(F("KNOB: PLAN PAGE"));
    else if (TEXT_EQUALS(oledStage, "build")) display.print(F("KNOB: HISTORY"));
    else if (TEXT_EQUALS(oledStage, "accept")) display.print(F("KNOB: SELECT"));
    else if (TEXT_EQUALS(oledStage, "denied")) display.print(F("KNOB: CURSOR"));
    else if (TEXT_EQUALS(oledStage, "diff")) display.print(F("KNOB: DIFF PAGE"));
    else if (TEXT_EQUALS(oledStage, "stop")) display.print(F("KNOB: LOG"));
    else display.print(F("KNOB: SCROLL"));
  }
  display.setCursor(0, 44);
  if (question) display.print(F("WAITING ANSWER"));
  else if (TEXT_EQUALS(oledStatus, "approved")) display.print(F("PLAN APPROVED"));
  else if (TEXT_EQUALS(oledStatus, "running")) display.print(F("RUNNING"));
  else if (TEXT_EQUALS(oledStatus, "stopped")) display.print(F("STOPPED"));
  else if (TEXT_EQUALS(oledStatus, "error")) display.print(F("CHECK ERROR"));
  else display.print(workflowProfile ? F("HUMAN GATE") : F("READY"));
  display.setCursor(0, 56);
  display.print(F("8:MODE"));
  display.display();
  oledDirty = false;
}

const unsigned long DEBOUNCE_MS = 35;
const char ACTIONS[][7] FLASH_STORAGE = {"codex", "yolo", "plan", "build", "view", "hide", "accept", "denied"};
const char EFFORTS[][7] FLASH_STORAGE = {"low", "medium", "high", "xhigh"};
const byte ACTION_COUNT = sizeof(ACTIONS) / sizeof(ACTIONS[0]);
const byte EFFORT_COUNT = sizeof(EFFORTS) / sizeof(EFFORTS[0]);
const byte ENCODER_CLK = 10;
const byte ENCODER_DT = 11;
const byte ENCODER_SW = 12;

char hostCommand[48];
byte hostLength = 0;
bool hostOverflow = false;
int lastEncoded = 0;
int encoderAccumulator = 0;

bool allowed(const char* value, const char values[][7], byte count) {
  for (byte index = 0; index < count; index++) {
    if (STORED_EQUALS(value, values[index])) return true;
  }
  return false;
}

void writeValue(const __FlashStringHelper* event, const char* value) {
  Serial.print(event);
  Serial.write(':');
  Serial.print(value);
  Serial.write('\n');
}

void writeEffort(byte index) {
  char effort[7];
  COPY_STORED(effort, EFFORTS[index], sizeof(effort));
  writeValue(F("BUTTON_LAB_EFFORT"), effort);
}

void readHost() {
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\n') {
      hostCommand[hostLength] = '\0';
      if (!hostOverflow && TEXT_EQUALS(hostCommand, "BUTTON_LAB_HELLO")) {
        Serial.print(F("BUTTON_LAB_READY:2:slots=7:mode=8\n"));
        oledDirty = true;
      } else if (!hostOverflow && TEXT_STARTS(hostCommand, "display:")) {
        char* profile = strtok(hostCommand + 8, ":");
        char* stage = strtok(NULL, ":");
        char* level = strtok(NULL, ":");
        char* status = strtok(NULL, ":");
        if (profile && stage && level && status && strlen(stage) < sizeof(oledStage) && strlen(status) < sizeof(oledStatus)
            && strlen(level) == 1 && level[0] >= '0' && level[0] <= '3'
            && (TEXT_EQUALS(profile, "workflow") || TEXT_EQUALS(profile, "agent")
                || TEXT_EQUALS(profile, "custom") || TEXT_EQUALS(profile, "codex"))) {
          workflowProfile = TEXT_EQUALS(profile, "workflow");
          strcpy(oledProfile, profile);
          strcpy(oledStage, stage); strcpy(oledStatus, status);
          if (workflowProfile) autonomyIndex = level[0] - '0';
          else effortIndex = level[0] - '0';
          oledDirty = true;
        }
      } else if (!hostOverflow && TEXT_STARTS(hostCommand, "key:") && strlen(hostCommand) == 5
                 && hostCommand[4] >= '1' && hostCommand[4] <= '7') {
        writeValue(F("BUTTON_LAB_SIMULATED_KEY"), hostCommand + 4);
      } else if (!hostOverflow && TEXT_EQUALS(hostCommand, "mode:toggle")) {
        Serial.print(F("BUTTON_LAB_SIMULATED_MODE:toggle\n"));
      } else if (!hostOverflow && (TEXT_EQUALS(hostCommand, "yes") || TEXT_EQUALS(hostCommand, "no"))) {
        // Backward-compatible screen ACCEPT / DENIED round-trip.
        writeValue(F("BUTTON_LAB_SIMULATED"), hostCommand);
      } else if (!hostOverflow && TEXT_STARTS(hostCommand, "action:")) {
        const char* action = hostCommand + 7;
        if (allowed(action, ACTIONS, ACTION_COUNT)) writeValue(F("BUTTON_LAB_SIMULATED_ACTION"), action);
      } else if (!hostOverflow && TEXT_STARTS(hostCommand, "knob:")) {
        const char* value = hostCommand + 5;
        if (TEXT_EQUALS(value, "left") || TEXT_EQUALS(value, "right") || TEXT_EQUALS(value, "press")) {
          writeValue(F("BUTTON_LAB_SIMULATED_KNOB"), value);
        }
      } else if (!hostOverflow && TEXT_STARTS(hostCommand, "effort:")) {
        const char* effort = hostCommand + 7;
        if (allowed(effort, EFFORTS, EFFORT_COUNT)) {
          for (byte index = 0; index < EFFORT_COUNT; index++) {
            if (STORED_EQUALS(effort, EFFORTS[index])) {
              if (workflowProfile) autonomyIndex = index;
              else effortIndex = index;
            }
          }
          writeValue(F("BUTTON_LAB_SIMULATED_EFFORT"), effort);
          oledDirty = true;
        }
      }
      hostLength = 0;
      hostOverflow = false;
    } else if (c != '\r' && !hostOverflow) {
      if (hostLength < sizeof(hostCommand) - 1) hostCommand[hostLength++] = c;
      else hostOverflow = true;
    }
  }
}

struct Button {
  byte pin;
  byte slot; // 1--7 = function key, 8 = mode, 0 = optional knob push.
  int reading;
  int stable;
  unsigned long changedAt;
};

Button buttons[] = {
  {2, 1, HIGH, HIGH, 0}, {3, 2, HIGH, HIGH, 0},
  {4, 3, HIGH, HIGH, 0}, {5, 4, HIGH, HIGH, 0},
  {6, 5, HIGH, HIGH, 0}, {7, 6, HIGH, HIGH, 0},
  {8, 7, HIGH, HIGH, 0}, {9, 8, HIGH, HIGH, 0},
  {ENCODER_SW, 0, HIGH, HIGH, 0},
};
const byte BUTTON_COUNT = sizeof(buttons) / sizeof(buttons[0]);

void scanButton(byte index, unsigned long now) {
  Button& button = buttons[index];
  const int reading = digitalRead(button.pin);
  if (reading != button.reading) {
    button.reading = reading;
    button.changedAt = now;
  }
  if (now - button.changedAt >= DEBOUNCE_MS && reading != button.stable) {
    button.stable = reading;
    if (reading == LOW) {
      if (button.slot == 8) {
        // The host rotates any number of profiles and keeps a pending question visible.
        Serial.print(F("BUTTON_LAB_MODE:toggle\n"));
      } else if (button.slot) {
        Serial.print(F("BUTTON_LAB_KEY:")); Serial.println(button.slot);
      } else Serial.print(F("BUTTON_LAB_KNOB:press\n"));
      oledDirty = true;
    }
  }
}

void scanEncoder() {
  const int encoded = (digitalRead(ENCODER_CLK) << 1) | digitalRead(ENCODER_DT);
  if (encoded == lastEncoded) return;
  const int transition = (lastEncoded << 2) | encoded;
  if (transition == 0b1101 || transition == 0b0100 || transition == 0b0010 || transition == 0b1011) encoderAccumulator++;
  if (transition == 0b1110 || transition == 0b0111 || transition == 0b0001 || transition == 0b1000) encoderAccumulator--;
  lastEncoded = encoded;
  if (encoderAccumulator >= 4) {
    encoderAccumulator = 0;
    Serial.print(F("BUTTON_LAB_KNOB:right\n"));
  } else if (encoderAccumulator <= -4) {
    encoderAccumulator = 0;
    Serial.print(F("BUTTON_LAB_KNOB:left\n"));
  }
}

void setup() {
  Serial.begin(115200);
  for (byte index = 0; index < BUTTON_COUNT; index++) {
    pinMode(buttons[index].pin, INPUT_PULLUP);
    buttons[index].reading = buttons[index].stable = digitalRead(buttons[index].pin);
  }
  pinMode(ENCODER_CLK, INPUT_PULLUP);
  pinMode(ENCODER_DT, INPUT_PULLUP);
  lastEncoded = (digitalRead(ENCODER_CLK) << 1) | digitalRead(ENCODER_DT);
  Wire.begin();
  Wire.beginTransmission(OLED_ADDRESS);
  if (Wire.endTransmission() == 0) oledReady = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS);
  if (!oledReady) Serial.print(F("OLED unavailable: check address/wiring or SRAM\n"));
  renderDisplay();
}

void loop() {
  readHost();
  const unsigned long now = millis();
  for (byte index = 0; index < BUTTON_COUNT; index++) scanButton(index, now);
  scanEncoder();
  if (oledDirty && now - lastDisplayAt >= 100) { lastDisplayAt = now; renderDisplay(); }
}
