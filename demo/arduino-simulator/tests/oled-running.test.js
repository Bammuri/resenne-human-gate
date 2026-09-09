const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('running animation advances without new terminal output, restores other states and resets per run', () => {
  const source = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const nodes = new Map();
  const node = () => ({ attributes: {}, setAttribute(key, value) { this.attributes[key] = value; } });
  const $ = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  $('#deck-oled-blocks').children = Array.from({length: 7}, node);
  let now = 0, timer, starts = 0;
  const context = { $, performance: { now: () => now },
    setInterval(callback) { starts++; timer = callback; return 1; },
    clearInterval() { timer = null; } };
  const update = vm.runInNewContext('let oledWorkingSince = null, oledAnimationTimer = null;\n' +
    source.slice(source.indexOf('function animateOled('), source.indexOf('function updateOled()')) + '\nupdateOledActivity', context);
  const fills = () => $('#deck-oled-blocks').children.map(n => n.attributes.fill);
  update('running');
  assert.equal($('#deck-oled-normal').attributes.visibility, 'hidden');
  assert.equal($('#deck-oled-running').attributes.visibility, 'visible');
  assert.equal($('#deck-oled-elapsed').textContent, '00:00');
  const initial = fills();
  now = 250; timer();
  assert.notDeepEqual(fills(), initial);
  assert.equal(fills().filter(fill => fill !== 'none').length, 3);
  now = 65000; update('running'); timer();
  assert.equal(starts, 1);
  assert.equal($('#deck-oled-elapsed').textContent, '01:05');
  for (const state of ['question', 'ready', 'stopped', 'error']) {
    update(state);
    assert.equal(timer, null);
    assert.equal($('#deck-oled-normal').attributes.visibility, 'visible');
    assert.equal($('#deck-oled-running').attributes.visibility, 'hidden');
    update('running');
    assert.equal($('#deck-oled-elapsed').textContent, '00:00');
  }
});

test('answer requests override running across every mode; an open idle terminal stays ready', () => {
  const source = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const context = { deck: {config: {mode: 'agent'}, question: null}, workflow: {data: {}},
    browserTerminal: {running: true, managed: false, working: true, mode: 'build'},
    EFFORTS: ['low', 'medium', 'high', 'xhigh'], state: {effort: 'medium'},
    AUTONOMY: ['Manual', 'Guide'], knobBinding: () => ({label: 'SCROLL'}) };
  const state = vm.runInNewContext(source.slice(source.indexOf('function oledState('), source.indexOf('function animateOled(')) + '\noledState', context);
  for (const mode of ['agent', 'workflow', 'custom']) {
    context.deck.config.mode = mode;
    assert.equal(state().status, 'running');
    context.deck.question = {options: [{id: '1'}]}; context.deck.page = 0;
    assert.equal(state().status, 'question');
    context.deck.question = null;
  }
  context.browserTerminal.working = false;
  assert.equal(state().status, 'ready');
  context.workflow.data.running = true;
  assert.equal(state().status, 'running');
});
