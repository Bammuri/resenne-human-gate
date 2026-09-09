const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {AnalogLevelSelector, knobBinding} = require('../controls');

test('current ADC position selects predictable bands including a wide medium band', () => {
  for (const [position, expected] of [[0,0],[351,0],[352,1],[432,1],[511,1],[512,2],[592,2],[671,2],[672,3],[1023,3]]) {
    const selector = new AnalogLevelSelector(4);
    selector.sample(position,0);
    assert.equal(selector.candidate,expected);
  }
});
test('slow sweeps retain every intermediate band, saturate and never reverse', () => {
  for (const count of [4,6]) {
    const selector=new AnalogLevelSelector(count), seen=new Set();
    let previous=0;
    for(let adc=0;adc<=1023;adc++) {
      selector.sample(adc,adc);assert.ok(selector.candidate>=previous);
      previous=selector.candidate;seen.add(previous);
    }
    assert.equal(seen.size,count);assert.equal(previous,count-1);
    for(let adc=1023;adc>=0;adc--) {
      selector.sample(adc,2046-adc);assert.ok(selector.candidate<=previous);
      previous=selector.candidate;
    }
    assert.equal(previous,0);
  }
});
test('boundary noise and short spikes cannot change medium', () => {
  const selector=new AnalogLevelSelector(4);
  selector.sample(432,0);
  for(const adc of [505,518,510,527,516,511,520]) {
    selector.sample(adc,200);assert.equal(selector.candidate,1);
  }
  selector.sample(900,300);assert.equal(selector.next(1,350),null);
  selector.sample(432,360);assert.equal(selector.next(1,600),null);
});
test('fast full rotation still applies medium then high then xhigh with minimum dwell', () => {
  const selector=new AnalogLevelSelector(4);
  selector.sample(1023,0);
  assert.equal(selector.next(0,119),null);
  assert.equal(selector.next(0,120),1);selector.committed(120);
  assert.equal(selector.next(1,519),null);
  assert.equal(selector.next(1,520),2);selector.committed(520);
  assert.equal(selector.next(2,920),3);selector.committed(920);
  assert.equal(selector.next(3,2000),null);
  selector.sample(0,2100);
  assert.equal(selector.next(3,2220),2);
});
test('invalid samples are ignored without changing the target', () => {
  const selector=new AnalogLevelSelector(4);selector.sample(432,0);
  for(const value of [-1,1024,NaN,null,2.5,'432'])assert.equal(selector.sample(value,200),false);
  assert.equal(selector.candidate,1);
});

function appHarness() {
  let now=0,id=0;
  const timers=new Map(), calls=[];
  const deck={config:{mode:'agent'},knobAction:'model',question:null};
  const state={source:'hardware',effort:'low',busy:false,serialBusy:false};
  const context={AnalogLevelSelector,knobBinding,deck,state,serialBridge:{state:'connected'},
    browserTerminal:{nativePending:false},workflow:{data:{autonomy:0,running:false},pending:false},
    EFFORTS:['low','medium','high','xhigh'],AUTONOMY:[0,1,2,3,4,5],
    potContext:'',potPosition:null,potAnchor:null,potLevels:null,potLevelTimer:null,potLevelInFlight:false,
    performance:{now:()=>now},status(){},useKnob:(value)=>calls.push(value),
    knobIdentity:()=>JSON.stringify([deck.config.mode,deck.knobAction,deck.question,state.source]),
    setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:id=>timers.delete(id),
    applyEffort:async effort=>{calls.push(effort);state.effort=effort;return true;}};
  const source=fs.readFileSync(require.resolve('../app.js'),'utf8');
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function cancelPotLevels('),source.indexOf('const boardCallbacks =')),context);
  return {context,calls,timers,advance:async time=>{now=time;context.clearTimeout(context.potLevelTimer);context.potLevelTimer=null;await context.flushPotLevels();}};
}
test('first sample is used immediately, not discarded as a relative anchor', async () => {
  const h=appHarness();h.context.applyPot(432);await h.advance(150);
  assert.deepEqual(h.calls,['medium']);
  h.context.applyPot(480);await h.advance(700);
  assert.deepEqual(h.calls,['medium']);
});
test('busy handling retains the newest position and emits one step at a time', async () => {
  const h=appHarness();h.context.state.busy=true;
  h.context.applyPot(432);await h.advance(150);
  h.context.applyPot(1023);await h.advance(300);
  assert.deepEqual(h.calls,[]);
  h.context.state.busy=false;await h.advance(350);await h.advance(750);await h.advance(1150);
  assert.deepEqual(h.calls,['medium','high','xhigh']);
});
test('in-flight updates coalesce to the latest value without parallel commands', async () => {
  const h=appHarness();let finish;
  h.context.applyEffort=effort=>{h.calls.push(effort);return new Promise(resolve=>{finish=()=>{h.context.state.effort=effort;resolve(true);};});};
  h.context.applyPot(1023);const pending=h.advance(150);
  h.context.applyPot(432);await h.advance(300);
  assert.deepEqual(h.calls,['medium']);
  finish();await pending;await h.advance(800);
  assert.deepEqual(h.calls,['medium']);
});
test('mode changes, questions and disconnect cancel stale AI adjustments', async () => {
  for(const change of [c=>c.deck.config.mode='custom',c=>c.deck.question={id:'q'},c=>c.serialBridge.state='disconnected',c=>c.state.source='web']) {
    const h=appHarness();h.context.applyPot(1023);change(h.context);await h.advance(500);
    assert.deepEqual(h.calls,[]);
  }
  const h=appHarness();h.context.deck.config.mode='custom';h.context.applyPot(900);await h.advance(500);
  assert.deepEqual(h.calls,[]);assert.equal(h.context.potLevels,null);
});
test('rejected commands clear pending retries', async () => {
  const h=appHarness();h.context.applyEffort=async()=>{h.context.schedulePotLevels();return false;};
  h.context.applyPot(900);await h.advance(150);
  assert.equal(h.context.potLevelTimer,null);assert.equal(h.timers.size,0);
});
