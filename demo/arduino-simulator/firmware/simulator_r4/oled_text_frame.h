#pragma once
#include <stdint.h>
#include <string.h>

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
