#!/usr/bin/env python3
"""Claude Code hook: record the session lifecycle state for the BindDeck bridge.

Registered in .claude/settings.json for UserPromptSubmit / PreToolUse / PostToolUse
/ Notification / Stop / SubagentStop. On each event it maps the event to a coarse
status and writes it atomically to the state file that server.py's
ClaudeStateReader tails (Application Design §4.1/§4.7).

Design constraints:
- This hook is a pure state SIGNAL. It NEVER decides permissions and NEVER writes
  to stdout, so the human-in-the-loop PTY answer path is preserved.
- It always exits 0 and swallows its own errors, so a hook failure can never block
  or alter the Claude session.

State file location: $BINDDECK_STATE_FILE, else <cwd>/.claude/binddeck-state.json
(<cwd> comes from the hook payload and matches server.py's --cwd workspace).
"""

import json
import os
from pathlib import Path
import sys
import time


def status_for(event, payload):
    if event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
        return "active"
    if event in ("Stop", "SubagentStop"):
        return "idle"
    if event == "Notification":
        notification = str(payload.get("notification_type") or payload.get("message") or "")
        return "waiting" if "permission" in notification.lower() else "idle"
    return None


def state_file(payload):
    override = os.environ.get("BINDDECK_STATE_FILE")
    if override:
        return Path(override)
    cwd = payload.get("cwd") or os.getcwd()
    return Path(cwd) / ".claude" / "binddeck-state.json"


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            payload = {}
    except (ValueError, OSError):
        payload = {}
    event = payload.get("hook_event_name", "")
    status = status_for(event, payload)
    if status is None:
        return
    try:
        path = state_file(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "status": status,
            "ts": time.time(),
            "event": event,
            "sessionId": payload.get("session_id", ""),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(record), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
