"use strict";

const DENIED_MESSAGE = "현재 제안은 거절합니다. 같은 방법을 반복하지 말고 다른 대안을 제안해 주세요. 새 대안은 바로 실행하지 말고 제 승인을 기다려 주세요.";
const CHECK_MESSAGE = "지금까지 한 작업을 직접 검증해 주세요. 관련 테스트를 실행하고 오류·누락·요구사항 충족 여부를 확인한 뒤, 수행한 검증과 결과를 보고해 주세요. 이미 검증했더라도 현재 상태를 기준으로 다시 확인해 주세요. 직접 확인할 수 없는 항목은 미검증으로 구분하고, 실제 장치 조작 등 사용자만 할 수 있는 확인만 요청해 주세요.";

class BrowserTerminal {
  constructor(options) {
    this.options = options;
    this.generation = ""; this.cursor = 0; this.running = false; this.thread = "";
    this.pending = false; this.polling = false; this.timer = null;
    this.inputChain = Promise.resolve();
    this.inputBlocked = false;
    this.kind = "shell";
    this.managed = false; this.ready = false; this.busy = false; this.question = null;
    this.mode = "build";
    this.buttonThread = "";
    this.checkingThread = "";
    this.nextButtonCheck = 0;
    this.reconnecting = false;
    this.nativeSignature = ""; this.nativeSince = 0; this.nativePending = false;
    this.dismissedNative = ""; this.lastSnapshot = null;
    this.term = new Terminal({ fontSize: 12, fontFamily: 'Menlo, Consolas, monospace', cursorBlink: true, scrollback: 3000, theme: { background: '#192826', foreground: '#d7e4cf', cursor: '#9acb8c', selectionBackground: '#496b4c' } });
    this.fit = new FitAddon.FitAddon();
    this.term.loadAddon(this.fit);
    this.term.open(document.querySelector("#terminal-screen"));
    this.term.onData(data => this.input(data));
    this.term.onResize(({ cols, rows }) => {
      clearTimeout(this.resizeTimer);
      const generation = this.generation;
      this.resizeTimer = setTimeout(() => {
        if (this.running) this.request("resize", { cols, rows, generation }).catch(error => this.message(error.message));
      }, 100);
    });
    this.resizeObserver = new ResizeObserver(() => this.fit.fit());
    this.resizeObserver.observe(document.querySelector("#terminal-screen"));
    document.querySelectorAll("[data-service]").forEach(button => {
      button.addEventListener("click", () => this.start(button.dataset.service));
    });
    document.querySelector("#terminal-stop").addEventListener("click", () => this.stop());
    document.querySelector("#terminal-prompt-form").addEventListener("submit", event => { event.preventDefault(); this.submitPrompt(); });
    this.fit.fit();
    this.poll();
  }
  message(text) { document.querySelector("#terminal-message").textContent = text; }
  async request(action, payload) {
    const response = await fetch(`/api/terminal/${action}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Simulator-Token": this.options.getToken() || "" },
      body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "터미널 요청에 실패했습니다.");
    return result;
  }
  controls() {
    const ready = Boolean(this.options.getToken());
    const disabled = !ready || this.pending || this.running;
    document.querySelectorAll("[data-service]").forEach(button => {
      const available = button.dataset.service.startsWith("claude") ? this.options.hasClaude() : this.options.hasCodex();
      button.disabled = disabled || !available;
      button.title = available ? "새 세션을 시작하고 hi를 자동 전송합니다." : "CLI를 찾을 수 없습니다.";
    });
    document.querySelector("#terminal-stop").disabled = this.pending || !this.running;
    document.querySelector("#terminal-prompt-form").hidden = !this.managed;
    document.querySelector("#terminal-prompt-send").disabled = this.pending || !this.ready || this.busy || Boolean(this.question);
    document.querySelector("#terminal-prompt").disabled = this.pending || !this.ready || this.busy || Boolean(this.question);
  }
  async apply(snapshot) {
    this.running = snapshot.running;
    this.kind = snapshot.kind || "shell";
    this.generation = snapshot.generation;
    this.cursor = snapshot.cursor;
    this.thread = snapshot.thread;
    this.managed = Boolean(snapshot.managed); this.ready = Boolean(snapshot.ready);
    this.busy = Boolean(snapshot.busy); this.question = snapshot.question || null;
    if (snapshot.reset) this.term.reset();
    if (snapshot.data) await new Promise(resolve => this.term.write(Uint8Array.from(atob(snapshot.data), char => char.charCodeAt(0)), resolve));
    this.syncNativeQuestion(snapshot);
    this.lastSnapshot = snapshot;
    const badge = document.querySelector("#terminal-state");
    const label = snapshot.kind === "claude-yolo" ? "Claude Bypass permissions 실행 중" : snapshot.kind === "codex-yolo" ? "Codex YOLO 실행 중"
      : snapshot.kind === "claude" ? "Claude 실행 중" : snapshot.kind === "codex" || snapshot.thread ? "Codex 실행 중" : "쉘 실행 중";
    badge.textContent = snapshot.running ? label : "중지됨";
    badge.className = `output-badge ${snapshot.running ? "connected" : ""}`;
    this.controls();
    this.options.onChange(snapshot);
  }
  syncNativeQuestion(snapshot = this.lastSnapshot) {
    if (snapshot && !this.managed) {
      const lines = this.screenLines();
      const candidate = snapshot.running ? terminalQuestion(lines, snapshot.generation) : null;
      const signature = candidate ? JSON.stringify([candidate.id, candidate.selected]) : "";
      if (signature !== this.nativeSignature) { this.nativeSignature = signature; this.nativeSince = performance.now(); }
      if (!candidate) this.dismissedNative = "";
      this.nativePending = candidate ? performance.now() - this.nativeSince < 600
        : lines.some(line => /^\s*[❯›>→]\s*\d{1,2}[.)]/.test(line));
      // Keep numeric bindings throughout detection and submission. A pending
      // or answered menu must never turn key 5 back into MODEL.
      this.question = candidate;
      snapshot.question = this.question;
      snapshot.nativePending = this.nativePending;
      this.working = Boolean(snapshot.running && !this.question && terminalWorking(lines));
      this.mode = terminalMode(lines) || this.mode;
      snapshot.effort = terminalEffort(lines);
    }
  }
  async start(kind) {
    if (this.pending || this.running) return false;
    const codex = kind === "codex-yolo" || kind === "codex";
    this.pending = true; this.controls();
    this.message("터미널을 시작하고 있습니다…");
    try {
      const result = await this.request("start", {
        kind, effort: this.options.getReasoning?.() || "medium",
        cols: Math.max(20, this.term.cols), rows: Math.max(5, this.term.rows),
      });
      await this.apply(result);
      this.mode = "build";
      this.inputBlocked = false;
      this.options.onStarted(kind);
      if (this.managed) document.querySelector("#terminal-prompt").focus(); else this.term.focus();
      this.message(!this.managed ? (kind === "shell" ? "터미널에 명령을 입력하세요." : "첫 메시지 hi를 자동 전송하도록 시작했습니다. 로그인·신뢰 확인이 나오면 먼저 완료해 주세요. 응답 후 바로 입력할 수 있습니다.") : kind.endsWith("-yolo") ? "YOLO 모드 · 권한 확인을 생략합니다. 아래 입력창에서 첫 요청을 보내세요."
        : codex || kind === "claude" ? `새 ${codex ? "Codex" : "Claude"} 세션입니다. 아래 입력창에서 첫 요청을 보내세요.` : "터미널에 명령을 입력하세요. codex 명령도 실행할 수 있습니다.");
      return true;
    } catch (error) { this.message(error.message); return false; }
    finally { this.pending = false; this.controls(); }
  }
  screenLines() {
    const buffer = this.term.buffer.active, lines = [];
    for (let i = buffer.baseY; i < buffer.baseY + this.term.rows; i++) {
      const row = buffer.getLine(i);
      let text = row?.translateToString(true) || "";
      const prefix = row?.translateToString(true, 0, buffer.cursorX) || "";
      // Placeholder text is drawn in the composer but is not a submitted answer.
      if (i === buffer.baseY + buffer.cursorY && /^\s*[❯›>]\s*$/.test(prefix) && !/^\s*[❯›>]\s*\d{1,2}[.)]/.test(text)) text = prefix;
      lines.push(text);
    }
    while (lines.length && !lines.at(-1).trim()) lines.pop();
    return lines;
  }
  async nativeInput(data, expectedCursor) {
    await this.inputChain;
    if (!this.running || this.inputBlocked) throw new Error("터미널 연결을 확인해 주세요.");
    await this.request("input", { data, generation: this.generation, ...(expectedCursor === undefined ? {} : { expectedCursor }) });
    this.term.focus();
  }
  async nativeCommand(command) {
    const buffer = this.term.buffer.active;
    const line = buffer.getLine(buffer.baseY + buffer.cursorY)?.translateToString(true, 0, buffer.cursorX) || "";
    if (/^\s*[❯›>]\s*\S/.test(line)) throw new Error("터미널에 작성 중인 입력을 먼저 보내거나 지워 주세요.");
    // Paste as a unit so slash-menu autocomplete cannot consume the submit key.
    await this.nativeInput(`\x1b[200~${command}\x1b[201~\r`);
  }
  async nativeAction(item) {
    if (item.generation !== this.generation) throw new Error("AI 세션이 바뀌었습니다.");
    if (item.action === "answer") {
      const question = terminalQuestion(this.screenLines(), this.generation);
      if (!question || question.id !== item.questionId || question.id === this.dismissedNative) throw new Error("터미널의 질문이 바뀌었거나 이미 답변했습니다.");
      const data = item.text !== undefined && !question.interactive
        ? `\x1b[200~${item.text}\x1b[201~\r` : terminalAnswer(question, item.choice);
      // Suppress duplicate clicks even if the CLI has not redrawn yet.
      this.dismissedNative = question.id;
      try { await this.nativeInput(data, this.cursor); }
      catch (error) { this.message(error.message); throw error; }
      return;
    }
    if (item.action === "plan" || item.action === "build") {
      if (item.action === this.mode) return;
      if (item.action === "plan") await this.nativeCommand("/plan");
      else await this.nativeInput("\x1b[Z");
      this.mode = item.action;
      return;
    }
    if (item.action === "model" || item.action === "diff") return this.nativeCommand(`/${item.action}`);
    if (item.action === "check") return this.nativeCommand(CHECK_MESSAGE);
    if (item.action === "accept") return this.nativeInput("\r");
    if (item.action === "denied") return this.nativeCommand(DENIED_MESSAGE);
    if (item.action === "stop") return this.nativeInput("\x1b");
    throw new Error("이 기능은 터미널에 직접 입력해 주세요.");
  }
  async knobInput(action, delta) {
    if (action === "scroll") return this.term.scrollLines(delta * 3);
    if (action === "pages") return this.term.scrollPages(delta);
    if (action === "top") return this.term.scrollToTop();
    if (action === "bottom") return this.term.scrollToBottom();
    if (action === "focus") return this.term.focus();
    if (action === "models") return this.nativeCommand("/model");
    if (action === "diff") {
      if (this.term.buffer.active.type !== "alternate") return this.term.scrollPages(delta);
      return this.nativeInput(delta < 0 ? "\x1b[5~" : "\x1b[6~");
    }
    const data = action === "history" || action === "select" ? (delta < 0 ? "\x1b[A" : "\x1b[B")
      : action === "cursor" ? (delta < 0 ? "\x1b[D" : "\x1b[C")
      : action === "enter" ? "\r" : action === "escape" ? "\x1b" : null;
    if (data) await this.nativeInput(data);
  }
  async setEffort(effort, previous) {
    if (!this.running) return;
    if (this.question || this.nativePending) throw new Error("현재 선택지를 먼저 답변해 주세요.");
    if (this.kind.startsWith("claude")) await this.nativeCommand(`/effort ${effort}`);
    else {
      const delta = TERMINAL_EFFORTS.indexOf(effort) - TERMINAL_EFFORTS.indexOf(previous);
      if (delta) await this.nativeInput((delta > 0 ? "\x1b[1;2A" : "\x1b[1;2B").repeat(Math.abs(delta)));
    }
    this.message(`추론 강도 ${effort.toUpperCase()} 변경 입력을 전달했습니다. CLI 표시를 확인하세요.`);
  }
  async submitPrompt() {
    const input = document.querySelector("#terminal-prompt"), text = input.value.trim();
    if (!text || this.pending || !this.ready || this.busy || this.question) return;
    this.pending = true; this.controls();
    try {
      const response = await fetch("/api/command", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Simulator-Token": this.options.getToken() || "" },
        body: JSON.stringify({ action: "prompt", text, target: "terminal", generation: this.generation, requestId: crypto.randomUUID() }),
        signal: AbortSignal.timeout(25000),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "요청을 전달하지 못했습니다.");
      input.value = ""; this.message("요청을 전달했습니다. 질문이 오면 버튼 번호로 선택하세요.");
      await this.poll();
    } catch (error) { this.message(error.message); }
    finally { this.pending = false; this.controls(); }
  }
  async stop() {
    if (this.pending || !this.running) return;
    this.pending = true; this.controls();
    try {
      await this.request("stop", { generation: this.generation });
      this.message("웹 터미널을 종료했습니다.");
      await this.poll();
    } catch (error) { this.message(error.message); }
    finally { this.pending = false; this.controls(); }
  }
  input(data) {
    if (this.pending || !this.running || this.inputBlocked) return;
    // Focus reports (CSI I/O), cursor reports and arrow navigation are not
    // answers. Clicking a deck key blurs xterm before its click handler runs.
    const controls = data.replace(/\x1b\[200~[\s\S]*?\x1b\[201~/g, "");
    if (this.question?.native && (/[\r\n]/.test(controls) || controls === "\x1b")) this.dismissedNative = this.question.id;
    const generation = this.generation;
    // Keep keystrokes and paste chunks in order. Never retry an uncertain write.
    const chars = Array.from(data);
    for (let i = 0; i < chars.length; i += 2000) {
      const chunk = chars.slice(i, i + 2000).join("");
      this.inputChain = this.inputChain.then(() => {
        if (!this.inputBlocked) return this.request("input", { data: chunk, generation });
      }).catch(error => {
        this.inputBlocked = true;
        this.message(`${error.message} 입력을 중단했습니다. 새로고침 후 터미널 화면을 확인하세요.`);
      });
    }
  }
  async checkButtonReady(snapshot) {
    if (snapshot.managed || snapshot.kind !== "shell") return Boolean(snapshot.ready);
    const thread = snapshot.running ? snapshot.thread : "";
    if (thread !== this.checkingThread) {
      this.checkingThread = thread;
      this.buttonThread = "";
      this.nextButtonCheck = 0;
    }
    if (!thread) return false;
    if (this.buttonThread === thread) return true;
    if (performance.now() < this.nextButtonCheck) return false;
    this.nextButtonCheck = performance.now() + 2000;
    try {
      // Codex takes its session lock before it persists the first request.
      // Check the existing session API once ready, then keep only the readiness flag.
      const response = await fetch("/api/output?target=terminal", {
        headers: { "X-Simulator-Token": this.options.getToken() },
        signal: AbortSignal.timeout(5000),
      });
      if (response.ok && (await response.json()).available) this.buttonThread = thread;
    } catch { /* Keep buttons disabled until the next readiness check. */ }
    return this.buttonThread === thread;
  }
  async poll() {
    if (this.polling) return;
    this.polling = true; clearTimeout(this.timer);
    try {
      if (!this.options.getToken()) return;
      const query = new URLSearchParams({ after: String(this.cursor), generation: this.generation });
      const response = await fetch(`/api/terminal?${query}`, { headers: { "X-Simulator-Token": this.options.getToken() }, signal: AbortSignal.timeout(8000) });
      if (response.status === 403) {
        this.options.onConnection?.(false);
        await this.options.refreshSession();
        return;
      }
      if (!response.ok) throw new Error("터미널 연결을 확인하고 있습니다.");
      const snapshot = await response.json();
      snapshot.buttonReady = await this.checkButtonReady(snapshot);
      await this.apply(snapshot);
      this.options.onConnection?.(true);
      if (this.reconnecting) {
        this.reconnecting = false;
        this.message("서버 연결이 복구됐습니다.");
      }
    } catch {
      this.reconnecting = true;
      this.options.onConnection?.(false);
      this.message("서버 재연결 중 · 연결이 복구되면 출력을 이어받습니다.");
    }
    finally {
      this.polling = false;
      this.timer = setTimeout(() => this.poll(), this.running && !document.hidden ? 180 : 1000);
    }
  }
}
