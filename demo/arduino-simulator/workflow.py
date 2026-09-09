"""Human-gated Codex jobs and recoverable, project-local file checkpoints."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time

from questions import parse_numbered_question
from workflow_documents import WorkflowDocuments, SCHEMA, DOC_DIRECTORY, public_schema
from side_question import SideQuestion

STAGES = tuple(SCHEMA)
INSTRUCTIONS = {
    "initialization": "프로젝트 초기화를 수행하라. 현재 파일, 지침, 진입점, 기술 스택, 의존성, 실행·테스트 명령과 기존 변경을 조사하라. 코드부터 쓰지 말고 근거 파일과 작업 규칙을 보고하라.",
    "ideation": "사용자의 문제, 가치, 대상 사용자, 시나리오, 목표, 포함·제외 범위와 성공 기준을 구체화하라. 구현하지 말고 가정과 미확정 사항을 구분하라.",
    "inception": "구현 없이 계획만 작성하라. 초기화 근거와 아이디어를 요구사항·사용자 스토리·인수 조건으로 바꾸고, 모호한 점만 질문하라. 확정된 요구로 구조·인터페이스·작업 단위·구현 순서·테스트·위험·복구 계획을 설계하라. 이 단계에서는 구현하지 말라. 승인된 계획의 구현은 CONSTRUCTION에서 수행한다.",
    "construction": "승인된 계획만 구현하라. 작업 단위별로 구현과 테스트를 수행하고 요구사항별 결과를 대조하라. 범위 확장이 필요하면 중단하고 질문하라. 변경 이유와 영향범위, 실행한 검사 명령과 실제 결과, 미검증 항목을 보고하라. 마지막에 VERDICT: PASS, VERDICT: FAIL 또는 VERDICT: BLOCKED를 명시하라.",
    "operation": "구현·검증 결과와 실제 Diff를 리뷰하고 인수·운영 준비 문서를 작성하라. 남은 결함, 요구사항 누락, 배포 전 점검, 모니터링·장애 대응·롤백·사용 안내를 정리하라. 실제 배포·인프라 변경·외부 서비스 호출은 수행하지 말라. 확인되지 않은 운영 상태는 미검증으로 명시하라.",
}
EXCLUDED = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache", ".pytest_cache", ".mypy_cache", "dist", "construction", "target", ".DS_Store", DOC_DIRECTORY}


def button_questions(text, run_id):
    """Read explicit choice menus emitted by the workflow, falling back to clear prose."""
    match = re.search(r"<button-questions>\s*([\s\S]*?)\s*</button-questions>", text)
    if not match:
        question = parse_numbered_question(text, run_id)
        return [question] if question else []
    try:
        data = json.loads(match.group(1))
        items = data.get("questions")
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            return []
        questions = []
        for i, item in enumerate(items):
            prompt, options = item.get("prompt"), item.get("options")
            if not isinstance(prompt, str) or not 1 <= len(prompt) <= 2000 or not isinstance(options, list) or not 2 <= len(options) <= 30:
                return []
            if not all(isinstance(label, str) and 1 <= len(label) <= 500 for label in options):
                return []
            questions.append({"id": f"{run_id}:{i + 1}", "kind": "choice", "prompt": prompt,
                              "index": i + 1, "total": len(items),
                              "options": [{"id": str(n + 1), "label": label} for n, label in enumerate(options)]})
        return questions
    except (ValueError, AttributeError, TypeError):
        return []


def signature(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


class Checkpoints:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.saved = None
        self.directory = None
        self.preview_token = ""

    def inventory(self):
        files = {}
        total = 0
        for root, dirs, names in os.walk(self.workspace, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
            for name in dirs + sorted(names):
                if name in EXCLUDED:
                    continue
                path = Path(root) / name
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError(f"안전지점은 심볼릭 링크를 지원하지 않습니다: {path.relative_to(self.workspace)}")
                if stat.S_ISDIR(info.st_mode):
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("일반 파일이 아닌 항목이 있어 안전지점을 만들 수 없습니다.")
                total += info.st_size
                if info.st_size > 32 * 1024 * 1024 or total > 128 * 1024 * 1024 or len(files) >= 10000:
                    raise ValueError("안전지점 한도 초과: 파일당 32MiB, 전체 128MiB, 10,000개 파일까지 지원합니다.")
                files[path.relative_to(self.workspace).as_posix()] = [hashlib.sha256(path.read_bytes()).hexdigest(), stat.S_IMODE(info.st_mode)]
        return files

    def capture(self, expected):
        before = self.inventory()
        if signature(before) != expected:
            raise ValueError("계획 승인 후 파일이 변경됐습니다. 계획을 다시 확인하고 승인해 주세요.")
        directory = Path(tempfile.mkdtemp(prefix="button-lab-checkpoint-"))
        for name in before:
            target = directory / "files" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.workspace / name, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != before[name][0]:
                raise ValueError("안전지점 저장 중 파일이 변경됐습니다. 다시 시도해 주세요.")
        if self.inventory() != before:
            raise ValueError("안전지점 저장 중 프로젝트가 변경됐습니다.")
        (directory / "manifest.json").write_text(json.dumps({"workspace": str(self.workspace), "files": before}, ensure_ascii=False))
        self.directory, self.saved = directory, before
        self.preview_token = ""

    def preview(self):
        if self.saved is None:
            raise ValueError("안전지점이 없습니다. 승인된 BUILD를 실행하면 구현 직전 파일이 저장됩니다.")
        current = self.inventory()
        changes, diffs = [], []
        for name in sorted(self.saved.keys() | current.keys()):
            if self.saved.get(name) == current.get(name):
                continue
            kind = "added" if name not in self.saved else "deleted" if name not in current else "modified"
            changes.append({"path": name, "kind": kind})
            old = (self.directory / "files" / name).read_bytes() if name in self.saved else b""
            new = (self.workspace / name).read_bytes() if name in current else b""
            if b"\0" in old + new or len(old) + len(new) > 200000:
                diffs.append(f"{name}: 바이너리/대용량 파일 또는 권한 변경 ({kind})\n")
            else:
                diff = "".join(difflib.unified_diff(old.decode(errors="replace").splitlines(True), new.decode(errors="replace").splitlines(True), fromfile=f"safe/{name}", tofile=f"current/{name}"))
                diffs.append(diff or f"{name}: 파일 권한 변경\n")
        self.preview_token = signature(current)
        return {"token": self.preview_token, "changes": changes, "diff": "\n".join(diffs)[:80000], "checkpoint": str(self.directory), "excluded": sorted(EXCLUDED)}

    def restore(self, token):
        if not token or token != self.preview_token or signature(self.inventory()) != token:
            raise ValueError("미리보기 이후 파일이 변경됐습니다. 복귀 내용을 다시 확인해 주세요.")
        preview = self.preview()
        if not preview["changes"]:
            raise ValueError("되돌릴 변경사항이 없습니다.")
        for name in self.saved:
            path = self.workspace / name
            if path.exists() and not path.is_file():
                raise ValueError(f"파일이 디렉터리로 변경되어 자동 복귀할 수 없습니다: {name}")
        # Back up every affected current file before replacing anything. Keep both backups.
        backup = Path(tempfile.mkdtemp(prefix="button-lab-before-revert-"))
        for change in preview["changes"]:
            name = change["path"]
            source = self.workspace / name
            if source.is_file():
                target = backup / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        (backup / "recovery.json").write_text(json.dumps({"workspace": str(self.workspace), "changes": preview["changes"]}))
        if signature(self.inventory()) != token:
            raise ValueError("백업 중 프로젝트가 변경됐습니다. 복귀를 취소했습니다.")
        for change in preview["changes"]:
            name = change["path"]
            path = self.workspace / name
            if name not in self.saved:
                path.unlink()  # Exact reviewed new file; its contents are already backed up.
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, staging = tempfile.mkstemp(prefix=".button-lab-", dir=path.parent)
                os.close(fd)
                shutil.copy2(self.directory / "files" / name, staging)
                os.replace(staging, path)
        self.preview_token = ""
        return {"restored": len(preview["changes"]), "backup": str(backup)}


class Workflow:
    def __init__(self, codex, workspace):
        self.codex, self.workspace = codex, Path(workspace).resolve()
        self.lock = threading.RLock()
        self.checkpoints = Checkpoints(self.workspace)
        self.requirements, self.plan, self.approval = "", "", ""
        self.autonomy = 1
        self.results = {}
        self.events = []
        self.running, self.cancelled = False, False
        self.stage, self.run_id, self.error = "", "", ""
        self.process = None
        self.plan_signature = ""
        self.questions = []
        self.awaiting_approval = False
        self.documents = WorkflowDocuments(self.workspace)
        saved = self.documents.load()
        self.inputs = {stage: dict(saved.get("inputs", {}).get(stage, {})) for stage in STAGES}
        # Preserve drafts from the earlier seven-stage layout if present.
        if saved.get("version") == 1:
            old = saved.get("inputs", {})
            self.inputs["ideation"] = dict(old.get("intent", {}))
            self.inputs["initialization"] = {"project": "", "workspace": old.get("context", {}).get("references", ""),
                "environment": old.get("context", {}).get("environment", ""), "rules": old.get("context", {}).get("constraints", "")}
            self.inputs["inception"] = {"requirements": "", "decisions": old.get("ask", {}).get("decisions", ""),
                "design": old.get("plan", {}).get("design", ""), "risks": old.get("plan", {}).get("risks", "")}
            self.inputs["construction"] = {"unit": old.get("build", {}).get("unit", ""), "boundaries": old.get("build", {}).get("boundaries", ""),
                "commands": old.get("verify", {}).get("commands", ""), "cases": old.get("verify", {}).get("cases", "")}
            self.inputs["operation"] = {"acceptance": old.get("review", {}).get("decision", ""), "release": "", "observability": "", "handoff": old.get("review", {}).get("handoff", "")}
        self.requirements = saved.get("requirements", "")
        self.results = {stage: result for stage, result in saved.get("results", {}).items() if stage in STAGES}
        self.plan = saved.get("plan", "")
        self.autonomy = saved.get("autonomy", 1)
        self.question_only = False
        self.question_results = {}
        self.question_inputs = {}
        self.ask_answers = {}
        self.gate_message = ""
        self.side_question = SideQuestion(codex, self.workspace)
        self.direct_run = False
        self.direct_target = ""

    def persist(self):
        self.documents.save(self.inputs, self.results, self.plan, self.requirements, self.autonomy)

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "stage": self.stage, "runId": self.run_id, "error": self.error,
                    "requirements": self.requirements, "plan": self.plan, "approved": bool(self.approval),
                    "autonomy": self.autonomy, "results": dict(self.results), "events": list(self.events),
                    "checkpoint": str(self.checkpoints.directory or ""), "cancelled": self.cancelled,
                    "generation": self.run_id, "ready": not self.running and bool(self.questions),
                    "question": self.questions[0] if self.questions and not self.running else None,
                    "inputs": {stage: dict(fields) for stage, fields in self.inputs.items()},
                    "schema": public_schema(), "documentsDirectory": str(self.documents.root), "awaitingApproval": self.awaiting_approval,
                    "humanGate": self.gate_message, "questionOnly": self.question_only, "questionResults": dict(self.question_results),
                    "sideQuestion": self.side_question.snapshot()}

    def idle(self):
        if self.running:
            raise ValueError("작업 실행 중입니다. STOP으로 중단한 뒤 변경해 주세요.")

    def configure(self, requirements, autonomy, stage=None, fields=None):
        with self.lock:
            self.idle()
            if stage is not None:
                if stage not in SCHEMA or not isinstance(fields, dict):
                    raise ValueError("올바른 단계와 입력 항목이 필요합니다.")
                allowed = {field[0] for field in SCHEMA[stage][2]}
                if set(fields) - allowed or any(not isinstance(v, str) or len(v) > (20000 if k == "brief" else 3000) for k, v in fields.items()):
                    raise ValueError("단계 입력은 20,000자 이하로 작성해 주세요.")
                if type(autonomy) is not int or not 0 <= autonomy <= 5:
                    raise ValueError("자율성은 0~5이어야 합니다.")
                base = {"decision": self.inputs[stage].get("decision", "")} if "brief" in fields else self.inputs[stage]
                normalized = {key: fields.get(key, base.get(key, "")) for key in allowed}
                if normalized.get("decision", "") not in ("", "pending", "approved", "hold", "rejected"):
                    raise ValueError("올바른 진행 판단을 선택해 주세요.")
                old = self.inputs[stage]
                decision_only = all(normalized.get(k, "") == old.get(k, "") for k in allowed if k != "decision")
                if normalized != old and decision_only:
                    self.inputs[stage] = normalized
                elif normalized != old:
                    self.inputs[stage] = normalized
                    self.approval = ""
                    for downstream in STAGES[STAGES.index(stage):]:
                        self.results.pop(downstream, None)
                        if self.inputs[downstream].get("decision") == "approved": self.inputs[downstream]["decision"] = "pending"
                    if STAGES.index(stage) <= STAGES.index("inception"):
                        self.plan = self.plan_signature = ""
                        self.questions = []
                if stage == "ideation" and (normalized.get("brief") or "brief" in fields):
                    self.requirements = normalized["brief"]
                elif stage == "ideation":
                    self.requirements = "\n\n".join(f"{label}:\n{normalized[key]}" for key, label, _ in SCHEMA[stage][2] if key not in ("decision", "instruction") and normalized[key].strip())
                if self.autonomy != autonomy: self.approval = ""
                self.autonomy = autonomy
                self.persist()
                return self.snapshot()
            if not isinstance(requirements, str) or len(requirements) > 20000 or type(autonomy) is not int or not 0 <= autonomy <= 5:
                raise ValueError("목표는 20,000자 이하, 자율성은 0~5이어야 합니다.")
            if self.requirements != requirements or self.autonomy != autonomy:
                self.approval = ""
            if self.requirements != requirements:
                self.plan, self.plan_signature, self.results = "", "", {}
                self.questions = []
            self.requirements, self.autonomy = requirements, autonomy
            self.persist()
            return self.snapshot()

    def answer(self, generation, question_id, choice):
        with self.lock:
            self.idle()
            if generation != self.run_id or not self.questions or self.questions[0]["id"] != question_id:
                raise ValueError("질문이 이미 처리됐거나 변경됐습니다.")
            question = self.questions[0]
            option = next((option for option in question["options"] if option["id"] == str(choice)), None)
            if not option:
                raise ValueError("표시된 선택지 번호를 눌러 주세요.")
            answer = f"\n\n질문: {question['prompt']}\n답변: {option['id']}. {option['label']}"
            if self.question_only:
                self.ask_answers[self.stage] = (self.ask_answers.get(self.stage, "") + answer)[-12000:]
                self.questions.pop(0)
                self.question_results[self.stage] = self.question_results.get(self.stage, "") + answer
                return self.snapshot()
            if len(self.requirements + answer) > 12000:
                raise ValueError("목표·답변이 12,000자를 넘습니다. 목표 입력란을 정리한 뒤 답변해 주세요.")
            self.requirements += answer
            self.inputs["inception"]["decisions"] = (self.inputs["inception"].get("decisions", "") + answer).strip()
            self.questions.pop(0)
            self.approval = self.plan = self.plan_signature = ""
            for stage in ("inception", "construction", "operation"):
                self.results.pop(stage, None)
            self.persist()
            return self.snapshot()

    def approve(self, plan):
        with self.lock:
            self.idle()
            if self.questions:
                raise ValueError("먼저 표시된 질문에 답변해 주세요.")
            if not isinstance(plan, str) or not plan.strip() or len(plan) > 20000 or not self.plan_signature:
                raise ValueError("먼저 3 INCEPTION을 완료하고 검토할 계획을 입력해 주세요.")
            current = signature(self.checkpoints.inventory())
            if current != self.plan_signature:
                raise ValueError("설계 이후 프로젝트가 변경됐습니다. 초기화 근거와 INCEPTION 계획을 갱신해 주세요.")
            self.plan, self.approval = plan, current
            self.awaiting_approval = False
            self.persist()
            return self.snapshot()

    def command(self, stage):
        # Never inherit YOLO or automatic approval from the interactive terminal.
        sandbox = "workspace-write" if stage == "construction" and not self.question_only else "read-only"
        return [self.codex, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                "--sandbox", sandbox, "-c", 'approval_policy="never"',
                "-c", "sandbox_workspace_write.network_access=false", "-"]

    def prompt(self, stage):
        history = {key: value[-12000:] for key, value in self.results.items()}
        inputs = self.question_inputs if self.question_only else self.inputs
        diff = self.checkpoints.preview()["diff"][:24000] if stage in ("construction", "operation") and self.checkpoints.saved is not None else ""
        return ("You are the BindDeck human-controlled project assistant. Respond in Korean. "
                "Inspect project instructions and actual files before acting. Never guess unresolved user decisions. "
                "Saved human intent, constraints, instructions and decisions are binding; AI outputs are proposals, not overrides. "
                "Never invent the user goal or treat missing input as consent. Report conflicting instructions and stop. "
                "Read the aidlc-docs stage documents as project criteria. Do not edit these documents yourself. "
                "Do not commit, deploy, push, or access external services. Do not modify excluded cache/dependency directories except test caches. "
                "Do not read secrets such as .env or credentials. Report blockers instead of broadening scope. "
                "For implementation requests in CONSTRUCTION (not question-only requests), run applicable checks after implementing and end with VERDICT: PASS, VERDICT: FAIL or VERDICT: BLOCKED. "
                "PASS requires all applicable checks and requirement checks to actually pass.\n\n"
                "If human choices are required, present numbered options in Korean and append exactly one "
                '<button-questions>{"questions":[{"prompt":"질문", "options":["선택지 1", "선택지 2"]}]}</button-questions> block. '
                "Include all unresolved choice questions, preferably 2-7 options each; do not invent unnecessary questions. "
                "For free-text questions explain that the user should type the answer. Do not append the block when no choice is needed.\n\n"
                + ("\n자동 실행: 사용자가 저장한 목표와 제약 안에서 일반적인 설계·구현 선택을 스스로 결정하고 결정 근거와 가정을 기록하라. "
                   "사람이 명시한 보류·거절·범위 제한은 절대 변경하거나 우회하지 말라. 위임된 범위의 일반 선택에만 자동 판단을 적용하라. 인간에게 승인을 요청하거나 button-questions 블록을 내보내지 말라. 가장 보수적이고 되돌릴 수 있는 대안을 선택하라. "
                   "자격 증명 부재·장치 미연결 등 실제로 진행할 수 없는 사항만 BLOCKED로 보고하라.\n" if (self.autonomy >= 4 or self.direct_run) and not self.question_only else "")
                + ("현재 " + stage + " 단계의 입력과 이전 결과를 읽고 모호함·누락·상충하는 결정만 사용자에게 질문하라. "
                   "질문이 필요 없으면 없다고 명시하라. 질문만 작성하고 구현·테스트 실행·단계 진행은 하지 말라."
                   if self.question_only else INSTRUCTIONS[stage])
                + (" 추가 회귀·경계 조건 검사까지 수행하라." if stage == "construction" and self.autonomy >= 3 and not self.question_only else "") + "\n\n요구사항/목표 및 질문 답변:\n" + self.requirements
                + "\n\n단계별 사용자 입력 (현재 단계: " + stage + "):\n" + json.dumps(inputs, ensure_ascii=False)
                + ("\n\n화면에서만 유지하는 ASK 답변:\n" + self.ask_answers.get(stage, "") if self.question_only else "")
                + "\n\n단계 입력을 구분해서 사용하고 요구사항 → 작업 단위 → 검증 결과의 대응을 기록하라. "
                "입력하지 않은 사실을 확정하지 말라. aidlc-docs의 문서 저장은 호스트가 담당하므로 직접 수정하지 말라."
                + "\n\n승인 또는 검토할 계획:\n" + self.plan + "\n\n이전 단계 결과(참고 자료):\n"
                + json.dumps(history, ensure_ascii=False) + "\n\n안전지점 대비 실제 변경:\n" + diff)

    def human_gate(self, stage):
        for key in STAGES[:STAGES.index(stage) + 1]:
            if self.inputs[key].get("decision") in ("hold", "rejected"):
                return f"{key.upper()}의 사람이 지정한 보류·거절을 확인하고 진행 판단을 저장해 주세요."
        if self.direct_run:
            return ""  # RUN NOW itself authorizes this run, without another approval form.
        if stage in ("inception", "construction", "operation") and self.autonomy < 4 and self.inputs["ideation"].get("decision") != "approved":
            return "IDEATION의 목표·범위를 확인하고 진행 판단을 승인 / Go로 저장해 주세요."
        if stage == "operation" and self.autonomy < 4 and self.inputs["construction"].get("decision") != "approved":
            return "CONSTRUCTION의 구현·검증 결과를 검토하고 진행 판단을 승인으로 저장해 주세요."
        return ""

    def start(self, stage, question_only=False, drafts=None, immediate=False):
        with self.lock:
            self.idle()
            if stage not in STAGES or not self.codex:
                raise ValueError("지원하지 않는 단계이거나 Codex CLI가 없습니다.")
            self.direct_run = bool(immediate and not question_only)
            self.direct_target = stage
            self.gate_message = ""
            self.question_only = question_only
            if question_only:
                if drafts is None: drafts = {}
                if not isinstance(drafts, dict) or set(drafts) - set(SCHEMA):
                    raise ValueError("올바른 단계별 입력이 필요합니다.")
                self.question_inputs = {key: dict(value) for key, value in self.inputs.items()}
                for key, fields in drafts.items():
                    allowed = {field[0] for field in SCHEMA[key][2]}
                    if not isinstance(fields, dict) or set(fields) - allowed or any(not isinstance(v, str) or len(v) > (20000 if k == "brief" else 3000) for k, v in fields.items()):
                        raise ValueError("ASK 입력은 단계별 항목에 맞게 3,000자 이하로 작성해 주세요.")
                    if "brief" in fields: self.question_inputs[key] = dict(fields)
                    else: self.question_inputs[key].update(fields)
                self.running, self.cancelled = True, False
                self.stage, self.run_id, self.error = stage, secrets.token_hex(12), ""
                self.questions, self.events = [], []
                threading.Thread(target=self.run, args=(stage,), daemon=True).start()
                return self.snapshot()
            if (stage != "initialization" or self.autonomy >= 3) and not self.requirements.strip():
                raise ValueError("2 IDEATION에서 무엇을 왜 만드는지 먼저 입력하고 저장해 주세요.")
            gate = self.human_gate(stage)
            if gate: raise ValueError(gate)
            if self.autonomy >= 4 or self.direct_run:
                # Recreate prerequisites instead of asking the user to approve a stale plan.
                if stage in ("inception", "construction") and not self.results.get("initialization"):
                    stage = "initialization"
                elif stage == "construction" and (not self.plan_signature or self.plan_signature != signature(self.checkpoints.inventory())):
                    stage = "inception"
                self.questions = []
            if self.questions and stage not in ("ideation", "initialization", "inception"):
                raise ValueError("먼저 표시된 질문에 답변해 주세요.")
            gate = self.human_gate(stage)
            if gate: raise ValueError(gate)
            if stage == "inception" and not self.results.get("initialization"):
                raise ValueError("먼저 1 INITIALIZATION으로 현재 프로젝트를 조사해 주세요.")
            if stage == "construction":
                if self.autonomy >= 4 or self.direct_run:
                    self.approval = self.plan_signature
                if not self.approval:
                    raise ValueError("CONSTRUCTION에는 설계 화면의 계획 승인이 필요합니다.")
                self.checkpoints.capture(self.approval)
                self.approval = ""  # One approval authorizes exactly one build.
            if stage in ("initialization", "ideation", "inception"):
                self.approval = ""
                self.plan_signature = ""
                self.plan = ""
            for downstream in STAGES[STAGES.index(stage):]:
                self.results.pop(downstream, None)
            self.persist()
            self.awaiting_approval = False
            self.running, self.cancelled = True, False
            self.stage, self.run_id, self.error = stage, secrets.token_hex(12), ""
            self.questions = []
            self.events = []
            threading.Thread(target=self.run, args=(stage,), daemon=True).start()
            return self.snapshot()

    def run(self, stage):
        process = None
        try:
            queue = list(STAGES[STAGES.index(stage):]) if self.autonomy >= 3 and not self.question_only else [stage]
            if self.direct_run and self.autonomy < 3:
                queue = list(STAGES[STAGES.index(stage):STAGES.index(self.direct_target) + 1])
            if self.autonomy == 4 and stage != "operation":
                queue = [item for item in queue if item != "operation"]
            decision_retries = {}
            for current in queue:
                with self.lock:
                    if self.cancelled:
                        break
                    if not self.question_only:
                        gate = self.human_gate(current)
                        if gate:
                            self.gate_message = gate
                            break
                    if current == "construction" and current != stage:
                        if self.autonomy < 4 and not self.direct_run:
                            self.awaiting_approval = True
                            break
                        self.checkpoints.capture(self.plan_signature)
                        self.approval = ""
                    if not self.question_only and current in ("construction", "operation") and self.inputs[current].get("decision") == "approved":
                        self.inputs[current]["decision"] = "pending"
                    self.stage = current
                    baseline = signature(self.checkpoints.inventory()) if current == "inception" and not self.question_only else ""
                    prompt = self.prompt(current)
                    env = os.environ.copy()
                    for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID"):
                        env.pop(key, None)
                    process = subprocess.Popen(self.command(current), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT, cwd=self.workspace, env=env,
                                               start_new_session=True)
                    self.process = process
                # Feeding stdin happens on its own thread so STOP can always kill the process group.
                def feed(proc=process, data=prompt.encode()):
                    try:
                        proc.stdin.write(data)
                        proc.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
                threading.Thread(target=feed, daemon=True).start()
                result, failure = "", ""
                for raw in process.stdout:
                    line = raw.decode(errors="replace")
                    try:
                        event = json.loads(line)
                    except ValueError:
                        event = {"type": "diagnostic", "message": line.strip()}
                    if not isinstance(event, dict):
                        continue
                    with self.lock:
                        self.events.append(line.strip()[:2000])
                        self.events = self.events[-40:]
                    if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                        result = event["item"].get("text", "")[:20000]
                    if event.get("type") in ("error", "turn.failed"):
                        failure = str(event.get("message") or event.get("error") or "Codex 실행 실패")
                code = process.wait()
                process.stdout.close()
                with self.lock:
                    self.process = None
                    if self.cancelled:
                        break
                    if code or failure or not result:
                        raise ValueError(failure or f"Codex 실행 실패 (종료 {code}). 로그인과 실행 로그를 확인해 주세요.")
                    if self.question_only:
                        self.question_results[current] = result
                        self.questions = button_questions(result, self.run_id)
                        break
                    self.results[current] = result
                    self.questions = button_questions(result, self.run_id)
                    if current == "inception":
                        if signature(self.checkpoints.inventory()) != baseline:
                            raise ValueError("계획 작성 중 파일이 변경됐습니다. PLAN을 다시 실행해 주세요.")
                        self.plan, self.plan_signature = result, baseline
                    self.persist()
                    if self.questions:
                        self.approval = ""
                        if (self.autonomy >= 4 or self.direct_run) and decision_retries.get(current, 0) < 2:
                            decision_retries[current] = decision_retries.get(current, 0) + 1
                            self.inputs["inception"]["decisions"] = (self.inputs["inception"].get("decisions", "") +
                                "\n자동 결정 필요: " + " / ".join(q["prompt"] for q in self.questions))[-3000:]
                            self.questions = []
                            # Retry this same phase before any downstream phase.
                            queue.insert(queue.index(current) + decision_retries[current], current)
                            continue
                        if self.autonomy >= 4 or self.direct_run:
                            self.error = "AI가 자동으로 결정을 완료하지 못해 중단했습니다. 결과에 미결 사유가 기록됐습니다."
                            self.questions = []
                        break
                    if current == "construction" and not result.rstrip().endswith("VERDICT: PASS"):
                        self.error = "검증이 통과하지 않았습니다. 결과를 확인해 주세요. 자동 후속 단계는 중단했습니다."
                        break
        except Exception as error:
            with self.lock:
                self.error = str(error)
        finally:
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
            with self.lock:
                self.running = False
                self.process = None

    def stop(self):
        self.side_question.stop()
        with self.lock:
            self.cancelled = True
            self.approval = ""
            self.questions = []
            process = self.process
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return self.snapshot()

    def preview(self):
        with self.lock:
            self.idle()
            return self.checkpoints.preview()

    def revert(self, token):
        with self.lock:
            self.idle()
            result = self.checkpoints.restore(token)
            self.approval, self.plan_signature = "", ""
            return result
