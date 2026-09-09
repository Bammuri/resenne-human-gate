const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const WorkflowController = vm.runInNewContext(fs.readFileSync(require.resolve('../workflow.js'), 'utf8') + '\nWorkflowController');

function controller(stage = 'initialization') {
  const flow = Object.create(WorkflowController.prototype), requests = [], messages = [];
  const dialog = () => ({ open: true, close() { this.open = false; }, showModal() { throw new Error('RUN NOW must not open a dialog'); } });
  const elements = { 'review-dialog': dialog(), revert: { hidden: false } };
  Object.assign(flow, { stage, data: { running: false, autonomy: 0 }, pending: false,
    dirtyStages: new Set(['initialization', 'ideation']), autoDirtyStages: new Set(['initialization', 'ideation']), savedStages: new Set(),
    drafts: { initialization: { brief: '현재 환경과 범위' }, ideation: { brief: '방금 입력한 구현 목표' } },
    saveRevision: 0, planDirty: true, dialog: dialog(), el: id => elements[id],
    options: { log() {}, onChange() {} }, render() {}, apply(data) { this.data = data; },
    message(text) { messages.push(text); },
    request: async (action, payload) => { requests.push({ action, payload }); return { running: action === 'start', autonomy: 0 }; }
  });
  return { flow, requests, messages, elements };
}

test('RUN NOW saves every dirty phase and starts construction without opening a dialog', async () => {
  for (const stage of ['initialization', 'ideation', 'inception', 'construction', 'operation']) {
    const { flow, requests, elements } = controller(stage);
    await flow.run();
    assert.deepEqual(requests.map(x => x.action), ['configure', 'configure', 'start']);
    assert.equal(requests[1].payload.fields.brief, '방금 입력한 구현 목표');
    assert.equal(requests[2].payload.stage, 'construction');
    assert.equal(flow.stage, 'construction');
    assert.equal(flow.dialog.open, false);
    assert.equal(elements['review-dialog'].open, false);
    assert.equal(flow.dirtyStages.size, 0);
    assert.equal(flow.autoDirtyStages.size, 0);
  }
});

test('RUN NOW does not start if saving the current input fails', async () => {
  const { flow, requests, messages } = controller();
  flow.request = async action => { requests.push(action); throw new Error('save failed'); };
  await flow.run();
  assert.deepEqual(requests, ['configure']);
  assert.equal(flow.dirtyStages.size, 2);
  assert.equal(flow.dialog.open, true);
  assert.deepEqual(messages, ['save failed']);
});

test('repeated RUN NOW presses while autosaving produce only one execution', async () => {
  const { flow, requests } = controller();
  let finishSave;
  flow.autosaveJob = new Promise(resolve => { finishSave = resolve; });
  const first = flow.run(), second = flow.run();
  finishSave();
  await Promise.all([first, second]);
  assert.equal(requests.filter(x => x.action === 'start').length, 1);
  await flow.run();
  assert.equal(requests.filter(x => x.action === 'start').length, 1);
});
