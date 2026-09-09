const test = require('node:test');
const assert = require('node:assert/strict');
const { DeckControls } = require('../controls.js');
const workflow = ['intent', 'context', 'ask', 'plan_workflow', 'build_workflow', 'verify', 'review'].map(value => [value, value.toUpperCase()]);
const create = () => { const deck = new DeckControls(workflow); deck.update('terminal', { generation: 'terminal-a', ready: true }); deck.update('current', { generation: 'current-a', ready: true }); return deck; };
const question = (id = 'question-a', count = 3, extra = {}) => ({ id, prompt: '어떻게 진행할까요?', kind: 'choice', options: Array.from({ length: count }, (_, i) => ({ id: `answer-${i + 1}`, label: `선택 ${i + 1}` })), ...extra });
const ask = (deck, q = question(), target = 'terminal', generation = 'terminal-a') => deck.update(target, { generation, ready: true, question: q });

test('exactly seven function slots and fixed MODE in all three profiles', () => {
  const deck = create();
  for (const mode of ['workflow', 'agent', 'custom']) {
    deck.configure({ ...deck.config, mode });
    assert.equal(deck.capture(8).action, 'mode');
    for (let slot = 1; slot <= 7; slot++) assert.ok(deck.capture(slot));
    assert.equal(deck.capture(9), null);
  }
  deck.configure({ ...deck.config, mode: 'agent' });
  assert.deepEqual(Array.from({ length: 7 }, (_, i) => deck.capture(i + 1).action), ['model', 'plan', 'build', 'check', 'accept', 'denied', 'stop']);
});

test('numbered responses override every underlying mode action and block unused slots', () => {
  const deck = create(); ask(deck);
  for (const mode of ['workflow', 'agent', 'custom']) {
    deck.configure({ ...deck.config, mode });
    assert.equal(deck.capture(1).action, 'answer');
    assert.equal(deck.capture(2).choice, 'answer-2');
    assert.equal(deck.capture(3).target, 'terminal');
    for (let slot = 4; slot <= 7; slot++) assert.equal(deck.capture(slot), null);
    assert.equal(deck.capture(8).action, 'mode');
  }
});

test('Arduino echoes cannot answer a newer question, trigger former mode functions, or switch targets', () => {
  const deck = create(); ask(deck);
  const original = deck.capture(2);
  ask(deck, question('question-b'));
  assert.equal(deck.isCurrent(original), false);
  deck.update('terminal', { generation: 'terminal-a', ready: true });
  assert.equal(deck.capture(2).action, 'plan');
  assert.equal(deck.isCurrent(original), false);
  ask(deck); const afterRestore = deck.capture(2);
  deck.setTarget('current');
  assert.equal(deck.isCurrent(afterRestore), false);
  deck.setTarget('terminal'); ask(deck, question(), 'terminal', 'terminal-b');
  assert.equal(deck.isCurrent(afterRestore), false);
});

test('an ordinary key captured before a question arrives cannot accidentally answer it', () => {
  const deck = create(); deck.configure({ ...deck.config, mode: 'agent' });
  const launch = deck.capture(1); assert.equal(launch.action, 'model');
  ask(deck); assert.equal(deck.isCurrent(launch), false);
});

test('answered question stays blocked through delayed polls and restores only after server clears it', () => {
  const deck = create(); ask(deck);
  deck.markAnswered(deck.capture(2));
  assert.equal(deck.waiting, true); assert.equal(deck.capture(2), null);
  ask(deck); assert.equal(deck.capture(2), null);
  assert.equal(deck.capture(8).action, 'mode');
  ask(deck, question('question-b')); assert.equal(deck.waiting, false); assert.equal(deck.capture(2).action, 'answer');
  deck.update('terminal', { generation: 'terminal-a', ready: true, question: null });
  assert.equal(deck.capture(2).action, 'plan');
});

test('more than seven options use page-local button numbers and stale pages invalidate echoes', () => {
  const deck = create(); ask(deck, question('many', 16));
  assert.equal(deck.pages, 3); const first = deck.capture(1);
  deck.movePage(1); assert.equal(deck.capture(1).choice, 'answer-8'); assert.equal(deck.capture(7).choice, 'answer-14');
  assert.equal(deck.isCurrent(first), false);
  deck.movePage(1); assert.equal(deck.capture(1).choice, 'answer-15'); assert.equal(deck.capture(3), null);
  ask(deck, question('next', 2)); assert.equal(deck.page, 0);
});

test('custom mappings keep their own execution target and fail identity checks after generation changes', () => {
  const deck = create();
  const custom = deck.config.custom.map(entry => ({ ...entry }));
  custom[0] = { label: '리뷰 요청', action: 'prompt', target: 'current', text: '변경 내용을 리뷰해 주세요.' };
  deck.configure({ mode: 'custom', custom });
  const mapped = deck.capture(1);
  assert.equal(mapped.target, 'current'); assert.equal(mapped.generation, 'current-a'); assert.equal(mapped.text, custom[0].text);
  deck.update('current', { generation: 'current-b', ready: true });
  assert.equal(deck.isCurrent(mapped), false);
});

test('workflow ASK answers retain workflow run identity and do not invoke stages', () => {
  const deck = create(); ask(deck, question('ask-a'), 'workflow', 'run-123');
  const answer = deck.capture(2);
  assert.equal(answer.target, 'workflow'); assert.equal(answer.generation, 'run-123'); assert.equal(answer.action, 'answer');
  deck.update('workflow', { generation: 'run-124', question: null }); assert.equal(deck.isCurrent(answer), false);
});

test('free-text and secret answers carry the same stale-question protection as physical choices', () => {
  const deck = create(); ask(deck, question('secret', 0, { isSecret: true }));
  assert.equal(deck.capture(1), null);
  const answer = deck.captureAnswer({ text: 'sample-value' });
  assert.equal(answer.questionId, 'secret'); assert.equal(deck.isCurrent(answer), true);
  ask(deck, question('another', 0)); assert.equal(deck.isCurrent(answer), false);
});

test('multi-select buttons toggle without submitting, span pages, and reset on the next question', () => {
  const deck = create(); ask(deck, question('multi', 10, { multiSelect: true }));
  assert.equal(deck.toggleSelection(deck.capture(2)), true); assert.deepEqual([...deck.selected], ['answer-2']);
  assert.equal(deck.waiting, false);
  deck.movePage(1); deck.toggleSelection(deck.capture(1));
  assert.deepEqual([...deck.selected], ['answer-2', 'answer-8']);
  const submit = deck.captureAnswer({ choice: [...deck.selected] }); assert.equal(deck.isCurrent(submit), true);
  deck.markAnswered(submit); assert.equal(deck.waiting, true);
  ask(deck, question('multi-next', 10, { multiSelect: true })); assert.equal(deck.selected.size, 0); assert.equal(deck.isCurrent(submit), false);
});

test('workflow questions stay available across modes, with the selected AI taking priority outside workflow mode', () => {
  const deck = create(); ask(deck, question('workflow-pending'), 'workflow', 'run-a');
  for (const mode of ['workflow', 'agent', 'custom']) {
    deck.configure({ ...deck.config, mode }); assert.equal(deck.capture(1).target, 'workflow');
  }
  ask(deck, question('terminal-pending'));
  assert.equal(deck.capture(1).target, 'terminal');
  deck.configure({ ...deck.config, mode: 'workflow' }); assert.equal(deck.capture(1).target, 'workflow');
});
