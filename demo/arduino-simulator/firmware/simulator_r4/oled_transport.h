#pragma once
#include <stdint.h>
#include <stddef.h>

// SSD1306 128x64, internal charge pump. Keep each I2C transfer well below
// the UNO R4's 25ms timeout (17 bytes at 100kHz is about 1.6ms).
template<class Bus> class OledTransport {
 public:
  Bus& bus;
  uint8_t address=0, error=0;
  explicit OledTransport(Bus& wire):bus(wire) {}
  bool probe() {
    for(uint8_t candidate=0x3C;candidate<=0x3D;candidate++) {
      bus.beginTransmission(candidate);
      error=bus.endTransmission();
      if(!error) { address=candidate;return true; }
    }
    address=0;return false;
  }
  bool write(uint8_t control,const uint8_t* data,size_t size) {
    bus.beginTransmission(address);
    bool buffered=bus.write(control)==1;
    for(size_t i=0;i<size;i++) if(bus.write(data[i])!=1)buffered=false;
    error=bus.endTransmission();
    if(!buffered && !error)error=1;
    return error==0;
  }
  bool configure() {
    // Same panel settings as Adafruit's 128x64 initialization, but page
    // addressing and every result checked. No OFF/ON flicker on refresh.
    const uint8_t commands[]={
      0xD5,0x80,0xA8,0x3F,0xD3,0x00,0x40,0x8D,0x14,
      0x20,0x02,0xA1,0xC8,0xDA,0x12,0x81,0xCF,
      0xD9,0xF1,0xDB,0x40,0xA4,0xA6,0x2E
    };
    return write(0x00,commands,sizeof(commands));
  }
  bool frame(const uint8_t* pixels) {
    if(!pixels || !address) { error=4;return false; }
    // Explicit row/column on EVERY page: a lost transfer cannot shift the
    // next page's text. Stop immediately on NACK/timeout and retry later.
    for(uint8_t page=0;page<8;page++) {
      const uint8_t cursor[]={uint8_t(0xB0+page),0x00,0x10};
      if(!write(0x00,cursor,sizeof(cursor)))return false;
      for(uint16_t column=0;column<128;column+=16)
        if(!write(0x40,pixels+page*128+column,16))return false;
    }
    const uint8_t on=0xAF;
    return write(0x00,&on,1);
  }
};
