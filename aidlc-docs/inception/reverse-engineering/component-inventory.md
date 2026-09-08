# Component Inventory

> This is a single-package application (no monorepo). "Packages" below are logical components within the one project.

## Application Packages
- **Backend HTTP server** (`server.py`) — routing, security guards, answer-delivery decision, idempotency/rate limiting.
- **Web terminal / PTY broker** (`terminal.py`, `pty_child.py`) — owns the PTY, session discovery, answer injection.
- **Session output reader** (`output.py`) — session state + visible-event parsing (Codex-format).
- **Frontend SPA** (`index.html`, `app.js`, `web-terminal.js`, `serial.js`, `style.css`, `favicon.svg`) — control surface, xterm.js terminal, Web Serial bridge.

## Infrastructure Packages
- None (no CDK/Terraform/CloudFormation; runs as a local process).

## Shared Packages
- **Vendored frontend libraries** (`vendor/xterm.js`, `vendor/addon-fit.js`, `vendor/xterm.css`, LICENSE files, `vendor/README.md`) — third-party UI utilities bundled to avoid a build/CDN.

## Firmware Packages
- **Arduino sketch** (`firmware/yes_no/yes_no.ino`) — debounced two-button input + serial handshake.

## Test Packages
- **Python unit tests** (`tests/test_server.py`, `tests/test_output.py`, `tests/test_terminal.py`) — server routing/guards, output parsing, terminal behavior (Codex send is mocked).
- **JS unit tests** (`tests/serial.test.js`) — `SerialLineParser`/`ButtonSerial` over a fake Web Serial stream (`node --test`).

## Total Count
- **Total logical components**: 10 (4 application + 0 infrastructure + 1 shared/vendored + 1 firmware + 2 test suites… counted as component groups).
- **Application**: 4
- **Infrastructure**: 0
- **Shared/Vendored**: 1 group (xterm.js + addon-fit + css)
- **Firmware**: 1
- **Test**: 4 files (3 Python + 1 JS)
- **Source file totals**: 18 first-party source/asset files + 4 test files; ~2,300 lines first-party code (excluding vendored libraries).
