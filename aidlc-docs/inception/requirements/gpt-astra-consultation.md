# GPT arsta mid 자문 기록 (Requirements Analysis)

> 사용자 지시("애매한건 정리해서 GPT arsta mid에게 물어보고 자동진행해")에 따라, 설치된 GPT(Codex CLI `codex exec`, `model_reasoning_effort=medium`, read-only 샌드박스)에게 10개 결정 사항을 정리해 자문했습니다. 아래는 그 응답 원문입니다. 이 판단 + AI 권장안을 합쳐 `requirement-verification-questions.md`의 답을 자동 확정했습니다.

- **일시**: 2026-09-08
- **호출**: `codex exec -s read-only --skip-git-repo-check -c model_reasoning_effort="medium"`
- **자문 프롬프트 요지**: Button Lab(Codex→Claude 리타겟) + 하드웨어 BindDeck(ESP32 매크로패드) 전제에서 Q1~Q10에 대한 판단 요청.

## 자문 응답 (원문)

권고안은 다음과 같습니다.

- **Q1: A** — BindDeck 펌웨어를 필요한 기능만 남겨 슬림화하고 `serial.js`도 함께 맞추는 것이 프로토콜·OLED·엔코더를 안정적으로 통제한다.
- **Q2: A + C** — BTN0=YES, BTN1=NO, BTN2=STOP(Esc)로 제한한다. ALWAYS는 오승인 위험이 있어 PoC 기본값에서 제외한다.
- **Q3: A** — 엔코더 회전은 `↑/↓`, push(BTN8)는 `Enter`로 매핑한다. 번호 키를 직접 보내기보다 실제 메뉴 선택 상태와 일치한다.
- **Q4: A** — OLED에 `waiting/active/idle`과 마지막 동작을 표시해 물리 장치의 상태를 즉시 확인한다.
- **Q5: A** — USB-serial만 사용하고 BLE/Wi‑Fi 및 하드코딩된 자격증명을 제거한다. localhost PoC에 네트워크 경로는 불필요하다.
- **Q6: A** — Hooks를 주 경로로 사용하고, 누락·재시작·상태 복구 시 `.jsonl`을 fallback으로 파싱한다. 단, 실제 번호 메뉴 입력은 PTY에 전송한다.
- **Q7: A** — 기존 SPA 구조와 가장 잘 맞고, 별도 Python serial 데몬이나 UDP 브리지가 필요 없다.
- **Q8: B** — localhost 단일 개발자 PoC이므로 AI-DLC의 전면 보안 게이트는 과하다. 다만 Wi‑Fi 제거와 입력 검증은 구현한다.
- **Q9: A** — 전체 AWS 수준의 문서화가 아니라, 재연결·타임아웃·중복 입력 방지·안전한 초기 상태만 적용한다.
- **Q10: B** — 순수 매핑 함수와 serial/telemetry 직렬화 round-trip만 property-based test로 검증해 비용 대비 효과를 확보한다.

실제로 Claude 메뉴가 `1. Yes / 2. Yes, don't ask again / 3. No`라면 YES 버튼은 무조건 `1`, NO 버튼은 `3`을 보내야 한다. `2`(always)는 별도 명시적 기능으로만 허용하는 편이 안전하다.

사용자만 결정해야 할 사항은 `ALWAYS` 버튼을 둘지, `STOP` 버튼의 물리적 위치와 동작감, OLED 표시 형식 정도다.

## AI 확정 (자문 반영)
- Q1=A, Q2=A+C(STOP 포함, ALWAYS 제외), Q3=A, Q4=A, Q5=A, Q6=A, Q7=A, Q8=B, Q9=A(적용 가능 범위만), Q10=B(부분).
- **엔코더 매핑 정정**: Q3의 "회전=↑/↓, push=Enter"가 GPT의 최종 권고이며 채택. 단, 단순 y/n 프롬프트에서는 YES/NO 버튼이 직접 `y`/`n`(또는 메뉴의 1/3)을 보내는 빠른 경로를 함께 제공.
- **사용자 재량 항목**(ALWAYS 버튼 유무, STOP 물리 배치, OLED 표시 형식)은 기본값으로 진행하되 언제든 변경 가능하도록 요구사항에 명시.
