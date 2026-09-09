# screenshots/ — 시연 증거

이 폴더에는 **DOCKPAD(8키 AI 컨트롤러, `demo/arduino-simulator/`) 실기기 시연 스크린샷**,
**실물 하드웨어 사진**, 그리고 **DOCKPAD 실기기 AI-DLC 무편집 시연 영상(`demo.mp4`)**이 들어 있습니다.
루트 `README.md`의 `## 시연` 절에서 연결합니다.

## 정직 경계 (필독)

- 이 컷들은 **DOCKPAD 앱의 화면**이며, 루트 2버튼 게이트 앱(`server.py`)의 화면이 아닙니다.
- 실제 Codex·Claude CLI를 PTY에서 구동하고 물리 키(USB 시리얼)로 AI-DLC 단계·승인·거절을
  전달하는 모습입니다. **이는 팀이 실기기로 확인한 사람 검증·시연 결과이며, 자동 테스트가
  증명하지 않습니다.** (자동 테스트는 가짜 CLI 프로세스를 사용합니다.)
- 루트 게이트 앱의 **완전 E2E 검증 경로 = PTY 키응답(USB 시리얼 / 웹 시뮬레이션)**입니다.
  UNO R4 WiFi Node Bridge(ws:8080) 경로는 **버튼→브리지 왕복까지만 실기기로 확인**했고,
  Node Bridge↔Python(PTY) 어댑터 통합은 남은 단계라 **초기·대체 설계**입니다. 즉 "물리 버튼 →
  브리지 → Python PTY → 실제 Claude Code 실행"을 잇는 완결된 실기기 E2E는 아직 아닙니다.

## 수록 이미지

- **`hardware-device.jpeg`** — 실물 장치 사진(3D 인클로저 · OLED `MODE 2 AI-DLC` · 자율성 노브 ·
  사진 키캡 8버튼 · 스피커).
- **AI-DLC 단계 (모드 1 · AI CONTROL, 실제 Claude Code 구동)**
  - `dockpad-session-start.png` — Claude Code 세션 시작(v2.1.266 · Opus 4.8).
  - `dockpad-01-model.png` · `dockpad-02-plan.png` · `dockpad-03-build.png` · `dockpad-04-check.png`
    — MODEL → PLAN → BUILD → CHECK 각 단계 화면.
  - `dockpad-plan-progress.png` · `dockpad-build-progress.png` — PLAN/BUILD 진행(OLED `RUNNING`).
- **사람의 승인·거절·중단 (물리 키)**
  - `dockpad-05-accept.png` — 검증 결과("…승인할까요, 거절할까요?") 앞 **ACCEPT 승인 전달**.
  - `dockpad-06-denied.png` — **DENIED 거절** 후 다른 대안 요청(해당 제안 미채택).
  - `dockpad-07-stop.png` — **STOP** 중단.
- `dockpad-08-mode.png` — AI CONTROL ↔ AI-DLC **모드 전환** + 검증 결과 화면.

## 수록 영상

- **`demo.mp4`** — **DOCKPAD(8키)의 실기기 AI-DLC 무편집 시연 영상**(사람 검증·시연, 자동 테스트가
  증명하지 않음). 실제 Claude Code를 PTY에서 구동하고 물리 키로 AI-DLC 단계·승인·거절을 전달합니다.
  약 8.9MB. GitHub에서는 인라인 재생 대신 파일 링크로 열립니다.

## 루트 2버튼 게이트 — PTY 키응답 (별도 경로)

위 `demo.mp4`는 **DOCKPAD** 시연이며, 루트 2버튼 게이트 앱과는 별개입니다. 루트 HUMAN GATE 게이트 앱의
PTY 키응답 경로는 아래 ①~③ 순서로 동작하고, 저장소 코드·단위·소프트웨어 E2E 테스트와 루트
`README.md`의 **구현과 검증 범위** 표로 뒷받침합니다.

1. **승인 대기** — Claude Code가 실행 직전 대기하고, 화면(또는 OLED `YOUR TURN` /
   `PRESS TO APPROVE`)이 사람을 호출하는 순간. 아직 아무 변경도 일어나지 않음.
2. **승인 후 실행** — ✓ 버튼(D2)을 누른 뒤 실제 코드 변경이 진행되는 화면.
3. **거절 후 미실행** — 새 요청에서 ✕ 버튼(D3)을 누른 뒤 **해당 요청이 실행되지 않았음**을
   화면·로그로 확인(거절은 대기 중인 그 요청에만 적용).

- 연출 상세(45~55초 컷, 25초 갤러리 영상) = `HACKATHON_EXECUTION_PLAN.md` §3·§4.
- 승인 후 실행 / 거절 후 미실행을 **각 3회 안정 재현**하고 로그를 보존합니다(계획서 §9).
