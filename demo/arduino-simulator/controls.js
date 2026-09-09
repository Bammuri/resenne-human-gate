"use strict";

// Read the rendered terminal, not raw ANSI output or historical chat logs.
const TERMINAL_EFFORTS = ["low", "medium", "high", "xhigh"];
function terminalQuestion(lines, generation) {
  const entries = [];
  let fenced = false;
  lines.forEach((line, row) => {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; return; }
    if (fenced) return;
    const match = line.match(/^\s*([❯›>→])?\s*(?:\*\*)?(\d{1,2})[.)](?:\*\*)?\s*(\S.*?)\s*$/);
    if (match) entries.push({ row, selected: Boolean(match[1]), id: match[2], label: match[3].replace(/\*\*/g, "") });
  });
  // Only the last consecutive menu can be current.
  const start = entries.findLastIndex(entry => entry.id === "1");
  const menu = entries.slice(start);
  if (start < 0 || menu.length < 2 || menu.some((entry, i) => Number(entry.id) !== i + 1)) return null;
  const first = menu[0].row, last = menu.at(-1).row;
  const before = lines.slice(Math.max(0, first - 5), first).filter(line => line.trim());
  const after = lines.slice(last + 1).join("\n");
  const prompt = before.slice(-3).join("\n").trim();
  const selected = menu.findIndex(entry => entry.selected);
  if (/space (?:to|for).*(?:select|toggle)|select multiple|복수 선택/i.test(after)) return null;
  const interactive = selected >= 0;
  const cue = /choose|select|pick|which.{0,80}\?|would you|do you|proceed\?|선택|골라|고르|진행할까요|어떻게.*진행|번호.*(?:답|알려)/i;
  if (!interactive && !cue.test(prompt + "\n" + after)) return null;
  // New user input or a new section below the choices makes a prose menu stale.
  if (!interactive && /(?:^|\n)\s*[❯›>]\s*\S|(?:^|\n)\s*(?:사용자:|user:|completed|완료)/i.test(after)) return null;
  if (lines.length - last > 18) return null;
  const options = menu.map(({ id, label }) => ({ id, label }));
  const signature = JSON.stringify([generation, prompt, options]);
  let hash = 2166136261;
  for (let i = 0; i < signature.length; i++) hash = Math.imul(hash ^ signature.charCodeAt(i), 16777619);
  return { id: `terminal-${(hash >>> 0).toString(16)}`, kind: "choice", prompt: prompt || "터미널 선택지",
    options, native: true, interactive, selected };
}
function terminalAnswer(question, choice) {
  const index = question.options.findIndex(option => option.id === String(choice));
  if (index < 0) throw new Error("현재 터미널에 표시된 선택지를 눌러 주세요.");
  if (question.interactive) {
    const delta = index - question.selected;
    return (delta < 0 ? "\x1b[A" : "\x1b[B").repeat(Math.abs(delta)) + "\r";
  }
  return `\x1b[200~${question.options[index].id}\x1b[201~\r`;
}
function terminalMode(lines) {
  const footer = lines.slice(-8).join("\n");
  if (/plan mode\s*(?:on|·|\(|\[)|\bplan\s*·|⏸\s*plan/i.test(footer)) return "plan";
  if (/bypass permissions|accept edits|default mode|shift\+tab to plan|gpt-\S+\s+(?:low|medium|high|xhigh)\s*·/i.test(footer)) return "build";
  return null;
}
function terminalWorking(lines) {
  // Active CLI status hints live near the composer; past prose is not activity.
  return lines.slice(-8).some(line => !/^\s*[❯›>]/.test(line) &&
    /\besc(?:ape)?\s+(?:to\s+)?(?:interrupt|cancel|stop)\b|\bctrl\+c\s+to\s+(?:interrupt|stop)\b/i.test(line));
}

function terminalEffort(lines) {
  const footer = lines.slice(-8).join("\n");
  const match = footer.match(/\b(low|medium|high|xhigh)\s*(?:effort|[·•].*\/effort)|\b(?:gpt-\S+|codex)\s+(low|medium|high|xhigh)\b/i);
  return match ? (match[1] || match[2]).toLowerCase() : null;
}


const KNOB_BINDINGS = {
  browse: { label: "SCROLL", hint: "회전: 출력 스크롤 · 누름: 최신 출력", rotate: "scroll", press: "bottom" },
  plan: { label: "PLAN PAGE", hint: "회전: 계획 페이지 탐색 · 누름: 맨 위", rotate: "pages", press: "top" },
  build: { label: "HISTORY", hint: "회전: 입력 기록 탐색 · 누름: 터미널 포커스", rotate: "history", press: "focus" },
  accept: { label: "SELECT", hint: "회전: 선택 항목 이동 · 누름: 확인", rotate: "select", press: "enter" },
  denied: { label: "EDIT CURSOR", hint: "회전: 입력 커서 좌우 이동 · 누름: 취소", rotate: "cursor", press: "escape" },
  model: { label: "AI EFFORT", hint: "회전: Low / Medium / High / XHigh · 누름: 모델 목록", rotate: "effort", press: "models" },
  check: { label: "CHECK LOG", hint: "회전: 검증 결과 페이지 탐색 · 누름: 최신 출력", rotate: "pages", press: "bottom" },
  stop: { label: "LOG SCROLL", hint: "회전: 중단 전 로그 탐색 · 누름: 최신 출력", rotate: "scroll", press: "bottom" },
};
function knobBinding(mode, action, question) {
  if (question) return { label: "ANSWER PAGE", hint: "회전: 보기 페이지 이동 · 답변은 번호 버튼", rotate: "questions", press: "focus" };
  if (mode === "workflow") return { label: "AUTONOMY", hint: "회전: AI-DLC 자율성 · 누름: 다음 단계", rotate: "autonomy", press: "autonomy" };
  return mode === "agent" ? KNOB_BINDINGS[action] || KNOB_BINDINGS.browse : KNOB_BINDINGS.browse;
}

const DECK_MODES = ["agent", "workflow", "custom"];
const AGENT_KEYS = [
  ["model", "MODEL", "노브 추론 강도 · 다시 누르면 모델 목록"],
  ["plan", "PLAN", "계획 모드 · 변경 전 설계"],
  ["build", "BUILD", "계획 모드를 나와 구현 준비"],
  ["check", "CHECK", "테스트 실행 및 요구사항 검증"],
  ["accept", "ACCEPT", "승인 / 동의"],
  ["denied", "DENIED", "거절하고 다른 대안 요청"],
  ["stop", "STOP", "대상 AI 중단"],
];

// Captures the meaning of a physical slot before transport, so an Arduino echo
// cannot select a newer question or launch an action after a question disappears.
class DeckControls {
  constructor(workflowKeys) {
    this.workflowKeys = workflowKeys;
    this.config = { mode: "agent", custom: Array.from({ length: 7 }, (_, i) => ({
      label: `커스텀 ${i + 1}`, target: "terminal", action: "prompt", text: "",
    })) };
    this.target = "terminal";
    this.knobAction = null;
    this.snapshots = { terminal: {}, current: {}, workflow: {} };
    this.page = 0;
    this.answered = new Set();
    this.selections = new Map();
  }
  configure(config) {
    const before = this.identity();
    if (config.mode !== this.config.mode) this.knobAction = null;
    this.config = { mode: DECK_MODES.includes(config.mode) ? config.mode : "agent", custom: config.custom.map(entry => ({ ...entry })) };
    if (before !== this.identity()) this.page = 0;
  }
  setTarget(target) { if (target !== this.target) { this.target = target; this.page = 0; } }
  get questionTarget() {
    if (this.config.mode === "workflow" && this.snapshots.workflow.question) return "workflow";
    if (this.snapshots[this.target].question) return this.target;
    return this.snapshots.workflow.question ? "workflow" : this.target;
  }
  identity(target = this.questionTarget) {
    const snapshot = this.snapshots[target];
    return JSON.stringify([target, snapshot.generation || "", snapshot.question?.id || ""]);
  }
  update(target, snapshot) {
    const before = this.identity(target);
    this.snapshots[target] = { ...snapshot };
    if (target === this.questionTarget && before !== this.identity(target)) this.page = 0;
    // Generations and question IDs are immutable server identities. A latch
    // survives repeated poll snapshots until that question actually disappears.
    if (before !== this.identity(target)) { this.answered.delete(before); this.selections.delete(before); }
  }
  get question() { return this.snapshots[this.questionTarget].question || null; }
  get waiting() { return this.answered.has(this.identity()); }
  get selected() { return this.selections.get(this.identity()) || new Set(); }
  get pages() { return Math.max(1, Math.ceil((this.question?.options?.length || 0) / 7)); }
  movePage(delta) { this.page = Math.max(0, Math.min(this.pages - 1, this.page + delta)); }
  capture(slot) {
    if (!Number.isInteger(slot) || slot < 1 || slot > 8) return null;
    const base = { slot, mode: this.config.mode, selectedTarget: this.target, context: this.identity(), page: this.page };
    if (slot === 8) return { ...base, action: "mode", label: "MODE" };
    if (this.question) {
      const option = this.question.options[this.page * 7 + slot - 1];
      if (!option || this.waiting) return null;
      return { ...base, action: "answer", target: this.questionTarget, generation: this.snapshots[this.questionTarget].generation,
        questionId: this.question.id, choice: option.id, label: option.label };
    }
    if (this.config.mode === "workflow") {
      const entry = this.workflowKeys[slot - 1];
      return { ...base, action: entry[0], label: entry[1], workflow: true };
    }
    const entry = this.config.mode === "agent"
      ? { action: AGENT_KEYS[slot - 1][0], label: AGENT_KEYS[slot - 1][1], target: this.target }
      : { ...this.config.custom[slot - 1] };
    return { ...base, ...entry, generation: this.snapshots[entry.target].generation };
  }
  captureAnswer(value) {
    if (!this.question || this.waiting) return null;
    return { slot: 0, mode: this.config.mode, selectedTarget: this.target, context: this.identity(), page: this.page,
      action: "answer", target: this.questionTarget, generation: this.snapshots[this.questionTarget].generation,
      questionId: this.question.id, label: "직접 답변", ...value };
  }
  toggleSelection(captured) {
    if (!this.question?.multiSelect || captured?.action !== "answer" || !captured.slot || !this.isCurrent(captured)) return false;
    const selected = new Set(this.selected);
    if (selected.has(captured.choice)) selected.delete(captured.choice); else selected.add(captured.choice);
    this.selections.set(this.identity(), selected); return true;
  }
  isCurrent(captured) {
    if (!captured) return false;
    const current = captured.slot === 0 ? this.captureAnswer(Object.fromEntries(["choice", "text"].filter(key => captured[key] !== undefined).map(key => [key, captured[key]]))) : this.capture(captured.slot);
    return current !== null && JSON.stringify(current) === JSON.stringify(captured);
  }
  markAnswered(captured) {
    if (captured.action === "answer" && captured.context === this.identity(captured.target)) this.answered.add(captured.context);
  }
}

if (typeof module !== "undefined") module.exports = { DeckControls, DECK_MODES, AGENT_KEYS, terminalQuestion, terminalAnswer, terminalMode, terminalEffort, terminalWorking, knobBinding };
