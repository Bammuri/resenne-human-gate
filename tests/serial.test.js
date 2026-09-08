const test = require('node:test');
const assert = require('node:assert/strict');
const { SerialLineParser, ButtonSerial, parseDeviceLine } = require('../serial.js');
const tick = () => new Promise(resolve => setTimeout(resolve, 15));

class FakePort {
  constructor(autoReady = true) { this.autoReady = autoReady; this.opens = 0; this.closes = 0; this.writes = []; }
  async open(options) {
    assert.equal(options.baudRate, 115200);
    this.opens++;
    this.readable = new ReadableStream({ start: controller => { this.controller = controller; } });
    this.writable = new WritableStream({ write: bytes => {
      const text = new TextDecoder().decode(bytes);
      this.writes.push(text);
      if (text === 'BUTTON_LAB_HELLO\n' && this.autoReady) this.emit('BUTTON_LAB_READY:1\n');
    }});
  }
  emit(text) { this.controller.enqueue(new TextEncoder().encode(text)); }
  async close() {
    assert.equal(this.readable.locked, false);
    assert.equal(this.writable.locked, false);
    this.closes++;
  }
}
class FakeSerial extends EventTarget {
  constructor(port) { super(); this.port = port; }
  async requestPort() { return this.port; }
}

test('parseDeviceLine maps only known BindDeck lines and ignores the rest', () => {
  assert.equal(parseDeviceLine('BTN:0'), 'yes');
  assert.equal(parseDeviceLine('BTN:1'), 'no');
  assert.equal(parseDeviceLine('BTN:2'), 'stop');
  assert.equal(parseDeviceLine('BTN:8'), 'confirm');
  assert.equal(parseDeviceLine('ENC:CW'), 'nav_down');
  assert.equal(parseDeviceLine('ENC:VDN'), 'nav_down');
  assert.equal(parseDeviceLine('ENC:CCW'), 'nav_up');
  assert.equal(parseDeviceLine('ENC:VUP'), 'nav_up');
  for (const line of ['BTN:3', 'BTN:7', 'BTN:9', 'BTN:', 'BTN:00', 'ENC:XX', 'ENC:', 'btn:0', 'RUN something', 'BUTTON_LAB_READY:1', '', 42, null, undefined])
    assert.equal(parseDeviceLine(line), null, `${line} should not map`);
});

test('line parser preserves split CRLF and drops whole oversized records', () => {
  const lines = []; const parser = new SerialLineParser(line => lines.push(line));
  parser.push('BTN:'); parser.push('0\r'); parser.push('\nBTN:1\nENC'); parser.push(':CW\n');
  // The 200-char overflow record is dropped up to its terminating newline, so the
  // 'BTN:2' that shares that record is discarded; only the next line survives.
  parser.push('x'.repeat(200)); parser.push('BTN:2\nBTN:8\n');
  assert.deepEqual(lines, ['BTN:0', 'BTN:1', 'ENC:CW', 'BTN:8']);
});

test('handshake precedes button input; unknown lines cannot trigger choices', async () => {
  const port = new FakePort(false), choices = [];
  const bridge = new ButtonSerial(new FakeSerial(port), { onChoice: choice => choices.push(choice) });
  try {
    await bridge.connect();
    assert.equal(bridge.state, 'syncing');
    port.emit('BTN:0\n'); await tick();
    assert.deepEqual(choices, []);                       // no input before the handshake
    port.emit('BUTTON_LAB_READY:1\r\n'); await tick();
    assert.equal(bridge.state, 'connected');
    port.emit('BTN:'); port.emit('0\r\nBTN:1\nRUN thing\nBTN:9\nENC:CW\n'); await tick();
    assert.deepEqual(choices, ['yes', 'no', 'nav_down']); // BTN:9 and RUN thing are ignored
  } finally { await bridge.disconnect(); }
  assert.equal(port.closes, 1);
});

test('OLED feedback is pushed only after the handshake completes', async () => {
  const port = new FakePort();
  const bridge = new ButtonSerial(new FakeSerial(port));
  await bridge.connect(); await tick();
  assert.equal(bridge.state, 'connected');
  await bridge.sendMessage('ACTIVE YES'); await tick();
  assert.ok(port.writes.includes('CMD:MSG:ACTIVE YES\n'));
  await bridge.disconnect();
  await bridge.sendMessage('IGNORED'); await tick();     // no-op when disconnected
  assert.ok(!port.writes.includes('CMD:MSG:IGNORED\n'));
});

test('disconnect cancels the pending reader and can reconnect without duplicates', async () => {
  const port = new FakePort(), choices = [];
  const bridge = new ButtonSerial(new FakeSerial(port), { onChoice: choice => choices.push(choice) });
  await bridge.connect(); await tick();
  await bridge.disconnect();
  assert.equal(bridge.state, 'disconnected');
  await bridge.connect(); await tick();
  port.emit('BTN:1\n'); await tick();
  await bridge.disconnect();
  assert.deepEqual(choices, ['no']);
  assert.equal(port.opens, 2); assert.equal(port.closes, 2);
});

test('unplug ends the read loop and reports a reconnectable error', async () => {
  const port = new FakePort(); const bridge = new ButtonSerial(new FakeSerial(port));
  await bridge.connect(); await tick();
  port.controller.error(new Error('USB removed'));
  await tick(); await tick();
  assert.equal(bridge.state, 'error');
  assert.equal(port.closes, 1);
});

test('cancelled picker and unsupported browsers remain usable', async () => {
  const serial = new FakeSerial(null);
  serial.requestPort = async () => { throw new DOMException('Cancelled', 'NotFoundError'); };
  const bridge = new ButtonSerial(serial);
  await bridge.connect();
  assert.equal(bridge.state, 'disconnected');
  const unsupported = new ButtonSerial(undefined);
  await unsupported.connect();
  assert.equal(unsupported.state, 'unsupported');
});
