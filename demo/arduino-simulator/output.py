"""Incrementally read the visible items of one local Codex session."""

from collections import deque
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import sqlite3
import threading
import time
import uuid


MAX_RECORD = 4 * 1024 * 1024
MAX_TEXT = 20000
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")


def visible_text(value):
    if not isinstance(value, str):
        return ""
    value = ANSI.sub("", value)
    value = "".join(char for char in value if char in "\n\t" or ord(char) >= 32)
    if len(value) > MAX_TEXT:
        value = value[:MAX_TEXT] + "\n… 긴 출력의 나머지는 터미널에서 확인해 주세요."
    return value


def content_text(content):
    if not isinstance(content, list):
        return ""
    return visible_text("\n".join(
        part["text"] for part in content
        if isinstance(part, dict) and part.get("type") in ("Text", "text", "input_text", "output_text")
        and isinstance(part.get("text"), str)
    ))


class OutputReader:
    def __init__(self, thread, codex_home=None):
        self.thread = thread
        self.home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex").resolve()
        self.lock = threading.Lock()
        self.path = None
        self.session_id = thread
        self.next_lookup = 0
        self.identity = None
        self.reset()

    def reset(self):
        self.generation = secrets.token_hex(8)
        self.offset = 0
        self.skipping = False
        self.events = deque(maxlen=120)
        self.seen = set()
        self.seen_order = deque()
        self.cursor = 0
        self.status = "waiting" if self.thread else "offline"

    def locate(self):
        if not self.thread or time.monotonic() < self.next_lookup:
            return None
        self.next_lookup = time.monotonic() + 3
        database = self.home / "state_5.sqlite"
        if database.is_file():
            try:
                connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.2)
                try:
                    rows = connection.execute(
                        "SELECT id, rollout_path FROM threads WHERE id = ? OR name = ? LIMIT 2",
                        (self.thread, self.thread),
                    ).fetchall()
                finally:
                    connection.close()
                if len(rows) == 1:
                    path = Path(rows[0][1]).resolve()
                    if path.is_relative_to(self.home) and path.is_file():
                        self.session_id = rows[0][0]
                        return path
            except (sqlite3.Error, OSError, TypeError):
                pass
        # Fallback for local installations without the metadata database.
        try:
            session_id = str(uuid.UUID(self.thread))
        except ValueError:
            return None
        matches = list((self.home / "sessions").glob(f"**/*-{session_id}.jsonl"))
        self.session_id = session_id
        return matches[0] if len(matches) == 1 else None

    def ingest(self, record):
        if not isinstance(record, dict) or record.get("type") != "event_msg":
            return
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return
        if payload.get("thread_id") not in (None, self.session_id):
            return
        event_type = payload.get("type")
        if event_type == "task_started":
            self.status = "active"
            return
        if event_type in ("task_complete", "turn_aborted"):
            self.status = "idle"
            return
        if event_type != "item_completed":
            return
        item = payload.get("item")
        if not isinstance(item, dict):
            return
        # Allow only user-visible messages and shell results. Never serialize raw records.
        kind = item.get("type")
        if kind == "AgentMessage":
            if item.get("phase") not in ("commentary", "final_answer", "final"):
                return
            event = {"kind": "assistant", "phase": item["phase"], "text": content_text(item.get("content"))}
        elif kind == "UserMessage":
            event = {"kind": "user", "text": content_text(item.get("content"))}
        elif kind == "CommandExecution":
            command = item.get("command", "")
            if isinstance(command, list) and all(isinstance(part, str) for part in command):
                if len(command) >= 3 and command[1] in ("-c", "-lc"):
                    command = command[2]
                else:
                    command = shlex.join(command)
            output = item.get("aggregated_output") or "\n".join(
                item.get(key, "") for key in ("stdout", "stderr") if isinstance(item.get(key), str)
            )
            event = {
                "kind": "command", "text": visible_text(output),
                "command": visible_text(command), "exitCode": item.get("exit_code"),
            }
        else:
            return
        if not event.get("text") and not event.get("command"):
            return
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in self.seen:
            return
        self.seen.add(item_id)
        self.seen_order.append(item_id)
        if len(self.seen_order) > 2000:
            self.seen.discard(self.seen_order.popleft())
        self.cursor += 1
        event.update(id=self.cursor, timestamp=record.get("timestamp", ""))
        self.events.append(event)

    def refresh(self):
        if self.path is None:
            self.path = self.locate()
        if self.path is None:
            return False
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                if self.identity != identity or stat.st_size < self.offset:
                    self.reset()
                    self.identity = identity
                stream.seek(self.offset)
                # Keep each poll bounded; a large history is caught up over subsequent polls.
                budget = 16 * 1024 * 1024
                while budget > 0:
                    line = stream.readline(MAX_RECORD + 1)
                    if not line:
                        break
                    budget -= len(line)
                    if self.skipping:
                        self.offset = stream.tell()
                        self.skipping = not line.endswith(b"\n")
                        continue
                    if len(line) > MAX_RECORD:
                        self.skipping = not line.endswith(b"\n")
                        self.offset = stream.tell()
                        continue
                    if not line.endswith(b"\n"):
                        # Do not consume a partially written UTF-8 / JSON line.
                        break
                    self.offset = stream.tell()
                    try:
                        self.ingest(json.loads(line))
                    except (ValueError, TypeError):
                        continue
            return True
        except OSError:
            self.path = None
            return False

    def snapshot(self, after=0, generation=""):
        with self.lock:
            available = self.refresh()
            oldest = self.events[0]["id"] if self.events else 1
            reset = generation != self.generation or after > self.cursor or after < oldest - 1
            return {
                "available": available,
                "status": self.status if available else ("waiting" if self.thread else "offline"),
                "generation": self.generation,
                "reset": reset,
                "cursor": self.cursor,
                "events": [event for event in self.events if reset or event["id"] > after],
            }
