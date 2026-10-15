import unittest
from unittest.mock import MagicMock, patch

from scripts.chat_input import _normalize_exit, _read_windows_tty, read_message


class ChatInputTests(unittest.TestCase):
    def read(self, lines, multiline=False):
        # Force fallback path (no tty smart reader) so unit tests stay deterministic
        stdin = MagicMock()
        stdin.isatty.return_value = False
        stdout = MagicMock()
        stdout.isatty.return_value = False
        with patch.dict('os.environ', {'REVIEWAGENT_SMART_INPUT': '0'}), \
                patch('sys.stdin', stdin), patch('sys.stdout', stdout), \
                patch('builtins.input', side_effect=lines), patch('builtins.print'), \
                patch('scripts.chat_input._drain_stdin_lines', return_value=[]):
            return read_message(multiline, network='auto')

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

    def test_exit_without_slash(self):
        self.assertEqual(self.read(['exit']), '/exit')
        self.assertEqual(self.read(['quit']), '/exit')

    def test_eof_discards_unfinished_block(self):
        with self.assertRaises(EOFError):
            self.read(['/paste', 'draft', EOFError()])

    def test_normalize_exit(self):
        self.assertEqual(_normalize_exit('exit'), '/exit')
        self.assertEqual(_normalize_exit('EXIT'), '/exit')
        self.assertEqual(_normalize_exit('/quit'), '/exit')
        self.assertEqual(_normalize_exit('quit'), '/exit')


class WindowsSmartInputTests(unittest.TestCase):
    def _run_keys(self, keys, shift_on_enter=False):
        """Simulate msvcrt.getwch sequence. keys: list of chars; Enter is '\\r'."""
        queue = list(keys)

        def getwch():
            if not queue:
                raise EOFError('no more keys')
            return queue.pop(0)

        msvcrt = MagicMock()
        msvcrt.getwch = getwch
        msvcrt.kbhit = MagicMock(return_value=False)

        shift_calls = {'n': 0}

        def shift_down():
            # Only true for the first Enter if requested
            if shift_on_enter and shift_calls['n'] == 0:
                shift_calls['n'] += 1
                return True
            return False

        stdout = MagicMock()
        with patch.dict('sys.modules', {'msvcrt': msvcrt}), \
                patch('scripts.chat_input._shift_down', side_effect=shift_down), \
                patch('scripts.chat_input.time.sleep'), \
                patch('sys.stdout', stdout), \
                patch('builtins.print'):
            return _read_windows_tty('> ')

    def test_enter_sends(self):
        self.assertEqual(self._run_keys(list('hi') + ['\r']), 'hi')

    def test_shift_enter_then_enter(self):
        # first \r with shift → newline; second \r without → send
        keys = list('ab') + ['\r'] + list('cd') + ['\r']
        self.assertEqual(self._run_keys(keys, shift_on_enter=True), 'ab\ncd')

    def test_paste_newlines_do_not_submit(self):
        # Simulate Ctrl+V flood: line1\\r line2\\r then idle Enter to send.
        # After each paste \\r, kbhit is True (more chars queued).
        keys = list('L1') + ['\r'] + list('L2') + ['\r'] + list('L3') + ['\r']
        # pending map: True for first two Enters (paste), False for final send Enter
        pending_flags = [True, True, False]

        queue = list(keys)

        def getwch():
            return queue.pop(0)

        msvcrt = MagicMock()
        msvcrt.getwch = getwch
        msvcrt.kbhit = MagicMock(side_effect=lambda: pending_flags.pop(0) if pending_flags else False)

        stdout = MagicMock()
        with patch.dict('sys.modules', {'msvcrt': msvcrt}), \
                patch('scripts.chat_input._shift_down', return_value=False), \
                patch('scripts.chat_input.time.sleep'), \
                patch('sys.stdout', stdout), \
                patch('builtins.print'):
            result = _read_windows_tty('> ')
        self.assertEqual(result, 'L1\nL2\nL3')

    def test_bracketed_paste_newlines(self):
        # ESC[200~ a \\r b ESC[201~ then Enter to send
        keys = (
            ['\x1b', '[', '2', '0', '0', '~']
            + list('a') + ['\r'] + list('b')
            + ['\x1b', '[', '2', '0', '1', '~']
            + ['\r']
        )
        queue = list(keys)

        def getwch():
            return queue.pop(0)

        msvcrt = MagicMock()
        msvcrt.getwch = getwch
        msvcrt.kbhit = MagicMock(return_value=False)

        stdout = MagicMock()
        with patch.dict('sys.modules', {'msvcrt': msvcrt}), \
                patch('scripts.chat_input._shift_down', return_value=False), \
                patch('scripts.chat_input.time.sleep'), \
                patch('sys.stdout', stdout), \
                patch('builtins.print'):
            result = _read_windows_tty('> ')
        self.assertEqual(result, 'a\nb')

    def test_exit_token(self):
        self.assertEqual(self._run_keys(list('exit') + ['\r']), '/exit')

    def test_ctrl_c_raises(self):
        with self.assertRaises(KeyboardInterrupt):
            self._run_keys(['\x03'])


if __name__ == '__main__':
    unittest.main()
