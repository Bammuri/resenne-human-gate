# Construction Unit — approval-gate (allow/deny PreToolUse 게이트 코드 통합)

> **AI-DLC 단계:** CONSTRUCTION / Functional + NFR Design (unit = `approval-gate`).
> **선행 결정 반영:** requirements FR-3(사람 입력을 실제 Claude 대기 요청에 전달), application-design D2(입력 매핑을 설정으로 분리), 계획서 §0.7(창의성 근거=게이트 코드·정직 가드), audit.md의 결정 사슬(임포트 **보류(B)** → 팀 override **옵션 C** → 배선범위 **A**).
> **정직 경계(불변):** PTY 키응답 경로 = 제출 유일 **완전 E2E 검증** 경로. 이 유닛의 allow/deny 게이트는 **코드 통합 + 단위검증 + SW E2E**(진짜 `hook_bridge.py` 프로세스 ↔ 브로커 ↔ 브라우저(웹) resolver — subprocess 테스트 3개 + 실서버 curl 스모크로 검증)까지 완료. **브라우저 승인 패널(`/gate.html`)에서 사람이 대기 중 도구 실행에 allow/deny를 제출할 수 있음(검증됨).** 남은 것 = 실행 중인 진짜 `claude`가 그 stdout 결정을 존중하는 **라이브 링크(사람/라이브 데모 몫)**. 이 라이브 링크 전까지 "게이트가 (완전히·실제 실행까지) 동작한다"는 완성 시제 금지.

## INTENT (이 유닛이 푸는 것)

기존 제출 경로(사람 입력 → `/api/press` → `terminal.send_choice()` → 앱소유 Claude PTY 키바이트)는 "승인 메뉴에서 키를 대신 눌러 주는" 경로다. 이와 **별개로**, Claude Code의 `PreToolUse` 훅을 이용해 **지정 도구 실행을 사람이 결정할 때까지 정지**시키고 `allow`/`deny`를 반환하는 **대안 승인 메커니즘의 코드를 제출 저장소에 실재화**한다. 목적 = 창의성(구조적 차별점 "실행 촉발 → 이미 제안된 실행의 승인·거절")을 **주장이 아니라 제출 repo 안의 코드 + 단위테스트로** 증명.

## CONTEXT (제약·자문)

- 두 계보: 제출 repo(PTY 키응답) / PoC repo `arduino-simulator`(승인 브로커 + `hook_bridge.py`, 팀 실기기 E2E 검증됨).
- 무하드웨어·무-대화형-Claude 제약 → 이 에이전트는 **SW 단위검증까지만** 가능. 실기기 훅→브로커→버튼 allow/deny가 진짜 도구 실행을 막는 **E2E는 사람 몫**.
- gpt-6-astra(low) 자문 3회:
  1. 임포트 여부 → 처음 **보류(B)**. 이후 **팀이 override**해 **옵션 C**(이식하되 "코드 통합·단위검증, E2E 미검증" 라벨)로 확정.
  2. 배선 범위 → **A 확정**: 브로커 + `hook_bridge.py` + 단위테스트만 이식. `terminal.py`의 기본 Claude 실행경로는 **건드리지 않음**(검증된 PTY 데모 회귀 방지). 게이트 활성화 = **별도 예시 settings + README 절차**(사람이 켜고 E2E 재검증). 프로젝트 `.claude/settings.json`에는 **등록하지 않음**(개발용 세션이 안 뜬 브로커에 롱폴하다 마비되는 것 방지).
  3. "HTML로 게이트 동작을 검증할 수 있다"는 팀 지적 → **Q1=C 확정**: 승인 패널을 **별도 페이지 `/gate.html` + 외부 `gate.js`** 로 추가(기존 `index.html`/`app.js`·PTY 데모와 격리해 회귀위험 0). **Q2=N**: 중첩 `claude` 세션으로 "실제 실행 존중"을 이 에이전트가 시도하지 않음(인증·행오버·자가승인 리스크 > 마감 전 실익) → 라이브 데모 몫. **Q3**: 패널 검증 후 "브라우저에서 게이트 요청에 승인·거절을 제출할 수 있다"만 현재형 허용, "claude 결정 준수는 라이브 미검증·PTY만 완전 E2E"를 병기.

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

### 4) `gate.html` + `gate.js` — 브라우저 승인 패널 (astra Q1=C, 격리 페이지)
- **별도 페이지**로 추가 — 기존 `index.html`/`app.js`·PTY 데모를 건드리지 않는다. `server.py`의 `ASSETS`에 `/gate.html`·`/gate.js`만 additive 등록.
- `gate.js`: `/api/session`에서 **ui 토큰**(앱 페이지가 이미 받는 것과 동일)을 받아, `GET /api/approval`(대기목록 폴링) + `POST /api/approval/resolve`(허용/거부)만 호출. `/api/press`·`/api/terminal`은 **호출하지 않음**(격리 보장, 테스트로 강제).
- CSP 불변: `gate.js`는 **동일 출처 파일**(script-src `'self'`), 인라인 스크립트 없음. 스타일만 인라인(style-src `'unsafe-inline'` 허용 범위).
- 테스트 가능하도록 순수 계층 분리: `describePending`(순수), `GateApi`(fetch 주입), `initGatePanel(doc, api)`(DOM은 `document`/`api` 주입) — 브라우저 부트스트랩은 `typeof document !== "undefined"` 가드.

## VERIFY (단위 + SW E2E — 이 에이전트가 수행)

- 브로커 단위테스트(`tests/test_approval.py`, 기존 `test_server.py`와 격리): 중복제거(같은 tool_use_id) · 원자 resolve + 2차 resolve 충돌(409) · 동시 resolve를 대기 중 wait가 수신 · 미지 approval→ask · 세션 종료가 그 세션 pending 만료 · `summarize_tool` 요약·240자 컷 · `/api/approval`는 ui|device 요구(hook 403) · `/api/approval/wait`는 hook 요구+payload 검증 · **hook 토큰은 resolve 불가(403), ui가 resolve** · device 토큰 resolve 가능 · resolve 나쁜입력 400 · 세션 생명주기.
- **SW E2E (subprocess, 신규 3개):** 진짜 `hooks/hook_bridge.py` 프로세스를 Claude Code PreToolUse 훅처럼 stdin(PreToolUse JSON)+env(`BUTTONLAB_*`)로 구동, **브라우저와 동일한 ui 토큰**을 쥔 웹 resolver가 HTTP로 결정 → 훅 stdout의 `permissionDecision` 계약을 검증: **allow / deny / (env 없음→fail-safe ask)** 전부 통과.
- **브라우저 패널(신규):** `gate.js` JS 테스트(`tests/gate.test.js`, node --test) — `describePending` 순수, `GateApi` connect/list/resolve(+409), `initGatePanel` 렌더·버튼 배선(가짜 DOM). 서버 테스트(`test_server.py`) — `/gate.html`·`/gate.js`가 동일 strict CSP로 서빙되고 `/api/press`·`/api/terminal`를 호출하지 않음(격리 강제).
- **실서버 curl 스모크(수동, 재현 스크립트 보존):** 실제 `python3 server.py --mock --show-gate-token`에 대해 asset 200 → 훅 롱폴이 pending 생성 → **브라우저(ui 토큰)가 pending 조회 → 사람이 APPROVE → 훅이 `{decision: allow}` 수신**, hook 토큰 자가 resolve = 403. 게이트의 SW 체인이 실제 엔트리포인트에서 동작함을 확인.
- 회귀: **총 68개 통과 — 49 Python + 19 JS**(2026-09-09 재측정). 기존 45개 전부 유지 + 게이트 브로커/서브프로세스(Python) + 패널(JS·서버) 신규.
- **미검증(사람/라이브 몫):** 실행 중인 진짜 `claude`가 훅 stdout 결정을 존중해 **실제 도구 실행을 allow/deny** 하는 라이브 링크. 팀 실기기 PoC에선 통과했으나 제출버전 라이브 재확인은 사람이 수행 — PTY 키응답이 제출 유일 **완전** E2E 경로.

## REVIEW (정직 가드)

- PTY 키응답 = 제출 유일 **완전 E2E 검증** 경로 — 흐리거나 깨지 않음. 브라우저 패널은 별도 페이지라 이 경로에 무영향(격리 테스트로 강제).
- 게이트 = **코드 통합 + 단위검증 + SW E2E(subprocess·live-curl) 완료**. 허용 현재형: "브라우저(`/gate.html`)에서 사람이 대기 중 도구 실행에 allow/deny를 제출할 수 있다". **금지 현재형**: "게이트가 실제 `claude` 실행을 (완전히) 승인·거절한다" — 이 라이브 링크는 미검증(사람/라이브 데모 몫)이며 반드시 "PTY만 완전 E2E"를 병기.
- 보안 회귀 없음: localhost 가드·`compare_digest`·Origin·CSP(script-src `'self'`, unsafe-inline 없음)·`X-Frame-Options: DENY` 유지, hook 자가승인 차단(패널은 ui 토큰), 시크릿은 환경변수, `gate.js`는 외부 URL·PTY/터미널 경로 미참조(테스트 강제).
