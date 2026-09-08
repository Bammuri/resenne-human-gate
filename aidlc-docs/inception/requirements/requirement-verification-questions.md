# 요구사항 확인 질문 (Requirements Clarification Questions)

> 각 질문의 `[Answer]:` 태그 뒤에 알파벳(A/B/C…)을 적어 답변해 주세요. 해당하는 보기가 없으면 마지막의 **"Other"** 를 선택하고 자유롭게 설명을 적어주시면 됩니다. 여러 개를 고르고 싶은 문항은 `A, C` 처럼 쉼표로 나열해도 됩니다. 모두 작성하신 뒤 "done"(또는 완료)이라고 알려주세요.

> **⚙️ 확정 방식 (2026-09-08)**: 사용자 지시("애매한건 정리해서 GPT arsta mid에게 물어보고 자동진행해")에 따라, 아래 답변은 **설치된 GPT(Codex CLI, medium 추론) 자문 + AI 권장안**으로 자동 확정되었습니다. 자문 원문은 `aidlc-docs/inception/requirements/gpt-astra-consultation.md`에 보관되어 있으며, 사용자는 언제든 답을 바꿔 재생성을 요청할 수 있습니다.

---

## 의도 요약 (내가 이해한 내용)
- **요청 원문**: "HW는 https://github.com/SanX18/BindDeck 이거쓸꺼야 분석해서 다시 만들어보자"
- **요청 유형**: Migration + Enhancement (하드웨어 표면을 UNO R4 2버튼 → BindDeck ESP32 매크로패드로 교체하고, YES/NO 브릿지 대상은 Codex → Claude Code로 리타겟)
- **범위 추정**: Multiple Components (펌웨어 + 브라우저 Web Serial 계층 + Python send/state 계층)
- **복잡도 추정**: Moderate ~ Complex
- 아래 질문들은 이 이해를 확정하기 위한 것입니다.

---

## Question 1 — "다시 만들어보자"의 범위
BindDeck을 대상으로 "다시 만든다"의 실제 작업 범위는 무엇인가요?

A) **펌웨어 포크 + 호스트 적응** — BindDeck 펌웨어를 슬림하게 포크(불필요 기능 제거)하고, 브라우저 `serial.js`를 BindDeck 프레이밍(`BTN:`/`ENC:`)에 맞게 수정 (권장)

B) **호스트 계층만 적응** — 펌웨어는 BindDeck 원본을 그대로 쓰고, 우리 쪽 `serial.js`만 `BTN:`/`ENC:` 프로토콜을 해석하도록 수정

C) **전면 재작성** — BindDeck을 참고만 하고 펌웨어/호스트 모두 새로 작성

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2 — 물리 버튼 → 동작 매핑
BindDeck의 8개 스위치 + 엔코더 버튼(BTN:8)을 어떤 동작에 연결할까요? (복수 선택 가능)

A) **YES / NO만** — `BTN:0`→yes, `BTN:1`→no (현행 2버튼과 동일한 최소 구성)

B) **YES / NO / ALWAYS(모두 허용)** — 위 + `BTN:2`→"항상 허용/2번 선택"

C) **YES / NO / ALWAYS / STOP(중단·Esc)** — 위 + `BTN:3`→Claude 중단(Esc)

D) **위 + 커스텀 메시지 버튼** — 남는 스위치를 자주 쓰는 프롬프트/명령 전송에 할당

X) Other (please describe after [Answer]: tag below)

[Answer]: A, C

## Question 3 — 엔코더로 Claude "번호 매긴 권한 메뉴" 탐색
Claude Code의 권한 프롬프트는 종종 `1. Yes / 2. Yes, and don't ask again / 3. No`처럼 **번호 메뉴**로 뜹니다. 현행 `yes\n` 리터럴 전송으로는 정확히 대응되지 않습니다. 엔코더(회전 + 누름)를 어떻게 쓸까요?

A) **엔코더로 메뉴 이동 + 누름(BTN:8)으로 선택 확정** — 회전으로 위/아래 이동(↑/↓ 키), 누름으로 Enter (번호 메뉴에 가장 견고함, 권장)

B) **버튼으로 번호 직접 전송** — YES=1, NO=제시된 "거부" 번호를 눌러 해당 숫자 키 전송 (엔코더 미사용)

C) **엔코더는 이번 범위에서 제외** — 단순 yes/no만 처리, 번호 메뉴 대응은 후속 과제로

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4 — OLED 화면(역방향 피드백)
BindDeck에는 SSD1306 OLED가 있습니다. Claude 세션 상태를 여기에 표시할까요?

A) **예 — Claude 상태 표시** — 대기(승인 필요)/작업 중/유휴 및 마지막 답변을 `CMD:MSG:`/텔레메트리 라인으로 OLED에 표시 (권장)

B) **아니오 — OLED 미사용** — 입력(버튼/엔코더)만 사용, 화면 피드백은 이번 범위에서 제외

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5 — BindDeck 부가 기능(BLE HID / Wi-Fi UDP) 처리
BindDeck 펌웨어는 USB 시리얼 외에 **BLE HID 키보드**와 **Wi-Fi UDP**(하드코딩된 SSID/비밀번호 포함)도 동작합니다. 이번 리빌드에서 어떻게 할까요?

A) **USB 시리얼만 유지, BLE·Wi-Fi 제거** — 하드코딩 크리덴셜/텔레메트리/HID 매크로 제거로 단순·안전화 (권장)

B) **USB 시리얼 기본, Wi-Fi/BLE는 옵션(기본 비활성)** — 코드는 두되 컴파일 플래그로 꺼둠

C) **원본 그대로 전부 유지** — 하드코딩 Wi-Fi 크리덴셜 포함 (⚠️ 크리덴셜 노출 위험)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6 — Claude 세션 상태 읽기 방식
버튼으로 보낸 답이 반영됐는지, 지금 승인이 필요한지 등 Claude의 상태를 어떻게 감지할까요? (Codex의 sqlite/jsonl 파싱을 대체)

A) **Claude Hooks 우선 + `.jsonl` 트랜스크립트 폴백** — Notification/Stop/PostToolUse 훅으로 상태 신호를 받고, 훅이 없을 때 `~/.claude/projects/**/*.jsonl`로 보완 (이전 gpt-astra 자문 결론, 권장)

B) **`.jsonl` 트랜스크립트만 파싱** — 훅 설정 없이 전사 파일 tail만으로 상태 추정

C) **상태 읽기 없음(전송만)** — 버튼→PTY 전송만 하고 상태 표시는 하지 않음

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 7 — 호스트 연결 트랜스포트
브라우저(또는 호스트)와 BindDeck 간 연결 방식은?

A) **브라우저 Web Serial (USB)** — 현행 `serial.js` 구조 재사용, 별도 설치 불필요 (권장)

B) **Python 호스트가 시리얼을 직접 열기** — 브라우저 대신 서버가 시리얼 포트를 읽고 PTY로 전달

C) **Wi-Fi UDP 브릿지** — 무선(UDP 4210/4211)으로 이벤트 수신

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

# 확장(Extensions) 적용 여부

> AI-DLC 확장 규칙입니다. 이 프로젝트(로컬 개발 도구/PoC 성격)에 어떤 기준을 적용할지 선택해 주세요.

## Question 8 — 보안 확장 (Security Extensions)
이 프로젝트에 보안 확장 규칙을 (블로킹 제약으로) 적용할까요?

A) 예 — 모든 SECURITY 규칙을 블로킹 제약으로 강제 (프로덕션급 애플리케이션에 권장)

B) 아니오 — SECURITY 규칙 전체 생략 (PoC·프로토타입·실험 프로젝트에 적합)

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 9 — 복원력 확장 (Resiliency Extensions)
복원력(Resiliency) 베이스라인을 이 프로젝트에 적용할까요?

**이 확장의 성격**: 활성화하면 AWS Well-Architected(신뢰성 기둥) 기반의 **설계 단계 모범사례(방향성 가이드)** 세트를 요구사항/설계/코드에 반영합니다(내결함성·고가용성·관측성·복구성 등 15개 영역). **이것만으로 프로덕션 준비 완료를 보장하지는 않으며**, 정식 Well-Architected 리뷰의 대체물이 아닌 **좋은 출발점**입니다.

A) 예 — 복원력 베이스라인을 설계 단계 방향성 가이드로 적용 (비즈니스 크리티컬 워크로드에 권장; 이후 검증·강화 전제)

B) 아니오 — 복원력 베이스라인 생략 (빠른 반복이 더 중요한 PoC·프로토타입·실험 프로젝트에 적합)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 10 — 속성 기반 테스트 확장 (Property-Based Testing)
속성 기반 테스트(PBT) 규칙을 이 프로젝트에 적용할까요?

A) 예 — 모든 PBT 규칙을 블로킹 제약으로 강제 (비즈니스 로직·데이터 변환·직렬화·상태 저장 컴포넌트가 있는 프로젝트에 권장)

B) 부분 — 순수 함수와 직렬화 왕복(round-trip)에 대해서만 PBT 적용 (알고리즘 복잡도가 제한적인 프로젝트에 적합)

C) 아니오 — PBT 규칙 전체 생략 (단순 CRUD·UI 전용·비즈니스 로직이 거의 없는 얇은 통합 계층에 적합)

X) Other (please describe after [Answer]: tag below)

[Answer]: B
