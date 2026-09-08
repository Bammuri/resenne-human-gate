// Arduino UNO R4 WiFi: YES button D2--GND, NO button D3--GND.
// Serial Monitor: 115200 baud. Holding a button does not repeat its message.
// Connect with Button Lab's physical-board mode in desktop Chrome.
#include <string.h>

const unsigned long DEBOUNCE_MS = 35;
char hostCommand[32];
byte hostLength = 0;
bool hostOverflow = false;

void readHost() {
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\n') {
      hostCommand[hostLength] = '\0';
      if (!hostOverflow && strcmp(hostCommand, "BUTTON_LAB_HELLO") == 0) {
        Serial.print("BUTTON_LAB_READY:1\n");
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
  const char* message;
  int reading;
  int stable;
  unsigned long changedAt;
};

Button buttons[] = {
  {2, "yes", HIGH, HIGH, 0},
  {3, "no", HIGH, HIGH, 0},
};

void setup() {
  Serial.begin(115200);
  for (Button& button : buttons) {
    pinMode(button.pin, INPUT_PULLUP);
    // A held button at boot must be released before it can send a response.
    button.reading = button.stable = digitalRead(button.pin);
  }
}

void loop() {
  readHost();
  const unsigned long now = millis();
  for (Button& button : buttons) {
    const int reading = digitalRead(button.pin);
    if (reading != button.reading) {
      button.reading = reading;
      button.changedAt = now;
    }
    if (now - button.changedAt >= DEBOUNCE_MS && reading != button.stable) {
      button.stable = reading;
      if (reading == LOW) {
        Serial.print(button.message);
        Serial.write('\n');
      }
    }
  }
}
