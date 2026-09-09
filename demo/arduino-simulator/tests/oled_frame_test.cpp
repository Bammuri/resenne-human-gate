#include "../firmware/simulator_r4/oled_text_frame.h"
#include <assert.h>
#include <string>
#include <vector>

struct Canvas {
  int size=1,x=0,y=0;
  std::vector<std::string> labels;
  std::vector<int> blocks;
  void bounds(int left,int top,int width,int height) {
    assert(left>=0 && top>=0 && left+width<=128 && top+height<=64);
  }
  void drawRect(int x,int y,int w,int h,int) { bounds(x,y,w,h); }
  void fillRect(int x,int y,int w,int h,int) { bounds(x,y,w,h);blocks.push_back(x); }
  void fillCircle(int x,int y,int r,int) { bounds(x-r,y-r,2*r+1,2*r+1); }
  void setTextSize(int value) { size=value; }
  void setCursor(int left,int top) { x=left;y=top; }
  void print(const char* text) { bounds(x,y,strlen(text)*6*size,8*size);labels.push_back(text); }
};

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
  Canvas initial;
  OledRunningFrame::draw(initial,0);
  assert(initial.labels[0]=="AI WORKING" && initial.labels[1]=="RUNNING");
  assert(initial.labels[2]=="00:00");
  for(uint32_t ms: {250U,1500U,1750U,65000U,3600000U,UINT32_MAX}) {
    Canvas next;OledRunningFrame::draw(next,ms);
    assert(next.blocks.size()==3);
    if(ms==250)assert(next.blocks!=initial.blocks);
    if(ms==1750)assert(next.blocks==initial.blocks);
    if(ms==65000)assert(next.labels[2]=="01:05");
    if(ms==3600000)assert(next.labels[2]=="60:00");
    assert(next.size==1);
  }
}
