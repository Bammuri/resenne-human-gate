"""Workspace-specific deck settings and replies to an existing Codex conversation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

from questions import parse_numbered_question

MODES = ("agent", "workflow", "custom")
ACTIONS = ("prompt", "accept", "denied", "continue", "retry", "stop")


def defaults():
    return {"mode": "agent", "custom": [
        {"label": f"커스텀 {i}", "target": "terminal", "action": "prompt", "text": ""}
        for i in range(1, 8)]}


def validate_config(value):
    if not isinstance(value, dict) or value.get("mode") not in MODES:
        raise ValueError("모드는 workflow, agent, custom 중 하나여야 합니다.")
    slots = value.get("custom")
    if not isinstance(slots, list) or len(slots) != 7:
        raise ValueError("커스텀 버튼은 정확히 7개를 설정해 주세요.")
    clean = []
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("올바른 버튼 설정이 필요합니다.")
        label, text = slot.get("label"), slot.get("text", "")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 24 or any(ord(c) < 32 for c in label):
            raise ValueError("버튼 이름은 1~24자의 한 줄 텍스트여야 합니다.")
        if slot.get("target") not in ("terminal", "current") or slot.get("action") not in ACTIONS:
            raise ValueError("지원하지 않는 실행 대상 또는 명령입니다.")
        if not isinstance(text, str) or len(text) > 8192 or "\0" in text:
            raise ValueError("프롬프트는 8,192자 이하여야 합니다.")
        clean.append({"label": label.strip(), "target": slot["target"], "action": slot["action"], "text": text})
    return {"mode": value["mode"], "custom": clean}


class ControlSettings:
    def __init__(self, workspace, directory=None):
        base = Path(directory or os.environ.get("BUTTON_LAB_CONFIG_DIR") or Path.home() / ".config" / "button-lab")
        key = hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest()[:24]
        self.path = base / key / "controls.json"
        self.lock = threading.Lock()
        self.value = defaults()
        try:
            self.value = validate_config(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def save(self, value):
        value = validate_config(value)
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, staging = tempfile.mkstemp(prefix=".controls-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(staging, self.path)
            finally:
                if os.path.exists(staging):
                    os.unlink(staging)
            self.value = value
            return copy.deepcopy(value)


class ConversationQuestions:
    """Read only completed, visible messages; never interpret a prose list as a tool approval."""
    def __init__(self, output):
        self.output = output
        self.resolved = set()

    def snapshot(self, available=True):
        snap = self.output.snapshot()
        events = [event for event in snap.get("events", []) if event.get("kind") in ("assistant", "user")]
        question = None
        # Never revive a question after a subsequent user message or during an unfinished turn.
        if events and events[-1]["kind"] == "assistant" and snap.get("status") == "idle":
            event = events[-1]
            question = parse_numbered_question(event.get("text", ""), f"{snap.get('generation')}:{event.get('id')}")
            if question and question["id"] in self.resolved:
                question = None
        ready = bool(available and snap.get("available"))
        return {"ready": ready, "busy": snap.get("status") == "active", "generation": snap.get("generation", ""),
                "question": question if ready else None}

    def resolve(self, question_id):
        self.resolved.add(question_id)
        if len(self.resolved) > 1000:
            self.resolved = {question_id}
