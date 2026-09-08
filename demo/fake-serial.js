"use strict";
// Browser-injectable fake `navigator.serial` for hardware-free development/demos.
//
// Loaded ONLY when the page URL opts in with ?fakeserial=1 (see the bootstrap in
// index.html), so production assets and behavior stay unchanged. It implements the
// minimal Web Serial surface that serial.js::ButtonSerial uses — requestPort(),
// port.open()/close(), a readable + writable stream, and a "disconnect" event — so
// the REAL handshake and BTN:/ENC: line parsing and onChoice->press path all run
// with no device attached (works in any browser, incl. headless Chromium).
//
// Emit device lines through window.fakeBindDeck (used by the on-screen controls in
// fake-hardware mode and by automated tests). Nothing here auto-answers Claude.
(function () {
  if (!new URLSearchParams(location.search).has("fakeserial")) return;

  const encoder = new TextEncoder();

  // Logical action -> the exact device->PC line a real BindDeck would send.
  // Mirrors BUTTON_ACTIONS / ENCODER_ACTIONS in serial.js (kept in sync by hand).
  const ACTION_LINES = {
    yes: "BTN:0", no: "BTN:1", stop: "BTN:2", confirm: "BTN:8",
    nav_up: "ENC:CCW", nav_down: "ENC:CW",
  };

  class FakeSerialPort {
    constructor() {
      this.readable = null; this.writable = null;
      this._controller = null; this._open = false; this._ready = false; this._rx = "";
    }

    async open(options) {
      // The real API requires a baudRate; serial.js passes { baudRate: 115200 }.
      if (this._open) throw new DOMException("port is already open", "InvalidStateError");
      if (!options || typeof options.baudRate !== "number") throw new TypeError("open requires a baudRate");
      this._open = true; this._ready = false; this._rx = "";
      this.readable = new ReadableStream({
        start: (controller) => { this._controller = controller; },
        cancel: () => { this._controller = null; },   // reader.cancel() unblocks close()
      });
      this.writable = new WritableStream({ write: (chunk) => this._onWrite(chunk) });
    }

    // Parse the PC->device byte stream into lines exactly as firmware would, and
    // answer the handshake. CMD:MSG:<text> (OLED) lines are accepted and ignored.
    _onWrite(chunk) {
      this._rx += new TextDecoder().decode(chunk);
      let index;
      while ((index = this._rx.indexOf("\n")) >= 0) {
        const line = this._rx.slice(0, index).replace(/\r$/, "");
        this._rx = this._rx.slice(index + 1);
        if (line === "BUTTON_LAB_HELLO" && !this._ready) {
          this._ready = true;
          this.emitLine("BUTTON_LAB_READY:1");   // the board's hello/boot reply
        }
      }
    }

    // Push one device->PC line into the read stream (newline-framed, like real serial).
    emitLine(text) {
      if (this._open && this._controller) {
        try { this._controller.enqueue(encoder.encode(text + "\n")); }
        catch { /* stream is closing/cancelled */ }
      }
    }

    async close() {
      this._open = false; this._ready = false; this._rx = "";
      try { this._controller?.close(); } catch { /* already closed or cancelled */ }
      this._controller = null;
    }
  }

  class FakeSerial extends EventTarget {
    constructor() { super(); this._port = new FakeSerialPort(); }
    async requestPort() { return this._port; }   // always the same single fake port
    async getPorts() { return [this._port]; }
    get port() { return this._port; }
  }

  const fakeSerial = new FakeSerial();
  window.fakeBindDeckSerial = fakeSerial;   // app.js prefers this over navigator.serial

  // Deterministic emit API: primary interface for automated (Playwright) tests, and
  // used by app.js to route the on-screen controls through the fake port for a demo.
  window.fakeBindDeck = {
    // Emit the device line for a logical action (yes/no/stop/confirm/nav_up/nav_down).
    press(action) {
      const line = ACTION_LINES[action];
      if (line) fakeSerial.port.emitLine(line);
      return line || null;
    },
    // Inject an arbitrary raw line (e.g. to exercise unknown-line handling).
    line(raw) { fakeSerial.port.emitLine(String(raw)); },
    // Simulate a USB unplug so the reconnection path can be exercised.
    unplug() {
      const event = new Event("disconnect");
      event.port = fakeSerial.port;
      fakeSerial.dispatchEvent(event);
    },
    actions: ACTION_LINES,
  };

  // Small, unobtrusive badge so it is obvious the serial is simulated.
  addEventListener("DOMContentLoaded", () => {
    const badge = document.createElement("div");
    badge.textContent = "🧪 가짜 시리얼";
    badge.title = "?fakeserial=1 · Web Serial 장치 없이 실물 BindDeck 경로를 시뮬레이션합니다";
    badge.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:9999;background:#1c2b2c;color:#8fe3c0;" +
      "font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;padding:7px 10px;border-radius:8px;" +
      "box-shadow:0 6px 18px rgba(0,0,0,.25);opacity:.9;pointer-events:none";
    document.body.append(badge);
  });
})();
