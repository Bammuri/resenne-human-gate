import base64
from pathlib import Path
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal import ACTION_KEYS, ACTIONS, PROMPT_ACTIONS, WebTerminal


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

    def wait_until(self, predicate, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.03)
        self.fail(message)

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

    def test_stale_generation_cannot_type_or_stop_a_new_terminal(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            old = self.terminal.start('shell')['generation']
            self.terminal.stop(old)
            new = self.terminal.start('shell')['generation']
        self.assertNotEqual(old, new)
        for operation in [lambda: self.terminal.write('echo stale\r', old), lambda: self.terminal.stop(old), lambda: self.terminal.resize(80, 24, old)]:
            with self.assertRaises(ValueError):
                operation()
        self.assertTrue(self.terminal.snapshot()['running'])

    def test_only_shell_and_claude_kinds_are_allowed(self):
        # No CLI configured, so a shell PTY is never a Claude answer target.
        self.assertFalse(self.terminal.claude_ready())
        with self.assertRaises(ValueError):
            self.terminal.start('claude')   # claude CLI not found
        for kind in ('codex', 'codex-yolo', 'bash', ''):
            with self.assertRaises(ValueError):
                self.terminal.start(kind)
        self.assertFalse(self.terminal.snapshot()['running'])
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            self.terminal.start('shell')
        self.assertFalse(self.terminal.claude_ready())   # a shell is not Claude
        with self.assertRaises(ValueError):
            self.terminal.start('shell')                 # already running

    def test_claude_session_reports_ready_until_stopped(self):
        # Use `cat` as a stand-in long-lived "claude" so a real PTY is exercised.
        cat = shutil.which('cat') or '/bin/cat'
        terminal = WebTerminal(cat, self.temp.name)
        self.addCleanup(terminal.stop)
        snapshot = terminal.start('claude', 81, 23)
        self.assertEqual(snapshot['kind'], 'claude')
        self.wait_until(terminal.claude_ready, 'claude session never became ready')
        terminal.stop()
        self.assertFalse(terminal.claude_ready())

    def test_claude_can_be_launched_from_an_argv_list(self):
        # server.py --mock passes claude as an argv list ([python, demo/fake_claude.py]);
        # both a single path (real CLI) and a list must launch a Claude answer target.
        argv = [sys.executable, '-c', 'import sys; sys.stdin.read()']
        terminal = WebTerminal(argv, self.temp.name)
        self.addCleanup(terminal.stop)
        snapshot = terminal.start('claude', 81, 23)
        self.assertEqual(snapshot['kind'], 'claude')
        self.wait_until(terminal.claude_ready, 'claude session (argv list) never became ready')
        terminal.stop()
        self.assertFalse(terminal.claude_ready())

    def test_send_choice_maps_every_action_to_its_key_sequence(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            generation = self.terminal.start('shell')['generation']
        with patch.object(self.terminal, 'write') as write:
            for action in ACTIONS:
                self.assertEqual(self.terminal.send_choice(action), {'action': action, 'status': 'sent'})
        self.assertEqual([call.args for call in write.call_args_list], [(ACTION_KEYS[action], generation) for action in ACTIONS])

    def test_send_choice_rejects_unknown_actions_and_stale_generation(self):
        with patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            generation = self.terminal.start('shell')['generation']
        with patch.object(self.terminal, 'write') as write:
            for action in ('maybe', 'y', 'YES', '', 'queue', None):
                with self.assertRaises(ValueError):
                    self.terminal.send_choice(action)
            with self.assertRaises(ValueError):
                self.terminal.send_choice('yes', generation + 'x')
            write.assert_not_called()

    def test_action_tables_are_consistent(self):
        self.assertEqual(ACTIONS, tuple(ACTION_KEYS))
        self.assertTrue(all(isinstance(keys, str) and keys for keys in ACTION_KEYS.values()))
        self.assertTrue(PROMPT_ACTIONS <= set(ACTIONS))


if __name__ == '__main__':
    unittest.main()
