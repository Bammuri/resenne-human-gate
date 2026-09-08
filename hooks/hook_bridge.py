#!/usr/bin/env python3
"""Claude Code PreToolUse hook that bridges gated tool calls to the Re:senne approval broker.

Configured for a Claude session started with `claude --settings <json>` where the command is
`python3 hooks/hook_bridge.py`. The broker URL and a *hook* token (register/wait only — it
cannot resolve) are passed in the environment so nothing sensitive lands in the settings file.

Contract (stdout, PreToolUse, exit 0):
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "allow"|"deny"|"ask",
                            "permissionDecisionReason": "..."}}

Fail-safe policy: any network/parse/error path emits "ask" so Claude falls back to its own
permission menu (never an automatic approval). Only an explicit deny from a button denies.
stdout carries JSON ONLY; every diagnostic goes to stderr.

Status: code-integrated + unit-tested (see tests/test_approval.py). E2E re-verification on the
submission build (physical button -> broker -> real tool gate) is a human step; the PTY key
path (/api/press) remains the sole E2E-verified submission path.
"""

import json
import os
import sys
import urllib.request
import urllib.error

# A little longer than nothing but shorter than the Claude-side hook timeout (90s) and the
# server-side wait (80s); this is only the socket ceiling for the long-poll request.
WAIT_TIMEOUT = 88


def log(message):
    print(f"[hook_bridge] {message}", file=sys.stderr, flush=True)


def post(url, token, body, timeout):
    data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "X-Simulator-Token": token,
        "Host": url.split("//", 1)[-1].split("/", 1)[0],
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def pre_tool_use(base_url, token, bridge_id, payload):
    body = {
        "bridge_id": bridge_id,
        "session_id": payload.get("session_id", ""),
        "tool_use_id": payload.get("tool_use_id", ""),
        "tool_name": payload.get("tool_name", ""),
        "tool_input": payload.get("tool_input"),
    }
    try:
        result = post(f"{base_url}/api/approval/wait", token, body, WAIT_TIMEOUT)
        decision = result.get("decision", "ask")
        if decision not in ("allow", "deny", "ask"):
            decision = "ask"
    except urllib.error.HTTPError as error:
        # An auth or routing failure is a real misconfiguration; fail closed for those.
        decision = "deny" if error.code in (400, 403) else "ask"
        log(f"HTTP {error.code} from broker; decision={decision}")
    except Exception as error:  # noqa: BLE001 - any failure must still emit valid JSON
        decision = "ask"
        log(f"broker unreachable ({error}); decision=ask")
    reason = {
        "allow": "Re:senne: 사용자가 버튼으로 허용했습니다.",
        "deny": "Re:senne: 사용자가 버튼으로 거부했습니다.",
        "ask": "Re:senne: 브리지 응답이 없어 Claude 기본 권한 메뉴로 넘깁니다.",
    }[decision]
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}


def lifecycle(base_url, token, bridge_id, payload, event):
    endpoint = "register" if event == "SessionStart" else "end"
    try:
        post(f"{base_url}/api/session/{endpoint}", token,
             {"bridge_id": bridge_id, "session_id": payload.get("session_id", "")}, 10)
    except Exception as error:  # noqa: BLE001
        log(f"session/{endpoint} failed ({error})")
    return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    base_url = os.environ.get("BUTTONLAB_URL", "").rstrip("/")
    token = os.environ.get("BUTTONLAB_HOOK_TOKEN", "")
    bridge_id = os.environ.get("BUTTONLAB_BRIDGE_ID", "")
    event = payload.get("hook_event_name", "PreToolUse")

    output = None
    if not base_url or not token:
        log("BUTTONLAB_URL/BUTTONLAB_HOOK_TOKEN missing; falling back to ask")
        if event == "PreToolUse":
            output = {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "Re:senne 브리지 미설정",
            }}
    elif event == "PreToolUse":
        output = pre_tool_use(base_url, token, bridge_id, payload)
    elif event in ("SessionStart", "SessionEnd"):
        output = lifecycle(base_url, token, bridge_id, payload, event)

    if output is not None:
        sys.stdout.write(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
