#pragma once
#include <stdint.h>
#include <string.h>
#include <stdio.h>

// SSD1306 128x64: 6x8 font, 20 characters, 4px edge padding, 14px row pitch.
struct OledTextFrame {
  static const uint8_t ROWS=4, COLUMNS=20, LEFT=4, TOP=4;
  char lines[ROWS][COLUMNS+1] = {};
  static uint8_t rowY(uint8_t row) { return TOP+row*14; }
  void set(uint8_t row, const char* text) {
    if(row>=ROWS)return;
    memset(lines[row],0,sizeof(lines[row]));
    if(!text)return;
    for(uint8_t col=0;col<COLUMNS && text[col];col++) {
      unsigned char c=text[col];
      lines[row][col]=(c>=32 && c<=126)?c:'?';
    }
  }
  bool equals(const OledTextFrame& other) const {
    return memcmp(lines,other.lines,sizeof(lines))==0;
  }
};

// Same 128x64 layout as the web OLED. Blocks indicate activity, not percent.
struct OledRunningFrame {
  template<class Canvas> static void draw(Canvas& canvas, uint32_t elapsedMs) {
    canvas.drawRect(0,0,128,64,1);
    canvas.fillCircle(29,8,2,1);
    canvas.setCursor(37,5);canvas.print("AI WORKING");
    canvas.setTextSize(2);
    canvas.setCursor(22,21);canvas.print("RUNNING");
    canvas.setTextSize(1);
    uint8_t phase=(elapsedMs/250)%7;
    for(uint8_t i=0;i<7;i++) {
      uint8_t x=17+i*14;
      canvas.drawRect(x,43,10,6,1);
      if((i+7-phase)%7<3)canvas.fillRect(x+1,44,8,4,1);
    }
    uint32_t seconds=elapsedMs/1000;
    char timer[16];
    snprintf(timer,sizeof(timer),"%02lu:%02lu",(unsigned long)(seconds/60),(unsigned long)(seconds%60));
    canvas.setCursor((128-strlen(timer)*6)/2,53);canvas.print(timer);
  }
};
