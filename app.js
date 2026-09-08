"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { source: "web", serverOnline: false, claudeRunning: false, connectionKey: "", session: null, busy: false, count: 0, lastPress: -Infinity, timer: null, claudeState: null, statePoll: null };

// A press can be delivered when the server is up, Claude CLI exists, and a Claude
// session is running in the app-owned PTY (the server enforces this too).
function canSend() {
  return Boolean(state.serverOnline && state.session?.claudeAvailable && state.claudeRunning);
}

// Logical actions the BindDeck / virtual board can emit (mirror of terminal.ACTIONS).
const ACTION_LABELS = { yes: "YES", no: "NO", stop: "STOP", confirm: "ENTER", nav_up: "▲", nav_down: "▼" };

const matrix = $("#led-matrix");
const dots = [];
for (let row = 0; row < 8; row++) {
  for (let col = 0; col < 12; col++) {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", 387 + col * 7);
    dot.setAttribute("cy", 162 + row * 7);
    dot.setAttribute("r", "1.7");
    dot.setAttribute("class", "led-dot");
    matrix.append(dot);
    dots.push(dot);
  }
}

const patterns = {
  idle: ["000000000000", "000110011000", "001001100100", "001000000100", "000100001000", "000010010000", "000001100000", "000000000000"],
  yes: ["000000000000", "000000000100", "000000001100", "001000011000", "001100110000", "000111100000", "000011000000", "000000000000"],
  no: ["000000000000", "001100001100", "000110011000", "000011110000", "000011110000", "000110011000", "001100001100", "000000000000"],
};

function drawMatrix(name) {
  const bits = (patterns[name] || patterns.idle).join("");
  dots.forEach((dot, i) => dot.classList.toggle("on", bits[i] === "1"));
}

function log(kind, message, style = "") {
  const line = document.createElement("div");
  line.className = `log-line ${style}`;
  for (const [className, text] of [
    ["log-time", new Date().toLocaleTimeString("en-GB", { hour12: false })],
    ["log-kind", kind],
    ["log-text", message],
  ]) {
    const span = document.createElement("span");
    span.className = className;
    span.textContent = text;
    line.append(span);
  }
  const container = $("#serial-log");
  container.append(line);
  while (container.childElementCount > 100) container.firstChild.remove();
  container.scrollTop = container.scrollHeight;
}

function status(message, type = "") {
  $("#response-text").textContent = message;
  $("#response-status").className = `response-status ${type}`;
}

function connectionHint() {
  if (!state.serverOnline) return "서버 연결 대기 · 연결이 복구되면 버튼이 자동 활성화됩니다.";
  if (!state.session?.claudeAvailable) return "Claude Code CLI 설치와 로그인을 확인해 주세요.";
  if (!state.claudeRunning) return "웹 터미널에서 Claude를 시작해 주세요.";
  if (state.source === "hardware" && serialBridge.state !== "connected") return "USB BindDeck를 연결하면 실물 버튼 입력이 Claude에 전송됩니다.";
  return state.source === "hardware"
    ? "Claude 연결됨 · BindDeck 버튼과 엔코더로 답하세요."
    : "Claude 연결됨 · 버튼을 누르면 Claude 세션에 바로 전송됩니다.";
}

function animate(choice) {
  clearTimeout(state.timer);
  const stage = $("#circuit-stage");
  stage.classList.remove("signal-yes", "signal-no");
  if (choice === "yes" || choice === "no") stage.classList.add(`signal-${choice}`);
  document.querySelectorAll("[data-choice]").forEach((button) => {
    button.classList.toggle("pressed", button.dataset.choice === choice);
  });
  $("#serial-step").classList.add("active");
  drawMatrix(choice);
  state.timer = setTimeout(() => {
    stage.classList.remove("signal-yes", "signal-no");
    document.querySelectorAll(".pressed").forEach((button) => button.classList.remove("pressed"));
    $("#serial-step").classList.remove("active");
  }, 550);
}

function setBusy(busy) {
  state.busy = busy;
  // Hardware mode normally disables the on-screen controls (input comes from the
  // device); with the fake serial port connected, keep them live so a click emits a
  // BTN:/ENC: line through the real serial path.
  const fakeHardwareLive = Boolean(window.fakeBindDeckSerial) && state.source === "hardware" && serialBridge.state === "connected";
  const disabled = busy || !canSend() || (state.source !== "web" && !fakeHardwareLive);
  document.querySelectorAll("button[data-choice]").forEach((button) => { button.disabled = disabled; });
  document.querySelectorAll(".board-button").forEach((button) => {
    button.setAttribute("aria-disabled", String(disabled));
    button.setAttribute("tabindex", disabled ? "-1" : "0");
  });
}

async function press(choice, source = "web") {
  if (!ACTION_LABELS[choice]) return;
  if (source !== state.source || (source === "hardware" && serialBridge.state !== "connected")) return;
  if (!canSend()) {
    status(connectionHint());
    if (source === "hardware") log("SKIP", `${choice} · Claude 연결 대기`, "error");
    return;
  }
  const now = performance.now();
  if (state.busy || now - state.lastPress < 250) {
    if (source === "hardware") log("SKIP", `${choice} · 이전 입력 처리 중`, "error");
    return;
  }
  state.lastPress = now;
  animate(choice);
  state.count++;
  $("#event-count").textContent = state.count;
  log(source === "hardware" ? "RX" : "TX", `${choice} · ${ACTION_LABELS[choice]}`, choice === "yes" || choice === "no" ? choice : "");
  setBusy(true);
  status(`${ACTION_LABELS[choice]} 입력을 Claude에 전송하고 있어요…`);
  try {
    const response = await fetch("/api/press", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Simulator-Token": state.session.token },
      body: JSON.stringify({ choice, requestId: crypto.randomUUID() }),
      signal: AbortSignal.timeout(25000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "전송에 실패했습니다.");
    $("#claude-step").classList.add("active");
    log("SEND", `${choice} → Claude PTY`, "sent");
    status(`${ACTION_LABELS[choice]} 입력을 Claude에 전송했어요`, "success");
  } catch (error) {
    const message = error.name === "TimeoutError" || error instanceof TypeError
      ? "연결 상태를 확인할 수 없어요. 다시 누르기 전에 Claude 화면을 확인해 주세요."
      : error.message;
    log("ERR", message, "error");
    status(message, "error");
    $("#claude-step").classList.remove("active");
  } finally {
    setBusy(false);
    refreshTarget();
  }
}

// Route a control activation to the right place: straight to the server (web sim), or —
// when the fake serial port is active and we're in hardware mode — through the fake
// BindDeck so the real serial.js parse/onChoice path runs (a device-free demo).
function activate(choice) {
  if (window.fakeBindDeckSerial && state.source === "hardware") window.fakeBindDeck?.press(choice);
  else press(choice);
}

document.querySelectorAll("[data-choice]").forEach((button) => {
  button.addEventListener("click", () => activate(button.dataset.choice));
  button.addEventListener("keydown", (event) => {
    if (event.repeat && (event.key === "Enter" || event.key === " ")) event.preventDefault();
  });
  if (button.tagName.toLowerCase() === "g") {
    button.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && !event.repeat) {
        event.preventDefault();
        activate(button.dataset.choice);
      }
    });
  }
});

document.addEventListener("keydown", (event) => {
  if (event.repeat || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
  // Skip when a control is focused so its native activation (Enter/Space) isn't double-fired.
  if (event.target.closest("input, textarea, select, [contenteditable=true], #terminal-screen, [data-choice]")) return;
  const choice = { y: "yes", n: "no", arrowup: "nav_up", arrowdown: "nav_down", enter: "confirm", escape: "stop" }[event.key.toLowerCase()];
  if (choice) { event.preventDefault(); activate(choice); }
});
$("#clear-log").addEventListener("click", () => {
  $("#serial-log").replaceChildren();
  state.count = 0;
  $("#event-count").textContent = "0";
  drawMatrix("idle");
  log("SYS", "Monitor cleared");
});

drawMatrix("idle");
log("SYS", "BindDeck virtual board ready");
log("INIT", "BTN:0→YES, BTN:1→NO, BTN:2→STOP, ENC→menu, BTN:8→ENTER");

async function loadSession() {
    const response = await fetch("/api/session", { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error("세션에 연결할 수 없습니다.");
    const session = await response.json();
    state.session = session;
    state.serverOnline = true;
    $("#terminal-workspace").textContent = session.workspace || "";
    $("#terminal-workspace").title = session.workspace || "";
    refreshTarget();
    return session;
}

const STATE_WORDS = { waiting: "승인 대기", active: "작업 중", idle: "대기", offline: "연결 없음" };

// Poll the Claude session state and mirror it to the OLED over Web Serial (FR-5).
async function pollState() {
  clearTimeout(state.statePoll);
  try {
    if (state.session?.token) {
      const response = await fetch("/api/state", { headers: { "X-Simulator-Token": state.session.token }, signal: AbortSignal.timeout(5000) });
      if (response.ok) {
        const snapshot = await response.json();
        state.claudeState = snapshot;
        const word = STATE_WORDS[snapshot.status] || snapshot.status || "";
        $("#claude-state").textContent = `Claude · ${word}${snapshot.lastAnswer ? " · " + (ACTION_LABELS[snapshot.lastAnswer] || snapshot.lastAnswer) : ""}`;
        if (state.source === "hardware" && serialBridge.state === "connected") {
          const oled = `${(snapshot.status || "").toUpperCase()}${snapshot.lastAnswer ? " " + (ACTION_LABELS[snapshot.lastAnswer] || snapshot.lastAnswer) : ""}`;
          serialBridge.sendMessage(oled);
        }
      }
    }
  } catch { /* Transient; retried on the next tick. */ }
  finally {
    state.statePoll = setTimeout(pollState, document.hidden ? 3000 : 1200);
  }
}

function refreshTarget() {
  $("#session-label").textContent = "연결 대상 · Claude 세션";
  $("#session-id").textContent = !state.serverOnline ? "OFFLINE" : state.claudeRunning ? "Claude 실행 중" : "세션 대기";
  $("#stage-hint").textContent = !canSend() ? "Claude 세션을 시작한 뒤 버튼을 사용할 수 있어요"
    : state.source === "hardware" ? "BindDeck 버튼으로 Claude에 답하세요" : "버튼을 누르면 Claude로 전송됩니다 ↗";
  const connectionKey = JSON.stringify([state.source, state.claudeRunning, canSend(), state.serverOnline, serialBridge.state]);
  if (connectionKey !== state.connectionKey && !state.busy) {
    state.connectionKey = connectionKey;
    $("#claude-step").classList.remove("active");
    status(connectionHint());
  }
  setBusy(state.busy);
}

// Prefer an injected fake Web Serial port (demo/fake-serial.js, ?fakeserial=1) so the
// real hardware path runs with no device; fall back to the browser's navigator.serial.
const serialImpl = window.fakeBindDeckSerial || navigator.serial;
const serialBridge = new ButtonSerial(serialImpl, {
  onChoice: choice => press(choice, "hardware"),
  onLog: line => log("USB", line),
  onState: (connection, message) => {
    $("#hardware-status").textContent = message;
    $("#hardware-box").classList.toggle("connected", connection === "connected");
    $("#hardware-connect").textContent = connection === "connected" ? "USB 연결 해제" : "USB BindDeck 연결";
    const transitioning = ["connecting", "syncing", "disconnecting"].includes(connection);
    $("#hardware-connect").disabled = transitioning || connection === "unsupported";
    $("#source-web").disabled = transitioning;
    $("#source-hardware").disabled = transitioning;
    if (state.source === "hardware") $("#board-mode-tag").textContent = connection === "connected" ? "USB LIVE" : "USB 대기";
    log("USB", message, connection === "error" ? "error" : "");
    refreshTarget();
  },
});

async function changeSource(source) {
  if (source === state.source || state.busy || ["connecting", "syncing", "disconnecting"].includes(serialBridge.state)) return;
  state.source = source;
  if (source === "web" && serialBridge.port) await serialBridge.disconnect();
  const hardware = source === "hardware";
  $("#board-control-title").textContent = hardware ? "실물 BindDeck · 응답 컨트롤" : "가상 보드 · 응답 컨트롤";
  $("#source-web").classList.toggle("selected", !hardware);
  $("#source-hardware").classList.toggle("selected", hardware);
  $("#source-web").setAttribute("aria-pressed", String(!hardware));
  $("#source-hardware").setAttribute("aria-pressed", String(hardware));
  $("#hardware-box").hidden = !hardware;
  $("#circuit-stage").classList.toggle("hardware", hardware);
  $("#board-mode-title").textContent = hardware ? "실물 BindDeck 입력" : "가상 보드";
  $("#board-mode-tag").textContent = hardware ? "USB 대기" : "SIMULATOR";
  $("#serial-source").textContent = hardware ? "USB SERIAL" : "VIRTUAL SERIAL";
  if (hardware && !serialImpl) {
    $("#hardware-status").textContent = "이 브라우저는 USB 시리얼을 지원하지 않습니다. 데스크톱 Chrome에서 열어 주세요.";
    $("#hardware-connect").disabled = true;
  } else if (hardware) $("#hardware-status").textContent = window.fakeBindDeckSerial
    ? "가짜 BindDeck 시리얼 · ‘USB BindDeck 연결’을 누르면 장치 없이 바로 연결됩니다."
    : "binddeck_claude 펌웨어를 업로드한 뒤 USB 보드를 연결해 주세요.";
  refreshTarget();
}
$("#source-web").addEventListener("click", () => changeSource("web"));
$("#source-hardware").addEventListener("click", () => changeSource("hardware"));
$("#hardware-connect").addEventListener("click", () => serialBridge.state === "connected" ? serialBridge.disconnect() : serialBridge.connect());

const browserTerminal = new BrowserTerminal({
  getToken: () => state.session?.token,
  hasClaude: () => state.session?.claudeAvailable,
  refreshSession: loadSession,
  onConnection: online => {
    if (state.serverOnline !== online) {
      state.serverOnline = online;
      refreshTarget();
    }
  },
  onChange: snapshot => {
    const running = Boolean(snapshot.running && snapshot.kind === "claude");
    if (state.claudeRunning !== running) {
      state.claudeRunning = running;
      refreshTarget();
    }
  },
});

async function connectSession() {
  try { await loadSession(); pollState(); } catch {
    state.serverOnline = false;
    refreshTarget();
    $("#session-label").textContent = "서버 연결을 확인해 주세요";
    $("#session-id").textContent = "OFFLINE";
    log("SYS", "Claude 연결 대기 · 버튼 비활성화");
    setTimeout(connectSession, 2500);
  }
}
connectSession();
