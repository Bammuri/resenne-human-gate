const test = require('node:test');
const assert = require('node:assert/strict');
const { GateApi, describePending, initGatePanel } = require('../gate.js');

// --- pure helper -----------------------------------------------------------

test('describePending combines tool and summary, tolerates missing fields', () => {
  assert.equal(describePending({ tool_name: 'Bash', summary: 'rm -rf x' }), 'Bash — rm -rf x');
  assert.equal(describePending({ tool_name: 'Write' }), 'Write');
  assert.equal(describePending({}), 'tool');
  assert.equal(describePending(null), 'tool');
});

// --- network layer (fake fetch models the already-tested broker endpoints) --

function fakeFetch(routes) {
  const calls = [];
  const fetchImpl = async (path, options) => {
    calls.push({ path, options: options || {} });
    const handler = routes[path];
    if (!handler) return { status: 404, json: async () => ({}) };
    const { status, body } = handler(options || {});
    return { status, json: async () => body };
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

test('connect stores the ui token from /api/session', async () => {
  const api = new GateApi(fakeFetch({ '/api/session': () => ({ status: 200, body: { token: 'T0K' } }) }));
  assert.equal(await api.connect(), true);
  assert.equal(api.token, 'T0K');
});

test('connect fails cleanly when no token is returned', async () => {
  const api = new GateApi(fakeFetch({ '/api/session': () => ({ status: 200, body: {} }) }));
  assert.equal(await api.connect(), false);
  assert.equal(api.token, null);
});

test('listPending sends the token header and returns the pending list', async () => {
  const fetchImpl = fakeFetch({
    '/api/session': () => ({ status: 200, body: { token: 'T0K' } }),
    '/api/approval': (opts) => {
      assert.equal(opts.headers['X-Simulator-Token'], 'T0K');
      return { status: 200, body: { pending: [{ id: 'a1', tool_name: 'Bash', summary: 'ls' }], count: 1 } };
    },
  });
  const api = new GateApi(fetchImpl);
  await api.connect();
  const { status, body } = await api.listPending();
  assert.equal(status, 200);
  assert.equal(body.pending[0].id, 'a1');
});

test('resolve posts approval_id and decision, surfaces 409 conflicts', async () => {
  const fetchImpl = fakeFetch({
    '/api/session': () => ({ status: 200, body: { token: 'T0K' } }),
    '/api/approval/resolve': (opts) => {
      assert.equal(opts.method, 'POST');
      assert.equal(opts.headers['Content-Type'], 'application/json');
      const sent = JSON.parse(opts.body);
      assert.deepEqual(sent, { approval_id: 'a1', decision: 'deny' });
      return { status: 409, body: { error: 'already resolved' } };
    },
  });
  const api = new GateApi(fetchImpl);
  await api.connect();
  const { status } = await api.resolve('a1', 'deny');
  assert.equal(status, 409);
});

// --- DOM wiring (minimal fake document) ------------------------------------

function fakeElement(tag) {
  return {
    tag, className: '', type: '', _text: '', hidden: false, children: [], handlers: {},
    set textContent(v) { this._text = v; if (v === '') this.children = []; },
    get textContent() { return this._text; },
    appendChild(child) { this.children.push(child); },
    addEventListener(evt, fn) { this.handlers[evt] = fn; },
  };
}

function fakeDoc() {
  const nodes = { 'gate-list': fakeElement('ul'), 'gate-status': fakeElement('div'), 'gate-empty': fakeElement('p') };
  return {
    nodes,
    getElementById: (id) => nodes[id],
    createElement: (tag) => fakeElement(tag),
  };
}

test('poll renders pending rows with wired approve/reject buttons and hides empty', async () => {
  const doc = fakeDoc();
  let resolved = null;
  const api = { resolve: async (id, decision) => { resolved = { id, decision }; return { status: 200 }; },
                listPending: async () => ({ status: 200, body: { pending: [{ id: 'a1', tool_name: 'Bash', summary: 'ls' }] } }) };
  const panel = initGatePanel(doc, api);
  await panel.poll();

  assert.equal(doc.nodes['gate-empty'].hidden, true);
  assert.equal(doc.nodes['gate-list'].children.length, 1);
  const row = doc.nodes['gate-list'].children[0];
  const [label, approve, reject] = row.children;
  assert.equal(label._text, 'Bash — ls');
  assert.equal(approve.className, 'gate-approve');
  assert.equal(reject.className, 'gate-reject');

  await approve.handlers.click();
  assert.deepEqual(resolved, { id: 'a1', decision: 'allow' });
  assert.equal(doc.nodes['gate-status']._text, '허용을 전송했습니다.');
});

test('poll on an empty list shows the empty notice', async () => {
  const doc = fakeDoc();
  const api = { listPending: async () => ({ status: 200, body: { pending: [] } }) };
  const panel = initGatePanel(doc, api);
  await panel.poll();
  assert.equal(doc.nodes['gate-empty'].hidden, false);
  assert.equal(doc.nodes['gate-list'].children.length, 0);
});
