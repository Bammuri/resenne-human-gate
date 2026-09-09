#include "../firmware/simulator_r4/oled_transport.h"
#include <assert.h>
#include <vector>

struct FakeWire {
  uint8_t currentAddress=0, attachedAddress=0x3C;
  size_t failedTransaction=0, transactions=0, capacity=32;
  std::vector<uint8_t> pending;
  std::vector<std::vector<uint8_t>> writes;
  void beginTransmission(uint8_t address) { currentAddress=address;pending.clear(); }
  size_t write(uint8_t value) {
    if(pending.size()>=capacity)return 0;
    pending.push_back(value);return 1;
  }
  uint8_t endTransmission() {
    transactions++;writes.push_back(pending);
    if(failedTransaction==transactions)return 5;
    return currentAddress==attachedAddress?0:2;
  }
};
int main() {
  FakeWire bus;OledTransport<FakeWire> oled(bus);
  assert(oled.probe() && oled.address==0x3C);
  assert(oled.configure());
  uint8_t pixels[1024];
  for(size_t i=0;i<sizeof(pixels);i++)pixels[i]=uint8_t(i*7);
  bus.writes.clear();
  assert(oled.frame(pixels));
  assert(bus.writes.size()==73); // 8 pages * (cursor + 8 chunks), then ON.
  size_t offset=0;
  for(size_t page=0;page<8;page++) {
    assert((bus.writes[page*9]==std::vector<uint8_t>{0x00,uint8_t(0xB0+page),0x00,0x10}));
    for(size_t chunk=1;chunk<=8;chunk++) {
      const auto& packet=bus.writes[page*9+chunk];
      assert(packet.size()==17 && packet[0]==0x40);
      for(size_t i=1;i<packet.size();i++)assert(packet[i]==pixels[offset++]);
    }
  }
  assert(offset==1024);
  assert((bus.writes.back()==std::vector<uint8_t>{0x00,0xAF}));
  bus.failedTransaction=bus.transactions+3;
  assert(!oled.frame(pixels));assert(oled.error==5);
  assert(bus.transactions==bus.failedTransaction); // No further sends after failure.
  bus.failedTransaction=0;
  assert(oled.configure() && oled.frame(pixels) && oled.error==0);
  bus.capacity=2;assert(!oled.configure() && oled.error==1);
  bus.capacity=32;bus.attachedAddress=0x3D;
  assert(oled.probe() && oled.address==0x3D);
  bus.attachedAddress=0;assert(!oled.probe() && oled.address==0 && oled.error==2);
  assert(!oled.frame(pixels));
}
