# 리센느(Re:senne) — Re:senne HUMAN GATE

> **버튼의 재정의. 명령에서 승인·거절로.**
>
> 실행 앞에, 사람. — 제4회 디디톤 출품작 · 팀 리센느(Re:senne)

Re:senne HUMAN GATE는 AI 하네스의 **대기 중 실행 요청에 사람이 물리 버튼으로 승인·거절을 전달하는
소스 공개 컨트롤러**입니다. 키보드로 작업을 지시하고, 실행 직전의 판단은 전용 버튼으로 분리합니다.
검증된 하네스 예시는 **Claude Code**입니다. 브라우저에서 쉘과 Claude를 실행하는 웹 터미널,
상태 표시, 하드웨어 없이 사용할 수 있는 웹 시뮬레이션도 제공합니다.

카피·포지셔닝 기준은 [`CONCEPT_FINAL.md` §0.5](./CONCEPT_FINAL.md), 전체 실행계획은
[`HACKATHON_EXECUTION_PLAN.md`](./HACKATHON_EXECUTION_PLAN.md), AI-DLC 산출물은
[`aidlc-docs/`](./aidlc-docs/)에 정리했습니다. 영문 카피는 *“Redefining the button. From commands to consent.”*입니다.

## 문제와 해결

AI가 개발 흐름을 바꾸는 동안에도 작업 지시와 실행 승인은 같은 키보드에서 이루어집니다.
Claude Code에 파일 수정과 쉘 명령 실행을 맡기는 개발자는 승인 요청이 나올 때마다 터미널에서 내용을 읽고,
작업에 쓰던 키보드로 승인 메뉴를 선택·확정합니다. 사용자별 일일 발생 횟수는 아직 측정하지 않았습니다.

**HUMAN GATE는 실행 승인·거절을 전용 물리 버튼 두 개로 분리합니다.** 사용 흐름은 다음과 같습니다.

1. 키보드로 AI에 작업을 지시합니다.
2. AI가 실행 승인을 기다리면 요청 내용을 확인합니다. OLED는 `YOUR TURN`으로 사람을 부릅니다.
3. **✓ 승인(D2)** 또는 **✕ 거절(D3)**로 답합니다.

제출 게이트 앱에서 바로 실행되는 경로는 **USB 시리얼 → Python PTY 키응답**입니다.
웹 시뮬레이션도 같은 PTY 키응답 경로를 사용합니다. 위 OLED 문구를 사용하는 루트 UNO R4 WiFi
펌웨어의 Node Bridge(ws:8080) 경로는 **버튼→브리지 왕복까지만 실기기로 확인한 초기·대체 설계**이며,
Node Bridge↔Python(PTY) 어댑터 통합은 남아 있습니다.

매크로패드·스트림덱이 보통 단축키·명령으로 실행을 촉발한다면, HUMAN GATE의 버튼은 **이미 제안된
실행 요청의 승인·거절**에 연결됩니다. `terminal.py`의 `ACTION_KEYS`·`send_choice()`는 승인 대기 중인
요청에만, `request_id`별 최초 1회만 결정을 전달합니다. 다른 하네스와의 연동은 공통 프로토콜과
하네스별 어댑터를 통한 확장 방향입니다.

## 두 가지 실물 구성

### Re:senne HUMAN GATE — 2버튼 승인·거절 게이트

제출 게이트 앱과 **Arduino UNO R4 WiFi + 128×64 SSD1306 OLED + 물리 버튼 2개**로 구성합니다.
버튼은 ✓ 승인 D2 / ✕ 거절 D3입니다. 루트 펌웨어는 `firmware/resenne_uno_r4/`에 있으며,
USB 시리얼 경로와 WiFi 초기·대체 설계의 차이는 아래 하드웨어 절에서 설명합니다.

### DOCKPAD — 8키 AI 컨트롤러

DOCKPAD는 **`demo/arduino-simulator/`에 코드로 구현·커밋된 실물 컨트롤러**입니다.
팀의 다른 구성원이 개발한 별도 앱으로, 루트 HUMAN GATE 게이트 앱과 코드베이스가 분리되어 있습니다.
8버튼(D2–D9), 노브, OLED, 스피커로 구성하며 버튼 1–5는 AI-DLC 5단계, 6은 ASK, 7은 RUN NOW,
8은 MODE에 대응합니다. 노브로 자율성 0–5를 조절합니다.

실제 Codex·Claude CLI를 PTY에서 구동하고, 물리 키로 AI-DLC 5단계(Initialization~Operation)를
승인·진행합니다. 단계별 입력과 AI 결과는 실행 시점에 `aidlc-docs/01-initialization.md`~
`05-operation.md` 런타임 산출물로 저장합니다. 실제 세션에서 생성하므로 저장소에는 포함하지 않습니다.
UNO R4 WiFi 연결은 `board_wifi.py`의 **HTTP 직결로 완결된 구현**이며 별도 브리지가 필요 없습니다.

**소프트웨어 테스트는 가짜 CLI 프로세스를 사용합니다.** 실제 Codex·Claude 응답, 물리 보드와 물리 키를
통한 AI-DLC 단계 제어는 **팀이 실기기로 확인한 사람 검증·시연 결과**이며 자동 테스트가 증명하지 않습니다.
사용법은 [`demo/arduino-simulator/README.md`](./demo/arduino-simulator/README.md)를 참고하십시오.

리센느는 걸그룹 컨셉의 첫 테마 프로파일입니다. 페르소나는 컨셉이며, 팀 사진 키캡은 제작 예정입니다.

## 구현과 검증 범위

| 경로 | 확인한 범위 | 남은 확인·통합 |
|---|---|---|
| 게이트 앱의 PTY 키응답(USB 시리얼 / 웹 시뮬레이션) | 완전 소프트웨어 E2E 검증 경로이며, Claude Code는 팀의 실기기 검증 예시입니다. | 자동 테스트와 실기기 시연의 근거는 구분합니다. |
| 루트 UNO R4 WiFi Node Bridge(ws:8080) | 버튼→브리지 왕복을 실기기로 확인했습니다. | 브리지 서버는 미커밋이며, Node Bridge↔Python(PTY) 어댑터는 통합 전인 초기·대체 설계입니다. |
| PreToolUse allow/deny 게이트 | `server.py`의 `/api/approval*` + `hooks/hook_bridge.py` 코드 통합·단위·소프트웨어 E2E를 완료했습니다. | 실행 중인 진짜 `claude`가 결정을 존중해 실제 도구 실행을 allow/deny 하는 라이브 링크는 미검증이며, 사람/라이브 데모로 확인해야 합니다. |
| DOCKPAD (`demo/arduino-simulator/`) | 코드 구현·커밋 및 가짜 CLI 소프트웨어 테스트를 완료했습니다. 실제 AI 응답·보드·물리 키 단계 제어는 팀이 실기기로 시연했습니다. | 자동 테스트는 실제 Codex·Claude 응답이나 물리 장치의 동작을 증명하지 않습니다. |

allow/deny 게이트는 지정 도구 실행을 승인까지 대기시키고 `allow`/`deny`를 반환하는 승인 브로커입니다.
`tests/test_approval.py`의 단위·서브프로세스 E2E 테스트와 실서버 curl 스모크로 검증했습니다.
진짜 `hook_bridge.py` 프로세스 ↔ 브로커 ↔ 브라우저(ui 토큰) resolver 체인이 소프트웨어 검증 범위입니다.
브라우저 승인 패널 `/gate.html`에서 대기 중 요청에 ✓ 허용 / ✕ 거부를 제출할 수 있습니다.

이 게이트는 **별도 예시 settings로 옵트인 활성화**합니다. 제출 저장소의 `hooks/claude_state_hook.py`는
권한을 결정하지 않는 상태 신호입니다. 설정과 동작은 아래 승인 게이트 활성화·Claude 상태 읽기 절에서 설명합니다.

## 실행 방법

**사전조건**

- macOS 또는 Linux. Windows에서는 WSL에서 서버를 실행합니다.
- Python 3.10 이상. 런타임은 **외부 의존성이 없습니다**(xterm/addon-fit는 `vendor/`에 포함, 프런트는 무설치).
- Claude를 쓰려면 **사용자 본인의 Claude Code CLI 설치와 로그인**이 필요합니다. `claude --version`으로 확인하십시오.
- 실물 USB 보드는 Web Serial을 지원하는 **데스크톱 Chrome**에서 연결합니다. 웹 시뮬레이션에는 USB가 필요 없습니다.

**실행(단일 진입점)**

```bash
python3 server.py                          # http://127.0.0.1:8765
python3 server.py --cwd /path/to/project   # Claude 세션을 이 폴더에서 실행
python3 server.py --port 8766
python3 server.py --mock                   # claude·하드웨어 없이 승인 흐름만 재현(스크립트 스탠드인)
```

서버는 이 컴퓨터의 `127.0.0.1`에서만 접속할 수 있습니다. 웹 터미널 명령과 Claude 세션은 **서버를
실행한 사용자 계정으로 실제 실행**됩니다.

**환경변수·시크릿 (저장소에 실제 값 없음)**

- 로컬 웹 실행에는 별도 환경변수가 필요 없습니다. 승인 API는 `127.0.0.1` 접속으로 제한하고, 세션 토큰은
  `compare_digest`로 검증합니다(Host allowlist·Origin·CSP·`X-Frame-Options: DENY` 가드 포함).
- **HUMAN GATE 게이트 앱의 정본 경로인 USB 시리얼 연결에는 Wi-Fi 설정이 필요 없습니다.** `WIFI_SSID` /
  `WIFI_PASS` / `BRIDGE_HOST`는 루트 `firmware/resenne_uno_r4/`의 **초기·대체 설계인 Node Bridge(ws:8080)
  경로용** 설정이며(브리지 서버는 미커밋), 이때만 펌웨어 상단에서 **로컬로만** 채웁니다. 완결된 UNO R4 WiFi
  경로는 `demo/arduino-simulator/`의 `board_wifi.py` **HTTP 직결**이며, PC 쪽은 보드 IP(+선택 토큰)만
  입력하고 보드 Wi-Fi 자격증명은 로컬 `wifi_credentials.h`(gitignore)·보드 설정 페이지로만 넣습니다.
  저장소에는 어느 경로든 **placeholder만 커밋**하고 자격증명·API 키·로그인 정보는 포함하지 않습니다.

**첫 시나리오**

`python3 server.py` → 브라우저에서 `http://127.0.0.1:8765` 열기 → **Claude 시작** → 요청 입력 →
승인 프롬프트가 뜨면 **웹 시뮬레이션 또는 실물 버튼으로 ✓ 승인 / ✕ 거절** → 화면·OLED에서 결과 확인.

하드웨어나 Claude 설치 없이 흐름만 보려면 `python3 server.py --mock`으로 서버를 띄운 뒤 브라우저에서
**웹 시뮬레이션** 버튼으로 그대로 재현할 수 있습니다(승인·거절은 스크립트 스탠드인 세션에 전달되며 실제
도구는 실행하지 않습니다). 이 경로는 UNO R4 WiFi·Node Bridge 없이 동작합니다. 하드웨어 연결·시뮬레이션
키·검증 절차는 아래 상세 섹션을 참고하십시오.

### 승인 게이트 활성화 (옵트인)

allow/deny 게이트는 **기본 비활성**이며, 프로젝트 `.claude/settings.json`에는 등록하지 않습니다.
브로커가 꺼져 있으면 개발용 세션의 모든 도구 호출이 대기하므로 별도 예시 settings로 옵트인 활성화합니다. 소프트웨어 체인(훅 프로세스 ↔ 브로커 ↔ 브라우저 resolver)은 테스트·curl 스모크로
검증했고, **실행 중인 진짜 `claude`가 그 결정을 존중하는지의 라이브 확인은 사람이 수행**합니다.

```bash
python3 server.py --show-gate-token     # 브로커 기동 + hook 토큰을 콘솔에 출력
# 다른 터미널에서, Claude 세션을 게이트 settings로 실행:
BUTTONLAB_URL=http://127.0.0.1:8765 \
BUTTONLAB_HOOK_TOKEN=<위에서 출력된 hook 토큰> \
BUTTONLAB_BRIDGE_ID=$(hostname) \
claude --settings hooks/hook-gate.settings.example.json
```

`hook_bridge.py`는 도구 실행 직전 `/api/approval/wait`를 롱폴하고, 버튼(웹 UI 또는 실물 device 어댑터)이
`/api/approval/resolve`로 `allow`/`deny`를 보낼 때까지 대기합니다. **브리지 응답이 없거나 오류면 `ask`로
폴백**해 Claude 기본 권한 메뉴로 넘깁니다(자동 승인 없음). **토큰은 3가지 역할로 나뉩니다.** `ui`(조회+해결)·`device`
(조회+해결)·`hook`(등록·대기만). hook 토큰은 **스스로 승인할 수 없어** 사람의 결정을 우회하지 못합니다.

**브라우저 승인 패널.** 서버를 실행한 뒤 `http://127.0.0.1:8765/gate.html`을 열면 대기 중인 도구 실행
요청 목록과 **✓ 허용 / ✕ 거부** 버튼이 표시됩니다. 이 패널은 앱 페이지가 쓰는 것과 **동일한 `ui` 토큰**
으로 `/api/approval`(조회)·`/api/approval/resolve`(해결)만 호출하며, `/api/press`·PTY 데모와 분리된
**별도 페이지**입니다(검증된 키응답 경로에 영향 없음). 실물 device 어댑터 대신 하드웨어 없이 게이트를
시연·검증하는 데 쓸 수 있습니다.

**결정 감사 로그와 최근 결정 조회.** 처리된(허용/거부) 결정은 `.claude/approval-log.jsonl`(mode `0600`,
정적 웹루트 밖, `.gitignore`)에 **결정을 전달하기 전에 먼저 기록**됩니다. 기록 항목은
`tool_name·input_hash·decision·role·created_at·resolved_at`뿐이고 **summary·전체 tool_input·토큰은
남기지 않습니다.** 패널의 "최근 결정" 섹션과 `GET /api/approval/log`(ui/device 토큰만, hook 불가)로
최신순 조회할 수 있습니다. `role`은 **사용한 자격증명 역할(ui/device)**일 뿐 특정 사람의 신원이나 실제
물리버튼 사용, 도구 실행 결과를 증명하지 않습니다. 기록에 실패하면 결정을 전달하지 않으므로(요청은 대기 상태로
남고 훅은 `ask`로 폴백) **기록되지 않은 승인은 절대 전달되지 않습니다.**

## 사용한 AI 도구

- **Claude Code (Anthropic)** — 요구사항·설계·구현·검증 작업에 사용했습니다. AI-DLC 산출물은
  `aidlc-docs/`, 단계별 결정·승인 기록은 `aidlc-docs/audit.md`에 정리했습니다(`CLAUDE.md` = AI-DLC 규칙
  진입점, `.aidlc-rule-details/` = 단계별 규칙). Claude Code는 이 프로젝트가 **승인·거절 대상으로 실기기
  검증한 하네스**이기도 합니다.
- **AI-DLC 방법론** — INTENT → CONTEXT → ASK → PLAN → BUILD → VERIFY → REVIEW 단계로 진행하고,
  앞 단계 결정이 뒤 단계에 반영되도록 문서를 연결했습니다(단계별 연결 예시는 [`HACKATHON_EXECUTION_PLAN.md` §5](./HACKATHON_EXECUTION_PLAN.md)).
- **codex CLI(gpt-6-astra · gpt-5.6-luna)** — 기획·컨셉·실행계획을 냉정한 리뷰어 관점에서 검토하고,
  정직 경계(과대주장 제거)·카피·포지셔닝을 확정하는 데 반영했습니다([`CONCEPT_FINAL.md`](./CONCEPT_FINAL.md) §0.5,
  [`HACKATHON_EXECUTION_PLAN.md`](./HACKATHON_EXECUTION_PLAN.md)).

## 팀

**리센느(Re:senne)**는 소프트웨어와 하드웨어를 결합해 손으로 눌러 시연할 수 있는 디바이스를 만들었습니다.

| 이름 | 역할 |
|---|---|
| 이호섭 | 하드웨어·펌웨어 (UNO R4 WiFi, OLED, 물리 버튼, 배선) |
| 안중용 · 신현준 | 소프트웨어 (서버·웹 터미널·PTY 승인 경로·테스트) |
| 이호섭 · 안중용 · 김판규 · 신현준 (팀원 전원) | 기획·AI-DLC (문제 정의·컨셉·산출물 정합) |

## 라이선스

프로젝트 소스(서버·웹 터미널·펌웨어·훅·테스트·문서)는 **Apache License 2.0**으로 배포합니다 — 루트
[`LICENSE`](./LICENSE), 저작권·적용 범위·제3자 고지는 [`NOTICE`](./NOTICE)를 참고하십시오. 프런트엔드
라이브러리 `xterm.js`·`addon-fit`는 `vendor/`에 포함된 제3자(MIT) 구성요소로 각자의 라이선스를
유지합니다(`vendor/xterm-LICENSE`, `vendor/addon-fit-LICENSE`). 이 라이선스는 물리 하드웨어 설계나
팀 사진 키캡 이미지의 권리까지 보장하지는 않습니다. **라이선스는 팀 최종 sign-off 대기 상태입니다.**

## 시연 (스크린샷·영상)

> 시연 스크린샷과 영상은 현재 미첨부입니다. 제출 전 `screenshots/`에
> **① 승인 대기 → ② 승인 후 실행 → ③ 거절 후 해당 요청 미실행** 3컷과 무음 시연 영상을 추가하고
> 이 절에서 연결합니다.

---

*아래는 하드웨어 연결, 동작 규약, 검증 절차입니다.*

## 하드웨어와 연결 경로

이전 문서 일부에는 최종 HW가 BindDeck ESP32로 표기되어 있으나, 팀이 제작한 제출 디바이스는 **UNO R4 WiFi**입니다.

- **지금 이 저장소에서 바로 재현되는 정본 실행 경로 = USB 시리얼 → PTY.** 아래 "동작 방식·시리얼
  규약"이 이 전송을 설명합니다. 펌웨어는 `firmware/binddeck_claude/`(BindDeck ESP32 매크로패드,
  USB 시리얼)와 `firmware/yes_no/`(UNO R4 2버튼 USB 시리얼)이며, 웹 시뮬레이션으로 하드웨어 없이도
  같은 경로를 재현할 수 있습니다.
- **팀이 제작한 제출 디바이스 = Arduino UNO R4 WiFi** + 128×64 SSD1306 OLED + 물리 버튼 2개
  (✓ **APPROVE** = D2, ✕ **REJECT** = D3). 펌웨어 = **`firmware/resenne_uno_r4/`**.
- 루트 게이트 펌웨어(`firmware/resenne_uno_r4/`)의 UNO R4 WiFi 전송 경로 = 버튼 → UNO R4 WiFi(2.4GHz) →
  WebSocket → Node Bridge(`ws://…:8080`) → 앱의 PTY 승인 연결 지점. **버튼→브리지 왕복은 실기기에서 검증**했고
  (2026-09-07~08, 30ms 디바운스 21회 클린), OLED·D3 버튼도 팀 버튼 테스트 스케치로 확인한 뒤 이 펌웨어에
  통합했습니다. 다만 이 ws:8080 경로의 **Node Bridge 서버 자체는 미커밋이고 Node Bridge ↔ Python(PTY)
  어댑터 연결도 남은 단계**이므로(`HACKATHON_EXECUTION_PLAN.md` §2), 이 경로는 **초기·대체 설계**로 둡니다.
- **완결된 UNO R4 WiFi 구현은 `demo/arduino-simulator/`에 있습니다** — `board_wifi.py`가 보드 HTTP API
  (`/status`·`/events`·`/command`, 사설 IPv4만)로 **직결**하므로 별도 브리지가 필요 없습니다. 이 앱은 8키
  AI 컨트롤러(실제 Codex·Claude를 PTY에서 구동 + AI-DLC 5단계 물리 키 제어)로, **소프트웨어 테스트로 검증**했으나 **테스트는 가짜 CLI를 씁니다.** 실제 Codex·Claude 응답·물리 보드·AI-DLC 단계
  제어는 **팀이 실기기로 확인(사람 검증·시연)**했습니다. 펌웨어 = `demo/arduino-simulator/firmware/simulator_r4/`.
- **같은 물리 보드의 두 번째 펌웨어 = Re:senne 음원 플레이어**(`demo/arduino-simulator/firmware/uno_r4_soundboard/`,
  팀 하드웨어·펌웨어 담당 개발). D2–D9로 Re:senne 음원(오이쉬·거제야호·러브어택·데자뷰)을 **DFPlayer Pro**로
  재생하고 A0=볼륨·D10 WS2812B LED로 상태를 표시합니다. **AI 신호 프로토콜(`/events`·`BUTTON_LAB_*`)은
  구현하지 않는 별도 스케치**로, AI 컨트롤러(`simulator_r4`)와 **같은 배선을 공유하되 올리는 펌웨어만** 다릅니다
  (부품 연결도 = [`uno_r4_soundboard/README.md` §배선과 조작](./demo/arduino-simulator/firmware/uno_r4_soundboard/README.md)).
  커밋된 펌웨어는 **D10 LED를 구동**하며, HW 담당자의 최신 통합 작업본은 **LED 통합이 진행 중**(미커밋)이라 두
  버전을 모두 남겼습니다. **컴파일 성공은 실물 검증을 뜻하지 않습니다.**

## 동작 방식 (요약)

- 서버(`server.py`)가 **앱 소유 PTY**에서 `claude`를 실행합니다. `claude queue` 같은 큐 전송 경로가
  없으므로, 버튼 입력은 PTY에 **키 시퀀스를 직접 써서** 전달합니다.
- 버튼/엔코더 → 논리 동작 → 키 매핑은 `terminal.py`의 `ACTION_KEYS`가 **단일 소스**입니다.
  Claude의 승인 프롬프트는 방향키 메뉴이므로 숫자/y-n 대신 **↑/↓ + Enter**, 거절/중단은 **Esc**를 씁니다.
  - `yes` → Enter, `no` → Esc, `stop` → Esc, `confirm` → Enter, `nav_up` → ↑, `nav_down` → ↓
- Claude 세션 상태는 **Claude Code 훅**(`.claude/settings.json` → `hooks/claude_state_hook.py`)이
  상태 파일에 기록하고, 서버가 이를 읽어 `/api/state`로 노출합니다. 훅 파일이 없거나 오래되면
  트랜스크립트 **수정 시각(mtime)만** 참고하는 폴백을 사용합니다(스키마는 절대 파싱하지 않음).
  이 훅은 **권한을 결정하지 않는 상태 신호**일 뿐이며, 승인·거절 결정은 위의 PTY 키응답 경로가 담당합니다.
- 브라우저는 상태를 폴링해 USB 시리얼 기기(BindDeck)의 **OLED**에 표시합니다(`CMD:MSG:`).
  루트 UNO R4 WiFi 펌웨어는 상태를 WebSocket으로 받아 OLED에 표시하도록 구현되어 있습니다.
  이 경로는 버튼→브리지 왕복까지만 실기기로 확인했으며, Python(PTY) 어댑터 통합은 남아 있습니다.

## 웹 터미널과 Claude 연결

1. **쉘 시작**을 누르면 브라우저에서 명령을 입력할 수 있습니다(붙여넣기, Enter, Ctrl+C 등).
2. **Claude 시작**을 누르면 앱 소유 PTY에서 `claude`를 실행합니다. 터미널에 요청을 입력하고,
   승인 프롬프트가 뜨면 버튼으로 답하십시오. 쉘에서 직접 `claude`를 실행해도 됩니다.
3. **종료**는 웹에서 시작한 터미널을 종료합니다. 서버를 종료하면 함께 종료됩니다.
   페이지 새로고침은 실행 중인 세션을 유지합니다.

Claude 세션이 앱 소유 PTY에서 실행 중일 때만 버튼이 활성화됩니다. 연결 전이나 끊긴 동안에는
버튼을 비활성화하며, 그동안의 입력을 저장하거나 나중에 재전송하지 않습니다.

## 웹 시뮬레이션

`버튼 입력원 → 웹 시뮬레이션`을 선택합니다. 화면 버튼과 단축키를 사용할 수 있습니다.

| 동작 | 버튼 | 단축키 | 키 시퀀스 |
|---|---|---|---|
| YES | ✓ | `Y` | Enter |
| NO | × | `N` | Esc |
| 메뉴 위 | ▲ | `↑` | ↑ |
| 메뉴 아래 | ▼ | `↓` | ↓ |
| 확정 | ↵ | `Enter` | Enter |
| 중단 | ■ | `Esc` | Esc |

터미널 화면이나 버튼에 포커스가 있는 동안에는 단축키가 그 컨트롤의 기본 동작으로 처리됩니다.
누르면 실행 중인 Claude 세션에 해당 키를 바로 보냅니다. LED와 시리얼 모니터에서 동작을 확인할 수 있습니다.

이 시뮬레이션은 버튼·시리얼 동작을 재현합니다. ESP32 CPU나 펌웨어 실행을 에뮬레이션하지는 않습니다.

## 실물 UNO R4 WiFi 연결 (초기·대체 설계, ws:8080)

준비물: Arduino UNO R4 WiFi, 128×64 SSD1306 OLED(I2C), 물리 버튼 2개, USB 케이블, 2.4GHz AP.

1. Arduino IDE에 **UNO R4 보드 패키지(renesas_uno)**와 라이브러리 **WebSockets(Links2004)**,
   **Adafruit SSD1306 · Adafruit GFX · Adafruit BusIO**를 설치합니다(WiFiS3·Arduino_LED_Matrix·Wire는 코어 번들).
2. `firmware/resenne_uno_r4/resenne_uno_r4.ino`를 열고, 상단의 `WIFI_SSID`/`WIFI_PASS`/`BRIDGE_HOST`를
   **로컬에서만** 채웁니다(저장소에는 placeholder만 커밋 — 자격증명 금지).
3. 배선: 버튼 D2(✓)/D3(✕) ↔ GND, OLED SDA=A4·SCL=A5·GND 공통.
   ⚠️ A4/A5에는 보드 5V 풀업이 있으므로 **5V I2C를 견디는 OLED 모듈**을 쓰거나 레벨 변환을 적용하십시오.
4. 보드를 선택해 업로드합니다. OLED에 `OFFLINE` → 연결되면 `READY`가 뜹니다.
5. 팀 PoC에서는 Node Bridge(`ws://…:8080`)를 띄워 보드를 2.4GHz AP와 WebSocket으로 연결했습니다.
   펌웨어는 상태(`REVIEW_REQUIRED`→`YOUR TURN`)를 OLED에 표시하고 ✓/✕ 입력을 브리지로 보냅니다.
   브리지 서버는 미커밋이므로 저장소만으로 이 단계를 재현할 수 없으며, 대기 요청에 전달할 Python(PTY)
   어댑터 통합도 남아 있습니다.

OLED 상태 표기(펌웨어 실제 문구): IDLE=`READY`, RUNNING=`AI'S TURN`,
**REVIEW_REQUIRED=`YOUR TURN` / `PRESS TO APPROVE` / `OR PRESS X REJECT`**, SUCCESS=`DONE`,
ERROR=`ERROR`, DISCONNECTED=`OFFLINE`. 자동 승인은 꺼져 있으며, **사람이 눌러야** 버튼 입력을 보냅니다.

> **검증 상태:** 버튼→WiFi→WebSocket→Node Bridge 왕복은 실기기 확인. 다만 **Node Bridge 서버 자체가
> 미커밋**이고 Node Bridge ↔ Python PTY 승인(`server.py`) 어댑터도 통합 남은 작업이라
> (`HACKATHON_EXECUTION_PLAN.md` §2), 이 ws:8080 경로는 **초기·대체 설계**입니다. 게이트 앱에서 바로
> 실행되는 완성 경로는 아래 **USB 시리얼(BindDeck)** 연결이고, **완결된 UNO R4 WiFi(HTTP 직결) 구현은
> `demo/arduino-simulator/`**(`board_wifi.py`, 펌웨어 `firmware/simulator_r4/`)입니다.

## 실물 BindDeck 연결 (정본 실행 경로 · USB 시리얼)

준비물: BindDeck(ESP32-WROOM-32 + SSD1306 OLED + KY-040 엔코더 + 8 스위치), USB **데이터 케이블**.

1. Arduino IDE에 **ESP32 보드 패키지**와 **Adafruit SSD1306 · Adafruit GFX · Bounce2** 라이브러리를 설치합니다.
2. `firmware/binddeck_claude/binddeck_claude.ino`를 엽니다(웹의 **펌웨어 코드** 다운로드와 동일).
   이 펌웨어 포크는 **BLE·Wi-Fi를 제거**했고 **자격 증명을 담지 않습니다**. USB 시리얼만 사용합니다.
3. ESP32 보드와 포트를 선택하고 업로드합니다.
4. (선택) 상태 표시를 위해 이 폴더의 `.claude/settings.json` 훅을 활성화한 상태로 Claude를 실행합니다.
   훅이 없어도 트랜스크립트 mtime 폴백으로 대략적인 상태를 표시합니다.
5. 다른 시리얼 모니터를 닫고 데스크톱 Chrome에서 이 페이지(`http://127.0.0.1:8765`)를 엽니다.
6. **실물 BindDeck · USB → USB BindDeck 연결**을 누르고 보드 포트를 선택합니다.
7. **Claude 시작**으로 세션을 실행하면, 실물 버튼이 승인 프롬프트에 바로 전송됩니다.
   OLED에는 Claude 상태와 마지막 응답이 표시됩니다.

버튼 매핑: `BTN:0=YES`, `BTN:1=NO`, `BTN:2=STOP`, `BTN:8(엔코더 누름)=ENTER`,
엔코더 회전 `ENC:CW/VDN=메뉴 아래`, `ENC:CCW/VUP=메뉴 위`. `BTN:3..7`은 예약(호스트가 무시).

다시 업로드하려면 **USB 연결 해제**를 먼저 누르십시오. 케이블을 뽑으면 연결 해제 상태가 되며 재연결할 수 있습니다.

> 사람이 직접 버튼을 누를 때만 Claude로 전송됩니다. 훅과 브리지는 **자동 승인을 하지 않습니다**(human-in-the-loop 유지).

### 시리얼 규약

115200 baud / 8N1, 개행 구분.

- PC → 장치: `BUTTON_LAB_HELLO`(연결 확인), `CMD:MSG:<text>`(OLED 표시)
- 장치 → PC: `BUTTON_LAB_READY:1`(확인 응답), `BTN:0..8`(스위치/엔코더 누름), `ENC:CW`/`ENC:CCW`(엔코더 회전)

브라우저가 `BUTTON_LAB_HELLO\n`을 보내면 펌웨어가 `BUTTON_LAB_READY:1\n`으로 응답합니다.
확인 후에만 `BTN:`/`ENC:` 입력을 동작으로 매핑합니다. LF와 CRLF를 처리하고, 15ms 디바운스를 적용합니다.
버튼 입력은 자동 재시도하지 않습니다.

## Claude 상태 읽기 (주의)

- **1차 소스**: 훅이 기록한 작은 JSON 상태 파일(`--state-file`, 기본 `<cwd>/.claude/binddeck-state.json`).
  이벤트 매핑 — UserPromptSubmit/PreToolUse/PostToolUse=`active`, Notification(permission)=`waiting`, Stop/SubagentStop=`idle`.
- **폴백**: 훅 파일이 없거나 오래되면 `~/.claude/projects/**/*.jsonl` 중 최신 파일의 **mtime만** 봅니다.
  트랜스크립트 스키마는 Claude Code 내부 형식이며 불안정하므로 레코드를 **파싱하지 않습니다**.
- 어떤 경우에도 상태 리더는 예외를 던지지 않고 안전하게 `offline`으로 수렴합니다.
- 이 상태 신호는 **권한을 결정하지 않습니다.** 승인·거절 결정은 PTY 키응답 경로(웹/버튼 입력)가 담당합니다.

## 검증

테스트 전용 의존성만 별도 설치합니다(런타임은 여전히 무의존성).

```bash
# JS: fast-check (dev 전용). node_modules는 커밋하지 않습니다.
npm install
npm test                                   # node --test tests/*.test.js

# Python: hypothesis (PEP 668 대응 로컬 venv, 커밋하지 않음)
python3 -m venv .venv && ./.venv/bin/pip install hypothesis
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

- 서버 테스트의 PTY 전송(`send_choice`)은 모의 실행이며, 실제 키 시퀀스 매핑은 단위 테스트로 검증합니다.
- USB 테스트는 가상 Web Serial 스트림을 사용합니다.
- 속성 기반 테스트(PBT): 순수 매핑 함수의 전체성/일관성을 검증합니다
  (`tests/mapping.pbt.test.js`, `tests/test_mapping_pbt.py`).
- **8키·AI-DLC 구현(`demo/arduino-simulator/`)의 테스트**: 해당 앱 디렉터리에서 `python3 -m unittest discover -s tests`와
  `node --test tests/*.test.js`로 실행합니다. 다만 이 테스트는 **가짜 CLI 프로세스**로
  질문·승인 프로토콜·세션 변경·커스텀 저장을 검증하며, **실제 Codex·Claude 응답이나 실물 보드를 대체하지 않습니다.**
- **사람 검증·시연**: 실물 보드 업로드·배선·버튼 작동과 DOCKPAD의 실제 Codex·Claude 응답·물리 키를 통한
  AI-DLC 단계 제어는 팀이 실기기로 확인했습니다. 시연 근거로 무편집 영상을 제출 전 시연 절에 첨부할 예정입니다.
- **미검증 라이브 링크**: 실행 중인 진짜 `claude`가 allow/deny 게이트의 결정을 존중해 실제 도구 실행을
  허용·거부하는지는 사람/라이브 데모로 확인해야 합니다. 위 실기기 확인이나 소프트웨어 E2E에 포함하지 않습니다.
- `ACTION_KEYS`의 리터럴 바이트는 설정값이므로 스모크 결과에 따라 로직 변경 없이 조정할 수 있습니다.

빌드·테스트 상세 절차는 `aidlc-docs/construction/build-and-test/`를 참고하십시오.

프런트엔드 라이브러리는 `vendor/`에 포함되며 각 LICENSE 파일(`vendor/xterm-LICENSE`·
`vendor/addon-fit-LICENSE`)을 함께 배포합니다. 프로젝트 라이선스(Apache-2.0)는 위
[`## 라이선스`](#라이선스) 절과 루트 `LICENSE`·`NOTICE`를 참고하십시오.

참고: [Arduino UNO R4 WiFi](https://docs.arduino.cc/hardware/uno-r4-wifi/),
[WebSockets (Links2004)](https://github.com/Links2004/arduinoWebSockets),
[Chrome Web Serial](https://developer.chrome.com/docs/capabilities/serial),
[BindDeck (SanX18)](https://github.com/SanX18/BindDeck),
[Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks),
[xterm.js](https://xtermjs.org/).
