# Construction Unit — approval-gate (allow/deny PreToolUse 게이트 코드 통합)

> **AI-DLC 단계:** CONSTRUCTION / Functional + NFR Design (unit = `approval-gate`).
> **선행 결정 반영:** requirements FR-3(사람 입력을 실제 Claude 대기 요청에 전달), application-design D2(입력 매핑을 설정으로 분리), 계획서 §0.7(창의성 근거=게이트 코드·정직 가드), audit.md의 결정 사슬(임포트 **보류(B)** → 팀 override **옵션 C** → 배선범위 **A**).
> **정직 경계(불변):** PTY 키응답 경로 = 제출 유일 **E2E 검증** 경로. 이 유닛이 추가하는 allow/deny 게이트는 제출버전에서 **코드 통합 + 단위검증까지만**, **E2E는 미검증(사람 몫)**. 현재형 "동작한다" 주장 금지.

## INTENT (이 유닛이 푸는 것)

기존 제출 경로(사람 입력 → `/api/press` → `terminal.send_choice()` → 앱소유 Claude PTY 키바이트)는 "승인 메뉴에서 키를 대신 눌러 주는" 경로다. 이와 **별개로**, Claude Code의 `PreToolUse` 훅을 이용해 **지정 도구 실행을 사람이 결정할 때까지 정지**시키고 `allow`/`deny`를 반환하는 **대안 승인 메커니즘의 코드를 제출 저장소에 실재화**한다. 목적 = 창의성(구조적 차별점 "실행 촉발 → 이미 제안된 실행의 승인·거절")을 **주장이 아니라 제출 repo 안의 코드 + 단위테스트로** 증명.

## CONTEXT (제약·자문)

- 두 계보: 제출 repo(PTY 키응답) / PoC repo `arduino-simulator`(승인 브로커 + `hook_bridge.py`, 팀 실기기 E2E 검증됨).
- 무하드웨어·무-대화형-Claude 제약 → 이 에이전트는 **SW 단위검증까지만** 가능. 실기기 훅→브로커→버튼 allow/deny가 진짜 도구 실행을 막는 **E2E는 사람 몫**.
- gpt-6-astra(low) 자문 2회:
  1. 임포트 여부 → 처음 **보류(B)**. 이후 **팀이 override**해 **옵션 C**(이식하되 "코드 통합·단위검증, E2E 미검증" 라벨)로 확정.
  2. 배선 범위 → **A 확정**: 브로커 + `hook_bridge.py` + 단위테스트만 이식. `terminal.py`의 기본 Claude 실행경로는 **건드리지 않음**(검증된 PTY 데모 회귀 방지). 게이트 활성화 = **별도 예시 settings + README 절차**(사람이 켜고 E2E 재검증). 프로젝트 `.claude/settings.json`에는 **등록하지 않음**(개발용 세션이 안 뜬 브로커에 롱폴하다 마비되는 것 방지).

## DECISIONS (ASK 해소)

| # | 결정 | 근거 |
|---|---|---|
| D-A | 배선 범위 = **A** (브로커+훅+테스트만, terminal.py 불변) | 무하드웨어라 실배선 E2E 검증 불가 → terminal.py 수정은 검증된 PTY 데모 회귀위험만 큼 (astra) |
| D-B | 프로젝트 `.claude/settings.json`에 게이트 훅 **미등록**, 별도 예시 settings로만 배포 | 브로커 미기동 시 개발용 Claude 툴콜마다 80s 롱폴→ask로 개발 마비 (astra Q2=Y) |
| D-C | `self.token`을 **ui_token 별칭**으로 유지 + `hook_token`·`device_token` 신설, **역할별 검사** | 기존 `/api/press`·`/api/state`·`/api/terminal`·45테스트 무변경 + 3역할 권한 분리 |
| D-D | **hook 토큰은 register/wait만**, 조회·resolve 불가 | Claude 에이전트가 Bash로 자기 환경을 읽을 수 있으므로, 자가승인 가능한 훅은 게이트 자체를 무력화 |
| D-E | fail-safe = **ask**(네트워크/파싱 오류), **deny는 오직 HTTP 400/403** | 사람 미개입 시 자동 승인 절대 금지 — Claude 기본 권한 메뉴로 안전 폴백 |

## DESIGN (BUILD 대상)

### 1) `server.py` — 승인 브로커 (additive, PTY 경로 불변)
- 모듈 상수: `APPROVAL_WAIT_SECONDS=80`, `SESSION_TTL_SECONDS=1800`.
- `summarize_tool(tool_name, tool_input)`: 사람이 읽을 짧은 요약(Bash=command, 그 외 file_path/path/url…). 240자 컷.
- `SimulatorServer` 상태: `ui_token`(=기존 `self.token`), `hook_token`, `device_token`; `approvals={}`, `sessions={}`, `approval_cv=threading.Condition()`.
- 메서드(모든 변이는 `approval_cv` 아래 — resolve는 원자 compare-and-set, 롱폴은 즉시 깨움):
  - `create_approval(bridge_id, session_id, tool_use_id, tool_name, tool_input)` — (bridge, tool_use_id) 단위 **중복 제거**(재발화 훅은 같은 레코드에 붙음). `input_hash` 부착. deadline 설정.
  - `wait_for_decision(approval_id)` — allow/deny면 반환, deadline 경과·미지 id·expired면 **ask**.
  - `resolve_approval(approval_id, decision)` — pending일 때만 성공(원자 CAS), 아니면 None(=409/이미 처리).
  - `list_pending()` / `register_session()` / `end_session()`(그 세션의 pending을 expired로) / `_purge(now)`.
- 라우트:
  - `GET /api/approval` — 대기목록. **ui|device 토큰**(hook 불가).
  - `POST /api/approval/wait` — **hook 토큰만**. create→wait(롱폴)→`{approval_id, decision}`.
  - `POST /api/approval/resolve` — **ui|device 토큰**. `{approval_id, decision∈allow/deny}` 검증, 성공 200 / 충돌 409 / 나쁜입력 400.
  - `POST /api/session/register|end` — **hook 토큰만**.
- 공통: `token_ok(*expected)`(compare_digest), `read_json()`(415/400 처리)로 리팩터. 응답은 기존 `DEFAULT_CSP`(script-src `'self'`, unsafe-inline 없음) 그대로 — **CSP 완화 없음**.

### 2) `hooks/hook_bridge.py` — PreToolUse 훅 (이식)
- `PreToolUse`: `/api/approval/wait` 롱폴 → `permissionDecision` allow/deny/ask. `SessionStart/SessionEnd`: `/api/session/{register,end}`.
- 실패=ask, HTTP 400/403만 deny. stdout=JSON only, 진단=stderr, exit 0. 환경변수 `BUTTONLAB_URL`/`BUTTONLAB_HOOK_TOKEN`/`BUTTONLAB_BRIDGE_ID`(시크릿은 settings 파일에 안 남김).

### 3) `hooks/hook-gate.settings.example.json` — 활성화 예시(사람이 사용)
- `claude --settings hooks/hook-gate.settings.example.json`로 게이트를 **옵트인** 활성화. PreToolUse/SessionStart/SessionEnd에 `hook_bridge.py` 등록. 실제 URL·토큰은 **환경변수로 주입**(파일엔 placeholder/주석). 프로젝트 `.claude/settings.json`과 분리.

## VERIFY (단위검증 — 이 에이전트가 수행)

- 신규 브로커 단위테스트(신규 파일 `tests/test_approval.py`, **12개** — 기존 `test_server.py`의 15개 서버 테스트와 격리해 회귀위험 제거): 중복제거(같은 tool_use_id) · 원자 resolve + 2차 resolve 충돌(409) · 동시 resolve를 대기 중 wait가 수신 · 미지 approval→ask · 세션 종료가 그 세션 pending 만료 · `summarize_tool` 요약·240자 컷 · `/api/approval`는 ui|device 요구(hook 403) · `/api/approval/wait`는 hook 요구+payload 검증 · **hook 토큰은 resolve 불가(403), ui가 resolve** E2E-내부 · device 토큰 resolve 가능 · resolve 나쁜입력 400 · 세션 생명주기 hook 토큰.
- 회귀: **기존 45개(33 Python + 12 JS) 전부 유지 + 신규 12개 → 총 57개(45 Python + 12 JS) 통과**(2026-09-09 재측정).
- **미검증(사람 몫, E2E):** 제출버전에서 `claude --settings`로 훅을 켜고 실기기 버튼이 진짜 도구 실행을 allow/deny 하는 흐름. 팀 실기기 PoC에선 통과했으나 **제출버전 재검증은 사람이 수행.**

## REVIEW (정직 가드)

- PTY 키응답 = 제출 유일 **E2E 검증** 경로 — 흐리거나 깨지 않음.
- 게이트 = **코드 통합 + 단위검증 완료 / 제출버전 E2E 미검증**. README·문서는 이 시제로만 기술(현재형 "게이트가 동작한다" 금지).
- 보안 회귀 없음: localhost 가드·`compare_digest`·Origin·CSP(`'self'`)·`X-Frame-Options: DENY` 유지, hook 자가승인 차단, 시크릿은 환경변수.
