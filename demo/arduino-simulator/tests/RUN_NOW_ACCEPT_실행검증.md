# RUN NOW / ACCEPT 실제 실행 검증

2026-09-09, macOS의 실제 Chrome(헤드리스), Codex CLI, Claude Code v2.1.266으로 확인했다. Playwright로 시뮬레이터의 화면 버튼을 클릭했으며, CLI 응답이나 파일 생성은 모의 처리하지 않았다. 테스트는 별도의 서버와 임시 작업 폴더에서 수행했다.

## 모드 2 · RUN NOW

- Initialization 입력란에만 `run-now-proof.txt`를 생성하고 `RUN_NOW_OK` 한 줄을 저장·검증하도록 입력했다. Ideation 등 다른 단계는 비워 두었다.
- 입력 화면을 닫고 모드 2의 7 RUN NOW 버튼을 클릭했다.
- 실제 요청은 입력 저장 후 `start`의 `stage: construction` 순서로 전달됐다.
- 입력·결과 창이 새로 열리지 않았다. 실행 중 및 종료 후 열린 `dialog` 수는 0이었다.
- Codex가 필요한 조사·설계를 거쳐 구현까지 진행했다. 생성된 파일을 직접 읽어 `RUN_NOW_OK\n`과 일치함을 확인했다.
- Construction 결과는 `VERDICT: PASS`, 최종 오류는 없었다. 저장된 자율성 값은 유지됐다.

## 모드 1 · ACCEPT

- Claude가 번호 목록 없이 “현재 결과를 승인할까요?”라고 묻도록 요청했다.
- 입력란이 빈 상태에서 5 ACCEPT 버튼을 클릭했다.
- “현재 제안 또는 결과를 승인합니다. 해당 내용에 맞게 진행해 주세요.”가 한 번 전송됐다.
- Claude가 실제로 `ACCEPT_OK`라고 응답했다.
- CLI 자체의 폴더 신뢰 선택 화면에서도 ACCEPT가 Enter로 선택을 확인하는 동작을 검증했다.
- 작성 중인 답변 제출 및 번호 메뉴의 기존 응답 처리도 자동 검사로 확인했다.

## 자동 검사와 반영

- JavaScript: `node --test tests/*.test.js` — 76개 통과.
- Python: `python3 -m unittest discover -s tests` — 78개 통과.
- 입력 저장 실패 시 실행하지 않음, 자동 저장 중 RUN NOW 연속 클릭 시 한 번만 실행함, 어느 단계에 입력해도 Construction까지 진행함, 빈 입력 거부 및 명시된 보류 유지 등을 검사했다.
- 8765 서버에 실행 중인 AI 작업·워크플로·작성 중인 터미널 입력이 없음을 확인한 뒤 서버를 재시작했다. 저장된 단계 입력을 복원했고 최신 JavaScript 파일 제공을 확인했다. 서버 재시작으로 기존 웹 AI 프로세스는 종료됐으므로 새로 실행해야 한다.

## 범위

실물 보드의 물리 버튼을 누르는 검사는 포함하지 않았다. 웹 AI가 열려 있는 동안 워크플로 실행을 제한하는 기존 규칙과, 번호 질문이 표시되면 번호 답변 선택이 우선하는 기존 규칙은 유지된다.

임시 실행 기록과 화면 캡처는 `/var/folders/8f/9rl_523s7hqbqvfgr1r66qwr0000gn/T/arduino-run-accept-live-xr24368h/artifacts/`에 저장했다. 임시 경로는 운영체제에 의해 정리될 수 있다.
