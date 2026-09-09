// Temporary USB <-> DFPlayer diagnostic. No Wi-Fi, OLED, LED or button drivers.
// :baud N changes only the UNO UART (never the DFPlayer's stored settings).
String input;
void setup(){Serial.begin(115200);Serial1.begin(115200);}
void loop(){
  while(Serial1.available())Serial.write(Serial1.read());
  while(Serial.available()){
    char c=Serial.read();
    if(c=='\n'){
      if(input.startsWith(":baud ")){
        long baud=input.substring(6).toInt();
        if(baud==9600||baud==19200||baud==38400||baud==57600||baud==115200){
          Serial1.end();Serial1.begin(baud);Serial.print("UART=");Serial.println(baud);
        }
      }else if(input.length()){
        Serial1.print(input);Serial1.print("\r\n");
      }
      input="";
    }else if(c!='\r' && input.length()<128)input+=c;
  }
}
