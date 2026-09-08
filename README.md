# 리센느(Re:senne) — Re:senne HUMAN GATE / 물리 버튼으로 AI 하네스의 대기 중 실행을 사람이 승인·거절하는 소스 공개 물리 컨트롤러 (검증된 예시 = Claude Code)

물리 버튼(또는 웹 시뮬레이션)으로, 이 컴퓨터에서 실행 중인 AI 하네스의 **대기 중 실행 요청**에
사람이 승인·거절로 답합니다. 지금 실기기로 검증된 예시는 **Claude Code**입니다. AI가 준비하면
OLED가 사람을 부르고, 버튼을 누르면 실제 코드 변경이 진행됩니다. 브라우저에서 쉘과 Claude를
실행하는 웹 터미널과 상태 표시도 제공합니다.

> **제4회 디디톤 출품작 · 팀 리센느(Re:senne).** 메인 카피: **"버튼의 재정의. 명령에서 승인·거절로."**
> *(Redefining the button. From commands to consent.)* — 카피·포지셔닝 권위본 = [`CONCEPT_FINAL.md` §0.5](./CONCEPT_FINAL.md),
> 전체 실행계획 = [`HACKATHON_EXECUTION_PLAN.md`](./HACKATHON_EXECUTION_PLAN.md), AI-DLC 산출물 = [`aidlc-docs/`](./aidlc-docs/).

## 문제

Claude Code에 파일 수정과 쉘 명령 실행을 맡기면서, 실행 직전 승인·거절은 직접 결정하고 **그 승인을
타이핑과 분리하고 싶은** 개발자가 대상입니다.

**작업 지시(코드·프롬프트)와 실행 승인을 같은 키보드로 처리합니다.** 승인이 필요한 실행 요청이 나올
때마다 개발자는 터미널에서 내용을 읽고, 작업에 쓰던 키보드로 승인 메뉴를 선택·확정합니다 — 승인이라는
별도 판단이 일반 타이핑과 같은 입력 채널을 씁니다.

이 순간은 Claude Code가 실행 승인을 요청할 때마다(파일 수정·쉘 명령 등의 실행 직전) 반복됩니다.
사용자별 일일 발생 횟수는 아직 측정하지 않았습니다.

## 해결 방법

**Re:senne HUMAN GATE는 실행 승인·거절을 전용 물리 버튼 두 개로 분리합니다.** 개발자는 화면에서 실행
요청을 확인하고 UNO R4 WiFi의 **✓ 승인(D2)** 또는 **✕ 거절(D3)**을 누릅니다. 제출 버전은 사람의
물리·웹 시뮬 입력을 **Python PTY 키응답**으로 실제 Claude Code의 대기 중 요청에 전달합니다 —
**현재 이 저장소에서 바로 실행되는 완성 경로 = USB 시리얼 → PTY 키응답**입니다. **UNO R4 WiFi의
Node Bridge 경로(버튼→WebSocket→브리지→PTY)는 버튼↔브리지 왕복까지 실기기 확인**했고,
**브리지↔Python 어댑터 통합이 남은 단계**입니다(아래 [실물 UNO R4 WiFi 연결](#실물-uno-r4-wifi-연결-제출-기준)).

**[통합 예정] `hook_bridge.py`의 PreToolUse allow/deny 게이트** — 지정 도구 실행을 버튼 승인까지
정지시키고 `allow`/`deny`를 반환합니다. **팀 실기기 E2E에서 버튼→브리지→Python PTY→실제 Claude Code
실행 경로로 승인 시 실행 / 거절 시 해당 요청 미실행을 확인**했으며, 이 게이트는 **별도 저장소에 있어
제출 저장소로의 통합이 남은 단계**입니다. 현재 제출 저장소의 `hooks/claude_state_hook.py`는 권한을
결정하지 않는 상태 신호입니다([Claude 상태 읽기](#claude-상태-읽기-주의) 참고).

매크로패드·스트림덱은 보통 버튼에 단축키·명령을 매핑해 **실행을 촉발**하는 용도로 쓰입니다.
HUMAN GATE는 버튼을 **이미 제안된 실행 요청의 승인·거절 결정**에 연결합니다 — 이 구조적 차이는
승인 대기 중인 요청에만·`request_id` 최초 1회만 결정을 전달하는 입력 경로(`terminal.py`의
`ACTION_KEYS`·`send_choice()`)로 코드에서 확인할 수 있습니다.

설계 범위는 공통 프로토콜과 하네스별 어댑터를 통한 AI 하네스 연동이며, **현재 실기기 E2E로 검증된
예시는 Claude Code입니다.** 리센느 팀 사진 키캡은 첫 커스텀 프로파일입니다. 포스터의 8키 매크로패드 +
로터리 다이얼(`AI-DLC DOCKPAD`)은 **확장 로드맵**이며, 이 제출물에는 구현되어 있지 않습니다.

## 실행 방법

**사전조건**
- macOS 또는 Linux. Windows에서는 WSL에서 서버를 실행합니다.
- Python 3.10 이상. 런타임은 **외부 의존성이 없습니다**(xterm/addon-fit는 `vendor/`에 포함, 프런트는 무설치).
- Claude를 쓰려면 **사용자 본인의 Claude Code CLI 설치와 로그인**이 필요합니다. `claude --version`으로 확인하세요.
- 실물 USB 보드는 Web Serial을 지원하는 **데스크톱 Chrome**에서 연결합니다. 웹 시뮬레이션에는 USB가 필요 없습니다.

**실행(단일 진입점)**

```bash
python3 server.py                          # http://127.0.0.1:8765
python3 server.py --cwd /path/to/project   # Claude 세션을 이 폴더에서 실행
python3 server.py --port 8766
```

서버는 이 컴퓨터의 `127.0.0.1`에서만 접속할 수 있습니다. 웹 터미널 명령과 Claude 세션은 **서버를
실행한 사용자 계정으로 실제 실행**됩니다.

**환경변수·시크릿 (저장소에 실제 값 없음)**
- 로컬 웹 실행에는 별도 환경변수가 필요 없습니다. 승인 API는 `127.0.0.1` 접속으로 제한하고, 세션 토큰은
  `compare_digest`로 검증합니다(Host allowlist·Origin·CSP·`X-Frame-Options: DENY` 가드 포함).
- **현재 완성 경로인 USB 시리얼 연결에는 Wi-Fi 설정이 필요 없습니다.** `WIFI_SSID` / `WIFI_PASS` /
  `BRIDGE_HOST`는 **통합 예정인 Node Bridge(UNO R4 WiFi) 경로용** 설정이며, 이때만 펌웨어 상단에서
  **로컬로만** 채웁니다. 저장소에는 **placeholder만 커밋**하고 자격증명·API 키·로그인 정보는 포함하지 않습니다.

**첫 시나리오(핵심 경로 한 줄)**
`python3 server.py` → 브라우저에서 `http://127.0.0.1:8765` 열기 → **Claude 시작** → 요청 입력 →
승인 프롬프트가 뜨면 **웹 시뮬레이션 또는 실물 버튼으로 ✓ 승인 / ✕ 거절** → 화면·OLED에서 결과 확인.
하드웨어 연결·시뮬레이션 키·검증 절차는 아래 상세 섹션을 참고하세요.

## 사용한 AI 도구

- **Claude Code (Anthropic)** — 요구사항·설계·구현·검증 작업에 사용했습니다. AI-DLC 산출물은
  `aidlc-docs/`, 단계별 결정·승인 기록은 `aidlc-docs/audit.md`에 정리했습니다(`CLAUDE.md` = AI-DLC 규칙
  진입점, `.aidlc-rule-details/` = 단계별 규칙). Claude Code는 이 프로젝트가 **승인·거절 대상으로 실기기
  검증한 하네스**이기도 합니다.
- **AI-DLC 방법론** — INTENT → CONTEXT → ASK → PLAN → BUILD → VERIFY → REVIEW 단계로 진행하고,
  앞 단계 결정이 뒤 단계에 반영되도록 문서를 이어붙였습니다(대표 사슬은 [`HACKATHON_EXECUTION_PLAN.md` §5](./HACKATHON_EXECUTION_PLAN.md)).
- **codex CLI(gpt-6-astra · gpt-5.6-luna)** — 기획·컨셉·실행계획을 냉정한 리뷰어 관점에서 검토하고,
  정직 경계(과대주장 제거)·카피·포지셔닝을 확정하는 데 반영했습니다([`CONCEPT_FINAL.md`](./CONCEPT_FINAL.md) §0.5,
  [`HACKATHON_EXECUTION_PLAN.md`](./HACKATHON_EXECUTION_PLAN.md)).

## 팀

**리센느(Re:senne)** · 강점 = **SW + HW 결합** (손으로 눌러 보여주는 실물 디바이스).

| 이름 | 역할 |
|---|---|
| _(제출 전 기입)_ | 하드웨어·펌웨어 (UNO R4 WiFi, OLED, 물리 버튼, 배선) |
| _(제출 전 기입)_ | 소프트웨어 (서버·웹 터미널·PTY 승인 경로·테스트) |
| _(제출 전 기입)_ | 기획·AI-DLC (문제 정의·컨셉·산출물 정합) |

> 표의 이름·역할·인원은 실제 팀 구성에 맞춰 제출 전 채워 주세요.

## 시연 (스크린샷·영상)

> _(제출 전 실제 이미지로 교체)_ 시연 스크린샷은 현재 미첨부입니다. 제출 전 `screenshots/`에
> **① 승인 대기 → ② 승인 후 실행 → ③ 거절 후 해당 요청 미실행** 3컷과 무음 시연 영상을 추가하고
> 이 절에서 연결합니다.

---

*아래는 완성도·사용성·유지보수 근거가 되는 상세 문서입니다.*

## 하드웨어 (제출 기준 = Arduino UNO R4 WiFi)

- **제출·검증 하드웨어 = Arduino UNO R4 WiFi** + 128×64 SSD1306 OLED + 물리 버튼 2개
  (✓ **APPROVE** = D2, ✕ **REJECT** = D3). 펌웨어 = **`firmware/resenne_uno_r4/`**.
- 전송 경로 = 버튼 → UNO R4 WiFi(2.4GHz) → WebSocket → Node Bridge(`ws://…:8080`) → 앱의 PTY 승인 seam.
  **버튼→브리지 왕복을 실기기에서 검증**(2026-09-07~08, 30ms 디바운스 21회 클린). OLED·D3 버튼은
  팀 버튼 테스트 스케치로 실기기 확인한 뒤 이 펌웨어에 통합했습니다. **Node Bridge ↔ Python(PTY)
  어댑터 연결은 통합 남은 작업**입니다(`HACKATHON_EXECUTION_PLAN.md` §2).
- **초기 탐색 경로(문서 보존)**: `firmware/binddeck_claude/`(BindDeck ESP32 매크로패드, USB 시리얼)와
  `firmware/yes_no/`(UNO R4 초기 2버튼 USB 시리얼). 아래 "동작 방식·시리얼 규약"은 **이 USB 시리얼
  전송**을 설명하며, 현재 이 저장소에서 바로 실행되는 경로입니다. UNO R4 WiFi 경로는 같은 PTY 승인
  seam에 WebSocket(Node Bridge)로 도달합니다.

> ⚠️ 이전 문서 일부는 최종 HW를 BindDeck ESP32로 적었으나, **제출 기준 하드웨어는 UNO R4 WiFi**입니다.

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
  UNO R4 WiFi 펌웨어는 상태를 WebSocket으로 직접 받아 OLED에 표시합니다.

## 웹 터미널과 Claude 연결

1. **쉘 시작**을 누르면 브라우저에서 명령을 입력할 수 있습니다(붙여넣기, Enter, Ctrl+C 등).
2. **Claude 시작**을 누르면 앱 소유 PTY에서 `claude`를 실행합니다. 터미널에 요청을 입력하고,
   승인 프롬프트가 뜨면 버튼으로 답하세요. 쉘에서 직접 `claude`를 실행해도 됩니다.
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

## 실물 UNO R4 WiFi 연결 (제출 기준)

준비물: Arduino UNO R4 WiFi, 128×64 SSD1306 OLED(I2C), 물리 버튼 2개, USB 케이블, 2.4GHz AP.

1. Arduino IDE에 **UNO R4 보드 패키지(renesas_uno)**와 라이브러리 **WebSockets(Links2004)**,
   **Adafruit SSD1306 · Adafruit GFX · Adafruit BusIO**를 설치합니다(WiFiS3·Arduino_LED_Matrix·Wire는 코어 번들).
2. `firmware/resenne_uno_r4/resenne_uno_r4.ino`를 열고, 상단의 `WIFI_SSID`/`WIFI_PASS`/`BRIDGE_HOST`를
   **로컬에서만** 채웁니다(저장소에는 placeholder만 커밋 — 자격증명 금지).
3. 배선: 버튼 D2(✓)/D3(✕) ↔ GND, OLED SDA=A4·SCL=A5·GND 공통.
   ⚠️ A4/A5에는 보드 5V 풀업이 있으므로 **5V I2C를 견디는 OLED 모듈**을 쓰거나 레벨 변환하세요.
4. 보드를 선택해 업로드합니다. OLED에 `OFFLINE` → 연결되면 `READY`가 뜹니다.
5. 앱 쪽에서 Node Bridge(`ws://…:8080`)를 띄우고, 보드가 2.4GHz AP에 접속해 WebSocket으로 붙으면
   상태(`REVIEW_REQUIRED`→`YOUR TURN`)가 OLED에 뜨고 ✓/✕ 버튼이 대기 요청에 전송됩니다.

OLED 상태 표기(펌웨어 실제 문구): IDLE=`READY`, RUNNING=`AI'S TURN`,
**REVIEW_REQUIRED=`YOUR TURN` / `PRESS TO APPROVE` / `OR PRESS X REJECT`**, SUCCESS=`DONE`,
ERROR=`ERROR`, DISCONNECTED=`OFFLINE`. 자동 승인은 꺼져 있어 **사람이 눌러야만** 진행합니다.

> **검증 상태:** 버튼→WiFi→WebSocket→Node Bridge 왕복은 실기기 확인. Node Bridge ↔ 기존 Python PTY
> 승인 처리(`server.py`)를 잇는 어댑터는 통합 남은 작업입니다(`HACKATHON_EXECUTION_PLAN.md` §2).
> 현재 이 저장소에서 바로 실행되는 완성 경로는 아래 **USB 시리얼(BindDeck)** 연결입니다.

## 실물 BindDeck 연결 (초기 탐색 경로)

준비물: BindDeck(ESP32-WROOM-32 + SSD1306 OLED + KY-040 엔코더 + 8 스위치), USB **데이터 케이블**.

1. Arduino IDE에 **ESP32 보드 패키지**와 **Adafruit SSD1306 · Adafruit GFX · Bounce2** 라이브러리를 설치합니다.
2. `firmware/binddeck_claude/binddeck_claude.ino`를 엽니다(웹의 **펌웨어 코드** 다운로드와 동일).
   이 펌웨어 포크는 **BLE·Wi-Fi를 제거**했고 **자격 증명을 담지 않습니다**. USB 시리얼만 사용합니다.
3. ESP32 보드와 포트를 선택하고 업로드합니다.
4. (선택) 상태 표시를 위해 이 폴더의 `.claude/settings.json` 훅을 활성화한 상태로 Claude를 실행합니다.
   훅이 없어도 트랜스크립트 mtime 폴백으로 대략적인 상태를 표시합니다.
5. 다른 시리얼 모니터를 닫고 데스크톱 Chrome에서 Button Lab을 엽니다.
6. **실물 BindDeck · USB → USB BindDeck 연결**을 누르고 보드 포트를 선택합니다.
7. **Claude 시작**으로 세션을 실행하면, 실물 버튼이 승인 프롬프트에 바로 전송됩니다.
   OLED에는 Claude 상태와 마지막 응답이 표시됩니다.

버튼 매핑: `BTN:0=YES`, `BTN:1=NO`, `BTN:2=STOP`, `BTN:8(엔코더 누름)=ENTER`,
엔코더 회전 `ENC:CW/VDN=메뉴 아래`, `ENC:CCW/VUP=메뉴 위`. `BTN:3..7`은 예약(호스트가 무시).

다시 업로드하려면 **USB 연결 해제**를 먼저 누르세요. 케이블을 뽑으면 연결 해제 상태가 되며 재연결할 수 있습니다.

> 사람이 직접 버튼을 누를 때만 Claude로 전송됩니다. 훅과 브릿지는 **자동 승인을 하지 않습니다**(human-in-the-loop 유지).

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
- 어떤 경우에도 상태 리더는 예외를 던지지 않고 안전하게 `offline`로 수렴합니다.
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
- **아직 하지 않은 것**: 실물 BindDeck 업로드·배선·버튼 작동, 실제 `claude` 세션에 대한 키 시퀀스 스모크
  테스트. `ACTION_KEYS`의 리터럴 바이트는 설정값이므로, 스모크 테스트 결과에 따라 로직 변경 없이 조정할 수 있습니다.

빌드·테스트 상세 절차는 `aidlc-docs/construction/build-and-test/`를 참고하세요.

프런트엔드 라이브러리는 `vendor/`에 포함되어 있으며 해당 LICENSE 파일을 함께 배포하세요. 프로젝트
자체 라이선스는 아직 지정하지 않았습니다(현재 **소스 공개 PoC**).

참고: [Arduino UNO R4 WiFi](https://docs.arduino.cc/hardware/uno-r4-wifi/),
[WebSockets (Links2004)](https://github.com/Links2004/arduinoWebSockets),
[Chrome Web Serial](https://developer.chrome.com/docs/capabilities/serial),
[BindDeck (SanX18)](https://github.com/SanX18/BindDeck),
[Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks),
[xterm.js](https://xtermjs.org/).
