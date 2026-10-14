import unittest
from unittest.mock import patch

from scripts.chat_input import read_message


class ChatInputTests(unittest.TestCase):
    def read(self, lines, multiline=False):
        with patch('builtins.input', side_effect=lines), patch('builtins.print'):
            return read_message(multiline)

    def test_single_line_still_sends(self):
        self.assertEqual(self.read(['hello']), 'hello')

    def test_paste_preserves_blank_lines_and_indentation(self):
        self.assertEqual(self.read(['/paste', '问题描述', '', 'def f():', '    return 1', '/send']),
                         '问题描述\n\ndef f():\n    return 1')

    def test_multiline_does_not_send_on_first_enter(self):
        self.assertEqual(self.read(['first', 'second', '/send'], True), 'first\nsecond')

    def test_commands_and_cancel(self):
        self.assertEqual(self.read(['/exit'], True), '/exit')
        self.assertEqual(self.read(['/paste', 'draft', '/cancel']), '')

    def test_eof_discards_unfinished_block(self):
        with self.assertRaises(EOFError):
            self.read(['/paste', 'draft', EOFError()])


if __name__ == '__main__':
    unittest.main()
