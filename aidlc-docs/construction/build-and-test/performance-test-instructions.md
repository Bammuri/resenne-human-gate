# Performance / Resiliency Test Instructions — `claude-binddeck-retarget`

This is a single-user localhost tool, so there is **no load/throughput target**.
Performance concerns are latency-perception and resiliency (RESILIENCY-05/06/10,
the enabled subset). Verify the following by observation.

## Latency / responsiveness

- **Button → keystroke**: a press should reach the Claude PTY within perceptible
  real-time. The host throttles to one send per 0.5s (429 otherwise) and debounces
  0.25s client-side; this is intentional, not a bottleneck.
- **State polling**: the browser polls `/api/state` every ~1.2s (3s when the tab is
  hidden) and `/api/terminal` every ~180ms while running. Confirm CPU stays low and
  the terminal stream is smooth.

## Resiliency (enabled subset)

| Rule | What to verify | How |
|---|---|---|
| RESILIENCY-06 (liveness) | Buttons disable when no Claude PTY is live | Stop the session → `claude_ready()` false → 503 on press, UI disables |
| RESILIENCY-10 (timeouts / graceful degradation) | Bounded waits; no hang on disconnect | Unplug USB mid-session → bridge → `error`, reconnectable; server reconnect banner on network blip; PTY write has a 2s deadline |
| RESILIENCY-10 (state fallback) | State degrades, never crashes | Delete/expire the hook state file → `/api/state` falls back to transcript mtime, then `offline`; reader never raises |
| RESILIENCY-05 (structured logging) | Sends are logged | `send_choice` prints `action`/`keys`/`kind`; server logs non-200s (200 polls suppressed) |

## Bounded-memory checks

- PTY scrollback is capped at 512 KiB (`terminal.py`).
- The idempotency reply cache is bounded to 1000 entries (`server.py`).

No automated performance suite is included; these are manual/observational checks
appropriate to a single-user local bridge.
