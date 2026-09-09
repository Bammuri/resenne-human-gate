"""Stage-specific AI-DLC inputs and durable Markdown artifacts."""
import json
import os
from pathlib import Path
import tempfile

SCHEMA = {
    'initialization': ('INITIALIZATION · 프로젝트 초기화', '01-initialization.md', [
        ('project', '프로젝트 · 작업 유형', '신규 개발 / 기존 기능 개선 / 버그 수정 중 무엇인가요?'),
        ('workspace', '코드 구조 · 참고 문서', '주요 모듈, 진입점, 확인할 파일·문서 경로'),
        ('environment', '개발 환경 · 실행 방법', '언어·프레임워크, 설치·실행 명령, 장치 구성. 비밀 키는 입력하지 마세요.'),
        ('rules', '작업 규칙 · 변경 금지 범위', '코딩 규칙, 보안·호환성 제약, 수정하면 안 되는 부분')]),
    'ideation': ('IDEATION · 문제와 가치 구체화', '02-ideation.md', [
        ('goal', '해결할 문제 · 기대 효과', '무엇을 왜 만드나요? 현재 불편과 달성할 효과를 적으세요.'),
        ('users', '사용자 · 사용 시나리오', '누가 언제 사용하며 어떤 흐름을 기대하나요?'),
        ('scope', '이번 범위 · 제외 범위', '이번에 포함할 기능과 다음으로 미룰 기능'),
        ('success', '성공 기준 · 우선순위', '측정 가능한 완료 기준, 중요도, 일정·비용 제약')]),
    'inception': ('INCEPTION · 요구사항과 실행 설계', '03-inception.md', [
        ('requirements', '사용자 스토리 · 인수 조건', '사용자로서 원하는 행동과 이를 만족했다고 판단할 조건'),
        ('decisions', '미결 질문 · 확정 답변', '모호한 점, 대안, 선택한 답변과 근거. AI 질문에도 여기에 답하세요.'),
        ('design', '구조 · 인터페이스 · 작업 단위', '설계 방향, API·데이터 모델, 수정할 모듈, 구현 순서와 의존성'),
        ('risks', '검증 전략 · 위험 · 복구 계획', '작업별 검사 방법, 예상 실패, 승인 조건, 되돌리는 방법')]),
    'construction': ('CONSTRUCTION · 구현과 검증', '04-construction.md', [
        ('unit', '이번에 구현할 작업 단위', '승인된 계획 중 이번에 진행할 작업과 완료 조건'),
        ('boundaries', '구현 지침 · 변경 범위', '수정 허용 범위, 호환성, 마이그레이션·코딩 규칙'),
        ('commands', '테스트 · 빌드 · 검사 명령', '단위·통합 테스트, lint, 타입 검사, 빌드 명령과 예상 결과'),
        ('cases', '경계 조건 · 실물 확인', '오류·회귀 시나리오, 실제 장치 등 AI가 직접 확인하지 못하는 항목')]),
    'operation': ('OPERATION · 인수와 운영 준비', '05-operation.md', [
        ('acceptance', '인수 판단 · 남은 결함', '승인 / 수정 후 재검토 / 보류, 발견한 문제와 판단 근거'),
        ('release', '배포 대상 · 배포 전 조건', '운영 환경, 배포 절차, 담당자, 사전 점검. 실제 배포는 별도 승인 후 수행합니다.'),
        ('observability', '모니터링 · 장애 대응', '확인할 지표·로그, 알림 기준, 담당자와 장애 시 조치'),
        ('handoff', '사용 안내 · 복구 · 인수인계', '사용법, 롤백 절차, 운영 문서, 남은 작업')]),
}
HUMAN_ROLES = {
    'initialization': '최소 입력: 프로젝트·환경·공통 제약. 나머지 구조는 AI가 조사합니다.',
    'ideation': '사람이 목적·문제·대상·범위·우선순위를 정하고 Go / No-Go를 판단합니다.',
    'inception': 'AI의 요구사항·스토리·설계를 보정하고 실행 계획을 검토·승인합니다.',
    'construction': 'AI의 기술적 질문에 답하고, 테스트 근거와 변경 결과를 검토·승인합니다.',
    'operation': '운영 정책·장애·롤백 기준과 Production 승인 여부를 기록합니다. 이 앱은 배포 준비까지만 수행합니다.',
}
for stage, (_, _, fields) in SCHEMA.items():
    fields.append(('brief', '이 단계의 기준 · 지시', '필요한 내용만 자유롭게 작성하세요.'))
    fields.append(('instruction', '사람의 지시 · 판단 · 예외 처리', 'AI가 반드시 지킬 지시, 질문에 대한 답변, 선택한 대안과 이유를 적으세요. 저장 후 다음 실행에 반영합니다.'))
    if stage in ('ideation', 'construction', 'operation'):
        fields.append(('decision', {'ideation': '목표·범위 승인 · Go / No-Go', 'construction': '구현·검증 결과 승인', 'operation': 'Production 승인 판단 · 실제 배포는 별도'}[stage], '보류·거절은 자동 모드에서도 우선합니다.'))
DECISIONS = [('pending', '판단 대기'), ('approved', '승인 / Go'), ('hold', '보류 / No-Go'), ('rejected', '거절 / 수정 필요')]
DOC_DIRECTORY = 'aidlc-docs' 

def public_schema():
    return {stage: {'title': title, 'path': f'{DOC_DIRECTORY}/{filename}',
                    'humanRole': HUMAN_ROLES[stage], 'fields': [{'key': k, 'label': label, 'hint': hint, **({'options': [{'value': v, 'label': t} for v, t in DECISIONS]} if k == 'decision' else {})} for k, label, hint in fields]}
            for stage, (title, filename, fields) in SCHEMA.items()}

class WorkflowDocuments:
    def __init__(self, workspace):
        self.root = Path(workspace) / DOC_DIRECTORY

    def safe_root(self):
        if self.root.is_symlink():
            raise ValueError('aidlc-docs는 심볼릭 링크를 사용할 수 없습니다.')
        self.root.mkdir(exist_ok=True)

    def load(self):
        if self.root.is_symlink():
            raise ValueError('aidlc-docs는 심볼릭 링크를 사용할 수 없습니다.')
        path = self.root / '.workflow-state.json'
        if not path.exists():
            return {}
        if path.is_symlink() or path.stat().st_size > 1000000:
            raise ValueError('AI-DLC 저장 상태 파일을 확인해 주세요.')
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get('version') not in (1, 2):
            raise ValueError('지원하지 않는 AI-DLC 저장 상태입니다.')
        return data

    def write(self, filename, text):
        self.safe_root()
        path = self.root / filename
        if path.is_symlink():
            raise ValueError('AI-DLC 문서가 심볼릭 링크입니다.')
        fd, name = tempfile.mkstemp(prefix='.writing-', dir=self.root)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(text)
            os.replace(name, path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def save(self, inputs, results, plan, requirements, autonomy):
        # Check destinations before writing any artifact.
        self.safe_root()
        for name in ['.workflow-state.json'] + [v[1] for v in SCHEMA.values()]:
            if (self.root / name).is_symlink(): raise ValueError('AI-DLC 문서가 심볼릭 링크입니다.')
        for stage, (title, filename, fields) in SCHEMA.items():
            lines = [f'# {stage.capitalize()} · {title.split(" · ")[-1]}', '', '## 실행 규칙', '', HUMAN_ROLES[stage], '저장한 사람의 목표·제약·지시가 AI 제안보다 우선합니다. 보류·거절을 자동 승인으로 바꾸지 않습니다. 입력 변경 시 기존 후속 결과와 승인은 재검토합니다.', '', '## 사용자 입력', '']
            for key, label, _ in fields:
                if inputs.get(stage, {}).get('brief') and key not in ('brief', 'decision'): continue
                if key == 'brief' and 'brief' not in inputs.get(stage, {}): continue
                lines += [f'### {label}', '', inputs.get(stage, {}).get(key, '').strip() or '_미입력_', '']
            if stage == 'ideation' and requirements and not inputs.get('ideation', {}).get('goal'):
                lines += ['### 기존 목표', '', requirements, '']
            lines += ['## AI 결과', '', results.get(stage) or '_아직 실행하지 않았거나 입력 변경으로 재실행이 필요합니다._', '']
            if stage == 'inception' and plan:
                lines += ['## 검토할 계획', '', plan, '']
            self.write(filename, '\n'.join(lines))
        self.write('.workflow-state.json', json.dumps({'version': 2, 'inputs': inputs, 'results': results,
                   'plan': plan, 'requirements': requirements, 'autonomy': autonomy}, ensure_ascii=False, indent=2)+'\n')
