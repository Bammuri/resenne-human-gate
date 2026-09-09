const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../firmware/simulator_r4/simulator_r4.ino'), 'utf8');

test('working-reference startup selects music mode and starts quietly', () => {
  const setup = source.slice(source.indexOf('void setup()'), source.indexOf('void renderPixels()'));
  const commands = [...setup.matchAll(/sendAudio\("([^"]+)"\)/g)].map(m => m[1]);
  assert.deepEqual(commands, ['AT+VOL=0', 'AT+FUNCTION=1', 'AT+AMP=OFF', 'AT+PLAYMODE=3', 'AT+VOL=3']);
  assert.match(setup, /sendAudio\("AT\+FUNCTION=1"\);waitWithUsb\(2000\)/);
});
test('paced playback cannot abort solely because an OK is missing', () => {
  assert.match(source, /millis\(\)-audioSentAt<audioGap/);
  assert.doesNotMatch(source, /audioAwaiting|No OK response|AT\+TIME=/);
  assert.match(source, /c=='\\n' \|\| c=='\\r'/);
});
test('amplifier is enabled before file playback and STOP cancels queued starts', () => {
  const playback=source.slice(source.indexOf('void queueButtonSound('),source.indexOf('bool queueAudio('));
  assert.ok(playback.indexOf('queueAudio("AT+AMP=ON")')<playback.indexOf('queueAudio("AT+PLAYFILE='));
  assert.doesNotMatch(playback,/queueAudio\("AT\+AMP=OFF"\)/);
  assert.match(source,/audioGap=command=="AT\+AMP=ON"\?500:250/);
  assert.match(source,/profile=="custom" && slot==7\) \{ stopAudio\(\);return; \}/);
  const stop=source.match(/void stopAudio\(\) \{([\s\S]*?)\n\}/)[1];
  assert.match(stop,/audioQueueSize=0;volumePending=false/);
  assert.match(stop,/sendAudio\("AT\+AMP=OFF"\)/);
});
test('quiet sound test does not dispatch a simulator key', () => {
  const block = source.match(/if\(command=="audio:test"\) \{([\s\S]*?)\n  \}/)[1];
  assert.match(block, /AT\+VOL=3/);
  assert.match(block, /AT\+PLAYFILE=\/sound1\.mp3/);
  assert.doesNotMatch(block, /BUTTON_LAB_KEY|SIMULATED_KEY/);
});
test('custom profile enables volume and button presses do not disable it', () => {
  assert.match(source,/volumeControl=p=="custom"/);
  const key=source.slice(source.indexOf('void queueButtonSound('),source.indexOf('bool queueAudio('));
  assert.match(key,/volumeControl=profile=="custom"/);
  assert.doesNotMatch(key,/volumeControl=false|slot==5/);
  assert.match(source,/audioVolume\+\(value=="right"\?1:-1\),0,30/);
});
test('startup waits continue serving USB and OLED I2C has a bounded timeout', () => {
  const wait=source.match(/void waitWithUsb\(uint32_t duration\) \{([\s\S]*?)\n\}/)[1];
  assert.match(wait,/readSerial\(\);delay\(1\)/);
  assert.match(source,/oledWire\.setWireTimeout\(25000\)/);
  assert.match(source,/bootComplete=true;bootCheckpoint\("ready"\)/);
  const setup=source.slice(source.indexOf('void setup()'),source.indexOf('void renderPixels()'));
  assert.doesNotMatch(setup,/\bdelay\(/);
});
