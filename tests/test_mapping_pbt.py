"""Property-based tests for the action -> keystroke mapping (terminal.py).

Covers PBT-08 (send_choice totality: only mapped actions are ever accepted) and
PBT-09 (consistency: every mapped action writes exactly its configured keys).
Requires the test-only `hypothesis` dependency (see aidlc-docs build-and-test).
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from hypothesis import assume, given, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal import ACTION_KEYS, ACTIONS, PROMPT_ACTIONS, WebTerminal

# Actions whose delivery is recorded for the OLED (server.handle_press); must be
# a subset of the mapped actions or the state feedback would send unknown labels.
ANSWER_ACTIONS = frozenset({"yes", "no", "stop", "confirm"})


class MappingPropertyTests(unittest.TestCase):
    def test_action_tables_are_the_single_source_of_truth(self):
        self.assertEqual(ACTIONS, tuple(ACTION_KEYS))
        self.assertTrue(all(isinstance(keys, str) and keys for keys in ACTION_KEYS.values()))
        self.assertTrue(PROMPT_ACTIONS <= set(ACTIONS))
        self.assertTrue(ANSWER_ACTIONS <= set(ACTIONS))

    def test_every_mapped_action_writes_exactly_its_keys(self):
        # PBT-09: consistency over the (finite) mapped-action domain.
        for action, keys in ACTION_KEYS.items():
            terminal = WebTerminal(None)
            with patch.object(terminal, "write") as write:
                self.assertEqual(terminal.send_choice(action), {"action": action, "status": "sent"})
                write.assert_called_once_with(keys, "")

    @given(st.text())
    def test_unmapped_actions_are_always_rejected_before_any_write(self, action):
        # PBT-08: totality — nothing outside ACTION_KEYS is ever sent to the PTY.
        assume(action not in ACTION_KEYS)
        terminal = WebTerminal(None)
        with patch.object(terminal, "write") as write:
            with self.assertRaises(ValueError):
                terminal.send_choice(action)
            write.assert_not_called()

    @given(st.one_of(st.integers(), st.none(), st.booleans(), st.lists(st.text()), st.binary()))
    def test_non_string_actions_are_rejected(self, action):
        terminal = WebTerminal(None)
        with patch.object(terminal, "write") as write:
            with self.assertRaises((ValueError, TypeError)):
                terminal.send_choice(action)
            write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
