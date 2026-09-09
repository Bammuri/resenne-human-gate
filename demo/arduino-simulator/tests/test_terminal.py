import base64
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal import WebTerminal


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.terminal = WebTerminal(None, self.temp.name)

    def tearDown(self):
        self.terminal.stop()
        self.temp.cleanup()

    def wait_for_output(self, text):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = self.terminal.snapshot()
            data = base64.b64decode(snapshot['data']).decode(errors='replace')
            if text in data:
                return snapshot
            time.sleep(.03)
        self.fail(f'Expected terminal output not received: {text!r}')

    def test_real_pty_input_output_resize_and_exit(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            snapshot = self.terminal.start('shell', 81, 23)
        generation = snapshot['generation']
        self.terminal.write("printf 'PTY_%s\\n' 'WORKS'\r", generation)
        self.wait_for_output('PTY_WORKS')
        self.terminal.resize(99, 31, generation)
        self.terminal.write('stty size\r', generation)
        self.wait_for_output('31 99')
        self.terminal.write("printf 'PWD_%s\\n' \"$PWD\"\r", generation)
        self.wait_for_output('PWD_' + str(Path(self.temp.name).resolve()))
        current = self.terminal.snapshot()
        self.assertEqual(self.terminal.snapshot(current['cursor'], current['generation'])['data'], '')
        self.terminal.stop(generation)
        self.assertFalse(self.terminal.snapshot()['running'])

    def test_ai_buttons_launch_interactive_clis_in_real_pty(self):
        cli = Path(self.temp.name) / 'fake-ai'
        cli.write_text("#!/usr/bin/env python3\nimport sys, json, os\nprint('CLI_READY', json.dumps(sys.argv[1:]), os.isatty(0), os.isatty(1), flush=True)\nwhile True:\n line = sys.stdin.readline()\n if not line: break\n print('INPUT:' + line, flush=True)\n")
        cli.chmod(0o700)
        self.terminal.codex = self.terminal.claude = str(cli)
        for kind in ['codex', 'codex-yolo', 'claude', 'claude-yolo']:
            with self.subTest(kind=kind):
                snapshot = self.terminal.start(kind, 81, 23)
                snapshot = self.wait_for_output('CLI_READY')
                self.assertFalse(snapshot['managed'])
                output = base64.b64decode(snapshot['data']).decode()
                self.assertIn('True True', output)
                self.assertNotIn('app-server', output)
                self.assertNotIn('--print', output)
                flag = '--dangerously-skip-permissions' if kind.startswith('claude') else '--dangerously-bypass-approvals-and-sandbox'
                self.assertEqual(flag in output, kind.endswith('yolo'))
                self.terminal.write('hello-cli\r', snapshot['generation'])
                self.wait_for_output('INPUT:hello-cli')
                self.terminal.stop(snapshot['generation'])

    def test_button_input_rejects_a_changed_terminal_screen(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            initial = self.terminal.start('shell')
        self.terminal.write("printf 'SCREEN_%s\\n' 'CHANGED'\r", initial['generation'])
        current = self.wait_for_output('SCREEN_CHANGED')
        with self.assertRaisesRegex(ValueError, '화면이 바뀌었습니다'):
            self.terminal.write('1\r', current['generation'], expected_cursor=current['cursor'] - 1)
        with self.assertRaises(ValueError):
            self.terminal.write('1\r', current['generation'], expected_cursor=True)

    def test_stale_generation_cannot_type_or_stop_a_new_terminal(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            old = self.terminal.start('shell')['generation']
            self.terminal.stop(old)
            new = self.terminal.start('shell')['generation']
        self.assertNotEqual(old, new)
        for operation in [lambda: self.terminal.write('echo stale\r',old), lambda: self.terminal.stop(old), lambda: self.terminal.resize(80,24,old)]:
            with self.assertRaises(ValueError): operation()
        self.assertTrue(self.terminal.snapshot()['running'])

    def test_plain_shell_is_not_a_codex_button_target(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            self.terminal.start('shell')
        with self.assertRaises(ValueError): self.terminal.target_thread()
        with self.assertRaises(ValueError): self.terminal.start('shell')

    def test_rejects_unknown_kind_and_reasoning_effort(self):
        with self.assertRaisesRegex(ValueError, '종류'):
            self.terminal.start('editor')
        with self.assertRaisesRegex(ValueError, '추론 강도'):
            self.terminal.start('shell', effort='extreme')
        with self.assertRaisesRegex(ValueError, 'Codex CLI'):
            self.terminal.start('codex-yolo')


if __name__ == '__main__':
    unittest.main()
