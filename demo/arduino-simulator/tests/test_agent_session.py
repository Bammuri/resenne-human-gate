import base64
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal import WebTerminal
from questions import parse_numbered_question


FAKE_CLI = r'''#!/usr/bin/env python3
import json,sys
claude='--print' in sys.argv
with open('args.json','w') as f: json.dump(sys.argv[1:],f)
def send(x):
 print(json.dumps(x),flush=True)
def emit(method,params):
 send({'method':method,'params':{'threadId':'thread-test',**params}})
def finish(text):
 if claude:
  send({'type':'stream_event','event':{'type':'message_start'}})
  send({'type':'stream_event','event':{'type':'content_block_delta','delta':{'type':'text_delta','text':text}}})
  send({'type':'assistant','message':{'id':'msg-1','content':[{'type':'text','text':text}]}})
  send({'type':'result','result':text,'is_error':False})
 else:
  emit('item/agentMessage/delta',{'itemId':'msg-1','delta':text})
  emit('item/completed',{'item':{'id':'msg-1','type':'agentMessage','text':text}})
  emit('turn/completed',{'turn':{'id':'turn-test','status':'completed'}})
for line in sys.stdin:
 m=json.loads(line)
 with open('wire.jsonl','a') as f: f.write(json.dumps(m)+'\n')
 if claude:
  if m.get('type')=='control_request':
   req=m['request']
   send({'type':'control_response','response':{'subtype':'success','request_id':m['request_id'],'response':{}}})
   if req['subtype']=='interrupt': send({'type':'result','is_error':True})
  elif m.get('type')=='user':
   text=m['message']['content']
   if text in ['approval','choices']:
    req={'subtype':'can_use_tool','tool_name':'Bash','input':{'command':'echo approved'}}
    if text=='choices': req.update(tool_name='AskUserQuestion',input={'questions':[{'question':'Choose color?','options':[{'label':'Red'},{'label':'Blue'}]},{'question':'Choose size?','options':[{'label':'Small'},{'label':'Large'}]}]})
    send({'type':'control_request','request_id':'provider-request','request':req})
   elif text=='long': pass
   else: finish('Which option do you choose?\n1. Red\n2. Blue' if text=='prose' else 'DONE:'+text)
  elif m.get('type')=='control_response': finish('REPLY:'+json.dumps(m['response']['response'],sort_keys=True))
 else:
  method=m.get('method')
  if method=='initialize': send({'id':m['id'],'result':{}})
  elif method=='thread/start': send({'id':m['id'],'result':{'thread':{'id':'thread-test'}}})
  elif method=='turn/start':
   send({'id':m['id'],'result':{'turn':{'id':'turn-test'}}})
   emit('turn/started',{'turn':{'id':'turn-test'}})
   text=m['params']['input'][0]['text']
   if text=='approval': send({'id':'provider-request','method':'item/commandExecution/requestApproval','params':{'threadId':'thread-test','turnId':'turn-test','command':'echo approved'}})
   elif text=='choices': send({'id':'provider-request','method':'item/tool/requestUserInput','params':{'threadId':'thread-test','turnId':'turn-test','questions':[{'id':'color','question':'Choose color?','options':[{'label':'Red'},{'label':'Blue'}]},{'id':'size','question':'Choose size?','options':[{'label':'Small'},{'label':'Large'}]}]}})
   elif text=='long': pass
   else: finish('Which option do you choose?\n1. Red\n2. Blue' if text=='prose' else 'DONE:'+text)
  elif method=='turn/interrupt':
   send({'id':m['id'],'result':{}})
   emit('turn/completed',{'turn':{'id':'turn-test','status':'interrupted'}})
  elif 'result' in m: finish('REPLY:'+json.dumps(m['result'],sort_keys=True))
'''


class QuestionTests(unittest.TestCase):
    def test_conservative_detection_and_full_option_count(self):
        self.assertIsNone(parse_numbered_question('Completed tasks:\n1. Setup\n2. Tests', 'x'))
        self.assertIsNone(parse_numbered_question('Choose an option:\n```\n1. Foo\n2. Bar\n```', 'x'))
        self.assertIsNone(parse_numbered_question('Choose:\n1. Foo\n3. Bar', 'x'))
        self.assertIsNone(parse_numbered_question('Choose:\n1. Foo\n2. Bar\nNext section:\n1. X\n2. Y', 'x'))
        text = '어떻게 진행할까요?\n' + '\n'.join(f'{i}. Choice {i}' for i in range(1, 10))
        question = parse_numbered_question(text, 'x')
        self.assertEqual(len(question['options']), 9)
        self.assertEqual(question['options'][-1]['id'], '9')
        self.assertEqual(question, parse_numbered_question(text, 'x'))
        self.assertNotEqual(question['id'], parse_numbered_question(text, 'y')['id'])


class ManagedSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cli = Path(self.temp.name) / 'fake-cli'
        self.cli.write_text(FAKE_CLI)
        self.cli.chmod(0o700)
        self.terminal = WebTerminal(str(self.cli), self.temp.name, claude=str(self.cli))
        self.serial = 0

    def tearDown(self):
        self.terminal.stop()
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            snapshot = self.terminal.snapshot()
            if predicate(snapshot):
                return snapshot
            time.sleep(.01)
        self.fail('Managed session did not reach expected state')

    def start(self, kind):
        self.terminal.start(kind, managed=True)
        snapshot = self.wait(lambda s: s['ready'])
        self.generation = snapshot['generation']

    def command(self, action, **kw):
        self.serial += 1
        return self.terminal.command(action, self.generation, kw.pop('request_id', f'test-{self.serial}'), **kw)

    def records(self):
        return [json.loads(line) for line in (Path(self.temp.name) / 'wire.jsonl').read_text().splitlines()]

    def transcript(self):
        return base64.b64decode(self.terminal.snapshot()['data']).decode()

    def test_service_modes_select_correct_provider_and_permissions(self):
        for kind in ['codex', 'codex-yolo', 'claude', 'claude-yolo']:
            with self.subTest(kind=kind):
                self.start(kind)
                args = json.loads((Path(self.temp.name) / 'args.json').read_text())
                if kind.startswith('claude'):
                    self.assertIn('--print', args)
                    self.assertEqual('--dangerously-skip-permissions' in args, kind.endswith('yolo'))
                    self.assertEqual(args[args.index('--permission-mode') + 1],
                                     'bypassPermissions' if kind.endswith('yolo') else 'default')
                    with self.assertRaises(ValueError):
                        self.terminal.target_thread()
                else:
                    self.assertIn('app-server', args)
                    params = [r['params'] for r in self.records() if r.get('method') == 'thread/start'][-1]
                    self.assertEqual(params['approvalPolicy'], 'never' if kind.endswith('yolo') else 'on-request')
                    self.assertEqual(params['sandbox'], 'danger-full-access' if kind.endswith('yolo') else 'workspace-write')
                self.command('prompt', text='approval')
                question = self.wait(lambda s: s['question'])['question']
                self.command('denied', question_id=question['id'])
                self.wait(lambda s: not s['busy'])
                self.terminal.stop()

    def test_codex_real_approval_response_is_scoped_and_idempotent(self):
        self.start('codex-yolo')
        self.command('prompt', text='approval')
        question = self.wait(lambda s: s['question'])['question']
        self.assertEqual(question['kind'], 'approval')
        with self.assertRaises(ValueError): self.command('accept', question_id='stale')
        with self.assertRaises(ValueError): self.terminal.command('accept', 'old-generation', 'id', question_id=question['id'])
        self.command('accept', question_id=question['id'], request_id='approve-once')
        again = self.command('accept', question_id=question['id'], request_id='approve-once')
        self.assertTrue(again['duplicate'])
        self.wait(lambda s: not s['busy'])
        self.assertEqual([m for m in self.records() if m.get('id')=='provider-request'], [
            {'id':'provider-request','result':{'decision':'accept'}}])
        self.assertEqual(self.transcript().count('REPLY:'), 1)
        with self.assertRaises(ValueError): self.command('denied', question_id=question['id'], request_id='approve-once')

    def test_codex_questions_are_answered_one_at_a_time(self):
        self.start('codex')
        self.command('prompt', text='choices')
        first = self.wait(lambda s: s['question'])['question']
        self.assertEqual((first['index'], first['total']), (1, 2))
        self.command('answer', question_id=first['id'], choice='2')
        second = self.terminal.snapshot()['question']
        self.assertEqual(second['index'], 2)
        with self.assertRaises(ValueError): self.command('answer', question_id=first['id'], choice='1')
        self.assertFalse(any('result' in r for r in self.records()))
        self.command('answer', question_id=second['id'], choice=1)
        self.wait(lambda s: not s['busy'])
        reply = next(r['result'] for r in self.records() if 'result' in r)
        self.assertEqual(reply, {'answers':{'color':{'answers':['Blue']},'size':{'answers':['Small']}}})

    def test_claude_answers_preserve_tool_input_and_permission_denial(self):
        self.start('claude-yolo')
        self.command('prompt', text='choices')
        question = self.wait(lambda s: s['question'])['question']
        self.command('answer', question_id=question['id'], choice='2')
        self.command('answer', question_id=self.terminal.snapshot()['question']['id'], text='Custom size')
        self.wait(lambda s: not s['busy'])
        replies = [r['response']['response'] for r in self.records() if r.get('type')=='control_response']
        self.assertEqual(replies[0]['behavior'], 'allow')
        self.assertEqual(replies[0]['updatedInput']['answers'], {'Choose color?':'Blue','Choose size?':'Custom size'})
        self.assertEqual(len(replies[0]['updatedInput']['questions']), 2)
        self.assertEqual(self.transcript().count('REPLY:'), 1)
        self.command('prompt', text='approval')
        question = self.wait(lambda s: s['question'])['question']
        self.command('denied', question_id=question['id'])
        self.wait(lambda s: not s['busy'])
        replies = [r['response']['response'] for r in self.records() if r.get('type')=='control_response']
        self.assertEqual(replies[-1]['behavior'], 'deny')

    def test_prose_menu_and_buffered_keyboard_input(self):
        self.start('codex-yolo')
        self.terminal.write('pro', self.generation)
        self.assertFalse(self.terminal.snapshot()['busy'])
        self.terminal.write('se\r', self.generation)
        question = self.wait(lambda s: s['question'])['question']
        self.assertTrue(question['id'].startswith('prose-'))
        self.command('answer', question_id=question['id'], choice='2')
        self.wait(lambda s: not s['busy'])
        self.assertIn('DONE:2. Blue', self.transcript())

    def test_claude_multiple_selections_return_joined_labels(self):
        self.cli.write_text(FAKE_CLI.replace("'question':'Choose color?','options'", "'question':'Choose color?','multiSelect':True,'options'"))
        self.start('claude-yolo')
        self.command('prompt', text='choices')
        question = self.wait(lambda s: s['question'])['question']
        self.assertTrue(question['multiSelect'])
        with self.assertRaises(ValueError): self.command('answer', question_id=question['id'], choice=['missing'])
        self.command('answer', question_id=question['id'], choice=['1', '2'])
        second = self.terminal.snapshot()['question']
        with self.assertRaises(ValueError): self.command('answer', question_id=second['id'], choice=['1', '2'])
        self.command('answer', question_id=second['id'], choice='1')
        self.wait(lambda s: not s['busy'])
        reply = next(r['response']['response'] for r in self.records() if r.get('type')=='control_response')
        self.assertEqual(reply['updatedInput']['answers']['Choose color?'], 'Red, Blue')

    def test_secret_keyboard_answer_is_masked_without_changing_wire_value(self):
        fake = FAKE_CLI.replace("'id':'color','question'", "'id':'color','isSecret':True,'question'")
        fake = fake.replace("elif 'result' in m: finish('REPLY:'+json.dumps(m['result'],sort_keys=True))",
                            "elif 'result' in m: finish('SECRET_ACCEPTED')")
        self.cli.write_text(fake)
        self.start('codex')
        self.command('prompt', text='choices')
        question = self.wait(lambda s: s['question'])['question']
        self.assertTrue(question['isSecret'])
        secret = 'test-PRIVATE-credential-42'
        self.terminal.write(secret, self.generation)
        self.assertNotIn(secret, self.transcript())
        self.assertIn('*' * len(secret), self.transcript())
        self.terminal.write('\r', self.generation)
        self.command('answer', question_id=self.terminal.snapshot()['question']['id'], choice='1')
        self.wait(lambda s: not s['busy'])
        reply = next(r['result'] for r in self.records() if 'result' in r)
        self.assertEqual(reply['answers']['color']['answers'], [secret])
        self.assertNotIn(secret, self.transcript())
        self.assertIn('[답변] 입력 완료', self.transcript())

    def test_available_approval_decisions_are_preserved(self):
        self.cli.write_text(FAKE_CLI.replace("'command':'echo approved'}})", "'command':'echo approved','availableDecisions':['acceptForSession','cancel']}})"))
        self.start('codex')
        self.command('prompt', text='approval')
        question = self.wait(lambda s: s['question'])['question']
        self.assertEqual([o['id'] for o in question['options']], ['acceptForSession', 'cancel'])
        with self.assertRaises(ValueError): self.command('accept', question_id=question['id'])
        self.command('answer', question_id=question['id'], choice='cancel')
        self.wait(lambda s: not s['busy'])
        reply = next(r['result'] for r in self.records() if 'result' in r)
        self.assertEqual(reply, {'decision':'cancel'})

    def test_stop_interrupts_current_turn_without_ending_session(self):
        for kind in ['codex-yolo', 'claude-yolo']:
            with self.subTest(kind=kind):
                self.start(kind)
                self.command('prompt', text='long')
                self.wait(lambda s: s['busy'] and (kind=='claude-yolo' or self.terminal.managed.turn))
                self.command('stop')
                snapshot = self.wait(lambda s: not s['busy'])
                self.assertTrue(snapshot['running'])
                self.assertTrue(snapshot['ready'])
                self.assertIsNone(snapshot['question'])
                self.command('prompt', text='next')
                self.wait(lambda s: not s['busy'])
                self.assertIn('DONE:next', self.transcript())
                self.terminal.stop()


if __name__ == '__main__':
    unittest.main()
