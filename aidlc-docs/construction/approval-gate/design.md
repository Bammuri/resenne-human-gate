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
- 회귀(증분1 시점): **총 68개 통과 — 49 Python + 19 JS**(2026-09-09). 기존 45개 전부 유지 + 게이트 브로커/서브프로세스(Python) + 패널(JS·서버) 신규. → **증분2(아래) 후 77개**.
- **미검증(사람/라이브 몫):** 실행 중인 진짜 `claude`가 훅 stdout 결정을 존중해 **실제 도구 실행을 allow/deny** 하는 라이브 링크. 팀 실기기 PoC에선 통과했으나 제출버전 라이브 재확인은 사람이 수행 — PTY 키응답이 제출 유일 **완전** E2E 경로.

## REVIEW (정직 가드)

- PTY 키응답 = 제출 유일 **완전 E2E 검증** 경로 — 흐리거나 깨지 않음. 브라우저 패널은 별도 페이지라 이 경로에 무영향(격리 테스트로 강제).
- 게이트 = **코드 통합 + 단위검증 + SW E2E(subprocess·live-curl) 완료**. 허용 현재형: "브라우저(`/gate.html`)에서 사람이 대기 중 도구 실행에 allow/deny를 제출할 수 있다". **금지 현재형**: "게이트가 실제 `claude` 실행을 (완전히) 승인·거절한다" — 이 라이브 링크는 미검증(사람/라이브 데모 몫)이며 반드시 "PTY만 완전 E2E"를 병기.
- 보안 회귀 없음: localhost 가드·`compare_digest`·Origin·CSP(script-src `'self'`, unsafe-inline 없음)·`X-Frame-Options: DENY` 유지, hook 자가승인 차단(패널은 ui 토큰), 시크릿은 환경변수, `gate.js`는 외부 URL·PTY/터미널 경로 미참조(테스트 강제).

---

# 증분 2 (2026-09-09) — 결정 감사 로그 + 최근 결정 뷰

> **AI-DLC 단계:** CONSTRUCTION / 같은 유닛(`approval-gate`)의 두 번째 증분. 검증된 게이트 위에 얹는 additive 변경.
> **선행 결정:** aidlc-state 확장설정 **RESILIENCY-05(structured logging) = enforced NFR**가 준수 근거. gpt-6-astra(low) 자문이 후보 A/B/C/D 중 **B(최소 영속 결정 로그 + 최근 결정 뷰)**로 확정(범위확대·과대주장 경계).

## INTENT (이 증분이 푸는 것)

`resolve_approval`은 지금까지 in-memory 상태만 pending→allow/deny로 뒤집을 뿐, **누가(어느 토큰 역할) 언제 무슨 결정을 내렸는지 어떤 흔적도 남기지 않는다.** 결정 이력을 조회할 엔드포인트도 없다. 이 증분은 **성공적으로 처리된(resolved) 결정만** 영속 감사 로그에 남기고, ui/device 토큰으로 읽는 **최근 결정 뷰**를 패널에 추가한다. 목적 = (1) 결정이 흔적 없이 사라지는 실제 갭 해소, (2) enforced NFR RESILIENCY-05 준수(범위확대 아님), (3) 유지보수·보안 + 완성도/사용성 보강. **결정이 '제출됐다'는 사실만 기록** → 라이브-claude 주장과 무관해 정직.

## CONTEXT (제약·자문)

- gpt-6-astra(low) 판정: **B를 택하되 '최소 영속 결정 로그 + 최근 결정 표시'로 고정**(A/C/D와 묶지 않음). 근거·정직 시제·닫아야 할 위험을 함께 지시.
- 노출 우려: `summary`(command/path)는 이미 `list_pending`이 localhost ui/device 토큰으로 노출 중이나, **로그에는 summary·전체 tool_input·토큰을 넣지 않는다**(노출면 최소화, astra 지시).
- 무하드웨어·무-대화형-claude 제약 그대로 → **SW E2E까지만** 이 에이전트가 수행.

## DECISIONS (ASK 해소)

| # | 결정 | 근거 |
|---|---|---|
| D-F | **성공 resolve만** 로그. 레코드 = `{id, tool_name, input_hash, decision, role, created_at, resolved_at}` — **summary·전체 tool_input·토큰 제외** | 노출면 최소화. hook 자가승인 차단 모델을 `role`로 보강하되 신원·물리버튼 증명은 아님 (astra) |
| D-G | 저장 = **정적 웹루트 밖 + gitignore된 로컬 파일**(`.claude/approval-log.jsonl`), **mode 0600**, `deque(maxlen=500)` + 파일 크기 상한(초과 시 best-effort compaction) | 로그가 소스·웹자산으로 새지 않게, 무한 성장 방지 (astra) |
| D-H | CAS와 로그 기록을 **같은 임계구역**에서. 기록 실패 시 **결정 미전달·성공 미반환**(요청은 pending 유지 → 훅은 fail-safe ask). 성공 resolve당 정확히 1레코드 | "기록된 결정만 전달" — 기록 없는 allow를 절대 내주지 않음 (astra) |
| D-I | 로그 조회 = **ui|device 토큰만**, hook 금지. `role`은 **서버가 인증 결과로** 판정(요청자 자칭 아님) | 조회권한 = 대기목록과 동일 정책. hook이 결정 이력을 자가승인 판단에 못 쓰게 |

## DESIGN (BUILD 대상)

### 5) `server.py` — 결정 감사 로그 (additive)
- 상수: `APPROVAL_LOG_MAX=500`, `APPROVAL_LOG_READ_LIMIT=50`. `import collections`.
- `__init__`: `decision_log=deque(maxlen=MAX)`, `_decision_log_lines`, `decision_log_path = workspace/.claude/approval-log.jsonl`, `_load_decision_log()`(재시작 후 뷰 워밍).
- `resolve_approval(approval_id, decision, resolver_role="ui")` — **기존 2인자 호출 호환**(기본값). CAS 성공 직후, **상태를 뒤집기 전에** `_append_decision_log(entry)` 호출(기록 실패=OSError 전파 → 상태 pending 유지). 그 뒤 status/resolved_at/resolver_role 세팅 + notify.
- `_append_decision_log(entry)`(cv 보유): `os.open(..., O_WRONLY|O_CREAT|O_APPEND, 0o600)`로 JSON 한 줄 append → deque에 캐시. `lines > MAX*2`면 best-effort `_compact_decision_log()`(temp 0600 → `os.replace`).
- `recent_decisions(limit=50)` → 최신순 `{decisions, count}`.
- 라우트: `GET /api/approval/log` — **ui|device 토큰**(hook 403). `Handler.resolver_role()`(compare_digest device→"device" else "ui"). `handle_approval_resolve`는 `resolver_role()` 전달 + `OSError`→**500**("결정을 기록하지 못해 승인을 전달하지 않았습니다.").
- **불변:** `terminal.py`·프로젝트 `.claude/settings.json`·CSP·hook 토큰 권한. `.gitignore`에 `approval-log.jsonl`(+`.tmp`) 추가.

### 6) `gate.js` + `gate.html` — 최근 결정 뷰 (additive)
- 순수 `describeDecision(entry)`(tool·verdict·role·time·hash; **tool_input 없음**). `GateApi.listLog()` → `GET /api/approval/log`. `initGatePanel`에 `renderLog`/`pollLog`(둘 다 `#gate-log` 요소 + `api.listLog` 존재 시에만 동작 — 기존 pending 테스트 무영향). 부트스트랩 폴링 루프에 `pollLog` 합류. `gate.html`에 `#gate-log`/`#gate-log-empty` 섹션 + 정직 문구(role=자격증명 역할, 신원·물리버튼·실행결과 증명 아님).

## VERIFY (단위 + SW E2E — 이 에이전트가 수행)

- 브로커 단위테스트(신규 5, `tests/test_approval.py`): resolve가 **resolver_role과 함께 기록**(ui/device) + 레코드 키가 **안전집합과 정확히 일치**(summary·tool_input·토큰 없음) · `/api/approval/log`는 **ui|device만**(hook 403) · **중복 resolve는 정확히 1회만 로그**(409는 미기록) · 로그 파일 **0600 + 재시작 후 `_load`로 뷰 복원** · **로그 기록 실패 시 500 + 결정 미전달(요청 pending 유지, 로그 0)**.
- 패널 JS(신규 4, `tests/gate.test.js`): `describeDecision` 순수(allow/deny/결측) · `listLog` 토큰 헤더+반환 · `pollLog` 렌더(deny 행 클래스 구분·empty 숨김) · empty 로그 안내.
- **실서버 curl 스모크(재현 스크립트 보존 `tmp/gate_log_smoke.py`):** 실제 `python3 server.py --mock --show-gate-token`에서 ui가 resolve(200) → **hook 토큰 `/api/approval/log`=403** → ui 조회=200 & 레코드 1건(안전키만) → 디스크 파일 **0600** + 한 줄 기록 확인.
- 회귀: **총 77개 통과 — 54 Python + 23 JS**(2026-09-09). 증분1의 68개 전부 유지 + 결정 로그(Python 5)·최근 결정 뷰(JS 4) 신규.
- **미검증(사람/라이브 몫, 불변):** 실행 중인 진짜 `claude`가 훅 결정을 존중해 실제 도구 실행을 allow/deny 하는 라이브 링크 — PTY 키응답이 유일 **완전** E2E 경로.

## REVIEW (정직 가드)

- **허용 현재형:** "브라우저/버튼에서 제출한 게이트 결정과 resolver 토큰 역할을 영속 기록하고 최근 이력을 조회할 수 있다. 소프트웨어 E2E로 검증했다."
- **금지(과대주장):** 이 로그를 "Claude 실행이 차단됐다는 증거", "사용자 신원 감사", "변조 불가 보안 로그"로 포장 금지. `role=ui/device`는 **사용한 자격증명 역할**이지 특정 사람의 신원·실제 물리버튼 사용 증명이 아니며, 로그는 **도구 실행 결과를 증명하지 않는다**. 이 한 증분만으로 RESILIENCY-05 완전 준수를 선언하지 않는다.
- **보안:** 로그에 summary·tool_input·토큰 미포함, 파일 0600·웹루트 밖·gitignore, 조회=ui|device만(hook 금지), 기록 실패 시 결정 미전달(기록된 결정만 전달). CSP·terminal.py·프로젝트 settings·hook 권한 전부 불변.
