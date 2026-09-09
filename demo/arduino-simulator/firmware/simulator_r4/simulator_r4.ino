// UNO R4 WiFi: D2-D9 buttons, A0 potentiometer, A4/A5 OLED,
// D0/D1 Serial1 DFPlayer Pro DFR0768, D10 WS2812B x8.
// Buttons send slot events to the simulator; the host owns modes, ASK and RUN NOW.
#include <WiFiS3.h>
#include <EEPROM.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>
#include "board_config.h"
#include "oled_text_frame.h"
#include "oled_transport.h"

const char* READY = "BUTTON_LAB_READY:3:slots=8:knob=analog";
const uint32_t CONFIG_MAGIC = 0x424C5234;
struct NetworkConfig { uint32_t magic; char ssid[33]; char password[65]; } config;
struct BootCounter { uint32_t magic; uint32_t count; } boot;
struct Button { uint8_t pin; bool reading; bool stable; uint32_t changed; } buttons[8];
struct Event { uint32_t id; char line[128]; } events[24];
uint32_t sequence = 0;
String bootId;
TwoWire& oledWire = OLED_USE_QWIIC ? Wire1 : Wire;
Adafruit_SSD1306 display(128, 64, &oledWire, -1, 100000UL, 100000UL);
OledTransport<TwoWire> oledTransport(oledWire);
uint32_t oledFrames=0, oledFailures=0, oledRecoveries=0, oledSuccessAt=0;
bool oledForce=true;
uint8_t oledBusBefore=3, oledBusAfter=3;
Adafruit_NeoPixel pixels(8, 10, NEO_GRB + NEO_KHZ800);
uint32_t keyLitAt[8] = {}, pixelsAt = 0;
bool displayLinked = false;
bool oledReady = false, oledDirty = true, apMode = false, networkReady = false;
String profile = "agent", stage = "browse", runState = "ready", audioReply;
uint32_t workingSince = 0;
String audioQueue[12], audioPendingCommand, audioError;
uint8_t audioQueueSize=0;
uint32_t audioSentAt=0, volumeChangedAt=0;
uint16_t audioGap=250;
int audioVolume=3;
bool volumeControl = false, volumePending = false;
int volumeTarget = 0, volumeAnchor = 0;
uint8_t level = 1;
int potFiltered = 0, potLastSent = 0;
uint32_t potAt = 0, oledAt = 0, networkAt = 0, networkLostAt = 0, reconnectAt = 0;
WiFiServer httpServer(80);
WiFiClient httpClient;
String httpRequest;
uint32_t httpStarted = 0;
String usbLine, audioLine;
bool usbOverflow = false, audioOverflow = false;
bool bootComplete=false;
const char* bootStage="serial";

void bootCheckpoint(const char* stageName) {
  bootStage=stageName;
  Serial.print("BUTTON_LAB_BOOT:");Serial.println(bootStage);
}
void waitWithUsb(uint32_t duration) {
  uint32_t started=millis();
  while(millis()-started<duration) { readSerial();delay(1); }
}

void emitLine(const String& line) {
  if (line.length() > 127) return;
  if (Serial) Serial.println(line);
  Event& event = events[sequence % 24];
  event.id = ++sequence;
  line.toCharArray(event.line, sizeof(event.line));
}
String jsonString(const String& text) {
  String result = "\"";
  for (unsigned int i = 0; i < text.length(); i++) {
    char c = text[i];
    if (c == '"' || c == '\\') { result += '\\'; result += c; }
    else if (c == '\n') result += "\\n";
    else if (c == '\r') result += "\\r";
    else if ((uint8_t)c >= 32) result += c;
  }
  return result + '"';
}
bool numberIn(const String& text, int low, int high) {
  if (!text.length() || text.length() > 5) return false;
  for (unsigned int i = 0; i < text.length(); i++) if (!isDigit(text[i])) return false;
  return text.toInt() >= low && text.toInt() <= high;
}
bool displayCommand(String value) {
  int a=value.indexOf(':'), b=value.indexOf(':',a+1), c=value.indexOf(':',b+1);
  if (a<0 || b<0 || c<0) return false;
  String p=value.substring(0,a), s=value.substring(a+1,b), l=value.substring(b+1,c), r=value.substring(c+1);
  if (p!="agent" && p!="workflow" && p!="custom" && p!="codex") return false;
  if (!s.length() || s.length()>16 || !numberIn(l,0,p=="workflow"?5:3)) return false;
  for (unsigned int i=0;i<s.length();i++) if (!isLowerCase(s[i]) && s[i]!='_') return false;
  if (r!="ready" && r!="running" && r!="approved" && r!="stopped" && r!="error" && r!="question") return false;
  if(displayLinked && profile==p && stage==s && level==l.toInt() && runState==r)return true;
  if(r=="running" && runState!="running") workingSince=millis();
  if(profile!=p || !displayLinked) {
    volumeAnchor=potFiltered;potLastSent=potFiltered;
    emitLine("BUTTON_LAB_POT_RESET:"+String(potFiltered));
  }
  volumeControl=p=="custom";
  profile=p; stage=s; level=l.toInt(); runState=r; displayLinked=true; oledDirty=true;
  return true;
}
uint8_t buttonSound(const String& mode, uint8_t slot) {
  if(slot==8) return 8;
  if(slot<1 || slot>7) return 0;
  if(mode=="workflow") return slot+8;
  if(mode=="custom") return slot<=4?slot+15:0;
  return slot;
}
void queueButtonSound(uint8_t slot) {
  // All custom-mode keys retain knob volume control; key 7 only stops audio.
  volumeControl=profile=="custom";
  volumeAnchor=potFiltered;potLastSent=potFiltered;
  emitLine("BUTTON_LAB_POT_RESET:"+String(potFiltered));
  oledDirty=true;
  if(profile=="custom" && slot==7) { stopAudio();return; }
  uint8_t track=buttonSound(profile,slot);
  if(!track)return;
  // Latest press wins; do not accumulate stale spoken button announcements.
  audioQueueSize=0;
  queueAudio("AT+VOL="+String(audioVolume));
  queueAudio("AT+AMP=ON");
  queueAudio("AT+PLAYFILE=/sound"+String(track)+".mp3");
}
bool queueAudio(const String& command) {
  if(audioQueueSize>=12)return false;
  audioQueue[audioQueueSize++]=command;return true;
}
void sendAudio(const String& command) {
  Serial1.print(command);Serial1.print("\r\n");
  // Warm the amplifier before decoding the new file, not after its intro.
  audioGap=command=="AT+AMP=ON"?500:250;
  audioSentAt=millis();emitLine("BUTTON_LAB_AUDIO_SENT:"+command);
}
void stopAudio() {
  audioQueueSize=0;volumePending=false;
  sendAudio("AT+AMP=OFF"); // Stop overrides a pending start/warm-up immediately.
}
void serviceButtonAudio() {
  // Match the user's working firmware: paced commands, not mandatory OK gates.
  if(millis()-audioSentAt<audioGap)return;
  if(!audioQueueSize && volumePending && millis()-volumeChangedAt>=200) {
    volumePending=false;queueAudio("AT+VOL="+String(audioVolume));
  }
  if(!audioQueueSize)return;
  audioPendingCommand=audioQueue[0];
  for(uint8_t i=1;i<audioQueueSize;i++)audioQueue[i-1]=audioQueue[i];
  audioQueue[--audioQueueSize]="";
  sendAudio(audioPendingCommand);
}
bool processCommand(const String& command) {
  if (command == "BUTTON_LAB_HELLO") {
    emitLine(READY);
    if(bootComplete)emitLine("BUTTON_LAB_POT_RESET:"+String(potFiltered));
    return true;
  }
  if (command == "boot:info") { emitLine("BUTTON_LAB_BOOT:"+String(bootStage));return true; }
  if (command == "oled:info") { reportOled();return true; }
  if (command == "oled:refresh") { oledForce=true;oledDirty=true;return true; }
  if (command == "wifi:info") {
    if(!bootComplete){emitLine("BUTTON_LAB_WIFI:starting");return true;}
    emitLine("BUTTON_LAB_WIFI:" + String(apMode?"AP:":"STA:") + WiFi.localIP().toString()); return true;
  }
  if (command.startsWith("display:")) return displayCommand(command.substring(8));
  if (command.startsWith("key:") && numberIn(command.substring(4),1,8)) {
    keyLitAt[command.substring(4).toInt()-1]=millis();
    queueButtonSound(command.substring(4).toInt());
    emitLine("BUTTON_LAB_SIMULATED_KEY:"+command.substring(4)); return true;
  }
  if (command=="mode:toggle") { queueButtonSound(8);emitLine("BUTTON_LAB_SIMULATED_MODE:toggle"); return true; }
  if (command.startsWith("knob:")) {
    String value=command.substring(5);
    if (value!="left" && value!="right" && value!="press") return false;
    if(profile=="custom" && value!="press") {
      audioVolume=volumeTarget=constrain(audioVolume+(value=="right"?1:-1),0,30);
      volumeAnchor=potFiltered;volumeChangedAt=millis();volumePending=true;oledDirty=true;
    }
    emitLine("BUTTON_LAB_SIMULATED_KNOB:"+value); return true;
  }
  if (command.startsWith("pot:") && numberIn(command.substring(4),0,1023)) {
    emitLine("BUTTON_LAB_SIMULATED_POT:"+command.substring(4)); return true;
  }
  String at;
  if(command=="audio:stop") { stopAudio();return true; }
  if(command=="audio:test") {
    audioQueueSize=0;volumePending=false;audioVolume=volumeTarget=3;
    queueAudio("AT+VOL=3");queueAudio("AT+AMP=ON");
    queueAudio("AT+PLAYFILE=/sound1.mp3");
    return true;
  }
  if (command=="audio:status") at="AT";
  else if (command=="audio:toggle") at="AT+PLAY=PP";
  else if (command=="audio:next") at="AT+PLAY=NEXT";
  else if (command=="audio:previous") at="AT+PLAY=LAST";
  else if (command.startsWith("audio:volume:") && numberIn(command.substring(13),0,30)) at="AT+VOL="+command.substring(13);
  else if (command.startsWith("audio:play:") && numberIn(command.substring(11),1,9999)) at="AT+PLAYNUM="+command.substring(11);
  else return false;
  if(!queueAudio(at))return false;
  if(command.startsWith("audio:volume:"))audioVolume=volumeTarget=command.substring(13).toInt();
  return true;
}
void scanInputs() {
  uint32_t now=millis();
  for (uint8_t i=0;i<8;i++) {
    bool reading=digitalRead(buttons[i].pin);
    if (reading!=buttons[i].reading) { buttons[i].reading=reading; buttons[i].changed=now; }
    if (now-buttons[i].changed>=30 && reading!=buttons[i].stable) {
      buttons[i].stable=reading;
      if (reading==LOW) { keyLitAt[i]=now; queueButtonSound(i+1);emitLine("BUTTON_LAB_KEY:"+String(i+1)); }
    }
  }
  if (now-potAt>=10) {
    potAt=now;
    potFiltered=(potFiltered*3+(POT_REVERSED ? 1023-analogRead(A0) : analogRead(A0)))/4;
    if(volumeControl) {
      potLastSent=potFiltered;
      if(abs(potFiltered-volumeAnchor)>=24) {
        volumeAnchor=potFiltered;
        int next=constrain((potFiltered*30+511)/1023,0,30);
        if(next!=volumeTarget) { audioVolume=volumeTarget=next;volumeChangedAt=now;volumePending=true;oledDirty=true; }
      }
      return;
    }
    if (abs(potFiltered-potLastSent)>=12) {
      potLastSent=potFiltered;
      emitLine("BUTTON_LAB_POT:"+String(potFiltered));
    }
  }
}
void readSerial() {
  for (uint8_t n=0;n<96 && Serial.available();n++) {
    char c=Serial.read();
    if (c=='\n') {
      if (!usbOverflow && usbLine.length() && !processCommand(usbLine)) emitLine("BUTTON_LAB_ERROR:invalid-command");
      usbLine=""; usbOverflow=false;
    } else if (c!='\r') { if (usbLine.length()<255) usbLine+=c; else usbOverflow=true; }
  }
  for (uint8_t n=0;n<96 && Serial1.available();n++) {
    char c=Serial1.read();
    if (c=='\n' || c=='\r') {
      if (!audioOverflow && audioLine.length()) {
        audioLine.trim();audioReply=audioLine;emitLine("BUTTON_LAB_AUDIO:"+audioLine);
        // Responses are observable, but cannot be reliably matched to commands.
        if(audioLine.startsWith("ERR")) {
          audioError=audioLine;emitLine("BUTTON_LAB_AUDIO_ERROR:"+audioError);
          audioQueueSize=0;volumePending=false;
        }
      }
      audioLine=""; audioOverflow=false;
    } else { if (audioLine.length()<100) audioLine+=c; else audioOverflow=true; }
  }
}
void reportOled() {
  emitLine("BUTTON_LAB_OLED:"+String(oledReady?"OK":"ERROR")+
    ":address="+String(oledTransport.address,HEX)+":error="+String(oledTransport.error)+
    ":frames="+String(oledFrames)+":failures="+String(oledFailures)+
    ":bus="+String(oledBusBefore)+">"+String(oledBusAfter));
}
bool releaseOledClock(uint8_t scl) {
  pinMode(scl,INPUT); // Release only; never drive a 5V HIGH onto the module.
  uint32_t started=micros();
  while(digitalRead(scl)==LOW && micros()-started<1000) {}
  return digitalRead(scl)==HIGH;
}
void clearOledBus() {
  // NXP UM10204 3.1.16: up to nine clocks for stuck SDA, then STOP.
  // https://www.nxp.com/docs/en/user-guide/UM10204.pdf
  const uint8_t sda=OLED_USE_QWIIC?WIRE1_SDA_PIN:WIRE_SDA_PIN;
  const uint8_t scl=OLED_USE_QWIIC?WIRE1_SCL_PIN:WIRE_SCL_PIN;
  oledWire.end();pinMode(sda,INPUT);pinMode(scl,INPUT);delayMicroseconds(10);
  oledBusBefore=(digitalRead(sda)==HIGH?2:0)|(digitalRead(scl)==HIGH?1:0);
  if(releaseOledClock(scl) && digitalRead(sda)==LOW) {
    for(uint8_t pulse=0;pulse<9 && digitalRead(sda)==LOW;pulse++) {
      digitalWrite(scl,LOW);pinMode(scl,OUTPUT);delayMicroseconds(10);
      if(!releaseOledClock(scl))break;
      delayMicroseconds(10);
    }
    // SCL low before SDA low, then release SCL followed by SDA: STOP.
    digitalWrite(scl,LOW);pinMode(scl,OUTPUT);
    digitalWrite(sda,LOW);pinMode(sda,OUTPUT);delayMicroseconds(10);
    releaseOledClock(scl);delayMicroseconds(10);
    pinMode(sda,INPUT);delayMicroseconds(10);
  }
  oledBusAfter=(digitalRead(sda)==HIGH?2:0)|(digitalRead(scl)==HIGH?1:0);
}
bool beginOled() {
  if(!oledTransport.probe())return false;
  // Adafruit is used for its framebuffer/font, not its unchecked transfers.
  // Do not let begin() re-open a Wire bus already configured by this sketch.
  if(!display.getBuffer() && !display.begin(SSD1306_SWITCHCAPVCC,oledTransport.address,false,false)) {
    oledTransport.error=4;return false;
  }
  return oledTransport.configure();
}
void renderDisplay() {
  uint32_t now=millis();
  bool running=bootComplete && displayLinked && runState=="running";
  bool refresh=oledForce || now-oledSuccessAt>=5000;
  if(now-oledAt<(oledReady?250UL:2000UL))return;
  if(oledReady && !oledDirty && !refresh && !running)return;
  oledAt=millis();oledDirty=false;
  if(!oledReady) {
    clearOledBus();
    oledWire.begin();oledWire.setWireTimeout(25000);oledWire.setClock(100000);
    if(!beginOled()) { oledFailures++;reportOled();return; }
    oledRecoveries++;refresh=true;
  }
  OledTextFrame frame;
  if(!bootComplete) {
    frame.set(0,"Re:senne");
    frame.set(1,"STARTING...");
  } else if(!displayLinked) {
    frame.set(0,"Re:senne");
    frame.set(1,"CONNECT USB / WIFI");
    frame.set(2,apMode?"WIFI SETUP":"BOARD READY");
    String ip=networkReady?WiFi.localIP().toString():"USB READY";
    frame.set(3,ip.c_str());
  } else if(runState=="question") {
    frame.set(0,"ANSWER NEEDED");
    frame.set(1,"CHOOSE KEY 1-7");
    frame.set(2,"CHECK TERMINAL");
  } else if(profile=="custom") {
    frame.set(0,"MODE 3 SOUND");
    char volume[21];snprintf(volume,sizeof(volume),"VOLUME %d / 30",volumeTarget);
    frame.set(1,volume);
    frame.set(2,"KNOB: VOLUME");
    frame.set(3,"1-4 PLAY / 7 STOP");
  } else {
    frame.set(0,profile=="workflow"?"MODE 2 AI-DLC":"MODE 1 AI CONTROL");
    String title=stage;title.toUpperCase();
    frame.set(1,title.c_str());
    if(profile=="workflow") {
      char autonomy[21];snprintf(autonomy,sizeof(autonomy),"AUTONOMY %u / 5",level);
      frame.set(2,autonomy);
    } else {
      const char* efforts[]={"EFFORT LOW","EFFORT MEDIUM","EFFORT HIGH","EFFORT XHIGH"};
      frame.set(2,efforts[min((uint8_t)3,level)]);
    }
    String stateText=runState;stateText.toUpperCase();
    frame.set(3,runState=="question"?"CHOOSE KEY 1-7":stateText.c_str());
  }
  static OledTextFrame previous;
  static bool hasPrevious=false;
  static bool previousRunning=false;
  if(!running && !previousRunning && !refresh && hasPrevious && frame.equals(previous))return;
  display.clearDisplay();
  display.setRotation(0);display.setFont(NULL);display.setTextSize(1);
  display.setTextWrap(false);display.setTextColor(SSD1306_WHITE,SSD1306_BLACK);
  if(running) OledRunningFrame::draw(display,(uint32_t)(now-workingSince));
  else for(uint8_t row=0;row<OledTextFrame::ROWS;row++) {
    display.setCursor(OledTextFrame::LEFT,OledTextFrame::rowY(row));
    display.print(frame.lines[row]);
  }
  // Restore addressing/offset even when the logical text has not changed:
  // a module power interruption must not leave a permanently blank screen.
  bool wasReady=oledReady;
  oledReady=oledTransport.configure() && oledTransport.frame(display.getBuffer());
  if(!oledReady) { oledFailures++;oledDirty=true;oledForce=true;reportOled();return; }
  previous=frame;previousRunning=running;hasPrevious=true;oledForce=false;oledFrames++;oledSuccessAt=millis();
  if(!wasReady || oledFrames==1)reportOled();
}
String statusJson() {
  return "{\"board\":\"UNO R4 WiFi\",\"protocol\":3,\"boot\":"+jsonString(bootId)+",\"cursor\":"+String(sequence)+
    ",\"mode\":"+jsonString(apMode?"ap":"station")+",\"ip\":"+jsonString(WiFi.localIP().toString())+
    ",\"pot\":"+String(potFiltered)+",\"oled\":"+(oledReady?"true":"false")+
    ",\"oledAddress\":"+String(oledTransport.address)+",\"oledError\":"+String(oledTransport.error)+
    ",\"oledFrames\":"+String(oledFrames)+",\"oledFailures\":"+String(oledFailures)+
    ",\"oledRecoveries\":"+String(oledRecoveries)+",\"oledFrameAgeMs\":"+String(millis()-oledSuccessAt)+
    ",\"audioReply\":"+jsonString(audioReply)+",\"audioError\":"+jsonString(audioError)+"}";
}
void respondHttp(int code, const String& body, const char* type="application/json") {
  httpClient.print("HTTP/1.1 ");httpClient.print(code);httpClient.println(code==200?" OK":code==401?" Unauthorized":" Error");
  httpClient.print("Content-Type: ");httpClient.println(type);
  httpClient.print("Content-Length: ");httpClient.println(body.length());
  httpClient.println("Cache-Control: no-store\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\n");
  httpClient.print(body);httpClient.stop();httpRequest="";
}
String formValue(const String& body, const String& key) {
  String value;
  int start=body.indexOf(key+"=");
  if (start<0 || (start>0 && body[start-1]!='&')) return value;
  start+=key.length()+1;int end=body.indexOf('&',start);if(end<0)end=body.length();
  for (int i=start;i<end;i++) {
    char c=body[i];
    if (c=='+') value+=' ';
    else if(c=='%' && i+2<end) { char hex[3]={body[i+1],body[i+2],0}; if(!isHexadecimalDigit(hex[0])||!isHexadecimalDigit(hex[1]))return "";value+=(char)strtol(hex,nullptr,16);i+=2; }
    else value+=c;
  }
  return value;
}
const char SETUP_PAGE[] = R"HTML(<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Button Lab R4 Wi-Fi</title><style>body{max-width:480px;margin:40px auto;padding:20px;font:16px system-ui;background:#f0f5ef;color:#243c30}input,button{box-sizing:border-box;display:block;width:100%;margin:8px 0 20px;padding:12px}small{line-height:1.7}</style><h1>Button Lab R4</h1><p>공유기 Wi-Fi 연결</p><form method="post" action="/wifi"><label>Wi-Fi 이름 (SSID)<input name="ssid" maxlength="32" required></label><label>Wi-Fi 비밀번호<input name="password" type="password" maxlength="63"></label><button>저장하고 연결</button></form><small>연결 뒤 OLED의 IP를 시뮬레이터에 입력하세요. 연결에 실패하면 보드 Wi-Fi로 돌아옵니다. API 토큰은 없습니다. 같은 네트워크에서 보드 IP만 입력하세요.</small></html>)HTML";
void handleHttp() {
  int headEnd=httpRequest.indexOf("\r\n\r\n");if(headEnd<0)return;
  int firstEnd=httpRequest.indexOf("\r\n");String first=httpRequest.substring(0,firstEnd);
  int a=first.indexOf(' '),b=first.indexOf(' ',a+1);if(a<0||b<0){respondHttp(400,"{}");return;}
  String method=first.substring(0,a),path=first.substring(a+1,b);
  String headers=httpRequest.substring(firstEnd+2,headEnd), lower=headers;lower.toLowerCase();
  int contentLength=0,cl=lower.indexOf("content-length:");
  if(cl>=0){int end=headers.indexOf("\r\n",cl);String length=headers.substring(cl+15,end<0?headers.length():end);length.trim();if(!numberIn(length,0,768)){respondHttp(413,"{}");return;}contentLength=length.toInt();}
  if(httpRequest.length()<(unsigned)(headEnd+4+contentLength))return;
  String body=httpRequest.substring(headEnd+4,headEnd+4+contentLength);
  if(method=="GET" && path=="/"){respondHttp(200,SETUP_PAGE,"text/html; charset=utf-8");return;}
  if(method=="GET" && path=="/status"){respondHttp(200,statusJson());return;}
  if(method=="GET" && path.startsWith("/events?after=")) {
    String value=path.substring(14);uint32_t after=strtoul(value.c_str(),nullptr,10);
    bool reset=after>sequence || sequence-after>24;
    String result="{\"boot\":"+jsonString(bootId)+",\"cursor\":"+String(sequence)+",\"reset\":"+(reset?"true":"false")+",\"events\":[";
    if(!reset){bool comma=false;for(uint32_t id=after+1;id<=sequence;id++){Event& event=events[(id-1)%24];if(comma)result+=',';result+="{\"id\":"+String(id)+",\"line\":"+jsonString(event.line)+"}";comma=true;}}
    respondHttp(200,result+"]}");return;
  }
  if(method=="POST" && path=="/command") {
    if(body.indexOf('\n')>=0 || body.indexOf('\r')>=0 || body.length()>255){respondHttp(400,"{}");return;}
    bool ok=processCommand(body);respondHttp(ok?200:400,ok?"{\"ok\":true}":"{\"error\":\"Unknown command\"}");return;
  }
  if(method=="POST" && path=="/wifi") {
    String ssid=formValue(body,"ssid"),password=formValue(body,"password");
    if(!ssid.length() || ssid.length()>32 || (password.length() && (password.length()<8 || password.length()>63))){respondHttp(400,"Invalid Wi-Fi settings","text/plain");return;}
    config.magic=CONFIG_MAGIC;ssid.toCharArray(config.ssid,33);password.toCharArray(config.password,65);EEPROM.put(0,config);
    respondHttp(200,"Saved. Reconnecting. Check the IP on the OLED.","text/plain");reconnectAt=millis()+800;return;
  }
  respondHttp(404,"{}");
}
void startNetwork() {
  networkReady=false;networkLostAt=0;
  WiFi.setTimeout(5000);
  if(WiFi.status()==WL_NO_MODULE){emitLine("BUTTON_LAB_WIFI:no-module");return;}
  WiFi.disconnect();
  int status=WL_IDLE_STATUS;
  if(config.magic==CONFIG_MAGIC && config.ssid[0]) status=config.password[0]?WiFi.begin(config.ssid,config.password):WiFi.begin(config.ssid);
  apMode=status!=WL_CONNECTED;
  if(apMode) { WiFi.config(IPAddress(192,168,4,1)); status=(BOARD_AP_PASSWORD[0] ? WiFi.beginAP(BOARD_AP_SSID,BOARD_AP_PASSWORD) : WiFi.beginAP(BOARD_AP_SSID)); }
  networkReady=status==WL_CONNECTED || status==WL_AP_LISTENING || status==WL_AP_CONNECTED;
  if(networkReady)httpServer.begin();
  oledDirty=true;
  emitLine("BUTTON_LAB_WIFI:"+String(apMode?"AP:":"STA:")+WiFi.localIP().toString());
}
void serviceNetwork() {
  if(reconnectAt && (int32_t)(millis()-reconnectAt)>=0){reconnectAt=0;startNetwork();}
  if(!networkReady)return;
  if(millis()-networkAt>=3000){networkAt=millis();int s=WiFi.status();
    if(!apMode && s!=WL_CONNECTED){if(!networkLostAt)networkLostAt=millis();if(millis()-networkLostAt>15000)startNetwork();}
    else networkLostAt=0;
  }
  if(!httpClient){httpClient=httpServer.available();if(httpClient){httpRequest="";httpStarted=millis();}else return;}
  for(uint8_t i=0;i<128 && httpClient.available();i++){
    httpRequest+=(char)httpClient.read();if(httpRequest.length()>1536){respondHttp(413,"{}");return;}
  }
  if(millis()-httpStarted>1800){httpClient.stop();httpRequest="";return;}
  handleHttp();
}
void setup() {
  Serial.begin(115200);Serial1.begin(115200);analogReadResolution(10);
  bootCheckpoint("usb-ready");waitWithUsb(1500);
  for(uint8_t i=0;i<8;i++){buttons[i]={uint8_t(i+2),HIGH,HIGH,0};pinMode(buttons[i].pin,INPUT_PULLUP);buttons[i].reading=buttons[i].stable=digitalRead(buttons[i].pin);}
  potFiltered=potLastSent=POT_REVERSED ? 1023-analogRead(A0) : analogRead(A0); // No pull-up, no startup action.
  audioVolume=volumeTarget=3; // Quiet startup; the knob adjusts in mode 3.
  bootCheckpoint("oled-begin");
  oledWire.begin();
  oledWire.setWireTimeout(25000);
  oledWire.setClock(100000);
  pixels.begin(); pixels.setBrightness(20); pixels.clear(); pixels.show();
  // Only a fully acknowledged frame may set oledReady. Draw before audio/Wi-Fi waits.
  oledAt=millis()-2000UL;renderDisplay();
  bootCheckpoint("oled-done");
  EEPROM.get(0,config);config.ssid[32]=0;config.password[64]=0;
#if defined(BOARD_STA_SSID) && defined(BOARD_STA_PASSWORD) && defined(BOARD_STA_REVISION)
  // Provision once per credentials revision, without undoing later portal edits.
  uint32_t provisionedRevision;
  EEPROM.get(144,provisionedRevision);
  if(config.magic!=CONFIG_MAGIC || provisionedRevision!=BOARD_STA_REVISION){
    static_assert(sizeof(BOARD_STA_SSID)<=sizeof(config.ssid), "SSID too long");
    static_assert(sizeof(BOARD_STA_PASSWORD)<=sizeof(config.password), "Password too long");
    config.magic=CONFIG_MAGIC;
    strcpy(config.ssid,BOARD_STA_SSID);strcpy(config.password,BOARD_STA_PASSWORD);
    EEPROM.put(0,config);
    provisionedRevision=BOARD_STA_REVISION;EEPROM.put(144,provisionedRevision);
  }
#endif
  EEPROM.get(128,boot);if(boot.magic!=CONFIG_MAGIC){boot.magic=CONFIG_MAGIC;boot.count=0;}boot.count++;EEPROM.put(128,boot);bootId=String(boot.count,HEX);
  httpRequest.reserve(1536);usbLine.reserve(256);audioLine.reserve(101);
  bootCheckpoint("audio-init");
  // Exact startup sequence from the user's confirmed-working sketch.
  // Boot-only waits keep normal button, display and network handling nonblocking.
  waitWithUsb(2000);sendAudio("AT+VOL=0");waitWithUsb(250);
  sendAudio("AT+FUNCTION=1");waitWithUsb(2000);
  sendAudio("AT+AMP=OFF");waitWithUsb(250);
  sendAudio("AT+PLAYMODE=3");waitWithUsb(250);
  sendAudio("AT+VOL=3");
  bootCheckpoint("wifi-init");
  startNetwork();renderDisplay();
  bootComplete=true;bootCheckpoint("ready");oledDirty=true;
}
void renderPixels() {
  if (millis()-pixelsAt<40) return;
  pixelsAt=millis();
  uint32_t color=profile=="workflow"?pixels.Color(30,80,200):profile=="custom"?pixels.Color(140,50,180):pixels.Color(0,130,65);
  if(runState=="error") color=pixels.Color(220,0,0);
  if(runState=="stopped") color=pixels.Color(180,70,0);
  if(runState=="running" && (millis()/350)%2) color=0;
  for(uint8_t i=0;i<8;i++) {
    uint32_t light=i==7?color:0;
    if(runState=="question" && i<7) light=pixels.Color(100,70,0);
    if(profile=="workflow" && i<7) {
      const char* stages[]={"initialization","ideation","inception","construction","operation","ask_workflow","start_workflow"};
      if(stage==stages[i]) light=color;
    }
    if(keyLitAt[i] && millis()-keyLitAt[i]<180) light=pixels.Color(150,150,150);
    pixels.setPixelColor(i,light);
  }
  pixels.show();
}
void loop(){scanInputs();readSerial();serviceNetwork();serviceButtonAudio();renderDisplay();renderPixels();}
