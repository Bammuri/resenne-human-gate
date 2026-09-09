"use strict";

const $ = selector => document.querySelector(selector);
const EFFORTS = ["low", "medium", "high", "xhigh"];
const MODE_NAMES = { workflow: "2 · AI-DLC", agent: "1 · AI CONTROL", custom: "3 · CUSTOM" };
const deck = new DeckControls(WORKFLOW_KEYS);
let workflow = null, oledTimer = null, lastOled = "", pendingKey = null, pendingKnob = null;
let configSaving = false, configLoaded = false, questionsPolling = false;
let questionRenderKey = "", questionInputKey = "", potContext = "";
let potPosition = null, potAnchor = null;
let potDirection = 0, potReverseTimer = null;
const state = { source: "web", target: "terminal", serverOnline: false, session: null,
  busy: false, serialBusy: false, effort: "medium", count: 0, timer: null, terminalThread: "", terminalReady: false };

const dots = [];
for (let row = 0; row < 8; row++) for (let col = 0; col < 12; col++) {
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  for (const [name, value] of Object.entries({ cx: 387 + col * 7, cy: 162 + row * 7, r: 1.7, class: "led-dot" })) dot.setAttribute(name, value);
  $("#led-matrix").append(dot); dots.push(dot);
}
const patterns = {
  idle: ["000000000000", "000110011000", "001001100100", "001000000100", "000100001000", "000010010000", "000001100000", "000000000000"],
  yes: ["000000000000", "000000000100", "000000001100", "001000011000", "001100110000", "000111100000", "000011000000", "000000000000"],
  no: ["000000000000", "001100001100", "000110011000", "000011110000", "000011110000", "000110011000", "001100001100", "000000000000"],
};
function drawMatrix(name) { const bits = patterns[name].join(""); dots.forEach((dot, i) => dot.classList.toggle("on", bits[i] === "1")); }
function log(kind, message, style = "") {
  const line = document.createElement("div"); line.className = `log-line ${style}`;
  for (const [className, text] of [["log-time", new Date().toLocaleTimeString("en-GB", { hour12: false })], ["log-kind", kind], ["log-text", message]]) {
    const span = document.createElement("span"); span.className = className; span.textContent = text; line.append(span);
  }
  $("#serial-log").append(line);
  while ($("#serial-log").childElementCount > 100) $("#serial-log").firstChild.remove();
  $("#serial-log").scrollTop = $("#serial-log").scrollHeight;
}
function status(message, type = "") { $("#response-text").textContent = message; $("#response-status").className = `response-status ${type}`; }
async function api(path, payload) {
  const response = await fetch(path, { method: payload ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Simulator-Token": state.session?.token || "" },
    ...(payload ? { body: JSON.stringify(payload) } : {}), signal: AbortSignal.timeout(25000) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "서버 요청을 처리하지 못했습니다.");
  return data;
}
function oledState() {
  const flow = deck.config.mode === "workflow", data = workflow?.data, question = deck.question;
  const working = Boolean(data?.running || (browserTerminal.running && (browserTerminal.managed ? browserTerminal.busy : browserTerminal.working)));
  const stage = question ? "question" : flow ? data?.running && data.questionOnly ? "ask_workflow" : data?.running ? data.stage : workflow?.stage || "initialization" : deck.knobAction || (browserTerminal.running ? browserTerminal.mode : "model") || "model";
  const level = flow ? data?.autonomy ?? 1 : EFFORTS.indexOf(state.effort);
  const status = question ? "question" : working ? "running" : flow && data?.error ? "error" : flow && data?.cancelled ? "stopped" : flow && data?.approved ? "approved" : "ready";
  const title = stage === "question" ? "ANSWER" : stage === "ask_workflow" ? "ASK" : stage === "start_workflow" ? "RUN NOW" : stage.toUpperCase();
  const detail = question ? `PICK 1–${Math.min(7, question.options.length - deck.page * 7)}` : flow ? AUTONOMY[level] : stage === "model" ? state.effort.toUpperCase() : knobBinding(deck.config.mode, stage, null).label;
  return {stage, level, status, title, detail};
}
function updateOled() {
  const view = oledState(), flow = deck.config.mode === "workflow";
  $("#deck-oled-mode").textContent = flow ? "2 AI-DLC" : deck.config.mode === "custom" ? "3 CUSTOM" : browserTerminal.running ? (browserTerminal.kind.startsWith("claude") ? "1 CLAUDE" : "1 CODEX") : "1 AI";
  $("#deck-oled-stage").textContent = view.title;
  $("#deck-oled-stage").style.fontSize = "8px";
  $("#deck-oled-depth").textContent = view.detail;
  $("#deck-oled-status").textContent = ({question: deck.waiting ? "SENT" : "? ANSWER", running: "RUNNING", approved: "APPROVED", stopped: "STOPPED", error: "! ERROR", ready: "READY"})[view.status];
  for (const [id, maxSize, width] of [["mode",8,120],["stage",8,120],["depth",8,120],["status",8,120]]) {
    const node=$("#deck-oled-"+id);
    node.textContent=node.textContent.slice(0,20);
    node.style.fontSize=`${maxSize}px`;
    const measured=node.getComputedTextLength();
    if(measured>width)node.style.fontSize=`${maxSize*width/measured}px`;
  }
  $("#deck-oled-indicator").classList.remove("working");
  $("#deck-oled-indicator").setAttribute("visibility", "hidden");
  $("#circuit-stage").dataset.mode = flow ? workflow?.data.stage || "initialization" : browserTerminal.mode;
  $("#circuit-stage").dataset.effort = EFFORTS[flow ? Math.round(view.level * 3 / (AUTONOMY.length - 1)) : view.level];
  clearTimeout(oledTimer); oledTimer = setTimeout(syncOled, 100);
}
async function syncOled() {
  if (serialBridge.state !== "connected") { lastOled = ""; return; }
  const view = oledState();
  const display = [deck.config.mode, view.stage, view.level, view.status];
  const key = JSON.stringify(display);
  if (key === lastOled) return;
  try { if (await serialBridge.sendDisplay(...display)) lastOled = key; else oledTimer = setTimeout(syncOled, 300); } catch { lastOled = ""; }
}
function available(action, transport = true) {
  if (!action) return false;
  if (transport && (state.serialBusy || (state.source === "hardware" && serialBridge.state !== "connected"))) return false;
  if (action.action === "mode") return !configSaving;
  if (["board_sound", "audio_stop"].includes(action.action)) return state.source === "hardware" && serialBridge.state === "connected";
  if (!state.serverOnline || state.busy) return false;
  if (action.workflow) return action.action === "ask_workflow" || (!workflow?.pending && (action.action !== "start_workflow" || !workflow?.data.running));
  if (["codex-yolo", "claude-yolo"].includes(action.action)) return !browserTerminal.running && !browserTerminal.pending && Boolean(state.session?.[action.action === "codex-yolo" ? "codexAvailable" : "claudeAvailable"]);
  if (action.target === "terminal" && !browserTerminal.managed && browserTerminal.nativePending) return false;
  if (action.action === "model" && deck.config.mode === "agent" && !deck.question) return !browserTerminal.pending;
  const snapshot = deck.snapshots[action.target];
  if (!snapshot.generation) return false;
  if (action.action === "stop") return action.target === "terminal" && browserTerminal.running;
  if (action.target === "terminal" && !snapshot.managed && snapshot.nativePending) return false;
  if (action.target === "terminal" && !snapshot.managed && !["prompt", "answer", "plan", "build", "accept", "denied", "model", "check", "diff"].includes(action.action)) return false;
  if (action.action === "prompt" && !action.text?.trim()) return false;
  if (action.action === "answer") return Boolean(snapshot.ready) && !deck.waiting;
  return Boolean(snapshot.ready) && !snapshot.busy;
}
function renderQuestion() {
  const question = deck.question, panel = $("#question-panel");
  // Terminal questions use the existing numbered deck keys. Keep their
  // choices in the CLI instead of rendering a second answer interface.
  if (!question || deck.questionTarget === "terminal") {
    panel.hidden = true;
    $("#question-options").replaceChildren();
    questionRenderKey = ""; questionInputKey = "";
    return;
  }
  const host = $("#workflow-review-dialog").open ? $("#workflow-question-slot") : $("#board-status-row");
  if (panel.parentElement !== host) host.append(panel);
  panel.hidden = !question;
  if (!question) { questionRenderKey = ""; questionInputKey = ""; return; }
  $("#question-heading").textContent = `${deck.questionTarget === "workflow" ? "AI-DLC" : deck.questionTarget === "terminal" ? "웹 AI" : "기존 Codex 세션"} · 답변 선택 중${question.total ? ` (${question.index ?? 1}/${question.total})` : ""}`;
  $("#question-prompt").textContent = question.prompt;
  $("#question-help").textContent = deck.waiting ? "답변을 전달했습니다. 다음 질문을 확인하고 있습니다…" : question.native ? "터미널 보기와 같은 번호의 버튼을 누르세요. 답변하면 PLAN · BUILD 등 기본 기능으로 돌아갑니다." : question.multiSelect ? "복수 선택 · 버튼 1–7로 선택하거나 해제한 뒤 ‘선택 완료’를 누르세요." : "화면 또는 실물 버튼 1–7로 선택하세요. 답변 후 현재 모드의 기능으로 돌아갑니다.";
  const renderKey = JSON.stringify([deck.identity(), deck.page, question.options]);
  if (renderKey !== questionRenderKey) {
  questionRenderKey = renderKey;
  const nodes = question.options.slice(deck.page * 7, deck.page * 7 + 7).map((option, i) => {
    const button = document.createElement("button"); button.type = "button";
    const number = document.createElement("b"); number.textContent = String(i + 1);
    const text = document.createElement("span"); text.textContent = option.label;
    if (option.description) { const detail = document.createElement("small"); detail.textContent = option.description; text.append(detail); }
    button.append(number, text); button.disabled = !available(deck.capture(i + 1));
    button.onclick = () => triggerKey(i + 1); return button;
  });
  $("#question-options").replaceChildren(...nodes);
  }
  Array.from($("#question-options").children).forEach((button, i) => {
    const item = deck.capture(i + 1); button.disabled = !available(item);
    if (question.multiSelect) button.setAttribute("aria-pressed", String(deck.selected.has(question.options[deck.page * 7 + i].id))); else button.removeAttribute("aria-pressed");
  });
  $("#question-selection-send").hidden = !question.multiSelect;
  $("#question-selection-send").textContent = `선택 완료 (${deck.selected.size})`;
  $("#question-selection-send").disabled = !deck.selected.size || !available(deck.captureAnswer({ choice: Array.from(deck.selected) }), false);
  $("#question-answer-form").hidden = question.kind === "approval" || Boolean(question.native && question.interactive);
  if (questionInputKey !== deck.identity()) {
    questionInputKey = deck.identity(); $("#question-answer").value = "";
    $("#question-answer").type = question.isSecret ? "password" : "text";
  }
  $("#question-answer-send").disabled = !available(deck.captureAnswer({ text: "" }), false);
  $("#question-answer").disabled = $("#question-answer-send").disabled;
  $("#question-pagination").hidden = deck.pages === 1;
  $("#question-page").textContent = `${deck.page + 1} / ${deck.pages} · 보기 ${deck.page * 7 + 1}–${Math.min(question.options.length, (deck.page + 1) * 7)}`;
  $("#question-prev").disabled = deck.page === 0 || state.busy || state.serialBusy;
  $("#question-next").disabled = deck.page === deck.pages - 1 || state.busy || state.serialBusy;
}
function setControls() {
  document.querySelectorAll(".deck-key").forEach((button, i) => {
    const disabled = !available(deck.capture(i + 1)); button.setAttribute("aria-disabled", String(disabled)); button.setAttribute("tabindex", disabled ? "-1" : "0");
  });
  const knobDisabled = state.busy || state.serialBusy || (state.source === "hardware" && serialBridge.state !== "connected") || (!deck.question && deck.config.mode === "workflow" && (!state.serverOnline || workflow?.pending || workflow?.data.running));
  $("#deck-knob").setAttribute("aria-disabled", String(knobDisabled)); $("#deck-knob").setAttribute("tabindex", knobDisabled ? "-1" : "0");
  $("#deck-profile").disabled = !available(deck.capture(8));
  $("#custom-open").disabled = !state.serverOnline || configSaving;
  renderQuestion();
}
function renderProfile() {
  $("#deck-profile").textContent = `8 MODE · ${MODE_NAMES[deck.config.mode]}`;
  $("#deck-profile").setAttribute("aria-label", `8번 MODE 버튼 · 현재 ${MODE_NAMES[deck.config.mode]} · 다음 모드로 전환`);
  $("#circuit-stage").dataset.profile = deck.config.mode;
  $("#workflow-shortcuts").hidden = false;
  $("#autonomy-hint").hidden = deck.config.mode !== "workflow";
  document.querySelectorAll(".deck-key").forEach((button, i) => {
    const item = deck.capture(i + 1);
    let label = i === 7 ? "MODE" : deck.question ? String(i + 1) : item?.label || "—";
    button.dataset.action = item?.action || "unused";
    button.classList.toggle("knob-owner", !deck.question && deck.config.mode === "agent" && deck.knobAction === item?.action);
    button.querySelector("text").textContent = deck.question && i < 7 ? label : `${i + 1} ${label}`;
    button.querySelector("text").style.fontSize = label.length > 9 ? "8px" : label.length > 6 ? "10px" : "12px";
    button.setAttribute("aria-label", `${i + 1} ${i === 7 ? "모드 전환" : item?.label || "사용하지 않는 보기"}`);
    let title = button.querySelector("title");
    if (!title) { title = document.createElementNS("http://www.w3.org/2000/svg", "title"); button.append(title); }
    title.textContent = `${i + 1} · ${item?.label || "사용하지 않는 보기"}${item?.text ? ` · ${item.text}` : ""}`;
  });
  const binding = knobBinding(deck.config.mode, deck.knobAction, deck.question);
  $("#deck-knob text").textContent = binding.label;
  $("#deck-knob").setAttribute("aria-label", binding.hint);
  $("#knob-help").textContent = binding.hint;
  $("#stage-hint").textContent = deck.question ? "답변 우선 · 1–7 선택 / 8 MODE" : deck.config.mode === "workflow" ? "Initialization → Ideation → Inception → Construction → Operation · 6 ASK · 7 RUN NOW" : deck.config.mode === "agent" ? "1 MODEL · 2 PLAN · 3 BUILD · 4 CHECK · 5 ACCEPT · 6 DENIED · 7 STOP" : "커스텀 설정에서 버튼의 기능을 저장하세요";
  updateOled(); setControls();
}
async function saveConfig(config) {
  if (configSaving) throw new Error("모드 설정을 저장하고 있습니다.");
  configSaving = true; setControls();
  try { deck.configure(await api("/api/controls", config)); configLoaded = true; renderProfile(); }
  finally { configSaving = false; setControls(); }
}
async function toggleProfile() {
  const next = DECK_MODES[(DECK_MODES.indexOf(deck.config.mode) + 1) % DECK_MODES.length];
  await saveConfig({ ...deck.config, mode: next });
  log("MODE", MODE_NAMES[next]); status(`${MODE_NAMES[next]} 모드${deck.question ? " · 질문 답변이 우선 적용됩니다." : ""}`);
}
function animateKey(item) {
  const button = $(`#deck-key-${item.slot}`); button?.classList.add("pressed");
  $("#serial-step").classList.add("active");
  if (item.action === "accept") drawMatrix("yes"); else if (item.action === "denied") drawMatrix("no");
  setTimeout(() => { button?.classList.remove("pressed"); $("#serial-step").classList.remove("active"); }, 350);
}
async function sendCommand(item) {
  const payload = { action: item.action, target: item.target, generation: item.generation, requestId: crypto.randomUUID() };
  for (const key of ["questionId", "choice", "text"]) if (item[key] !== undefined) payload[key] = item[key];
  const native = item.target === "terminal" && !browserTerminal.managed && item.action !== "prompt";
  const result = native ? (await browserTerminal.nativeAction(item), { ok: true }) : await api("/api/command", payload);
  if (item.action === "answer") deck.markAnswered(item);
  if (result.workflow) workflow.apply(result.workflow);
  if (result.question !== undefined && result.generation) deck.update(item.target, { ...deck.snapshots[item.target], ...result });
  $("#codex-step").classList.add("active");
  status(`${item.label} · 전달 완료`, "success");
  await Promise.allSettled([browserTerminal.poll(), pollQuestions()]);
}
async function executeKey(item, source) {
  if (!deck.isCurrent(item)) { status("질문 또는 모드가 바뀌었습니다. 현재 화면을 확인하고 다시 눌러 주세요.", "error"); return; }
  if (!available(item, false)) { status("현재 사용할 수 없는 버튼입니다. 질문·실행 상태와 연결을 확인해 주세요.", "error"); return; }
  state.count++; $("#event-count").textContent = state.count; animateKey(item); log(source === "web" ? "KEY" : "RX", `${item.slot} ${item.label} · ${source}`, "sent");
  let commandPending = false;
  try {
    if (item.action === "mode") return await toggleProfile();
    if (["board_sound", "audio_stop"].includes(item.action)) {
      // Hardware presses and acknowledged screen keys already run audio on UNO.
      // Do not send a duplicate playback command or an AI terminal action.
      status(item.action === "audio_stop" ? "음성 출력 정지 명령 전달" : `${item.label} · 음성 재생 명령 전달`);
      return;
    }
    if (item.workflow) return await workflow.trigger(item.action);
    if (deck.toggleSelection(item)) { status(`${deck.selected.size}개 선택 · 선택 완료 버튼으로 답변을 전달하세요.`); return; }
    commandPending = true; state.busy = true; setControls();
    if (["codex-yolo", "claude-yolo"].includes(item.action)) { await browserTerminal.start(item.action); return; }
    if (item.action === "model" && deck.config.mode === "agent") {
      await sendCommand(item);
      deck.knobAction = "model";
      status("MODEL 목록 요청 전달 · 목록을 닫은 뒤 A0 노브로 추론 강도 조절");
    } else {
      await sendCommand(item);
      if (deck.config.mode === "agent" && item.action !== "answer") deck.knobAction = item.action;
    }
  } catch (error) { status(error.message, "error"); log("ERR", error.message, "error"); }
  finally { if (commandPending) state.busy = false; renderProfile(); }
}
async function triggerKey(slot, source = "screen") {
  if (browserTerminal.running && !browserTerminal.managed) {
    browserTerminal.syncNativeQuestion();
    if (browserTerminal.lastSnapshot) browserTerminal.options.onChange(browserTerminal.lastSnapshot);
  }
  if (source !== "screen") {
    if (state.source !== "hardware" || serialBridge.state !== "connected") return;
    if (source === "hardware" && state.serialBusy) return;
    const item = source === "simulator" ? pendingKey : deck.capture(slot);
    if (!item || item.slot !== slot) return;
    if (source === "simulator") pendingKey = null;
    return executeKey(item, source === "simulator" ? "Arduino echo" : "Arduino input");
  }
  const item = deck.capture(slot);
  if (!available(item)) { status("이 버튼은 현재 사용할 수 없습니다. USB 연결과 질문·AI 실행 상태를 확인하세요.", "error"); return; }
  if (state.source !== "hardware") return executeKey(item, "web");
  state.serialBusy = true; pendingKey = item; setControls();
  try { log("TX", `key:${slot} · 화면 → Arduino`); await serialBridge.sendKey(slot); }
  catch (error) { status(error.message, "error"); log("ERR", error.message, "error"); }
  finally { pendingKey = null; state.serialBusy = false; setControls(); }
}
$("#deck-profile").onclick = () => triggerKey(8);
for (const button of document.querySelectorAll(".deck-key")) {
  const slot = Number(button.id.split("-").at(-1));
  button.onclick = () => triggerKey(slot);
  button.onkeydown = event => { if (["Enter", " "].includes(event.key) && !event.repeat) { event.preventDefault(); triggerKey(slot); } };
}
function pageQuestion(delta) { if (state.busy || state.serialBusy) return; deck.movePage(delta); renderProfile(); }
$("#question-prev").onclick = () => pageQuestion(-1);
$("#question-next").onclick = () => pageQuestion(1);
$("#question-answer-form").onsubmit = event => {
  event.preventDefault(); const text = $("#question-answer").value.trim();
  if (text) executeKey(deck.captureAnswer({ text }), "web");
};
$("#question-selection-send").onclick = () => {
  if (deck.selected.size) executeKey(deck.captureAnswer({ choice: Array.from(deck.selected) }), "web");
};
async function applyEffort(effort, source) {
  if (!EFFORTS.includes(effort) || state.busy || deck.question) return;
  const binding = knobBinding(deck.config.mode, deck.knobAction, deck.question);
  if (binding.rotate === "autonomy") return workflow.setAutonomy(EFFORTS.indexOf(effort));
  if (binding.rotate !== "effort") return;
  state.busy = true; setControls();
  try {
    await browserTerminal.setEffort(effort, state.effort);
    state.effort = effort; updateOled(); log("KNOB", `${effort.toUpperCase()} · ${source}`);
    status(`추론 강도: ${effort.toUpperCase()}`);
  } catch (error) { status(error.message, "error"); }
  finally { state.busy = false; setControls(); }
}
function knobIdentity() { return JSON.stringify([deck.config.mode, deck.knobAction, deck.identity(), state.source]); }
async function useKnob(value, origin = "screen") {
  if (origin === "screen" && $("#deck-knob").getAttribute("aria-disabled") === "true") return;
  if (origin !== "screen" && (state.source !== "hardware" || serialBridge.state !== "connected")) return;
  if (origin === "simulator") {
    if (!pendingKnob || pendingKnob.value !== value || pendingKnob.identity !== knobIdentity()) return;
    pendingKnob = null;
  } else if (state.serialBusy || state.busy) return;
  if (origin === "screen" && state.source === "hardware") {
    state.serialBusy = true; pendingKnob = { value, identity: knobIdentity() }; setControls();
    try { await serialBridge.sendKnob(value); } catch (error) { status(error.message, "error"); }
    finally { pendingKnob = null; state.serialBusy = false; setControls(); }
    return;
  }
  const binding = knobBinding(deck.config.mode, deck.knobAction, deck.question);
  const press = value === "press", delta = value === "left" ? -1 : 1;
  try {
    if (binding.rotate === "volume") {
      status(state.source === "hardware" ? "음량 조절 입력 전달 · OLED에서 설정값을 확인하세요." : "실물 보드를 연결하면 모드 3 노브로 음량을 조절합니다.");
      return;
    }
    if (!press && binding.rotate === "questions") { deck.movePage(delta); renderProfile(); return; }
    if (binding.rotate === "effort" && !press || binding.rotate === "autonomy") {
      const current = binding.rotate === "autonomy" ? workflow.data.autonomy : EFFORTS.indexOf(state.effort);
      const next = Math.max(0, Math.min(binding.rotate === "autonomy" ? AUTONOMY.length - 1 : 3, current + (press ? 1 : delta)));
      if (next !== current) {
        if (binding.rotate === "autonomy") await workflow.setAutonomy(next);
        else await applyEffort(EFFORTS[next], origin);
      }
      return;
    }
    state.busy = true; setControls();
    await browserTerminal.knobInput(press ? binding.press : binding.rotate, delta);
    status(`${binding.label} · ${binding.hint}`);
  } catch (error) { status(error.message, "error"); }
  finally { state.busy = false; renderProfile(); }
}
$("#deck-knob").onclick = () => useKnob("press");
$("#deck-knob").onkeydown = event => {
  if (!event.repeat && ["ArrowLeft", "ArrowRight", "Enter", " "].includes(event.key)) {
    event.preventDefault(); useKnob(event.key === "ArrowLeft" ? "left" : event.key === "ArrowRight" ? "right" : "press");
  }
};
$("#deck-knob").addEventListener("wheel", event => { event.preventDefault(); useKnob(event.deltaY < 0 ? "left" : "right"); }, { passive: false });
$("#clear-log").onclick = () => { $("#serial-log").replaceChildren(); state.count = 0; $("#event-count").textContent = "0"; drawMatrix("idle"); log("SYS", "Monitor cleared"); };

function refreshTarget() {
  $("#terminal-session-id").textContent = !state.serverOnline ? "OFFLINE" : state.terminalThread ? state.terminalThread.slice(0, 8) : state.terminalReady ? "연결됨" : "대기";
  $("#terminal-session-id").title = state.terminalThread || "";
  renderProfile();
}
function applyPot(value, reverseConfirmed = false) {
  if (!Number.isInteger(value) || value < 0 || value > 1023 || state.source !== "hardware") return;
  clearTimeout(potReverseTimer); potReverseTimer = null;
  potPosition = value;
  const identity = knobIdentity();
  // Custom-mode analog volume is applied locally by the firmware, not the AI.
  if (deck.config.mode === "custom") { potAnchor=value;potContext=identity;potDirection=0;return; }
  if (potContext !== identity || potAnchor === null) { potContext=identity;potAnchor=value;potDirection=0;return; }
  if (state.busy || state.serialBusy || browserTerminal.nativePending) { potAnchor=value;return; }
  const delta=value-potAnchor;
  const binding=knobBinding(deck.config.mode,deck.knobAction,deck.question);
  if (binding.rotate === "effort" || binding.rotate === "autonomy") {
    // Relative steps use any working part of the knob's travel. Firmware already
    // smooths ADC readings; this dead band rejects small jitter, and one event
    // can change at most one level even if a worn contact produces a large jump.
    const direction = Math.sign(delta);
    const reversing = potDirection !== 0 && direction !== potDirection;
    if (Math.abs(delta)<(reversing?72:48)) return;
    // A worn contact may briefly bounce backwards. Confirm a reversal only
    // after it holds steady; continuing rotation still uses the short step.
    if (reversing && !reverseConfirmed) {
      potReverseTimer = setTimeout(() => {
        if (potContext === identity && knobIdentity() === identity && potPosition === value)
          applyPot(value, true);
      }, 80);
      return;
    }
    potAnchor=value;
    potDirection=direction;
    const count=binding.rotate === "autonomy" ? AUTONOMY.length : EFFORTS.length;
    const current=binding.rotate === "effort" ? EFFORTS.indexOf(state.effort) : workflow.data.autonomy;
    // Saturate at both ends. Never wrap highest -> lowest or lowest -> highest.
    const next=Math.max(0,Math.min(count-1,current+direction));
    if (next!==current) {
      if (binding.rotate === "autonomy") workflow.setAutonomy(next);
      else applyEffort(EFFORTS[next],"A0");
    }
  } else {
    if (Math.abs(delta)<24) return;
    potAnchor=value;
    useKnob(delta>0?"right":"left","hardware");
  }
}
const boardCallbacks = {
  onKey: (slot, origin) => triggerKey(slot, origin),
  onPot: value => applyPot(value),
  onPotReset: value => {
    clearTimeout(potReverseTimer);potReverseTimer=null;
    potPosition=value;potAnchor=null;potDirection=0;potContext="";
  },
  onKnob: (value, origin) => useKnob(value, origin),
  onEffort: (effort, origin) => { if (state.source !== "hardware" || state.serialBusy) return; lastOled = ""; applyEffort(effort, origin); },
  onLog: line => log(serialBridge.isWifi ? "WIFI" : "USB", line),
  onState: (connection, message) => {
    lastOled = ""; clearTimeout(oledTimer); oledTimer = setTimeout(syncOled, 200);
    $("#hardware-status").textContent = message; $("#hardware-connect").title = message; $("#hardware-box").classList.toggle("connected", connection === "connected");
    const transport=serialBridge.isWifi?"Wi-Fi":"USB";
    $("#hardware-connect").textContent = connection === "connected" ? `${transport} 연결 해제` : `${transport} 연결`;
    $("#hardware-transport").disabled = connection === "connected" || ["connecting","syncing","disconnecting"].includes(connection);
    if (connection !== "connected") { potContext="";potAnchor=null; }
    const transitioning = ["connecting", "syncing", "disconnecting"].includes(connection);
    $("#hardware-connect").disabled = transitioning || connection === "unsupported";
    $("#source-web").disabled = transitioning; $("#source-hardware").disabled = transitioning;
    if (state.source === "hardware") $("#board-mode-tag").textContent = connection === "connected" ? `${transport} LIVE + SIM` : `${transport} + SIM`;
    log("USB", message, connection === "error" ? "error" : ""); refreshTarget();
  },
};
const usbBridge = new ButtonSerial(navigator.serial, boardCallbacks);
const wifiBridge = new ButtonWifi(api, boardCallbacks);
let serialBridge = usbBridge;
$("#hardware-settings-open").onclick = () => $("#hardware-settings").showModal();
$("#hardware-settings-close").onclick = () => $("#hardware-settings").close();
$("#hardware-transport").onchange = async () => {
  await serialBridge.disconnect();
  serialBridge = $("#hardware-transport").value === "wifi" ? wifiBridge : usbBridge;
  $("#wifi-fields").hidden = !serialBridge.isWifi;
  if (serialBridge.isWifi) $("#hardware-settings").showModal();
  serialBridge.update(serialBridge.state, serialBridge.isWifi ? "OLED의 보드 IP를 입력하세요. API 토큰은 필요하지 않습니다." : "USB 보드를 연결해 주세요.");
};

async function changeSource(source) {
  if (source === state.source || state.busy || state.serialBusy || ["connecting", "syncing", "disconnecting"].includes(serialBridge.state)) return;
  state.source = source; if (source === "web" && ["connected", "connecting", "syncing"].includes(serialBridge.state)) await serialBridge.disconnect();
  const hardware = source === "hardware";
  for (const value of ["web", "hardware"]) { $(`#source-${value}`).classList.toggle("selected", value === source); $(`#source-${value}`).setAttribute("aria-selected", String(value === source)); }
  $("#hardware-box").hidden = !hardware; $("#circuit-stage").classList.toggle("hardware", hardware);
  $("#board-mode-title").hidden = hardware;
  $("#board-mode-tag").textContent = hardware ? "USB + SIM" : "SIMULATOR"; $("#serial-source").textContent = hardware ? "HYBRID INPUT" : "VIRTUAL SERIAL";
  $("#hardware-status").textContent = hardware && !serialBridge.isWifi && !navigator.serial ? "USB 시리얼은 데스크톱 Chrome에서 연결해 주세요." : "최신 8버튼 펌웨어를 업로드한 뒤 USB 보드를 연결해 주세요.";
  $("#hardware-connect").title = $("#hardware-status").textContent;
  if (hardware && !serialBridge.isWifi && !navigator.serial) $("#hardware-connect").disabled = true;
  refreshTarget();
}
$("#source-web").onclick = () => changeSource("web"); $("#source-hardware").onclick = () => changeSource("hardware");
$("#hardware-connect").onclick = () => serialBridge.state === "connected" ? serialBridge.disconnect()
  : serialBridge.isWifi ? serialBridge.connect($("#board-ip").value.trim()) : serialBridge.connect();
document.querySelectorAll("[data-audio]").forEach(button => button.onclick = async () => {
  try {
    const command=button.dataset.audio === "volume" ? `audio:volume:${$("#audio-volume").value}` : button.dataset.audio === "play" ? `audio:play:${$("#audio-track").value}` : `audio:${button.dataset.audio}`;
    await serialBridge.sendAudio(command);status("DFPlayer Pro에 명령을 전달했습니다.");
  } catch(error) { status(error.message,"error"); }
});
$("#hardware-guide-link").onclick = event => { event.preventDefault(); $("#hardware-guide").showModal(); };
$("#hardware-guide-close").onclick = () => $("#hardware-guide").close();
async function loadSession() {
  state.session = await api("/api/session"); state.serverOnline = true;
  $("#terminal-workspace").textContent = state.session.workspace || ""; $("#terminal-workspace").title = state.session.workspace || "";
  if (!configLoaded) { deck.configure(await api("/api/controls")); configLoaded = true; }
  refreshTarget(); return state.session;
}
const browserTerminal = new BrowserTerminal({
  getToken: () => state.session?.token, getReasoning: () => state.effort,
  hasCodex: () => state.session?.codexAvailable, hasClaude: () => state.session?.claudeAvailable,
  refreshSession: loadSession,
  onConnection: online => { if (state.serverOnline !== online) { state.serverOnline = online; refreshTarget(); } },
  onChange: snapshot => {
    state.terminalThread = snapshot.thread || ""; state.terminalReady = Boolean(snapshot.managed ? snapshot.ready : snapshot.buttonReady);
    if (snapshot.effort && !state.busy && !deck.question) state.effort = snapshot.effort;
    deck.update("terminal", { ...snapshot, ready: state.terminalReady }); refreshTarget();
  },
  onStarted: kind => { deck.knobAction = null; if (kind !== "shell") { state.target = "terminal"; deck.setTarget("terminal"); refreshTarget(); } },
});
workflow = new WorkflowController({ getToken: () => state.session?.token, log, status,
  onChange: () => { if (workflow) deck.update("workflow", { ...workflow.data, generation: workflow.data.generation || workflow.data.runId, ready: !workflow.data.running }); renderProfile(); },
});
// Keep emergency stop and reviewed restore reachable independently of mode/USB.
$("#workflow-emergency").onclick = () => workflow.stop();
$("#workflow-restore").onclick = () => workflow.preview();
async function pollQuestions() {
  if (questionsPolling || !state.session?.token) return;
  questionsPolling = true;
  try { deck.update("current", await api("/api/questions?target=current")); renderProfile(); }
  catch (error) { deck.update("current", { ...deck.snapshots.current, ready: false }); setControls(); }
  finally { questionsPolling = false; }
}
async function questionLoop() { await pollQuestions(); setTimeout(questionLoop, 1000); }
async function connectSession() {
  try { await loadSession(); status("준비되었습니다."); }
  catch (error) { state.serverOnline = false; status(error.message, "error"); refreshTarget(); setTimeout(connectSession, 2500); }
}

function openCustom() {
  const rows = deck.config.custom.map((entry, i) => {
    const row = document.createElement("fieldset"); row.dataset.slot = i;
    const legend = document.createElement("legend"); legend.textContent = `버튼 ${i + 1}`; row.append(legend);
    const field = (name, label, element) => { const wrapper = document.createElement("label"); wrapper.textContent = label; element.name = name; wrapper.append(element); row.append(wrapper); return element; };
    const label = field("label", "버튼 이름", document.createElement("input")); label.value = entry.label; label.maxLength = 24; label.required = true;
    const target = field("target", "실행 대상", document.createElement("select"));
    for (const [value, text] of [["terminal", "웹 AI"], ["current", "기존 Codex 세션 · 메시지 응답"]]) target.add(new Option(text, value)); target.value = entry.target;
    const action = field("action", "기능", document.createElement("select"));
    for (const [value, text] of [["prompt", "프롬프트 보내기"], ["accept", "ACCEPT · 동의"], ["denied", "DENIED · 거절"], ["continue", "CONTINUE · 계속"], ["retry", "RETRY · 재시도"], ["stop", "STOP · 웹 AI 중단"]]) action.add(new Option(text, value)); action.value = entry.action;
    const prompt = field("text", "전송할 프롬프트 (비워 두면 버튼 비활성)", document.createElement("textarea")); prompt.value = entry.text || ""; prompt.rows = 2; prompt.maxLength = 8192;
    const update = () => { prompt.disabled = action.value !== "prompt"; };
    action.onchange = update; update();
    if (i < 4 || i === 6) { row.disabled = true; legend.textContent = `버튼 ${i+1} · ${["거제야호", "오이시", "러브어택", "대자부", "", "", "STOP"][i]} 고정 (기존 설정은 보존됨)`; }
    return row;
  });
  $("#custom-entries").replaceChildren(...rows); $("#custom-status").textContent = "모드 3에서는 노브가 항상 음량을 조절합니다. 1~4번 음원 재생 · 5~6번 사용자 지정 · 7번 음성 STOP."; $("#custom-dialog").showModal();
}
$("#custom-open").onclick = openCustom;
$("#custom-close").onclick = () => $("#custom-dialog").close();
$("#custom-form").onsubmit = async event => {
  event.preventDefault();
  const custom = Array.from($("#custom-entries").children, row => Object.fromEntries(["label", "target", "action", "text"].map(name => [name, row.querySelector(`[name="${name}"]`).value])));
  $("#custom-save").disabled = true;
  try { await saveConfig({ mode: deck.config.mode, custom }); $("#custom-dialog").close(); status("커스텀 버튼 7개를 저장했습니다.", "success"); }
  catch (error) { $("#custom-status").textContent = error.message; }
  finally { $("#custom-save").disabled = false; }
};
drawMatrix("idle"); renderProfile(); log("SYS", "7 function keys + B8 MODE · AI CONTROL / AI-DLC / CUSTOM");
connectSession(); questionLoop();
