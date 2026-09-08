# Button Lab · BindDeck × Claude Code

웹 버튼 또는 실물 **BindDeck**(ESP32 매크로패드) 버튼·엔코더로, 이 컴퓨터에서 실행 중인
**Claude Code** 세션의 승인 프롬프트에 답합니다. 브라우저에서 쉘과 Claude를 실행하는 웹 터미널과
USB 시리얼 모니터를 제공합니다.

이전 버전은 Arduino UNO R4 WiFi의 YES / NO 버튼으로 Codex에 답했습니다. 이 버전은 하드웨어를
**BindDeck**으로, 대상 에이전트를 **Claude Code**로 재타깃했습니다(AI-DLC 산출물: `aidlc-docs/`).

## 동작 방식 (요약)

- 서버(`server.py`)가 **앱 소유 PTY**에서 `claude`를 실행합니다. `claude queue` 같은 큐 전송 경로가
  없으므로, 버튼 입력은 PTY에 **키 시퀀스를 직접 써서** 전달합니다.
- 버튼/엔코더 → 논리 동작 → 키 매핑은 `terminal.py`의 `ACTION_KEYS`가 **단일 소스**입니다.
  Claude의 승인 프롬프트는 방향키 메뉴이므로 숫자/y-n 대신 **↑/↓ + Enter**, 거절/중단은 **Esc**를 씁니다.
  - `yes` → Enter, `no` → Esc, `stop` → Esc, `confirm` → Enter, `nav_up` → ↑, `nav_down` → ↓
- Claude 세션 상태는 **Claude Code 훅**(`.claude/settings.json` → `hooks/claude_state_hook.py`)이
  상태 파일에 기록하고, 서버가 이를 읽어 `/api/state`로 노출합니다. 훅 파일이 없거나 오래되면
  트랜스크립트 **수정 시각(mtime)만** 참고하는 폴백을 사용합니다(스키마는 절대 파싱하지 않음).
- 브라우저는 상태를 폴링해 실물 BindDeck의 **OLED**에 표시합니다(`CMD:MSG:`).

## 설치와 실행

- macOS 또는 Linux. Windows에서는 WSL에서 서버를 실행합니다.
- Python 3.10 이상. 런타임은 **외부 의존성이 없습니다**(xterm/addon-fit는 `vendor/`에 포함).
- Claude를 쓰려면 **사용자 본인의 Claude Code CLI 설치와 로그인**이 필요합니다. `claude --version`으로 확인하세요.
- 실물 USB 보드는 Web Serial을 지원하는 **데스크톱 Chrome**에서 연결합니다. 웹 시뮬레이션에는 USB가 필요 없습니다.

```bash
python3 server.py                       # http://127.0.0.1:8765
python3 server.py --cwd /path/to/project   # Claude 세션을 이 폴더에서 실행
python3 server.py --port 8766
```

서버는 이 컴퓨터의 `127.0.0.1`에서만 접속할 수 있습니다. 웹 터미널 명령과 Claude 세션은
**서버를 실행한 사용자 계정으로 실제 실행**됩니다. API 키·로그인 정보·다른 사람의 기록은 배포 파일에
포함하지 않으며, 사용자별 로컬 Claude 설정을 사용합니다.

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

## 실물 BindDeck 연결

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

프런트엔드 라이브러리는 `vendor/`에 포함되어 있으며 해당 LICENSE 파일을 함께 배포하세요.

참고: [Chrome Web Serial](https://developer.chrome.com/docs/capabilities/serial),
[BindDeck (SanX18)](https://github.com/SanX18/BindDeck),
[Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks),
[xterm.js](https://xtermjs.org/).
