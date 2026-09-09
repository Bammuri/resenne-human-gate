const test = require('node:test');
const assert = require('node:assert/strict');
const { terminalQuestion, terminalAnswer, terminalMode } = require('../controls');
const { DeckControls, DECK_MODES } = require('../controls');

test('custom mode always binds the knob to volume without reserving key five', () => {
  const {knobBinding} = require('../controls');
  for(const action of [null,'model','stop','audio_stop']) {
    assert.equal(knobBinding('custom',action,null).rotate,'volume');
    assert.equal(knobBinding('custom',action,{id:'q'}).rotate,'volume');
  }
  assert.equal(knobBinding('agent','model',null).rotate,'effort');
  assert.equal(knobBinding('workflow',null,null).rotate,'autonomy');
  const deck = new DeckControls([]);
  deck.configure({...deck.config,mode:'custom'});
  assert.equal(deck.capture(5).action,'prompt');
  assert.equal(deck.capture(7).action,'audio_stop');
});

test('custom audio keys have fixed labels and never dispatch AI answers', () => {
  const deck = new DeckControls(Array.from({length:7},(_,i)=>['stage'+i,'Stage']));
  assert.equal(deck.capture(7).action,'stop');
  deck.configure({...deck.config,mode:'workflow'});
  assert.equal(deck.capture(7).action,'stage6');
  deck.configure({...deck.config,mode:'custom'});
  assert.equal(deck.capture(7).action,'audio_stop');
  assert.deepEqual([1,2,3,4].map(i=>deck.capture(i).label),['거제야호','오이시','러브어택','대자부']);
  assert.equal(deck.capture(8).action,'mode');
  deck.update('terminal',{generation:'g',question:{id:'q',options:Array.from({length:7},(_,i)=>({id:String(i+1),label:'choice'}))}});
  assert.equal(deck.capture(7).action,'audio_stop');
  assert.equal(deck.capture(1).action,'board_sound');
  assert.equal(deck.capture(5).action,'answer');
  assert.equal(deck.isCurrent(deck.capture(7)),true);
});

test('MODEL dispatches immediately on the first press for every input source', async () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const code = source.slice(source.indexOf('async function executeKey('), source.indexOf('async function triggerKey('));
  for (const origin of ['web', 'Arduino input', 'Arduino echo']) {
    const sent = [];
    const deck = { config: { mode: 'agent' }, knobAction: null,
      isCurrent: () => true, toggleSelection: () => false };
    const context = { deck, state: {count: 0}, available: () => true,
      $: () => ({}), animateKey() {}, log() {}, status() {}, setControls() {}, renderProfile() {},
      sendCommand: async item => sent.push(item.action) };
    const execute = vm.runInNewContext(code + '\nexecuteKey', context);
    await execute({slot: 1, label: 'MODEL', action: 'model'}, origin);
    assert.deepEqual(sent, ['model']);
    assert.equal(deck.knobAction, 'model');
    assert.equal(context.state.busy, false);
  }
});

test('mode one is the main AI controller and workflow is mode two', () => {
  assert.deepEqual(DECK_MODES, ['agent', 'workflow', 'custom']);
  const deck = new DeckControls([]);
  assert.equal(deck.config.mode, 'agent');
  assert.deepEqual(Array.from({length:7}, (_,i)=>deck.capture(i+1).action), ['model','plan','build','check','accept','denied','stop']);
});
test('prose choices map each button to the same number, including later pages', () => {
  const q = terminalQuestion(['어떻게 진행할까요?', ...Array.from({length:9},(_,i)=>`${i+1}. 방법 ${i+1}`), '❯ '], 'generation');
  assert.equal(q.options.length,9);
  assert.equal(terminalAnswer(q,'5'), '\x1b[200~5\x1b[201~\r');
  const deck = new DeckControls([]); deck.update('terminal', {generation:'g',ready:true,question:q});
  assert.equal(deck.capture(5).choice,'5'); deck.movePage(1); assert.equal(deck.capture(1).choice,'8');
  deck.markAnswered(deck.capture(1)); assert.equal(deck.capture(1),null);
});
test('native menus select the requested row relative to the current cursor', () => {
  const lines=['Would you like to proceed?', '  1. Yes', '› 2. No', '  3. Tell me more', 'Enter to select · Esc to cancel'];
  const q=terminalQuestion(lines,'g');
  assert.equal(q.interactive,true);
  assert.equal(terminalAnswer(q,'1'),'\x1b[A\r');
  assert.equal(terminalAnswer(q,'3'),'\x1b[B\r');
  assert.equal(terminalAnswer(q,'2'),'\r');
  assert.throws(()=>terminalAnswer(q,'7'));
  assert.notEqual(q.id,terminalQuestion(lines,'other').id);
});
test('Claude question with descriptions and compact Korean numbers binds key 5 to answer 5', () => {
  const lines = ['☐ 점심 메뉴', '점심으로 뭐가 더 끌리세요?', '❯1.한식', '  김치찌개, 비빔밥', '2.양식', '  파스타', '3.일식', '4.분식', '5.Type something.', '6.Chat about this'];
  const q = terminalQuestion(lines, 'claude');
  assert.equal(q.interactive, true);
  assert.equal(terminalAnswer(q, '5'), '\x1b[B'.repeat(4) + '\r');
  const deck = new DeckControls([]);
  deck.update('terminal', { generation: 'claude', ready: true, nativePending: true, question: q });
  assert.equal(deck.capture(5).action, 'answer');
  assert.equal(deck.capture(5).choice, '5');
  deck.markAnswered(deck.capture(5));
  deck.update('terminal', { generation: 'claude', ready: true, question: q });
  assert.equal(deck.capture(5), null);
});
test('a cursor beside Claude option one does not erase it as composer placeholder text', () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const BrowserTerminal = vm.runInNewContext(fs.readFileSync(require.resolve('../web-terminal.js'), 'utf8') + '\nBrowserTerminal');
  const terminal = Object.create(BrowserTerminal.prototype);
  let row = '❯ 1. 한식';
  terminal.term = { rows: 1, buffer: { active: { baseY: 0, cursorY: 0, cursorX: 2,
    getLine: () => ({ translateToString: (_, start = 0, end) => row.slice(start, end) }),
  } } };
  assert.deepEqual(Array.from(terminal.screenLines()), ['❯ 1. 한식']);
  row = '❯ Try asking a question';
  assert.deepEqual(Array.from(terminal.screenLines()), ['❯ ']);
});
test('focus reports and navigation do not mark a native question answered', async () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const BrowserTerminal = vm.runInNewContext(fs.readFileSync(require.resolve('../web-terminal.js'), 'utf8') + '\nBrowserTerminal');
  for (const input of ['\x1b[I', '\x1b[O', '\x1b[A', '\x1b[B', '\x1b[12;3R', '5', '\x1b[200~line one\nline two\x1b[201~']) {
    const terminal = Object.create(BrowserTerminal.prototype), writes = [];
    Object.assign(terminal, { running: true, question: { native: true, id: 'q5' }, generation: 'g',
      inputChain: Promise.resolve(), dismissedNative: '', request: async (_, payload) => writes.push(payload.data) });
    terminal.input(input); await terminal.inputChain;
    assert.equal(terminal.dismissedNative, '');
    assert.deepEqual(writes, [input]);
    terminal.input('\r'); await terminal.inputChain;
    assert.equal(terminal.dismissedNative, 'q5');
  }
});
function buildTerminal({ mode = 'plan', draft = '', request } = {}) {
  const fs = require('node:fs'), vm = require('node:vm');
  const BrowserTerminal = vm.runInNewContext(fs.readFileSync(require.resolve('../web-terminal.js'), 'utf8') + '\nBrowserTerminal');
  const terminal = Object.create(BrowserTerminal.prototype), writes = [];
  Object.assign(terminal, { generation: 'g', mode, running: true, inputBlocked: false,
    inputChain: Promise.resolve(), request: request || (async (action, payload) => writes.push({ action, ...payload })),
    term: { focus() {}, buffer: { active: { baseY: 0, cursorY: 0, cursorX: 2 + draft.length,
      getLine: () => ({ translateToString: () => '❯ ' + draft }),
    } } } });
  return { terminal, writes };
}
test('BUILD leaves plan mode before submitting one implementation request', async () => {
  for (const kind of ['codex', 'codex-yolo', 'claude', 'claude-yolo']) {
    const { terminal, writes } = buildTerminal();
    terminal.kind = kind;
    await terminal.nativeAction({ generation: 'g', action: 'build' });
    assert.deepEqual(writes, [{ action: 'input', generation: 'g',
      data: '\x1b[Z\x1b[200~작성한 계획대로 구현을 시작해 주세요.\x1b[201~\r' }]);
    assert.equal(terminal.mode, 'build');
  }
});
test('BUILD in implementation mode submits the request without toggling back to plan', async () => {
  const { terminal, writes } = buildTerminal({ mode: 'build' });
  await terminal.nativeAction({ generation: 'g', action: 'build' });
  assert.deepEqual(writes, [{ action: 'input', generation: 'g',
    data: '\x1b[200~작성한 계획대로 구현을 시작해 주세요.\x1b[201~\r' }]);
  assert.equal(terminal.mode, 'build');
});
test('BUILD preserves an unsent draft and does not change modes', async () => {
  const { terminal, writes } = buildTerminal({ draft: '아직 작성 중인 요청' });
  await assert.rejects(terminal.nativeAction({ generation: 'g', action: 'build' }), /작성 중인 입력/);
  assert.deepEqual(writes, []);
  assert.equal(terminal.mode, 'plan');
});
test('BUILD rejects a stale session and does not retry a failed transmission', async () => {
  const { terminal, writes } = buildTerminal();
  await assert.rejects(terminal.nativeAction({ generation: 'old', action: 'build' }), /AI 세션이 바뀌었습니다/);
  assert.deepEqual(writes, []);
  let attempts = 0;
  const failed = buildTerminal({ request: async () => { attempts++; throw new Error('connection lost'); } });
  await assert.rejects(failed.terminal.nativeAction({ generation: 'g', action: 'build' }), /connection lost/);
  assert.equal(attempts, 1);
  assert.equal(failed.terminal.mode, 'plan');
});
test('PLAN still only changes mode and ignores a repeated plan press', async () => {
  const { terminal, writes } = buildTerminal({ mode: 'build' });
  await terminal.nativeAction({ generation: 'g', action: 'plan' });
  await terminal.nativeAction({ generation: 'g', action: 'plan' });
  assert.deepEqual(writes, [{ action: 'input', generation: 'g', data: '\x1b[200~/plan\x1b[201~\r' }]);
  assert.equal(terminal.mode, 'plan');
});
test('ACCEPT sends an explicit approval when the conversational input is empty', async () => {
  const { terminal, writes } = buildTerminal({ mode: 'build' });
  await terminal.nativeAction({ generation: 'g', action: 'accept' });
  assert.deepEqual(writes, [{ action: 'input', generation: 'g',
    data: '\x1b[200~현재 제안 또는 결과를 승인합니다. 해당 내용에 맞게 진행해 주세요.\x1b[201~\r' }]);
});
test('ACCEPT still submits drafted text and confirms native CLI menus with Enter', async () => {
  for (const kind of ['draft', 'numbered-menu', 'unnumbered-menu']) {
    const { terminal, writes } = buildTerminal({ draft: kind === 'draft' ? '직접 작성한 답변' : '' });
    if (kind === 'numbered-menu') terminal.question = { interactive: true };
    if (kind === 'unnumbered-menu') terminal.screenLines = () => ['❯ Yes', '  No', 'Enter to confirm · Esc to cancel'];
    await terminal.nativeAction({ generation: 'g', action: 'accept' });
    assert.deepEqual(writes, [{ action: 'input', generation: 'g', data: '\r' }]);
  }
});
test('DENIED requests alternatives, CHECK requests direct verification, and STOP remains Escape', async () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const BrowserTerminal = vm.runInNewContext(fs.readFileSync(require.resolve('../web-terminal.js'), 'utf8') + '\nBrowserTerminal');
  const terminal = Object.create(BrowserTerminal.prototype), writes = [];
  Object.assign(terminal, { generation: 'g', nativeInput: async data => writes.push(data),
    term: { buffer: { active: { baseY: 0, cursorY: 0, cursorX: 2,
      getLine: () => ({ translateToString: () => '❯ ' }),
    } } } });
  await terminal.nativeAction({ generation: 'g', action: 'denied' });
  assert.equal(writes.length, 1);
  assert.match(writes[0], /^\x1b\[200~현재 제안은 거절합니다\./);
  assert.match(writes[0], /다른 대안을 제안해 주세요/);
  assert.match(writes[0], /제 승인을 기다려 주세요\.\x1b\[201~\r$/);
  await terminal.nativeAction({ generation: 'g', action: 'stop' });
  assert.equal(writes[1], '\x1b');
  await terminal.nativeAction({ generation: 'g', action: 'check' });
  assert.match(writes[2], /^\x1b\[200~지금까지 한 작업을 직접 검증해 주세요\./);
  assert.match(writes[2], /관련 테스트를 실행/);
  assert.match(writes[2], /현재 상태를 기준으로 다시 확인/);
  assert.match(writes[2], /미검증/);
  assert.ok(writes[2].endsWith('\x1b[201~\r'));
});
test('ordinary lists, code, malformed choices and answered history are not menus', () => {
  for (const lines of [
    ['Completed changes:', '1. First', '2. Second'],
    ['Choose:', '```', '1. One', '2. Two', '```'],
    ['Choose:', '1. One', '3. Three'],
    ['Choose:', '1. One', '2. Two', '❯ 2'],
  ]) assert.equal(terminalQuestion(lines,'g'),null);
});
test('mode detection reads the footer rather than mentions in past output', () => {
  assert.equal(terminalMode(['⏸ plan mode on (shift+tab to cycle)']), 'plan');
  assert.equal(terminalMode(['bypass permissions (shift+tab to cycle)']), 'build');
  assert.equal(terminalMode(['⏵⏵ auto mode on (shift+tab to cycle) · esc to interrupt · ← for agents']), 'build');
  assert.equal(terminalMode(['⏸ manual mode on · ? for shortcuts · ← for agents']), 'build');
  assert.equal(terminalMode(['⏸ plan mode on (shift+tab to cycle)', ...Array(8).fill(''),
    '⏵⏵ auto mode on (shift+tab to cycle)']), 'build');
  assert.equal(terminalMode(['Please explain plan mode']),null);
});

test('effort is restricted to MODEL context and resets on mode changes', () => {
  const { knobBinding } = require('../controls');
  for (const action of [null,'plan','build','accept','denied','check','stop']) {
    assert.notEqual(knobBinding('agent',action,null).rotate,'effort');
  }
  assert.equal(knobBinding('agent','model',null).rotate,'effort');
  assert.equal(knobBinding('agent','model',{}).rotate,'questions');
  assert.equal(knobBinding('workflow','model',null).rotate,'autonomy');
  assert.notEqual(knobBinding('custom','model',null).rotate,'effort');
  const deck = new DeckControls([]);deck.knobAction='model';
  deck.configure({...deck.config,mode:'workflow'});assert.equal(deck.knobAction,null);
});

const { terminalWorking } = require('../controls');
test('activity indicator tracks CLI work instead of an open terminal', () => {
  assert.equal(terminalWorking(['› ', 'gpt-5 high · /effort']), false);
  assert.equal(terminalWorking(['• Working (3s • esc to interrupt)', '› ']), true);
  assert.equal(terminalWorking(['✻ Thinking… (esc to interrupt)', '❯ ']), true);
  assert.equal(terminalWorking(['› Explain esc to interrupt', '? for shortcuts']), false);
  assert.equal(terminalWorking(['Working (esc to interrupt)', ...Array(9).fill('idle')]), false);
  assert.equal(terminalWorking(['✻ Worked for 12s', '❯ ']), false);
});
