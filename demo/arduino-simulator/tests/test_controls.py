import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controls import ControlSettings, ConversationQuestions, defaults
from server import SimulatorServer
from workflow import Workflow, button_questions


class SettingsTests(unittest.TestCase):
    def test_settings_survive_restart_and_are_separate_per_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ControlSettings('/project/a', directory)
            value = defaults()
            value['mode'] = 'custom'
            value['custom'][0].update(label='현재 변경 설명', text='수정한 파일을 설명해 주세요.')
            settings.save(value)
            self.assertEqual(ControlSettings('/project/a', directory).snapshot(), value)
            self.assertEqual(ControlSettings('/project/b', directory).snapshot(), defaults())
            self.assertEqual(settings.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_update_cannot_destroy_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ControlSettings('/project', directory)
            saved = settings.save(defaults())
            bad = defaults()
            bad['custom'][0]['action'] = 'arbitrary-shell'
            with self.assertRaises(ValueError):
                settings.save(bad)
            self.assertEqual(ControlSettings('/project', directory).snapshot(), saved)


class QuestionTests(unittest.TestCase):
    def test_workflow_answers_are_sequential_and_invalidate_old_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Workflow('fake', directory)
            workflow.requirements = '프로젝트 목표'
            workflow.run_id = 'run-one'
            workflow.plan = 'old plan'
            workflow.approval = 'old approval'
            workflow.results = {'initialization': 'keep context', 'inception': 'old plan'}
            text = '<button-questions>' + json.dumps({'questions': [
                {'prompt': '저장 방식을 선택해 주세요.', 'options': ['파일', 'DB']},
                {'prompt': '화면을 선택해 주세요.', 'options': ['웹', '터미널']},
            ]}) + '</button-questions>'
            workflow.questions = button_questions(text, workflow.run_id)
            first = workflow.snapshot()['question']
            with self.assertRaises(ValueError):
                workflow.answer('stale', first['id'], '2')
            with self.assertRaises(ValueError):
                workflow.answer('run-one', first['id'], '7')
            workflow.answer('run-one', first['id'], '2')
            self.assertIn('답변: 2. DB', workflow.requirements)
            self.assertFalse(workflow.plan)
            self.assertFalse(workflow.approval)
            self.assertEqual(workflow.results, {'initialization': 'keep context'})
            with self.assertRaises(ValueError):
                workflow.answer('run-one', first['id'], '2')
            second = workflow.snapshot()['question']
            self.assertEqual(second['index'], 2)
            workflow.answer('run-one', second['id'], '1')
            self.assertIsNone(workflow.snapshot()['question'])
            self.assertIn('답변: 1. 웹', workflow.requirements)

    def test_question_parser_ignores_malformed_or_unrequested_lists(self):
        self.assertFalse(button_questions('변경 내역\n1. 버그 수정\n2. 문서 수정', 'one'))
        for data in ['null', '[]', '{"questions":[null]}', '{"questions":[{"prompt":"?", "options":[1,2]}]}']:
            self.assertFalse(button_questions(f'<button-questions>{data}</button-questions>', 'one'))

    def test_existing_conversation_does_not_revive_answered_or_outdated_question(self):
        class Reader:
            def snapshot(self):
                return current
        current = {'available': True, 'generation': 'g1', 'status': 'idle', 'events': [
            {'id': 1, 'kind': 'assistant', 'text': '어떻게 진행할까요?\n1. 구현\n2. 계획 수정'}]}
        questions = ConversationQuestions(Reader())
        question = questions.snapshot()['question']
        self.assertIsNotNone(question)
        questions.resolve(question['id'])
        self.assertIsNone(questions.snapshot()['question'])
        current['events'][0]['id'] = 2
        self.assertIsNotNone(questions.snapshot()['question'])
        current['events'].append({'id': 3, 'kind': 'user', 'text': '2'})
        self.assertIsNone(questions.snapshot()['question'])


class ControlsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = SimulatorServer(('127.0.0.1', 0), 'existing-thread', '/fake/codex', self.temp.name, self.temp.name)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.terminal.stop()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def request(self, path, payload=None, token=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Simulator-Token'] = self.server.token
        connection.request('GET' if payload is None else 'POST', path, None if payload is None else json.dumps(payload), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_config_api_and_token_checks(self):
        for path in ['/api/controls', '/api/questions?target=current']:
            self.assertEqual(self.request(path, token=False)[0], 403)
        value = defaults()
        value['mode'] = 'agent'
        self.assertEqual(self.request('/api/controls', value), (200, value))
        self.assertEqual(self.request('/api/controls'), (200, value))
        self.assertEqual(self.request('/api/controls', {'mode': 'custom', 'custom': []})[0], 400)

    def test_workflow_answer_retries_do_not_consume_next_question(self):
        workflow = self.server.workflow
        workflow.run_id = 'run1'
        workflow.requirements = 'goal'
        workflow.questions = button_questions('어떻게 진행할까요?\n1. 시작\n2. 보류', 'run1')
        question = workflow.questions[0]
        payload = {'action': 'answer', 'target': 'workflow', 'generation': 'run1', 'requestId': 'press1', 'questionId': question['id'], 'choice': '2'}
        first = self.request('/api/command', payload)
        self.assertEqual(first[0], 200)
        self.assertEqual(self.request('/api/command', payload), first)
        self.assertEqual(workflow.requirements.count('답변:'), 1)
        payload['choice'] = '1'
        self.assertEqual(self.request('/api/command', payload)[0], 409)

    @patch('server.subprocess.run')
    def test_external_answer_is_bound_to_question_and_generation(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '', '')
        question = {'id': 'question1', 'prompt': '선택하세요', 'options': [{'id': '1', 'label': '진행'}, {'id': '2', 'label': '보류'}]}
        snap = {'ready': True, 'generation': 'external1', 'question': question}
        with patch.object(self.server.questions, 'snapshot', return_value=snap):
            payload = {'action': 'answer', 'target': 'current', 'generation': 'old', 'requestId': 'p1', 'questionId': 'question1', 'choice': '2'}
            self.assertEqual(self.request('/api/command', payload)[0], 409)
            run.assert_not_called()
            payload.update(generation='external1', requestId='p2')
            self.assertEqual(self.request('/api/command', payload)[0], 200)
        self.assertEqual(run.call_args.args[0][-1], '선택하세요\n답변: 2. 보류')
        self.assertIn('question1', self.server.questions.resolved)

    @patch('server.subprocess.run', side_effect=subprocess.TimeoutExpired('codex', 20))
    def test_uncertain_custom_prompt_is_not_sent_twice(self, run):
        snap = {'ready': True, 'generation': 'external1', 'question': None}
        with patch.object(self.server.questions, 'snapshot', return_value=snap):
            payload = {'action': 'prompt', 'target': 'current', 'generation': 'external1', 'requestId': 'p1', 'text': '상태를 알려 주세요.'}
            self.assertEqual(self.request('/api/command', payload)[0], 504)
            self.assertEqual(self.request('/api/command', payload)[0], 504)
        run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
