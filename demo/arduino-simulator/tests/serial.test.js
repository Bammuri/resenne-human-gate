const test = require('node:test');
const assert = require('node:assert/strict');
const { SerialLineParser, ButtonSerial } = require('../serial.js');
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
const READY = 'BUTTON_LAB_READY:2:slots=7:mode=8\n';

class FakePort {
  constructor(autoReady = true) { this.autoReady = autoReady; this.readyLine = READY; this.autoEcho = true; this.opens = 0; this.closes = 0; this.writes = []; }
  async open(options) {
    assert.equal(options.baudRate, 115200);
    this.opens++;
    this.readable = new ReadableStream({ start: controller => { this.controller = controller; } });
    this.writable = new WritableStream({ write: bytes => {
      const command = new TextDecoder().decode(bytes);
      this.writes.push(command);
      if (command === 'BUTTON_LAB_HELLO\n') {
        if (this.autoReady) this.emit(this.readyLine);
      } else if (command.startsWith('key:')) {
        if (this.failKeyWrite) throw new Error('USB write failed after uncertain delivery');
        if (this.autoEcho) this.emit(`BUTTON_LAB_SIMULATED_KEY:${command.slice(4)}`);
      } else if (command === 'mode:toggle\n') {
        if (this.autoEcho) this.emit('BUTTON_LAB_SIMULATED_MODE:toggle\n');
      } else if (command === 'yes\n' || command === 'no\n') {
        this.emit(`BUTTON_LAB_SIMULATED:${command}`);
      } else if (command.startsWith('action:')) {
        this.emit(`BUTTON_LAB_SIMULATED_ACTION:${command.slice(7)}`);
      } else if (command.startsWith('knob:')) {
        if (this.autoEcho) this.emit(`BUTTON_LAB_SIMULATED_KNOB:${command.slice(5)}`);
      } else if (command.startsWith('effort:')) {
        this.emit(`BUTTON_LAB_SIMULATED_EFFORT:${command.slice(7)}`);
      } else if (command.startsWith('display:')) { /* OLED updates do not trigger actions. */ }
      else assert.fail(`unexpected serial command: ${JSON.stringify(command)}`);
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

test('mode, legacy events, and question OLED state share the serial link without double dispatch', async () => {
  const port = new FakePort(), events = [];
  const bridge = new ButtonSerial(new FakeSerial(port), {
    onKey: (slot, origin) => events.push({ slot, origin }),
    onMode: () => events.push('duplicate mode'), onRevert: () => events.push('preview'),
    onAction: action => events.push(action),
  });
  try {
    await bridge.connect(); await tick();
    assert.equal(await bridge.sendDisplay('workflow', 'plan', 2, 'approved'), true);
    assert.equal(port.writes.at(-1), 'display:workflow:plan:2:approved\n');
    for (const profile of ['workflow', 'agent', 'custom']) {
      assert.equal(await bridge.sendDisplay(profile, 'question', 1, 'question'), true);
      assert.equal(port.writes.at(-1), `display:${profile}:question:1:question\n`);
    }
    assert.deepEqual(events, []);
    port.emit('BUTTON_LAB_MODE:toggle\nBUTTON_LAB_ACTION:denied\nBUTTON_LAB_REVERT:preview\n');
    await tick();
    assert.deepEqual(events, [{ slot: 8, origin: 'hardware' }, 'denied', 'preview']);
    await assert.rejects(() => bridge.sendDisplay('workflow', 'plan\nattack', 1, 'ready'));
  } finally { await bridge.disconnect(); }
});

test('line parser preserves split CRLF and drops whole oversized records', () => {
  const lines=[]; const parser=new SerialLineParser(line=>lines.push(line));
  parser.push('ye'); parser.push('s\r'); parser.push('\nno\ny'); parser.push('es\n');
  parser.push('x'.repeat(200)); parser.push('yes\nno\n');
  assert.deepEqual(lines,['yes','no','yes','no']);
});

test('handshake precedes button input; unknown lines cannot trigger choices', async () => {
  const port=new FakePort(false), choices=[];
  const bridge=new ButtonSerial(new FakeSerial(port),{onChoice:choice=>choices.push(choice)});
  try {
    await bridge.connect();
    assert.equal(bridge.state,'syncing');
    port.emit('yes\nBUTTON_LAB_KEY:1\nBUTTON_LAB_MODE:toggle\n'); await tick();
    assert.deepEqual(choices,[]);
    port.emit(READY.replace('\n', '\r\n')); await tick();
    assert.equal(bridge.state,'connected');
    assert.deepEqual(bridge.capabilities, { protocol: 2, functionSlots: 7, modeSlot: 8 });
    port.emit('ye'); port.emit('s\r\nno\nRUN something\nYES\n'); await tick();
    assert.deepEqual(choices,['yes','no']);
  } finally { await bridge.disconnect(); }
  assert.equal(port.closes,1);
});

test('on-screen choice round-trips through the board before becoming input', async () => {
  const port=new FakePort(), events=[];
  const bridge=new ButtonSerial(new FakeSerial(port),{onChoice:(choice,origin)=>events.push({choice,origin})});
  try {
    await bridge.connect(); await tick();
    await bridge.sendChoice('yes'); await tick();
    assert.deepEqual(port.writes,['BUTTON_LAB_HELLO\n','yes\n']);
    assert.deepEqual(events,[{choice:'yes',origin:'simulator'}]);
    port.emit('BUTTON_LAB_INPUT:no\n'); await tick();
    assert.deepEqual(events,[{choice:'yes',origin:'simulator'},{choice:'no',origin:'hardware'}]);
    await assert.rejects(() => bridge.sendChoice('maybe'), /지원하지 않는/);
  } finally { await bridge.disconnect(); }
});

test('seven physical slots and the eighth MODE slot have one shared input callback', async () => {
  const port = new FakePort(), events = [];
  const bridge = new ButtonSerial(new FakeSerial(port), {
    onKey: (slot, origin) => events.push({ slot, origin }),
    onMode: () => assert.fail('onMode must not duplicate onKey(8)'),
  });
  try {
    await bridge.connect(); await tick();
    for (let slot = 1; slot <= 7; slot++) port.emit(`BUTTON_LAB_KEY:${slot}\n`);
    port.emit('BUTTON_LAB_MODE:toggle\nBUTTON_LAB_KEY:0\nBUTTON_LAB_KEY:8\nBUTTON_LAB_KEY:9\nBUTTON_LAB_KEY:01\n');
    await tick();
    assert.deepEqual(events, Array.from({ length: 8 }, (_, i) => ({ slot: i + 1, origin: 'hardware' })));
    events.length = 0;
    for (let slot = 1; slot <= 8; slot++) await bridge.sendKey(slot);
    assert.deepEqual(events, Array.from({ length: 8 }, (_, i) => ({ slot: i + 1, origin: 'simulator' })));
    assert.deepEqual(port.writes.slice(1), ['key:1\n', 'key:2\n', 'key:3\n', 'key:4\n', 'key:5\n', 'key:6\n', 'key:7\n', 'mode:toggle\n']);
    for (const slot of [0, 9, -1, 1.5, '1', NaN]) await assert.rejects(() => bridge.sendKey(slot), /버튼 번호/);
  } finally { await bridge.disconnect(); }
});

test('unsolicited, mismatched, and duplicate key acknowledgements cannot execute an action', async () => {
  const port = new FakePort(), events = [];
  port.autoEcho = false;
  const bridge = new ButtonSerial(new FakeSerial(port), { onKey: (slot, origin) => events.push({ slot, origin }) });
  try {
    await bridge.connect(); await tick();
    port.emit('BUTTON_LAB_SIMULATED_KEY:2\nBUTTON_LAB_SIMULATED_MODE:toggle\n');
    await tick();
    assert.deepEqual(events, []);
    let completed = false;
    const sent = bridge.sendKey(2).then(() => { completed = true; });
    await tick();
    port.emit('BUTTON_LAB_SIMULATED_KEY:1\nBUTTON_LAB_SIMULATED_MODE:toggle\n');
    await tick();
    assert.equal(completed, false);
    assert.deepEqual(events, []);
    assert.equal(await bridge.sendDisplay('agent', 'question', 1, 'question'), false);
    await assert.rejects(() => bridge.sendKey(3), /이전 시리얼/);
    port.emit('BUTTON_LAB_SIMULATED_KEY:2\nBUTTON_LAB_SIMULATED_KEY:2\n');
    await sent; await tick();
    assert.deepEqual(events, [{ slot: 2, origin: 'simulator' }]);
  } finally { await bridge.disconnect(); }
});

test('MODE retains the legacy callback when the new slot callback is absent', async () => {
  const port = new FakePort(), events = [];
  const bridge = new ButtonSerial(new FakeSerial(port), { onMode: origin => events.push(origin) });
  try {
    await bridge.connect(); await tick();
    port.emit('BUTTON_LAB_MODE:toggle\n'); await tick();
    await bridge.sendKey(8);
    assert.deepEqual(events, ['hardware', 'simulator']);
  } finally { await bridge.disconnect(); }
});

test('older or incompatible firmware is rejected with the correct eight-button wiring instructions', async () => {
  for (const readyLine of ['BUTTON_LAB_READY:1\n', 'BUTTON_LAB_READY:2:slots=8:mode=9\n']) {
    const port = new FakePort(), states = [], keys = [];
    port.readyLine = readyLine;
    const bridge = new ButtonSerial(new FakeSerial(port), {
      onState: (state, message) => states.push({ state, message }), onKey: slot => keys.push(slot),
    });
    try {
      await bridge.connect(); await tick(); await tick();
      assert.equal(bridge.state, 'error');
      assert.equal(bridge.capabilities, null);
      assert.equal(port.closes, 1);
      assert.equal(states.some(({ state }) => state === 'connected'), false);
      assert.match(states.at(-1).message, /yes_no\.ino.*D2~D8.*D9 MODE/);
      assert.deepEqual(keys, []);
    } finally { if (bridge.port) await bridge.disconnect(); }
  }
});

test('disconnect rejects a pending key without dispatching a fallback input', async () => {
  const port = new FakePort(), keys = [];
  port.autoEcho = false;
  const bridge = new ButtonSerial(new FakeSerial(port), { onKey: slot => keys.push(slot) });
  await bridge.connect(); await tick();
  const rejected = assert.rejects(bridge.sendKey(1), /USB 연결이 해제/);
  await tick();
  await bridge.disconnect();
  await rejected;
  assert.deepEqual(keys, []);
});

test('a timed-out key invalidates the link so its late echo cannot acknowledge the next press', async () => {
  const port = new FakePort(), keys = [], states = [];
  port.autoEcho = false;
  const bridge = new ButtonSerial(new FakeSerial(port), {
    onKey: slot => keys.push(slot),
    onState: (state, message) => {
      states.push({ state, message });
      if (state === 'disconnecting') port.emit('BUTTON_LAB_SIMULATED_KEY:1\n');
    },
  });
  try {
    await bridge.connect(); await tick();
    await assert.rejects(bridge.sendKey(1), /응답하지 않았/);
    await assert.rejects(bridge.sendKey(1), /먼저 연결/);
    await tick();
    assert.equal(bridge.state, 'error');
    assert.equal(port.closes, 1);
    assert.match(states.at(-1).message, /다시 연결/);
    assert.deepEqual(keys, []);
    // A new connection must finish its handshake; buffered old records before
    // READY are discarded, and the next key needs its own acknowledgement.
    port.autoReady = false;
    await bridge.connect();
    assert.equal(bridge.state, 'syncing');
    await assert.rejects(bridge.sendKey(1), /먼저 연결/);
    port.emit('BUTTON_LAB_SIMULATED_KEY:1\n' + READY);
    await tick();
    assert.deepEqual(keys, []);
    port.autoEcho = true;
    await bridge.sendKey(1);
    assert.deepEqual(keys, [1]);
    assert.equal(port.writes.filter(command => command === 'key:1\n').length, 2);
  } finally { await bridge.disconnect(); }
});

test('an uncertain USB write failure also requires a fresh handshake before another key', async () => {
  const port = new FakePort(), keys = [];
  const bridge = new ButtonSerial(new FakeSerial(port), { onKey: slot => keys.push(slot) });
  try {
    await bridge.connect(); await tick();
    port.failKeyWrite = true;
    await assert.rejects(bridge.sendKey(1), /전송하지 못했/);
    await assert.rejects(bridge.sendKey(1), /먼저 연결/);
    await tick();
    assert.equal(bridge.state, 'error');
    assert.equal(port.closes, 1);
    assert.deepEqual(keys, []);
    port.failKeyWrite = false;
    await bridge.connect(); await tick();
    await bridge.sendKey(1);
    assert.deepEqual(keys, [1]);
  } finally { await bridge.disconnect(); }
});

test('all deck actions and reasoning changes wait for Arduino acknowledgement', async () => {
  const port=new FakePort(), actions=[], efforts=[];
  const bridge=new ButtonSerial(new FakeSerial(port),{
    onAction:(action,origin)=>actions.push({action,origin}),
    onEffort:(effort,origin)=>efforts.push({effort,origin}),
  });
  try {
    await bridge.connect(); await tick();
    await bridge.sendAction('plan');
    await bridge.sendEffort('high');
    port.emit('BUTTON_LAB_ACTION:accept\nBUTTON_LAB_EFFORT:xhigh\n'); await tick();
    assert.deepEqual(port.writes,['BUTTON_LAB_HELLO\n','action:plan\n','effort:high\n']);
    assert.deepEqual(actions,[{action:'plan',origin:'simulator'},{action:'accept',origin:'hardware'}]);
    assert.deepEqual(efforts,[{effort:'high',origin:'simulator'},{effort:'xhigh',origin:'hardware'}]);
    await assert.rejects(() => bridge.sendAction('delete'), /지원하지 않는/);
    await assert.rejects(() => bridge.sendEffort('extreme'), /지원하지 않는/);
  } finally { await bridge.disconnect(); }
});

test('disconnect cancels the pending reader and can reconnect without duplicates', async () => {
  const port=new FakePort(), choices=[];
  const bridge=new ButtonSerial(new FakeSerial(port),{onChoice:choice=>choices.push(choice)});
  await bridge.connect(); await tick();
  await bridge.disconnect();
  assert.equal(bridge.state,'disconnected');
  await bridge.connect(); await tick();
  port.emit('no\n'); await tick();
  await bridge.disconnect();
  assert.deepEqual(choices,['no']);
  assert.equal(port.opens,2); assert.equal(port.closes,2);
});

test('unplug ends the read loop and reports a reconnectable error', async () => {
  const port=new FakePort(); const bridge=new ButtonSerial(new FakeSerial(port));
  await bridge.connect(); await tick();
  port.controller.error(new Error('USB removed'));
  await tick(); await tick();
  assert.equal(bridge.state,'error');
  assert.equal(port.closes,1);
});

test('cancelled picker and unsupported browsers remain usable', async () => {
  const serial=new FakeSerial(null);
  serial.requestPort=async()=>{ throw new DOMException('Cancelled','NotFoundError'); };
  const bridge=new ButtonSerial(serial);
  await bridge.connect();
  assert.equal(bridge.state,'disconnected');
  const unsupported=new ButtonSerial(undefined);
  await unsupported.connect();
  assert.equal(unsupported.state,'unsupported');
});

test('contextual knob rotation and press wait for matching Arduino echoes', async () => {
  const port = new FakePort(), events = [];
  const bridge = new ButtonSerial(new FakeSerial(port), { onKnob: (value, origin) => events.push([value, origin]) });
  try {
    await bridge.connect(); await tick();
    for (const value of ['left','right','press']) await bridge.sendKnob(value);
    assert.deepEqual(events, [['left','simulator'],['right','simulator'],['press','simulator']]);
    port.emit('BUTTON_LAB_KNOB:left\nBUTTON_LAB_KNOB:right\nBUTTON_LAB_KNOB:press\n');
    await tick(); assert.equal(events.length,6);
    port.emit('BUTTON_LAB_SIMULATED_KNOB:press\nBUTTON_LAB_KNOB:invalid\n');
    await tick(); assert.equal(events.length,6);
    await assert.rejects(()=>bridge.sendKnob('high'));
  } finally { await bridge.disconnect(); }
});

test('UNO R4 analog firmware accepts eight generic buttons and bounded A0 values', async () => {
  const port=new FakePort();port.readyLine='BUTTON_LAB_READY:3:slots=8:knob=analog\n';
  const events=[];const bridge=new ButtonSerial(new FakeSerial(port),{onKey:(slot)=>events.push(['key',slot]),onPot:(value)=>events.push(['pot',value])});
  try {
    await bridge.connect();await tick();assert.equal(bridge.capabilities.analogKnob,true);
    port.emit('BUTTON_LAB_KEY:8\nBUTTON_LAB_POT:512\nBUTTON_LAB_POT:1024\n');await tick();
    assert.deepEqual(events,[['key',8],['pot',512]]);
  } finally {await bridge.disconnect();}
});

test('Wi-Fi transport relays acknowledged keys and A0 without replaying old events', async () => {
  const { ButtonWifi } = require('../serial');
  const pending=[], seen=[], calls=[];
  const request=async (path,payload)=>{
    calls.push([path,payload]);
    if(path.endsWith('/connect'))return {ip:'192.168.4.1',pot:512};
    if(path.endsWith('/events'))return {events:pending.splice(0)};
    if(path.endsWith('/command')) {
      pending.push({line:payload.command==='key:2'?'BUTTON_LAB_SIMULATED_KEY:2':'BUTTON_LAB_AUDIO_SENT:AT+VOL=10'});
      return {ok:true};
    }
    return {ok:true};
  };
  const bridge=new ButtonWifi(request,{onKey:(slot,origin)=>seen.push([slot,origin]),onPot:value=>seen.push(['pot',value])});
  try {
    await bridge.connect('192.168.4.1','test-key-123456789');
    await bridge.sendKey(2);await bridge.sendAudio('audio:volume:10');
    pending.push({line:'BUTTON_LAB_KEY:8'},{line:'BUTTON_LAB_POT:700'});
    await new Promise(resolve=>setTimeout(resolve,150));
    assert.deepEqual(seen,[['pot',512],[2,'simulator'],[8,'hardware'],['pot',700]]);
    assert.equal(calls.filter(([path])=>path.endsWith('/command')).length,2);
  } finally {await bridge.disconnect();}
});
