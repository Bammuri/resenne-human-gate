# GPT arsta mid 자문 기록 (Application Design)

> 사용자 지시("애매한건 정리해서 GPT arsta mid에게 물어보고 자동진행해")에 따라, Application Design 단계의 3가지 애매한 결정을 설치된 GPT(Codex CLI `codex exec -s read-only -c model_reasoning_effort=medium`, `gpt-5.6-luna`)에게 자문했습니다.

- **일시**: 2026-09-08
- **자문 프롬프트**: `$CLAUDE_JOB_DIR/tmp/consult_pbt_prompt.md` (요지: Q1 PBT 의존성 전략, Q2 YES/NO fast-path 키 시퀀스, Q3 Claude 상태 소스)

## 자문 응답 (원문)
- **Q1: A** — Use the committed PBT frameworks as test-only dev dependencies; runtime remains dependency-free.
- **Q2: C** — Centralized configurable mappings allow empirical correction without changing control logic.
- **Q3: A** — Hooks provide explicit lifecycle signals; use transcript tailing only as a resilient fallback.

## AI 확정 (자문 반영 → application-design.md §0)
- **D1 (Q1=A)**: fast-check(npm devDep) + Hypothesis(pip --user)를 **테스트 전용** 의존성으로 설치. 런타임은 zero-dep 유지. `node_modules`는 gitignore, 설치 절차는 build-and-test에 문서화.
- **D2 (Q2=C)**: `ACTION_KEYS` 테이블을 단일 소스로 두고 기본값 `YES=Enter(\r)`, `NO=Esc(\x1b)`. 속성 테스트는 매핑의 **전역성/일관성**만 검증(리터럴 바이트는 하드웨어 스모크 후 테이블만 수정해 교정).
- **D3 (Q3=A)**: Hooks(Notification=waiting, Stop/SubagentStop=idle, UserPromptSubmit/PostToolUse=active)가 상태 파일에 기록 → 호스트가 tail. `.jsonl` transcript는 stale/부재 시 fallback. 훅은 자동 응답하지 않음(human-in-the-loop 유지; PermissionRequest 자동승인은 검토 후 기각).

## 근거 연구 (background agent a7d060cf46ba643ae)
- `Notification` 훅(matcher `permission_prompt`)이 승인 대기 시 발화, `Stop` 훅이 턴 종료 시 발화. stdin JSON에 `session_id`, `transcript_path`, `notification_type` 포함.
- 권한 프롬프트는 화살표 메뉴(↑/↓ + Enter). 숫자키(1/2/3)·y/n은 신뢰 불가 → 화살표+Enter, Esc=decline/interrupt.
- transcript `~/.claude/projects/**/<session>.jsonl`은 스키마 불안정 → fallback 전용.
