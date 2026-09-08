"use strict";

// Pure mapping: one BindDeck device line -> one logical action, or null (ignored).
// Total over the device-line domain; unknown/malformed lines never produce an action.
// (Property-tested: PBT-02/03/07 — see tests/mapping.pbt.test.js.)
const BUTTON_ACTIONS = { "0": "yes", "1": "no", "2": "stop", "8": "confirm" };
const ENCODER_ACTIONS = { CW: "nav_down", VDN: "nav_down", CCW: "nav_up", VUP: "nav_up" };
function parseDeviceLine(line) {
  if (typeof line !== "string") return null;
  const button = /^BTN:([0-8])$/.exec(line);
  if (button) return BUTTON_ACTIONS[button[1]] || null;
  const encoder = /^ENC:([A-Z]+)$/.exec(line);
  if (encoder) return ENCODER_ACTIONS[encoder[1]] || null;
  return null;
}

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
    this.timer = null; this.syncTimer = null; this.writing = false;
    this.serial?.addEventListener("disconnect", (event) => {
      if (event.target === this.port || event.port === this.port) this.disconnect("USB 연결이 끊어졌습니다. 다시 연결해 주세요.");
    });
  }
  update(state, message) { this.state = state; this.callbacks.onState?.(state, message); }
  async connect() {
    if (!this.serial || !["disconnected", "error"].includes(this.state)) return;
    this.closing = false;
    this.update("connecting", "연결할 BindDeck 포트를 선택해 주세요.");
    try {
      this.port = await this.serial.requestPort();
      await this.port.open({ baudRate: 115200 });
      if (!this.port.readable || !this.port.writable) throw new Error("시리얼 포트를 열 수 없습니다.");
      this.update("syncing", "BindDeck 펌웨어를 확인하고 있어요…");
      this.readTask = this.read();
      this.syncTimer = setInterval(() => this.hello(), 700);
      this.timer = setTimeout(() => this.disconnect("보드 응답이 없습니다. binddeck_claude 펌웨어를 업로드한 뒤 다시 연결해 주세요.", true), 7000);
      await this.hello();
    } catch (error) {
      const cancelled = error.name === "NotFoundError";
      await this.disconnect(cancelled ? "포트 선택을 취소했습니다." : "포트를 열 수 없습니다. USB 케이블과 다른 시리얼 모니터 연결을 확인해 주세요.", !cancelled);
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
  // OLED feedback (FR-5): best-effort push of Claude state to the device.
  async sendMessage(text) {
    if (this.state !== "connected" || this.writing || !this.port?.writable) return;
    this.writing = true;
    const writer = this.port.writable.getWriter();
    try { await writer.write(new TextEncoder().encode(`CMD:MSG:${String(text).slice(0, 120)}\n`)); }
    catch { /* Best-effort OLED update; the read loop reports real failures. */ }
    finally { writer.releaseLock(); this.writing = false; }
  }
  async read() {
    const parser = new SerialLineParser((line) => {
      if (this.closing) return;
      if (line === "BUTTON_LAB_READY:1") {
        clearTimeout(this.timer); clearInterval(this.syncTimer);
        this.update("connected", "BindDeck 연결됨 · 버튼과 엔코더를 사용해 보세요.");
      } else if (this.state === "connected") {
        const action = parseDeviceLine(line);
        if (action) this.callbacks.onChoice?.(action);
        else if (line) this.callbacks.onLog?.(line.slice(0, 128));
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
    this.update("disconnecting", "USB 연결을 해제하고 있어요…");
    try {
      if (this.reader) await this.reader.cancel();
      if (this.readTask) await this.readTask;
      // A pending write is short; wait for its writer lock to be released.
      for (let i = 0; this.writing && i < 50; i++) await new Promise(resolve => setTimeout(resolve, 20));
      if (this.port) await this.port.close();
    } catch { /* A removed USB device may already be closed. */ }
    this.port = null; this.readTask = null;
    this.update(failed ? "error" : "disconnected", message);
    this.closing = false;
  }
}

if (typeof module !== "undefined") module.exports = { SerialLineParser, ButtonSerial, parseDeviceLine };
