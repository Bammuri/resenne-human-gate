#include "../firmware/simulator_r4/oled_text_frame.h"
#include <assert.h>

int main() {
  OledTextFrame frame, copy;
  assert(frame.equals(copy));
  frame.set(0,"123456789012345678901234567890");
  assert(strlen(frame.lines[0])==20);
  assert(frame.lines[0][20]=='\0');
  frame.set(0,"READY");
  assert(strcmp(frame.lines[0],"READY")==0);
  for(int i=6;i<=20;i++)assert(frame.lines[0][i]==0);
  frame.set(1,"ABC\n\r\xFF");
  assert(strcmp(frame.lines[1],"ABC???")==0);
  copy=frame;frame.set(4,"invalid");assert(frame.equals(copy));
  for(uint8_t row=0;row<4;row++) {
    assert(OledTextFrame::rowY(row)>=4);
    assert(OledTextFrame::rowY(row)+8<=60);
    if(row<3)assert(OledTextFrame::rowY(row)+8<OledTextFrame::rowY(row+1));
  }
  assert(OledTextFrame::LEFT>=4);
  assert(OledTextFrame::LEFT+OledTextFrame::COLUMNS*6<=124);
}
