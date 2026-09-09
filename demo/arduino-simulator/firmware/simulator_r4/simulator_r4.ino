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

const char* READY = "BUTTON_LAB_READY:3:slots=8:knob=analog";
const uint32_t CONFIG_MAGIC = 0x424C5234;
struct NetworkConfig { uint32_t magic; char ssid[33]; char password[65]; } config;
struct BootCounter { uint32_t magic; uint32_t count; } boot;
struct Button { uint8_t pin; bool reading; bool stable; uint32_t changed; } buttons[8];
struct Event { uint32_t id; char line[128]; } events[24];
uint32_t sequence = 0;
String bootId;
TwoWire& oledWire = OLED_USE_QWIIC ? Wire1 : Wire;
Adafruit_SSD1306 display(128, 64, &oledWire, -1);
Adafruit_NeoPixel pixels(8, 10, NEO_GRB + NEO_KHZ800);
uint32_t keyLitAt[8] = {}, pixelsAt = 0;
bool displayLinked = false;
bool oledReady = false, oledDirty = true, apMode = false, networkReady = false;
String profile = "agent", stage = "browse", runState = "ready", audioReply;
uint8_t level = 1;
int potFiltered = 0, potLastSent = 0;
uint32_t potAt = 0, oledAt = 0, networkAt = 0, networkLostAt = 0, reconnectAt = 0;
WiFiServer httpServer(80);
WiFiClient httpClient;
String httpRequest;
uint32_t httpStarted = 0;
String usbLine, audioLine;
bool usbOverflow = false, audioOverflow = false;

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
  profile=p; stage=s; level=l.toInt(); runState=r; displayLinked=true; oledDirty=true;
  return true;
}
bool processCommand(const String& command) {
  if (command == "BUTTON_LAB_HELLO") { emitLine(READY); return true; }
  if (command == "wifi:info") {
    emitLine("BUTTON_LAB_WIFI:" + String(apMode?"AP:":"STA:") + WiFi.localIP().toString()); return true;
  }
  if (command.startsWith("display:")) return displayCommand(command.substring(8));
  if (command.startsWith("key:") && numberIn(command.substring(4),1,8)) {
    keyLitAt[command.substring(4).toInt()-1]=millis();
    emitLine("BUTTON_LAB_SIMULATED_KEY:"+command.substring(4)); return true;
  }
  if (command=="mode:toggle") { emitLine("BUTTON_LAB_SIMULATED_MODE:toggle"); return true; }
  if (command.startsWith("knob:")) {
    String value=command.substring(5);
    if (value!="left" && value!="right" && value!="press") return false;
    emitLine("BUTTON_LAB_SIMULATED_KNOB:"+value); return true;
  }
  if (command.startsWith("pot:") && numberIn(command.substring(4),0,1023)) {
    emitLine("BUTTON_LAB_SIMULATED_POT:"+command.substring(4)); return true;
  }
  String at;
  if (command=="audio:status") at="AT";
  else if (command=="audio:toggle") at="AT+PLAY=PP";
  else if (command=="audio:next") at="AT+PLAY=NEXT";
  else if (command=="audio:previous") at="AT+PLAY=LAST";
  else if (command.startsWith("audio:volume:") && numberIn(command.substring(13),0,30)) at="AT+VOL="+command.substring(13);
  else if (command.startsWith("audio:play:") && numberIn(command.substring(11),1,9999)) at="AT+PLAYNUM="+command.substring(11);
  else return false;
  Serial1.print(at); Serial1.print("\r\n");
  emitLine("BUTTON_LAB_AUDIO_SENT:"+at);
  return true;
}
void scanInputs() {
  uint32_t now=millis();
  for (uint8_t i=0;i<8;i++) {
    bool reading=digitalRead(buttons[i].pin);
    if (reading!=buttons[i].reading) { buttons[i].reading=reading; buttons[i].changed=now; }
    if (now-buttons[i].changed>=30 && reading!=buttons[i].stable) {
      buttons[i].stable=reading;
      if (reading==LOW) { keyLitAt[i]=now; emitLine("BUTTON_LAB_KEY:"+String(i+1)); }
    }
  }
  if (now-potAt>=10) {
    potAt=now;
    potFiltered=(potFiltered*3+(POT_REVERSED ? 1023-analogRead(A0) : analogRead(A0)))/4;
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
    if (c=='\n') {
      if (!audioOverflow && audioLine.length()) { audioReply=audioLine; emitLine("BUTTON_LAB_AUDIO:"+audioLine); }
      audioLine=""; audioOverflow=false;
    } else if (c!='\r') { if (audioLine.length()<100) audioLine+=c; else audioOverflow=true; }
  }
}
void centeredText(const String& text, int y, uint8_t size) {
  display.setTextSize(size);
  display.setCursor(max(0, (128 - (int)text.length()*6*size)/2), y);
  display.print(text);
}
void renderDisplay() {
  bool working = runState=="running";
  if (!oledReady || (!oledDirty && !working) || millis()-oledAt<(working?350:150)) return;
  oledAt=millis(); oledDirty=false;
  display.clearDisplay(); display.setTextSize(1); display.setTextColor(SSD1306_WHITE); display.setTextWrap(false);
  if (!displayLinked) {
    centeredText("CONNECT", 4, 2);
    centeredText(apMode?"WI-FI SETUP":"USB / WI-FI", 29, 1);
    centeredText(networkReady?WiFi.localIP().toString():"USB READY", 48, 1);
    display.display(); return;
  }
  display.setCursor(0,0); display.print(profile=="workflow"?"2 AI-DLC":profile=="custom"?"3 CUSTOM":"1 AI");
  if (working) {
    if ((millis()/350)%2) display.fillCircle(123,3,3,SSD1306_WHITE);
    else display.drawCircle(123,3,3,SSD1306_WHITE);
  }
  String title=stage; title.toUpperCase();
  if (stage=="question") title="ANSWER";
  if (stage=="ask_workflow") title="ASK";
  if (stage=="start_workflow") title="RUN NOW";
  if (stage=="browse") title="SCROLL";
  centeredText(title, title.length()>10?22:17, title.length()>10?1:2);
  String detail;
  if (stage=="question") detail="PICK 1-7";
  else if (stage=="model" && profile!="workflow") { const char* efforts[]={"LOW","MEDIUM","HIGH","XHIGH"}; detail=efforts[level]; }
  else if (profile=="workflow") { const char* modes[]={"MANUAL","GUIDE","STEP","AUTO CHECK","AUTO BUILD","FULL AUTO"}; detail=modes[level]; }
  else detail=stage=="build"?"HISTORY":stage=="denied"?"EDIT CURSOR":stage=="accept"?"SELECT":stage=="plan"?"PLAN PAGE":stage=="check"?"CHECK LOG":"SCROLL";
  centeredText(detail, 39, 1);
  String status=runState; status.toUpperCase();
  if (runState=="question") status="? ANSWER";
  if (runState=="error") status="! ERROR";
  centeredText(status, 55, 1);
  display.display();
}
String statusJson() {
  return "{\"board\":\"UNO R4 WiFi\",\"protocol\":3,\"boot\":"+jsonString(bootId)+",\"cursor\":"+String(sequence)+
    ",\"mode\":"+jsonString(apMode?"ap":"station")+",\"ip\":"+jsonString(WiFi.localIP().toString())+
    ",\"pot\":"+String(potFiltered)+",\"oled\":"+(oledReady?"true":"false")+",\"audioReply\":"+jsonString(audioReply)+"}";
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
  for(uint8_t i=0;i<8;i++){buttons[i]={uint8_t(i+2),HIGH,HIGH,0};pinMode(buttons[i].pin,INPUT_PULLUP);buttons[i].reading=buttons[i].stable=digitalRead(buttons[i].pin);}
  potFiltered=potLastSent=POT_REVERSED ? 1023-analogRead(A0) : analogRead(A0); // No pull-up, no startup action.
  oledWire.begin();
  pixels.begin(); pixels.setBrightness(20); pixels.clear(); pixels.show();
  for(uint8_t address=0x3C;address<=0x3D && !oledReady;address++){oledWire.beginTransmission(address);if(oledWire.endTransmission()==0)oledReady=display.begin(SSD1306_SWITCHCAPVCC,address);}
  EEPROM.get(0,config);config.ssid[32]=0;config.password[64]=0;
  EEPROM.get(128,boot);if(boot.magic!=CONFIG_MAGIC){boot.magic=CONFIG_MAGIC;boot.count=0;}boot.count++;EEPROM.put(128,boot);bootId=String(boot.count,HEX);
  httpRequest.reserve(1536);usbLine.reserve(256);audioLine.reserve(101);
  startNetwork();renderDisplay();Serial1.print("AT\r\n");
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
void loop(){scanInputs();readSerial();serviceNetwork();renderDisplay();renderPixels();}
