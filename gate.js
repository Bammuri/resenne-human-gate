// Re:senne HUMAN GATE — browser approval panel.
//
// A standalone page (gate.html) that lists the tool calls the Claude Code PreToolUse hook
// is waiting on, and lets a human APPROVE (allow) or REJECT (deny) each one. It reuses the
// same ui token the app page already receives from /api/session and talks only to the
// already-tested /api/approval (poll) and /api/approval/resolve endpoints. It deliberately
// does NOT import or touch the terminal / PTY demo — it is a separate surface so the
// verified /api/press key path stays untouched.
//
// Honest scope: this panel lets a human submit an allow/deny decision to the broker over
// HTTP — the software chain (button/click -> broker -> hook_bridge stdout) is unit- and
// subprocess-E2E-tested. Whether the real `claude` binary then honours that decision is a
// live step confirmed in a running Claude session; the PTY key path (/api/press) remains
// the sole fully E2E-verified submission path.

"use strict";

const GATE_POLL_MS = 1000;

// Pure: a short, human-readable line for one pending request.
function describePending(item) {
  const tool = item && item.tool_name ? String(item.tool_name) : "tool";
  const summary = item && item.summary ? String(item.summary) : "";
  return summary ? `${tool} — ${summary}` : tool;
}

// Pure: a short line for one resolved decision. The log stores no tool input — only the
// tool name, decision, resolver credential role, a short input hash, and timestamps — so
// this line reflects only what a resolver submitted, not that the tool actually ran.
function describeDecision(entry) {
  const tool = entry && entry.tool_name ? String(entry.tool_name) : "tool";
  const verdict = entry && entry.decision === "allow" ? "허용"
    : (entry && entry.decision === "deny" ? "거부" : "?");
  const role = entry && entry.role ? String(entry.role) : "?";
  const when = entry && entry.resolved_at
    ? new Date(entry.resolved_at * 1000).toLocaleTimeString() : "";
  const hash = entry && entry.input_hash ? ` #${String(entry.input_hash)}` : "";
  return `${tool} — ${verdict} (${role})${when ? " · " + when : ""}${hash}`;
}

// Thin network layer over the broker endpoints; fetch is injected so it is testable
// without a browser (the Python tests already prove the endpoints themselves).
class GateApi {
  constructor(fetchImpl) {
    this._fetch = fetchImpl;
    this.token = null;
  }

  async _json(path, options) {
    const response = await this._fetch(path, options || {});
    let body = {};
    try { body = await response.json(); } catch (_error) { body = {}; }
    return { status: response.status, body };
  }

  // The browser gets the same ui token the app page uses (/api/session -> {token}).
  async connect() {
    const { status, body } = await this._json("/api/session", {});
    if (status === 200 && body && body.token) { this.token = body.token; return true; }
    return false;
  }

  _headers(extra) {
    return Object.assign({ "X-Simulator-Token": this.token || "" }, extra || {});
  }

  listPending() {
    return this._json("/api/approval", { headers: this._headers() });
  }

  listLog() {
    return this._json("/api/approval/log", { headers: this._headers() });
  }

  resolve(approvalId, decision) {
    return this._json("/api/approval/resolve", {
      method: "POST",
      headers: this._headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({ approval_id: approvalId, decision }),
    });
  }
}

// Browser-only DOM wiring. Takes the document + api so the pure parts above stay testable.
function initGatePanel(doc, api) {
  const list = doc.getElementById("gate-list");
  const statusEl = doc.getElementById("gate-status");
  const emptyEl = doc.getElementById("gate-empty");
  const logList = doc.getElementById("gate-log");
  const logEmptyEl = doc.getElementById("gate-log-empty");

  function setStatus(text) { if (statusEl) statusEl.textContent = text; }

  function render(pending) {
    list.textContent = "";
    if (emptyEl) emptyEl.hidden = pending.length > 0;
    for (const item of pending) {
      const row = doc.createElement("li");
      row.className = "gate-item";

      const label = doc.createElement("span");
      label.className = "gate-desc";
      label.textContent = describePending(item);
      row.appendChild(label);

      const approve = doc.createElement("button");
      approve.className = "gate-approve";
      approve.type = "button";
      approve.textContent = "✓ 허용";            // ✓ 허용
      approve.addEventListener("click", () => decide(item.id, "allow"));
      row.appendChild(approve);

      const reject = doc.createElement("button");
      reject.className = "gate-reject";
      reject.type = "button";
      reject.textContent = "✕ 거부";            // ✕ 거부
      reject.addEventListener("click", () => decide(item.id, "deny"));
      row.appendChild(reject);

      list.appendChild(row);
    }
  }

  // The recent-decisions view. Guarded on both the DOM element and api.listLog so the
  // pending-only tests (which inject a minimal document + api) are unaffected.
  function renderLog(decisions) {
    if (!logList) return;
    logList.textContent = "";
    if (logEmptyEl) logEmptyEl.hidden = decisions.length > 0;
    for (const entry of decisions) {
      const row = doc.createElement("li");
      row.className = entry && entry.decision === "deny" ? "gate-log-deny" : "gate-log-allow";
      row.textContent = describeDecision(entry);
      logList.appendChild(row);
    }
  }

  async function decide(approvalId, decision) {
    const { status } = await api.resolve(approvalId, decision);
    if (status === 200) {
      setStatus(decision === "allow" ? "허용을 전송했습니다." : "거부를 전송했습니다.");
    } else if (status === 409) {
      setStatus("이미 처리되었거나 만료된 요청입니다.");
    } else if (status === 500) {
      setStatus("결정을 기록하지 못해 전송하지 않았습니다. 다시 시도해 주세요.");
    } else {
      setStatus("전송에 실패했습니다. 다시 시도해 주세요.");
    }
    await poll();
    await pollLog();
  }

  async function poll() {
    const { status, body } = await api.listPending();
    if (status !== 200) {
      setStatus("연결이 필요합니다. 페이지를 새로고침해 주세요.");
      return;
    }
    render((body && body.pending) || []);
  }

  async function pollLog() {
    if (!logList || !api.listLog) return;
    const { status, body } = await api.listLog();
    if (status !== 200) return;
    renderLog((body && body.decisions) || []);
  }

  return { poll, pollLog, decide, render, renderLog };
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", async () => {
    const api = new GateApi(window.fetch.bind(window));
    const panel = initGatePanel(document, api);
    const statusEl = document.getElementById("gate-status");
    if (!(await api.connect())) {
      if (statusEl) statusEl.textContent = "세션 토큰을 받지 못했습니다. 서버가 켜져 있는지 확인해 주세요.";
      return;
    }
    await panel.poll();
    await panel.pollLog();
    setInterval(() => { panel.poll(); panel.pollLog(); }, GATE_POLL_MS);
  });
}

if (typeof module !== "undefined") {
  module.exports = { GateApi, describePending, describeDecision, initGatePanel };
}
