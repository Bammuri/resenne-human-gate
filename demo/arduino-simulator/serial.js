"use strict";

class SerialLineParser {
  constructor(onLine) { this.onLine = onLine; this.buffer = ""; this.dropping = false; }
  push(text) {
    for (const char of text) {
      if (char === "\n") {
        if (!this.dropping) this.onLine(this.buffer.replace(/\r$/, ""));
        this.buffer = ""; this.dropping = false;
      } else if (!this.dropping) {
        this.buffer += char;
        if (this.buffer.length > 128) { this.buffer = ""; this.dropping = true; }
      }
    }
  }
}

class ButtonSerial {
  constructor(serial, callbacks = {}) {
    this.serial = serial;
    this.callbacks = callbacks;
    this.state = serial ? "disconnected" : "unsupported";
    this.port = null; this.reader = null; this.readTask = null; this.closing = false;
    this.timer = null; this.syncTimer = null; this.commandTimer = null; this.writing = false;
    this.pendingCommand = null;
    this.capabilities = null;
    this.serial?.addEventListener("disconnect", (event) => {
      if (event.target === this.port || event.port === this.port) this.disconnect("USB 연결이 끊어졌습니다. 다시 연결해 주세요.");
    });
  }
  update(state, message) { this.state = state; this.callbacks.onState?.(state, message); }
  async connect() {
    if (!this.serial || !["disconnected", "error"].includes(this.state)) return;
    this.closing = false;
    this.update("connecting", "연결할 Arduino USB 포트를 선택해 주세요.");
    try {
      this.port = await this.serial.requestPort();
      await this.port.open({ baudRate: 115200 });
      if (!this.port.readable || !this.port.writable) throw new Error("시리얼 포트를 열 수 없습니다.");
      this.update("syncing", "보드의 Button Lab 코드를 확인하고 있어요…");
      this.readTask = this.read();
      this.syncTimer = setInterval(() => this.hello(), 700);
      this.timer = setTimeout(() => this.disconnect("보드 응답이 없습니다. 최신 Arduino 코드를 업로드한 뒤 다시 연결해 주세요.", true), 7000);
      await this.hello();
    } catch (error) {
      const cancelled = error.name === "NotFoundError";
      await this.disconnect(cancelled ? "포트 선택을 취소했습니다." : "포트를 열 수 없습니다. USB 케이블과 Arduino IDE의 시리얼 모니터를 확인해 주세요.", !cancelled);
    }
  }
  async hello() {
    if (this.state !== "syncing" || this.writing || !this.port?.writable) return;
    this.writing = true;
    const writer = this.port.writable.getWriter();
    try { await writer.write(new TextEncoder().encode("BUTTON_LAB_HELLO\n")); }
    catch { /* The read loop / handshake timeout reports connection failures. */ }
    finally { writer.releaseLock(); this.writing = false; }
  }
  settleCommand(type, value, error) {
    if (!this.pendingCommand || (!error && (this.pendingCommand.type !== type || this.pendingCommand.value !== value))) return false;
    const pending = this.pendingCommand;
    this.pendingCommand = null;
    clearTimeout(this.commandTimer); this.commandTimer = null;
    if (error) pending.reject(error);
    else pending.resolve();
    return true;
  }
  failCommand(error) {
    // The wire protocol has no request IDs. After an uncertain delivery, a
    // delayed echo could otherwise acknowledge a later press of the same key.
    this.settleCommand("", "", error);
    // disconnect marks the link unusable synchronously, before callers can retry.
    void this.disconnect(`${error.message} USB 보드를 다시 연결해 주세요.`, true);
  }
  async sendCommand(type, value, line) {
    if (this.state !== "connected" || !this.port?.writable) throw new Error("Arduino USB 보드를 먼저 연결해 주세요.");
    if (this.writing || this.pendingCommand) throw new Error("이전 시리얼 명령을 처리하고 있습니다.");
    let resolveAck; let rejectAck;
    const acknowledgement = new Promise((resolve, reject) => { resolveAck = resolve; rejectAck = reject; });
    this.pendingCommand = { type, value, resolve: resolveAck, reject: rejectAck };
    this.commandTimer = setTimeout(() => this.failCommand(new Error("Arduino가 명령에 응답하지 않았습니다.")), 2500);
    this.writing = true;
    const writer = this.port.writable.getWriter();
    try {
      await writer.write(new TextEncoder().encode(`${line}\n`));
    } catch {
      const error = new Error("Arduino로 명령을 전송하지 못했습니다.");
      this.failCommand(error);
    } finally {
      writer.releaseLock(); this.writing = false;
    }
    return acknowledgement;
  }
  async sendChoice(choice) {
    if (choice !== "yes" && choice !== "no") throw new Error("지원하지 않는 버튼 명령입니다.");
    return this.sendCommand("choice", choice, choice);
  }
  async sendKey(slot) {
    if (!Number.isInteger(slot) || slot < 1 || slot > 8) throw new Error("지원하지 않는 버튼 번호입니다. 1~8을 사용해 주세요.");
    return this.sendCommand("key", slot, slot === 8 ? "mode:toggle" : `key:${slot}`);
  }
  async sendAction(action) {
    if (!["codex", "yolo", "plan", "build", "view", "hide", "accept", "denied"].includes(action)) throw new Error("지원하지 않는 기능 명령입니다.");
    return this.sendCommand("action", action, `action:${action}`);
  }
  async sendAudio(command) {
    const mapping = { "audio:toggle": "AT+PLAY=PP", "audio:next": "AT+PLAY=NEXT", "audio:previous": "AT+PLAY=LAST", "audio:status": "AT+QUERY=5" };
    let expected = mapping[command];
    if (/^audio:volume:\d+$/.test(command) && Number(command.split(":")[2]) <= 30) expected = `AT+VOL=${Number(command.split(":")[2])}`;
    if (/^audio:play:\d+$/.test(command) && Number(command.split(":")[2]) >= 1 && Number(command.split(":")[2]) <= 9999) expected = `AT+PLAYNUM=${Number(command.split(":")[2])}`;
    if (!expected) throw new Error("올바른 음원 명령이 필요합니다.");
    return this.sendCommand("audio", expected, command);
  }
  async sendKnob(value) {
    if (!["left", "right", "press"].includes(value)) throw new Error("지원하지 않는 노브 입력입니다.");
    return this.sendCommand("knob", value, `knob:${value}`);
  }
  async sendEffort(effort) {
    if (!["low", "medium", "high", "xhigh"].includes(effort)) throw new Error("지원하지 않는 추론 강도입니다.");
    return this.sendCommand("effort", effort, `effort:${effort}`);
  }
  async sendDisplay(profile, stage, level, status) {
    if (!["workflow", "agent", "custom", "codex"].includes(profile) || !/^[a-z_]{1,14}$/.test(stage) ||
        !Number.isInteger(level) || level < 0 || level > (profile === "workflow" ? 5 : 3) || !["ready", "running", "approved", "stopped", "error", "question"].includes(status)) {
      throw new Error("잘못된 OLED 상태입니다.");
    }
    if (this.state !== "connected" || this.writing || this.pendingCommand || !this.port?.writable) return false;
    this.writing = true;
    const writer = this.port.writable.getWriter();
    try { await writer.write(new TextEncoder().encode(`display:${profile}:${stage}:${level}:${status}\n`)); return true; }
    finally { writer.releaseLock(); this.writing = false; }
  }
  notifyKey(slot, origin) {
    if (this.callbacks.onKey) this.callbacks.onKey(slot, origin);
    else if (slot === 8) this.callbacks.onMode?.(origin);
  }
  async read() {
    const parser = new SerialLineParser((line) => {
      if (this.closing) return;
      if (["BUTTON_LAB_READY:2:slots=7:mode=8", "BUTTON_LAB_READY:3:slots=8:knob=analog"].includes(line) && this.state === "syncing") {
        clearTimeout(this.timer); clearInterval(this.syncTimer);
        this.capabilities = { protocol: line.includes(":3:") ? 3 : 2, functionSlots: 7, modeSlot: 8, ...(line.includes(":3:") ? { analogKnob: true } : {}) };
        this.update("connected", "Arduino USB 보드 연결됨 · 기능키 1~7 / 8번 MODE");
      } else if (line.startsWith("BUTTON_LAB_READY:") && !["BUTTON_LAB_READY:2:slots=7:mode=8", "BUTTON_LAB_READY:3:slots=8:knob=analog"].includes(line)) {
        this.disconnect("버튼 배치가 다른 구형 또는 지원하지 않는 펌웨어입니다. firmware/yes_no/yes_no.ino를 업로드하고 D2~D8 기능키 / D9 MODE 배선으로 다시 연결해 주세요.", true);
      } else if (this.state === "connected" && /^BUTTON_LAB_KEY:[1-8]$/.test(line)) {
        const slot = Number(line.slice(-1));
        if (slot < 8 || this.capabilities?.protocol === 3) this.notifyKey(slot, "hardware");
      } else if (this.state === "connected" && line === "BUTTON_LAB_MODE:toggle") {
        this.notifyKey(8, "hardware");
      } else if (this.state === "connected" && /^BUTTON_LAB_SIMULATED_KEY:[1-7]$/.test(line)) {
        const slot = Number(line.slice(-1));
        if (this.settleCommand("key", slot)) this.notifyKey(slot, "simulator");
      } else if (this.state === "connected" && line === "BUTTON_LAB_SIMULATED_MODE:toggle") {
        if (this.settleCommand("key", 8)) this.notifyKey(8, "simulator");
      } else if (this.state === "connected" && line === "BUTTON_LAB_REVERT:preview") {
        this.callbacks.onRevert?.();
      } else if (this.state === "connected" && (line === "BUTTON_LAB_SIMULATED:yes" || line === "BUTTON_LAB_SIMULATED:no")) {
        const choice = line.slice("BUTTON_LAB_SIMULATED:".length);
        this.settleCommand("choice", choice);
        this.callbacks.onChoice?.(choice, "simulator");
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_SIMULATED_ACTION:")) {
        const action = line.slice("BUTTON_LAB_SIMULATED_ACTION:".length);
        if (["codex", "yolo", "plan", "build", "view", "hide", "accept", "denied"].includes(action)) {
          this.settleCommand("action", action);
          this.callbacks.onAction?.(action, "simulator");
        }
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_ACTION:")) {
        const action = line.slice("BUTTON_LAB_ACTION:".length);
        if (["codex", "yolo", "plan", "build", "view", "hide", "accept", "denied"].includes(action)) this.callbacks.onAction?.(action, "hardware");
      } else if (this.state === "connected" && /^BUTTON_LAB_POT:\d{1,4}$/.test(line)) {
        const value = Number(line.split(":")[1]);
        if (value <= 1023) this.callbacks.onPot?.(value, "hardware");
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_AUDIO_SENT:")) {
        this.settleCommand("audio", line.slice("BUTTON_LAB_AUDIO_SENT:".length));
        this.callbacks.onLog?.(line);
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_SIMULATED_KNOB:")) {
        const value = line.slice("BUTTON_LAB_SIMULATED_KNOB:".length);
        if (["left", "right", "press"].includes(value) && this.settleCommand("knob", value)) this.callbacks.onKnob?.(value, "simulator");
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_KNOB:")) {
        const value = line.slice("BUTTON_LAB_KNOB:".length);
        if (["left", "right", "press"].includes(value)) this.callbacks.onKnob?.(value, "hardware");
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_SIMULATED_EFFORT:")) {
        const effort = line.slice("BUTTON_LAB_SIMULATED_EFFORT:".length);
        if (["low", "medium", "high", "xhigh"].includes(effort)) {
          this.settleCommand("effort", effort);
          this.callbacks.onEffort?.(effort, "simulator");
        }
      } else if (this.state === "connected" && line.startsWith("BUTTON_LAB_EFFORT:")) {
        const effort = line.slice("BUTTON_LAB_EFFORT:".length);
        if (["low", "medium", "high", "xhigh"].includes(effort)) this.callbacks.onEffort?.(effort, "hardware");
      } else if (this.state === "connected" && (line === "BUTTON_LAB_INPUT:yes" || line === "BUTTON_LAB_INPUT:no")) {
        this.callbacks.onChoice?.(line.slice("BUTTON_LAB_INPUT:".length), "hardware");
      } else if (this.state === "connected" && (line === "yes" || line === "no")) {
        this.callbacks.onChoice?.(line, "hardware");
      } else if (line) this.callbacks.onLog?.(line.slice(0, 128));
    });
    const decoder = new TextDecoder();
    this.reader = this.port.readable.getReader();
    try {
      while (!this.closing) {
        const { value, done } = await this.reader.read();
        if (done) break;
        parser.push(decoder.decode(value, { stream: true }));
      }
    } catch { /* Close below, including physical unplug. */ }
    finally { this.reader.releaseLock(); this.reader = null; }
    if (!this.closing) {
      // Schedule cleanup after this read task has settled.
      setTimeout(() => this.disconnect("USB 읽기가 종료됐습니다. 보드를 다시 연결해 주세요.", true), 0);
    }
  }
  async disconnect(message = "USB 연결을 해제했습니다.", failed = false) {
    if (this.closing) return;
    this.closing = true;
    clearTimeout(this.timer); clearInterval(this.syncTimer);
    this.settleCommand("", "", new Error("USB 연결이 해제되어 명령을 완료하지 못했습니다."));
    this.update("disconnecting", "USB 연결을 해제하고 있어요…");
    try {
      if (this.reader) await this.reader.cancel();
      if (this.readTask) await this.readTask;
      // A pending HELLO write is short; wait for its writer lock to be released.
      for (let i = 0; this.writing && i < 50; i++) await new Promise(resolve => setTimeout(resolve, 20));
      if (this.port) await this.port.close();
    } catch { /* A removed USB device may already be closed. */ }
    this.port = null; this.readTask = null;
    this.capabilities = null;
    this.update(failed ? "error" : "disconnected", message);
    this.closing = false;
  }
}



// Uses the local simulator proxy so no browser-to-device CORS exception is needed.
class ButtonWifi extends ButtonSerial {
  constructor(request, callbacks) {
    super(null, callbacks); this.request = request; this.state = "disconnected"; this.isWifi = true;
    this.epoch = 0; this.pollTimer = null;
  }
  async connect(host, token = "") {
    if (!["disconnected", "error"].includes(this.state)) return;
    const epoch = ++this.epoch; this.update("connecting", "Wi-Fi 보드 연결 중…");
    try {
      const status = await this.request("/api/board/connect", { host, token });
      if (epoch !== this.epoch) return;
      this.capabilities = { protocol: 3, functionSlots: 7, modeSlot: 8, analogKnob: true };
      this.update("connected", `Wi-Fi 보드 연결됨 · ${status.ip}`);
      this.callbacks.onPot?.(status.pot, "hardware");
      this.poll(epoch);
    } catch (error) { if(epoch===this.epoch)this.update("error", error.message); }
  }
  async poll(epoch) {
    if (epoch !== this.epoch || this.state !== "connected") return;
    try {
      const result = await this.request("/api/board/events");
      if (epoch !== this.epoch || this.state !== "connected") return;
      for (const event of result.events) {
        if (this.state !== "connected") break;
        const line = event.line;
        if (/^BUTTON_LAB_KEY:[1-8]$/.test(line)) this.notifyKey(Number(line.split(":")[1]), "hardware");
        else if (/^BUTTON_LAB_POT:\d{1,4}$/.test(line) && Number(line.split(":")[1]) <= 1023) this.callbacks.onPot?.(Number(line.split(":")[1]), "hardware");
        else if (/^BUTTON_LAB_SIMULATED_KEY:[1-8]$/.test(line)) { const n = Number(line.split(":")[1]); if (this.settleCommand("key", n)) this.notifyKey(n, "simulator"); }
        else if (line === "BUTTON_LAB_SIMULATED_MODE:toggle") { if (this.settleCommand("key", 8)) this.notifyKey(8, "simulator"); }
        else if (/^BUTTON_LAB_SIMULATED_KNOB:(left|right|press)$/.test(line)) { const value=line.split(":")[1]; if(this.settleCommand("knob",value))this.callbacks.onKnob?.(value,"simulator"); }
        else if (line.startsWith("BUTTON_LAB_AUDIO_SENT:")) { this.settleCommand("audio",line.slice("BUTTON_LAB_AUDIO_SENT:".length));this.callbacks.onLog?.(line); }
        else this.callbacks.onLog?.(line);
      }
    } catch (error) { if(epoch===this.epoch)await this.disconnect(error.message, true); return; }
    if (epoch === this.epoch && this.state === "connected") this.pollTimer = setTimeout(() => this.poll(epoch), 100);
  }
  async sendCommand(type, value, line) {
    if (this.state !== "connected" || this.pendingCommand) throw new Error("Wi-Fi 연결 또는 이전 명령을 확인해 주세요.");
    let resolve, reject; const ack = new Promise((yes,no) => { resolve=yes;reject=no; });
    this.pendingCommand = { type, value, resolve, reject };
    ack.catch(() => {}); // The acknowledgement can fail before the HTTP request returns.
    this.commandTimer = setTimeout(() => this.failCommand(new Error("보드 응답이 지연됐습니다. 다시 연결해 주세요.")), 4000);
    try { await this.request("/api/board/command", { command: line }); }
    catch (error) { this.failCommand(error); }
    return ack;
  }
  async sendDisplay(profile, stage, level, status) {
    if(this.state!=="connected" || this.pendingCommand || this.writing)return false;
    this.writing=true;
    try { await this.request("/api/board/command", { command:`display:${profile}:${stage}:${level}:${status}` });return true; }
    finally { this.writing=false; }
  }
  async disconnect(message="Wi-Fi 연결 해제", failed=false) {
    ++this.epoch;clearTimeout(this.pollTimer);
    this.settleCommand("","",new Error(message));
    this.update(failed?"error":"disconnected",message);
    try { await this.request("/api/board/disconnect", {}); } catch { /* Local state is already disconnected. */ }
  }
}
if (typeof module !== "undefined") module.exports = { SerialLineParser, ButtonSerial, ButtonWifi };
