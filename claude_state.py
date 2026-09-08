"""Read Claude Code session state: hook-written state file first, transcript fallback.

Primary source: a small JSON state file written atomically by the Claude hooks
(hooks/claude_state_hook.py) on lifecycle events (UserPromptSubmit/PostToolUse ->
active, Notification permission_prompt -> waiting, Stop/SubagentStop -> idle).

Fallback (RESILIENCY-10, graceful degradation): when the hook file is missing or
stale, infer coarse state from the freshness of the newest transcript under
~/.claude/projects/**/*.jsonl. The transcript schema is internal to Claude Code
and unstable, so we only use its modification time — never parse its records.
Any error yields the safe initial state "offline"; this reader never raises.
"""

import json
import os
from pathlib import Path
import threading
import time

VALID_STATUS = ("offline", "idle", "active", "waiting")
FRESH_SECONDS = 30  # a hook state / transcript newer than this counts as "live"


class ClaudeStateReader:
    def __init__(self, state_file, projects_root=None, *, terminal=None, now=time.time, fresh_seconds=FRESH_SECONDS):
        self.state_file = Path(state_file) if state_file else None
        self.projects_root = Path(projects_root or (Path.home() / ".claude" / "projects"))
        self.terminal = terminal
        self.now = now
        self.fresh_seconds = fresh_seconds
        self.lock = threading.Lock()
        self.last_answer = None

    def note_answer(self, action):
        with self.lock:
            self.last_answer = action

    def _read_hook_state(self):
        """(status, fresh) from the hook state file, or (None, False)."""
        if not self.state_file:
            return None, False
        try:
            stat = self.state_file.stat()
            fresh = (self.now() - stat.st_mtime) <= self.fresh_seconds
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            status = data.get("status") if isinstance(data, dict) else None
            if status in VALID_STATUS:
                return status, fresh
        except (OSError, ValueError, TypeError):
            pass
        return None, False

    def _transcript_fresh(self):
        """(exists, fresh) for the newest transcript under the projects root."""
        try:
            newest = max(
                (p.stat().st_mtime for p in self.projects_root.glob("**/*.jsonl")),
                default=None,
            )
        except OSError:
            return False, False
        if newest is None:
            return False, False
        return True, (self.now() - newest) <= self.fresh_seconds

    def snapshot(self, after=0, generation=""):
        with self.lock:
            last_answer = self.last_answer
        pty_live = bool(self.terminal and self.terminal.claude_ready())
        status, hook_fresh = self._read_hook_state()
        source = "none"
        if status is not None and hook_fresh:
            source = "hook"
        else:
            exists, fresh = self._transcript_fresh()
            if exists:
                status = "active" if fresh else "idle"
                source = "transcript"
            elif pty_live:
                status = "active"
            else:
                status = "offline"
        available = pty_live or hook_fresh or source == "transcript"
        return {
            "status": status if status in VALID_STATUS else "offline",
            "available": available,
            "lastAnswer": last_answer,
            "source": source,
        }
