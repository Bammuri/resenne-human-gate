const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../firmware/simulator_r4/simulator_r4.ino'), 'utf8');

test('OLED ready requires checked complete-frame transfer, not buffer allocation', () => {
  assert.doesNotMatch(source, /display\.display\(\)/);
  assert.match(source, /oledReady=oledTransport\.configure\(\) && oledTransport\.frame\(display\.getBuffer\(\)\)/);
  assert.match(source, /if\(!oledReady\) \{ oledFailures\+\+;oledDirty=true;oledForce=true;reportOled\(\);return; \}/);
});
test('OLED idle refresh and failed-transfer recovery cannot be suppressed by text cache', () => {
  assert.match(source, /now-oledSuccessAt>=5000/);
  assert.match(source, /if\(!refresh && hasPrevious && frame\.equals\(previous\)\)return/);
  assert.match(source, /oledRecoveries\+\+;refresh=true/);
  assert.match(source, /oledReady\?250UL:2000UL/);
});
test('OLED diagnostics do not trigger button/audio events', () => {
  assert.match(source, /command == "oled:info"\) \{ reportOled\(\);return true; \}/);
  assert.match(source, /command == "oled:refresh"\) \{ oledForce=true;oledDirty=true;return true; \}/);
  assert.match(source, /display\.begin\(SSD1306_SWITCHCAPVCC,oledTransport.address,false,false\)/);
});
test('bus recovery is bounded and never drives the OLED lines HIGH', () => {
  const recovery=source.slice(source.indexOf('bool releaseOledClock('),source.indexOf('bool beginOled('));
  assert.match(recovery, /micros\(\)-started<1000/);
  assert.match(recovery, /pulse<9/);
  assert.doesNotMatch(recovery, /digitalWrite\([^,]+,HIGH\)|INPUT_PULLUP/);
  assert.match(source, /clearOledBus\(\);\s+oledWire\.begin\(\)/);
});
test('startup shows the product name before normal mode/status content', () => {
  assert.match(source, /if\(!bootComplete\) \{\s+frame\.set\(0,"Re:senne"\);\s+frame\.set\(1,"STARTING\.\.\."\)/);
  assert.match(source, /else if\(!displayLinked\) \{\s+frame\.set\(0,"Re:senne"\)/);
  assert.match(source, /bootComplete=true;bootCheckpoint\("ready"\);oledDirty=true/);
});
