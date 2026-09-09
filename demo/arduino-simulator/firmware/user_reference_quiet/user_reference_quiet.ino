// User-supplied working sketch, with volume capped at 3/30 for comparison.
// No Wi-Fi, NeoPixel, simulator protocol, or mandatory response acknowledgments.
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

Adafruit_SSD1306 oled(128, 64, &Wire, -1);
const byte buttonPins[8] = {2, 3, 4, 5, 6, 7, 8, 9};
bool rawState[8], stableState[8];
unsigned long changedAt[8] = {};
bool oledReady = false, dirty = true;
unsigned long lastDraw = 0;
int selectedSound = 1;
bool outputEnabled = false;
const char* actionText = "STOP (OUTPUT OFF)";
const char* soundNames[4] = {"OISHI", "GEOJE YAHO", "LOVE ATTACK", "DEJA VU"};
float filteredADC = 0;
int targetVolume = 3, sentVolume = -1;
unsigned long lastAnalogRead = 0, volumeChangedAt = 0;
const byte QUEUE_SIZE = 24;
char atQueue[QUEUE_SIZE][48];
byte queueRead = 0, queueWrite = 0;
unsigned long lastSend = 0;

bool respondsAt(byte address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}
int queueFree() {
  return (queueRead + QUEUE_SIZE - queueWrite - 1) % QUEUE_SIZE;
}
bool enqueueAT(const char* command) {
  byte next = (queueWrite + 1) % QUEUE_SIZE;
  if (next == queueRead) { Serial.println("ERR: MP3 queue full"); return false; }
  snprintf(atQueue[queueWrite], sizeof(atQueue[0]), "%s", command);
  queueWrite = next;
  return true;
}
void sendAT(const char* command) {
  Serial.print("SEND: "); Serial.println(command);
  Serial1.print(command); Serial1.print("\r\n");
  lastSend = millis();
}
void playSound(int number) {
  if (queueFree() < 3) { Serial.println("BUSY: try again"); return; }
  selectedSound = constrain(number, 1, 4);
  enqueueAT("AT+AMP=OFF");
  char command[48];
  snprintf(command, sizeof(command), "AT+PLAYFILE=/sound%d.mp3", selectedSound);
  enqueueAT(command);
  enqueueAT("AT+AMP=ON");
  outputEnabled = true; actionText = "PLAY COMMAND"; dirty = true;
}
void stopSound() {
  queueRead = queueWrite;
  enqueueAT("AT+AMP=OFF");
  outputEnabled = false; actionText = "STOP (OUTPUT OFF)"; dirty = true;
}
void toggleSound() {
  if (outputEnabled) stopSound(); else playSound(selectedSound);
}
void handleButton(byte index) {
  Serial.print("Button "); Serial.println(index + 1);
  if (index < 4) { playSound(index + 1); return; }
  switch (index) {
    case 4: playSound(selectedSound); break;
    case 5: stopSound(); break;
    case 6: playSound(selectedSound == 4 ? 1 : selectedSound + 1); break;
    case 7: playSound(selectedSound == 1 ? 4 : selectedSound - 1); break;
  }
}
void readButtons() {
  unsigned long now = millis();
  for (byte i = 0; i < 8; i++) {
    bool reading = digitalRead(buttonPins[i]);
    if (reading != rawState[i]) { rawState[i] = reading; changedAt[i] = now; }
    if (now - changedAt[i] >= 30 && reading != stableState[i]) {
      stableState[i] = reading; dirty = true;
      if (reading == LOW) handleButton(i);
    }
  }
}
void readVolumeKnob() {
  unsigned long now = millis();
  if (now - lastAnalogRead < 10) return;
  lastAnalogRead = now;
  int raw = 1023 - analogRead(A0);
  filteredADC += (raw - filteredADC) * 0.15f;
  // Only intentional behavioral change: fixed quiet test volume, not A0 volume.
  int newVolume = 3;
  if (newVolume != targetVolume) {
    targetVolume = newVolume; volumeChangedAt = now; dirty = true;
  }
}
void serviceMP3() {
  if (millis() - lastSend < 250) return;
  if (queueRead != queueWrite) {
    sendAT(atQueue[queueRead]);
    queueRead = (queueRead + 1) % QUEUE_SIZE;
    return;
  }
  if (targetVolume != sentVolume && millis() - volumeChangedAt >= 200) {
    char command[24];
    snprintf(command, sizeof(command), "AT+VOL=%d", targetVolume);
    sendAT(command); sentVolume = targetVolume;
  }
}
void printHelp() {
  Serial.println("1-4: select and play sound");
  Serial.println("p: replay selected sound");
  Serial.println("s: output stop");
  Serial.println("n: next sound / b: previous sound");
  Serial.println("0: output stop / restart");
  Serial.println("?: connection test");
  Serial.println("QUIET REFERENCE TEST: fixed volume 3/30");
}
void readSerial() {
  for (byte i = 0; i < 64 && Serial1.available(); i++) Serial.write(Serial1.read());
  for (byte i = 0; i < 8 && Serial.available(); i++) {
    char c = Serial.read();
    if (c >= '1' && c <= '4') { playSound(c - '0'); continue; }
    switch (c) {
      case 'p': case 'P': playSound(selectedSound); break;
      case 's': case 'S': stopSound(); break;
      case 'n': case 'N': playSound(selectedSound == 4 ? 1 : selectedSound + 1); break;
      case 'b': case 'B': playSound(selectedSound == 1 ? 4 : selectedSound - 1); break;
      case '0': toggleSound(); break;
      case '?': enqueueAT("AT"); break;
      case 'h': case 'H': printHelp(); break;
      case '\r': case '\n': case ' ': break;
      default: Serial.println("Unknown command. Send h."); break;
    }
  }
}
void drawOLED() {
  if (!oledReady || !dirty || millis() - lastDraw < 100) return;
  dirty = false; lastDraw = millis();
  oled.clearDisplay(); oled.setTextSize(1); oled.setTextWrap(false);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0); oled.print("SOUND "); oled.print(selectedSound);
  oled.print("   VOL:"); oled.print(targetVolume);
  oled.setCursor(0, 12); oled.print(soundNames[selectedSound - 1]);
  oled.setCursor(0, 24); oled.print(actionText);
  oled.drawRect(0, 37, 128, 8, SSD1306_WHITE);
  int width = map(targetVolume, 0, 30, 0, 126);
  if (width > 0) oled.fillRect(1, 38, width, 6, SSD1306_WHITE);
  for (byte i = 0; i < 8; i++) {
    int x = i * 16; bool pressed = stableState[i] == LOW;
    if (pressed) { oled.fillRect(x, 50, 14, 13, SSD1306_WHITE); oled.setTextColor(SSD1306_BLACK); }
    else { oled.drawRect(x, 50, 14, 13, SSD1306_WHITE); oled.setTextColor(SSD1306_WHITE); }
    oled.setCursor(x + 4, 53); oled.print(i + 1);
  }
  oled.display();
}
void setup() {
  Serial.begin(115200); Serial1.begin(115200);
  analogReadResolution(10);
  for (byte i = 0; i < 8; i++) {
    pinMode(buttonPins[i], INPUT_PULLUP);
    rawState[i] = stableState[i] = digitalRead(buttonPins[i]);
  }
  filteredADC = 1023 - analogRead(A0);
  targetVolume = 3;
  Wire.begin();
  byte address = 0;
  if (respondsAt(0x3C)) address = 0x3C;
  else if (respondsAt(0x3D)) address = 0x3D;
  if (address) oledReady = oled.begin(SSD1306_SWITCHCAPVCC, address);
  delay(2000);
  sendAT("AT+VOL=0"); delay(250);
  sendAT("AT+FUNCTION=1"); delay(2000);
  sendAT("AT+AMP=OFF"); delay(250);
  sendAT("AT+PLAYMODE=3"); delay(250);
  sentVolume = -1; volumeChangedAt = millis();
  printHelp();
}
void loop() {
  readButtons(); readVolumeKnob(); readSerial(); serviceMP3(); drawOLED();
}
