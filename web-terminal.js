"use strict";

class BrowserTerminal {
  constructor(options) {
    this.options = options;
    this.generation = ""; this.cursor = 0; this.running = false; this.kind = "";
    this.pending = false; this.polling = false; this.timer = null;
    this.inputChain = Promise.resolve();
    this.inputBlocked = false;
    this.reconnecting = false;
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
    document.querySelector("#terminal-shell").addEventListener("click", () => this.start("shell"));
    document.querySelector("#terminal-claude").addEventListener("click", () => this.start("claude"));
    document.querySelector("#terminal-stop").addEventListener("click", () => this.stop());
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
    document.querySelector("#terminal-shell").disabled = !ready || this.pending || this.running;
    document.querySelector("#terminal-claude").disabled = !ready || this.pending || this.running || !this.options.hasClaude();
    document.querySelector("#terminal-stop").disabled = this.pending || !this.running;
  }
  apply(snapshot) {
    this.running = snapshot.running;
    this.generation = snapshot.generation;
    this.cursor = snapshot.cursor;
    this.kind = snapshot.kind;
    if (snapshot.reset) this.term.reset();
    if (snapshot.data) this.term.write(Uint8Array.from(atob(snapshot.data), char => char.charCodeAt(0)));
    const badge = document.querySelector("#terminal-state");
    badge.textContent = snapshot.running ? (snapshot.kind === "claude" ? "Claude 실행 중" : "쉘 실행 중") : "중지됨";
    badge.className = `output-badge ${snapshot.running ? "connected" : ""}`;
    document.querySelector("#terminal-link").textContent = snapshot.running && snapshot.kind === "claude"
      ? "Claude 세션 연결됨 · 버튼으로 응답하세요"
      : snapshot.running ? "쉘 실행 중 · Claude를 시작하면 버튼이 연결됩니다"
      : "Claude를 시작하면 버튼 응답이 연결됩니다";
    this.controls();
    this.options.onChange(snapshot);
  }
  async start(kind) {
    if (this.pending || this.running) return;
    this.pending = true; this.controls();
    this.message("터미널을 시작하고 있습니다…");
    try {
      const result = await this.request("start", { kind, cols: Math.max(20, this.term.cols), rows: Math.max(5, this.term.rows) });
      this.apply(result);
      this.inputBlocked = false;
      this.term.focus();
      this.message(kind === "claude"
        ? "Claude 세션이 시작됐습니다. 요청을 입력하고, 승인 프롬프트는 버튼으로 답하세요."
        : "터미널에 명령을 입력하세요. claude 명령도 직접 실행할 수 있습니다.");
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
      this.apply(snapshot);
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
