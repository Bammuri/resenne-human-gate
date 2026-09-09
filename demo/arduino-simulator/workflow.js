"use strict";

const WORKFLOW_KEYS = [
  ["initialization", "Initialization", "프로젝트 초기화", "구조·환경·규칙을 조사합니다."],
  ["ideation", "Ideation", "문제와 가치 구체화", "문제·사용자·범위·성공 기준을 구체화합니다."],
  ["inception", "Inception", "요구사항과 실행 설계", "질문·요구사항·작업 단위를 정리하고 계획을 승인합니다."],
  ["construction", "Construction", "구현과 검증", "승인한 계획을 구현하고 실제 테스트 결과를 확인합니다."],
  ["operation", "Operation", "인수와 운영 준비", "변경 검토·운영 점검·복구·인수인계를 준비합니다."],
  ["ask_workflow", "ASK", "자유로운 중간 질문", "AI-DLC와 별개로 질문하고 답변받습니다. MD에 저장하지 않습니다."],
  ["start_workflow", "RUN NOW", "입력 저장 후 현재 단계 실행", "현재 입력을 저장하고 선택한 단계를 실행합니다."],
];
const WORKFLOW_STOP = ["stop_revert", "RESTORE", "안전지점 복귀", "실제 변경 내용을 검토하고 복귀합니다."];
const AUTONOMY = ["MANUAL", "GUIDE", "STEP", "AUTO CHECK", "AUTO BUILD", "FULL AUTO"];
const AUTONOMY_HINTS = ["선택 단계 실행", "선택 단계 실행 · 다음 단계 안내", "실행 후 다음 입력 화면", "단계 자동 진행 · 추가 검증", "AI 판단 · 구현·검증까지", "AI 판단 · 운영 준비까지 전체 진행"];

// One project follows the app's five stages; examples are reference text, never drafts.
const PHASE_GUIDANCE = {
  initialization: {
    question: "어떤 프로젝트에서, 어떤 조건으로 시작하나요?",
    inputs: ["만들거나 고칠 프로젝트와 현재 상태", "사용할 기기·실행 환경 (모르면 ‘AI가 확인’)", "확인할 폴더·자료와 지켜야 할 작업 범위"],
    result: "AI에게 받을 결과: 현재 파일·실행 방법·작업 범위 정리. 이 단계에서는 현황을 조사합니다.",
    template: "프로젝트와 현재 상태: \n사용 환경: \n참고할 자료: \n지켜야 할 조건: ",
    sample: `프로젝트와 현재 상태: ‘나만의 할 일 목록 웹앱’을 새로 만들려고 합니다. 준비된 화면이나 코드는 없습니다.
사용 환경: 제 노트북의 Chrome에서 혼자 사용할 예정입니다. 개발 도구는 잘 모르니 적합한 실행 방법을 확인해 주세요.
참고할 자료: 현재 작업 폴더에 기존 코드와 설명서가 있는지 먼저 확인해 주세요.
지켜야 할 조건: 별도 회원가입이나 유료 서비스 없이 사용하고 싶습니다. 현재 폴더의 다른 프로젝트는 수정하지 마세요.
이번 요청: 현재 상태와 시작 방법을 정리해 주세요. 기능 설계와 구현은 다음 단계에서 진행하겠습니다.`
  },
  ideation: {
    question: "누구의 어떤 불편을 해결하고, 어디까지 만들까요?",
    inputs: ["사용자와 현재 겪는 불편", "이번에 꼭 필요한 기능과 나중으로 미룰 기능", "성공했다고 판단할 기준과 우선순위"],
    result: "AI에게 받을 결과: 사용자·목표·포함/제외 기능·성공 기준 정리. 이를 보고 진행할지 판단합니다.",
    template: "사용자와 불편: \n꼭 필요한 기능: \n이번에 제외할 기능: \n성공 기준과 우선순위: ",
    sample: `사용자와 불편: 저 혼자 사용합니다. 할 일을 메모지에 적다 보니 잊어버리거나 이미 끝낸 일을 다시 확인하게 됩니다.
꼭 필요한 기능: 할 일 추가, 완료 표시와 취소, 삭제, 저장이 필요합니다.
사용 장면: 아침에 ‘장보기’와 ‘책 읽기’를 적고, 장을 본 뒤 ‘장보기’를 완료 표시합니다.
이번에 제외할 기능: 로그인, 알림, 마감일, 다른 사람과 공유하기는 다음으로 미룹니다.
성공 기준과 우선순위: 가장 중요한 것은 기록이 남는 것입니다. 같은 브라우저에서 다시 열었을 때 목록과 완료 상태가 유지되면 좋겠습니다.
이번 요청: 이 범위로 목표와 성공 기준을 정리하고, 빠진 결정 사항을 질문해 주세요.`
  },
  inception: {
    question: "기능이 정확히 어떻게 동작해야 하나요?",
    inputs: ["사용자가 할 행동과 그때 화면에 나타날 결과", "빈 입력·삭제 등 예외 상황의 처리 규칙", "AI가 계획할 내용과 아직 결정하지 못한 사항"],
    result: "AI에게 받을 결과: 화면·데이터 저장 방식·구현 순서·검사 계획. 계획을 검토한 뒤 구현 단계로 넘어갑니다.",
    template: "화면과 사용 흐름: \n기능별 동작 규칙: \n예외 처리: \n미정 사항과 계획 요청: ",
    sample: `화면과 사용 흐름: 위에는 할 일 입력칸과 ‘추가’ 버튼을, 아래에는 목록을 보여 주세요. 각 항목에는 완료 체크와 삭제 버튼이 필요합니다.
기능별 동작 규칙: ‘장보기’를 입력하고 추가하면 목록에 한 번 나타나야 합니다. 완료 체크를 하면 글자에 줄이 생기고, 체크를 풀면 원래대로 돌아와야 합니다.
예외 처리: 공백만 입력하면 추가하지 말고 안내해 주세요. 삭제 버튼을 누르면 해당 항목만 없어져야 합니다. 항목이 없으면 ‘할 일을 추가해 보세요’라고 보여 주세요.
저장 규칙: 같은 브라우저에서 새로고침하거나 닫았다 다시 열어도 목록과 완료 상태를 유지해 주세요.
미정 사항과 계획 요청: 저장 기술은 AI가 제안해 주세요. 화면 구성, 구현 순서, 위 규칙을 확인할 검사 목록을 먼저 작성해 주세요. 이번 단계에서는 코드를 작성하지 마세요.`
  },
  construction: {
    question: "승인한 계획 중 무엇을 만들고, 어떻게 확인할까요?",
    inputs: ["검토한 계획 중 이번에 구현할 작업", "수정할 범위와 반드시 유지할 조건", "직접 따라 해 볼 검사 순서와 기대 결과"],
    result: "AI에게 받을 결과: 구현된 코드와 검사별 통과/실패 결과. 실행하지 못한 검사와 남은 문제도 확인합니다.",
    template: "이번에 구현할 작업: \n수정 범위와 유지할 조건: \n검사 순서와 기대 결과: \n결과 보고 요청: ",
    sample: `이번에 구현할 작업: 3단계에서 검토·승인한 계획에 따라 할 일 목록의 추가, 완료 표시와 취소, 삭제, 저장을 구현해 주세요.
수정 범위와 유지할 조건: 할 일 웹앱의 코드와 검사 파일만 수정해 주세요. 로그인이나 알림은 추가하지 마세요.
검사 순서와 기대 결과:
1. ‘장보기’와 ‘책 읽기’를 추가하면 두 항목이 보여야 합니다.
2. ‘장보기’를 완료 체크하면 줄이 생기고, 해제하면 줄이 없어져야 합니다.
3. ‘장보기’를 다시 완료 처리하고 ‘책 읽기’를 삭제하면 완료된 ‘장보기’만 남아야 합니다.
4. 같은 주소를 새로고침하고 브라우저를 닫았다 다시 열어도 그 상태가 유지되어야 합니다.
5. 공백만 추가하면 항목 수가 늘지 않아야 합니다.
결과 보고 요청: 각 검사를 실제로 실행했는지와 통과 여부를 알려 주세요. 실패한 항목은 수정하고 다시 확인해 주세요. 직접 확인할 수 없는 항목은 제가 따라 할 방법을 적어 주세요.`
  },
  operation: {
    question: "완성된 것을 어디서 쓰고, 문제에 어떻게 대응할까요?",
    inputs: ["직접 확인한 결과와 남은 문제 (미확인이면 그대로 표시)", "사용할 환경과 공개·배포 범위", "필요한 사용법·오류 대응·복구 안내"],
    result: "AI에게 받을 결과: 사용 안내, 사용 전 점검표, 문제 해결·복구 방법. 실제 확인 결과를 보고 인수 여부를 판단합니다.",
    template: "직접 확인한 결과와 남은 문제: \n사용 환경과 공개 범위: \n필요한 사용 안내: \n오류 대응과 복구 요청: ",
    sample: `직접 확인한 결과와 남은 문제: AI가 보고한 검사 결과는 검토하되, 제 노트북에서는 아직 확인하지 않았습니다. 제가 검사한 뒤 사용 가능 여부를 판단하겠습니다.
사용 환경과 공개 범위: 제 노트북의 Chrome에서 혼자 사용합니다. 이번에는 인터넷에 공개하지 않습니다.
필요한 사용 안내: 실행 방법과 할 일 추가·완료·삭제 방법을 짧게 적어 주세요. 매번 같은 주소와 브라우저로 열어야 하는지, 브라우저 데이터를 지우면 목록이 어떻게 되는지도 설명해 주세요.
오류 대응과 복구 요청: 화면이 열리지 않거나 목록이 사라졌을 때 확인할 순서를 적어 주세요. 코드 변경을 되돌리는 방법과 삭제된 목록을 복구할 수 있는지는 구분해서 알려 주세요.
이번 요청: 제가 따라 할 최종 점검표와 사용 안내를 남겨 주세요. 직접 확인한 결과를 기록한 뒤 남은 문제와 다음 개선 사항을 정리하겠습니다.`
  }
};

function phaseDraft(schema, fields = {}) {
  const entries = (schema?.fields || []).filter(f => !["brief", "decision"].includes(f.key) && fields[f.key]);
  const brief = fields.brief || (entries.length === 1 ? fields[entries[0].key] : entries.map(f => `${f.label}\n${fields[f.key]}`).join("\n\n"));
  return {brief, ...(schema?.fields.some(f => f.key === "decision") ? {decision: fields.decision || "pending"} : {})};
}

class WorkflowController {
  constructor(options) {
    this.options = options;
    this.data = { autonomy: 1, running: false, results: {}, events: [] };
    this.stage = "initialization";
    this.pending = false;
    this.previewToken = "";
    this.dirtyStages = new Set();
    this.autoDirtyStages = new Set();
    this.savedStages = new Set();
    this.autosaveTimer = null; this.autosaveJob = null; this.saveRevision = 0;
    this.saveError = false; this.composing = false;
    this.drafts = {};
    this.renderedStage = "";
    this.planDirty = false;
    this.initialized = false;
    this.dialog = document.querySelector("#workflow-dialog");
    this.el = id => document.querySelector(`#workflow-${id}`);
    WORKFLOW_KEYS.slice(0, 5).forEach(([action, label], i) => {
      const button = document.createElement("button");
      button.textContent = `${i + 1} ${label}`;
      button.addEventListener("click", () => this.open(action));
      this.el("steps").append(button);
    });
    this.el("close").onclick = () => { this.dialog.close(); this.el("review-dialog").close(); };
    this.el("input-close").onclick = () => this.closeInput();
    this.dialog.addEventListener("cancel", event => { event.preventDefault(); this.closeInput(); });
    this.dialog.addEventListener("click", event => {
      const box = this.dialog.getBoundingClientRect();
      if (event.target === this.dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) this.closeInput();
    });
    this.el("brief").oninput = () => {
      (this.drafts[this.stage] ||= {}).brief = this.el("brief").value;
      this.dirtyStages.add(this.stage); this.autoDirtyStages.add(this.stage); this.saveError = false;
      this.scheduleAutoSave(); this.render();
    };
    this.el("brief").addEventListener("compositionstart", () => { this.composing = true; clearTimeout(this.autosaveTimer); });
    this.el("brief").addEventListener("compositionend", () => { this.composing = false; this.scheduleAutoSave(); });
    this.el("save").onclick = () => this.save();
    this.el("autonomy").onchange = event => this.setAutonomy(Number(event.target.value));
    Array.from(this.el("autonomy").options).forEach((option, i) => { option.textContent = `${i} · ${AUTONOMY[i]} — ${AUTONOMY_HINTS[i]}`; });
    this.el("approve").onclick = () => this.perform(async () => {
      if (this.dirty) throw new Error("수정한 단계별 입력을 먼저 MD로 저장해 주세요.");
      const data = await this.request("approve", { plan: this.el("plan").textContent });
      this.planDirty = false;
      this.apply(data);
      this.message("계획 승인 완료 · 4 Construction 선택 후 7 RUN NOW으로 실행할 수 있습니다.");
    });
    this.el("run").onclick = () => this.run();
    this.el("ask").onclick = () => this.ask();
    this.el("chat-close").onclick = () => this.el("chat-dialog").close();
    this.el("chat-form").onsubmit = event => { event.preventDefault(); this.sendSideQuestion(); };
    this.el("stop").onclick = () => this.stop();
    this.el("preview").onclick = () => this.preview();
    this.el("revert-confirm").onclick = () => this.perform(async () => {
      const result = await this.request("revert", { token: this.previewToken });
      this.previewToken = "";
      this.el("revert").hidden = true;
      this.message(`${result.restored}개 파일 복귀 완료 · 복귀 전 백업: ${result.backup}`);
      this.options.log("REVERT", `${result.restored} files · backup ${result.backup}`);
      await this.refresh();
    });
    document.querySelector("#workflow-open").onclick = () => this.open(this.stage);
    document.querySelector("#workflow-emergency").onclick = () => this.stop();
    this.refresh();
  }
  get dirty() { return this.dirtyStages.size > 0; }
  renderFields() {
    const schema = this.data.schema?.[this.stage];
    const guide = PHASE_GUIDANCE[this.stage];
    if (guide && this.renderedStage !== this.stage) {
      this.el("guide-question").textContent = guide.question;
      this.el("guide-inputs").replaceChildren(...guide.inputs.map(text => {
        const item = document.createElement("li"); item.textContent = text; return item;
      }));
      this.el("guide-result").textContent = guide.result;
      this.el("sample-text").textContent = guide.sample;
      this.el("brief").placeholder = guide.template;
      this.el("sample").open = true;
      this.renderedStage = this.stage;
    }
    if (!this.composing) this.el("brief").value = this.drafts[this.stage]?.brief || "";
    this.el("brief").disabled = this.pending || !schema;
    this.el("brief").setAttribute("aria-label", `${WORKFLOW_KEYS.find(([key]) => key === this.stage)?.[2] || this.stage} · 내 프로젝트 입력`);
    this.dialog.setAttribute("aria-label", `${this.stage} 입력`);
  }
  compatibleFields(stage, fields) {
    const schema = this.data.schema?.[stage];
    if (!fields || !("brief" in fields) || schema?.fields.some(f => f.key === "brief")) return fields;
    if (fields.brief.length > 3000) throw new Error("현재 서버는 3,000자까지 지원합니다. 긴 입력은 8766 주소에서 저장해 주세요.");
    return {...Object.fromEntries(schema.fields.map(f => [f.key, ""])), [stage === "ideation" ? "goal" : "instruction"]: fields.brief, ...(fields.decision ? {decision: fields.decision} : {})};
  }
  async request(action, payload) {
    if (action === "configure" && payload?.stage) payload = {...payload, fields: this.compatibleFields(payload.stage, payload.fields)};
    if (action === "ask" && payload?.drafts) payload = {...payload, drafts: Object.fromEntries(Object.entries(payload.drafts).map(([stage, fields]) => [stage, this.compatibleFields(stage, fields)]))};
    const response = await fetch(`/api/workflow${action ? `/${action}` : ""}`, {
      method: action ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-Simulator-Token": this.options.getToken() || "" },
      ...(action ? { body: JSON.stringify(payload || {}) } : {}),
      signal: AbortSignal.timeout(20000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "워크플로 연결을 확인해 주세요.");
    return result;
  }
  message(text, error = false) {
    this.el("status").textContent = text;
    this.el("status").classList.toggle("error", error);
    this.options.status(text, error ? "error" : "");
  }
  async perform(fn) {
    if (this.pending) return;
    if (this.autosaveJob) await this.autosaveJob;
    this.pending = true; this.render();
    try { await fn(); }
    catch (error) { this.message(error.message, true); }
    finally { this.pending = false; this.render(); this.options.onChange?.(); }
  }
  apply(data) {
    const previous = this.data;
    this.data = data;
    for (const stage of Object.keys(data.schema || {})) {
      if (!this.dirtyStages.has(stage)) this.drafts[stage] = phaseDraft(data.schema[stage], data.inputs?.[stage]);
    }
    if (!this.planDirty && data.plan !== previous.plan) this.el("plan").textContent = data.plan || "";
    this.el("autonomy").value = String(data.autonomy);
    if (previous.running && !data.running) {
      const text = data.cancelled ? "AI 실행을 중단했습니다. 파일은 자동으로 되돌리지 않습니다."
        : data.error || data.humanGate || `${data.stage.toUpperCase()} ${data.questionOnly ? "질문 생성 완료" : "완료"}${data.awaitingApproval ? " · 설계 화면에서 계획 승인 후 4 Construction → 7 RUN NOW" : ""}`;
      this.el("results-panel").open = true;
      this.message(text, Boolean(data.error));
      this.options.log(data.error ? "ERR" : "FLOW", text);
      if (data.stage === "inception" && !data.questionOnly) { this.planDirty = false; this.el("plan").textContent = data.plan || ""; }
    }
    // Keep the phase being edited stable while automatic work advances.
    if (previous.running && !data.running && !data.error && !data.cancelled && [1, 2].includes(data.autonomy) && !data.question && !data.questionOnly) {
      const next = WORKFLOW_KEYS.slice(0, 5).findIndex(([key]) => key === data.stage) + 1;
      if (next > 0 && next < 5) { if (data.autonomy === 2 && !this.dirty) this.stage = WORKFLOW_KEYS[next][0]; this.message(`완료 · 다음 단계는 ${WORKFLOW_KEYS[next][1]}입니다. 입력을 확인하고 7 RUN NOW을 누르세요.`); }
    }
    this.render();
    this.options.onChange?.();
  }
  render() {
    this.renderSideQuestion();
    const entry = WORKFLOW_KEYS.find(([key]) => key.replace("_workflow", "") === this.stage) || WORKFLOW_STOP;
    const index = WORKFLOW_KEYS.indexOf(entry);
    this.el("title").textContent = entry[1];
    this.el("input-heading").textContent = `${index + 1}. ${entry[1]} · ${entry[2]}`;
    const busy = this.data.running || this.pending;
    this.renderFields();
    for (const id of ["save", "autonomy", "plan"]) this.el(id).disabled = busy;
    this.el("save").disabled = this.pending || !this.data.schema?.[this.stage];
    this.el("save").textContent = this.saveError ? "저장 재시도" : this.autosaveJob ? "저장 중…" : this.autoDirtyStages.size ? (this.data.running ? "실행 후 자동 저장" : "저장 대기…") : this.savedStages.has(this.stage) && !this.dirtyStages.has(this.stage) ? "저장됨" : "저장";
    this.el("gate").hidden = !["inception", "construction"].includes(this.stage) || !this.data.plan;
    this.el("approve").disabled = busy || this.dirty || !this.el("plan").textContent.trim();
    this.el("approval").textContent = this.data.autonomy >= 4 ? `${AUTONOMY[this.data.autonomy]} · AI가 계획 승인 후 구현` : this.data.approved && !this.planDirty && !this.dirty ? "✓ 승인됨 · 1회 BUILD" : "승인 대기";
    this.el("run").textContent = "7 RUN NOW";
    this.el("ask").disabled = false;
    this.el("run").disabled = busy || !this.data.schema?.[this.stage] || this.stage === "stop_revert";
    this.el("preview").disabled = busy || !this.data.checkpoint;
    this.el("revert-confirm").disabled = busy || !this.previewToken;
    this.el("result").textContent = this.data.running && this.data.stage === this.stage ? "프로젝트를 확인하며 작업 중입니다…" : (this.data.questionOnly && this.data.stage === this.stage ? this.data.questionResults?.[this.stage] : this.data.results[this.stage]) || entry[3];
    this.el("stop").hidden = !this.data.running;
    this.el("events").textContent = (this.data.events || []).join("\n");
    Array.from(this.el("steps").children).forEach((button, i) => {
      button.classList.toggle("selected", i === index);
      button.setAttribute("aria-current", i === index ? "step" : "false");
    });
    document.querySelector("#autonomy-hint").textContent = `${this.data.autonomy} · ${AUTONOMY_HINTS[this.data.autonomy]}`;
  }
  open(action) {
    this.el("review-dialog").close();
    if (this.stage !== action.replace("_workflow", "")) this.el("results-panel").open = false;
    this.stage = action.replace("_workflow", "");
    this.render();
    if (!this.dialog.open) this.dialog.showModal();
    this.el("brief").focus();
    this.options.onChange?.();
  }
  async stopBeforeSave() {
    if (!this.data.running) return;
    await this.request("stop");
    for (let i = 0; i < 40; i++) {
      const data = await this.request("");
      if (!data.running) { this.apply(data); return; }
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    throw new Error("중단 처리 중입니다. 초안은 유지됩니다. 잠시 후 MD 저장을 눌러 주세요.");
  }
  scheduleAutoSave() {
    clearTimeout(this.autosaveTimer);
    if (!this.composing) this.autosaveTimer = setTimeout(() => this.flushAutoSave(), 400);
  }
  async closeInput() {
    clearTimeout(this.autosaveTimer);
    await this.flushAutoSave();
    this.dialog.close();
  }
  async flushAutoSave() {
    clearTimeout(this.autosaveTimer);
    if (this.autosaveJob) { await this.autosaveJob; return; }
    if (this.pending || this.data.running || this.composing || !this.autoDirtyStages.size) return;
    this.autosaveJob = (async () => {
      while (this.autoDirtyStages.size && !this.pending && !this.data.running) {
        const stage = this.autoDirtyStages.values().next().value;
        const fields = {...this.drafts[stage]}, serialized = JSON.stringify(fields);
        this.saveRevision++;
        try {
          const result = await this.request("configure", {stage, fields, autonomy: this.data.autonomy});
          if (JSON.stringify(this.drafts[stage]) === serialized) {
            this.autoDirtyStages.delete(stage); this.dirtyStages.delete(stage);
          }
          this.apply(result); this.saveError = false; this.savedStages.add(stage);
          this.options.status(`${stage.toUpperCase()} 자동 저장 완료`, "success");
        } catch (error) {
          this.saveError = true; this.message(`자동 저장 실패 · 입력은 유지됩니다. ${error.message}`, true);
          break;
        }
      }
    })();
    this.render();
    try { await this.autosaveJob; }
    finally { this.autosaveJob = null; this.render(); }
  }
  async save() {
    this.autoDirtyStages.add(this.stage); this.saveError = false;
    await this.flushAutoSave();
  }
  async setAutonomy(value) {
    if (this.data.running || this.pending) { this.message("STOP으로 중단한 뒤 자율성을 조절해 주세요.", true); this.render(); return; }
    return this.perform(async () => {
      this.apply(await this.request("configure", { requirements: this.data.requirements || "", autonomy: value }));
      this.message(`자율성 ${value} · ${AUTONOMY_HINTS[value]}`);
      this.options.log("KNOB", `AUTONOMY ${value} ${AUTONOMY[value]}`);
    });
  }
  async saveDrafts() {
    for (const stage of Array.from(this.dirtyStages)) {
      const result = await this.request("configure", { stage, fields: this.drafts[stage] || {}, autonomy: this.data.autonomy });
      this.dirtyStages.delete(stage);
      this.autoDirtyStages.delete(stage); this.savedStages.add(stage); this.saveRevision++;
      if (["initialization", "ideation", "inception"].includes(stage)) this.planDirty = false;
      this.apply(result);
    }
  }
  ask() {
    this.renderSideQuestion();
    if (!this.el("chat-dialog").open) this.el("chat-dialog").showModal();
    this.el("chat-question").focus();
  }
  renderSideQuestion() {
    const chat = this.data.sideQuestion || {messages: []};
    const key = JSON.stringify(chat.messages || []);
    if (key !== this.chatRendered) {
      this.chatRendered = key;
      this.el("chat-messages").replaceChildren(...(chat.messages || []).map(message => {
        const article = document.createElement("article"), label = document.createElement("strong"), body = document.createElement("p");
        label.textContent = message.role === "user" ? "나의 질문" : "AI 답변";
        body.textContent = message.content; article.append(label, body); return article;
      }));
      this.el("chat-messages").scrollTop = this.el("chat-messages").scrollHeight;
    }
    this.el("chat-send").disabled = Boolean(this.chatPending || chat.running);
    this.el("chat-status").textContent = this.chatError || chat.error || (chat.running || this.chatPending ? "답변을 작성하고 있습니다…" : "질문과 답변은 MD에 저장되지 않습니다.");
  }
  async sendSideQuestion() {
    if (this.chatPending || this.data.sideQuestion?.running) return;
    const question = this.el("chat-question").value.trim();
    if (!question) { this.el("chat-question").focus(); return; }
    this.chatPending = true; this.chatError = ""; this.renderSideQuestion();
    try {
      const data = await this.request("ask", {question});
      this.data.sideQuestion = data.sideQuestion;
      if (this.el("chat-question").value.trim() === question) this.el("chat-question").value = "";
    } catch (error) { this.chatError = error.message; }
    finally { this.chatPending = false; this.renderSideQuestion(); }
  }
  async run() {
    const stage = this.stage;
    this.openReview();
    return this.perform(async () => {
      await this.saveDrafts();
      this.apply(await this.request("start", { stage }));
      this.previewToken = ""; this.el("revert").hidden = true;
      this.message(`${this.stage.toUpperCase()} 실행 중 · STOP으로 언제든 중단할 수 있습니다.`);
      this.options.log("FLOW", `${this.stage.toUpperCase()} 시작`);
    });
  }
  openReview() {
    // ASK / RUN show questions, progress, approvals and results, not the editor.
    // Keep drafts and pending autosaves intact when switching the visible dialog.
    this.dialog.close();
    this.render();
    this.el("results-panel").open = true;
    if (!this.el("review-dialog").open) this.el("review-dialog").showModal();
    this.options.onChange?.();
  }
  async trigger(action) {
    if (action === "ask_workflow") return this.ask();
    if (action === "start_workflow") return this.run();
    this.open(action);
    if (action === "stop_revert") return this.stop();
    if (action === "operation" && this.data.checkpoint) {
      try {
        const review = await this.request("preview");
        this.el("review-diff").textContent = review.diff || "안전지점 대비 변경사항이 없습니다.";
        this.el("review").hidden = false;
      } catch (error) { this.message(error.message, true); }
    }
    // Open the stage for its own inputs; execution is an explicit next step.
  }
  async stop() {
    // Independent of pending requests and serial connectivity: emergency control stays usable.
    try {
      this.apply(await this.request("stop"));
      this.message("중단 요청 전달 완료 · 이 앱이 실행한 AI와 웹 터미널을 종료합니다.");
      this.options.log("STOP", "사용자 중단 요청");
    } catch (error) { this.message(`중단을 확인하지 못했습니다: ${error.message}`, true); }
  }
  async preview() {
    this.stage = "stop_revert"; this.render();
    this.el("review-dialog").showModal();
    this.el("results-panel").open = true;
    return this.perform(async () => {
      const result = await this.request("preview");
      this.previewToken = result.changes.length ? result.token : "";
      this.el("changes").replaceChildren(...result.changes.map(change => {
        const li = document.createElement("li"); li.textContent = `${change.kind} · ${change.path}`; return li;
      }));
      this.el("diff").textContent = result.diff || "되돌릴 변경사항이 없습니다.";
      this.el("revert").hidden = false;
      this.message(`안전지점: ${result.checkpoint} · 제외 폴더: ${result.excluded.join(", ")}`);
    });
  }
  async refresh() {
    clearTimeout(this.timer);
    try {
      if (this.options.getToken() && !this.pending && !this.autosaveJob) {
        const revision = this.saveRevision, data = await this.request("");
        if (revision === this.saveRevision && !this.autosaveJob) this.apply(data);
        this.initialized = true;
        if (!data.running && this.autoDirtyStages.size && !this.saveError) this.scheduleAutoSave();
      }
    } catch (error) {
      if (this.dialog.open) this.message(`상태 확인 실패: ${error.message}`, true);
    } finally { this.timer = setTimeout(() => this.refresh(), 1000); }
  }
}
