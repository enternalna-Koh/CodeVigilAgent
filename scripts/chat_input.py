"""Terminal chat input.

Windows TTY: Enter=send, Shift+Enter=newline, Ctrl+C=/exit, type exit+Enter.
Fallback: builtin input() + /paste (always works for Ctrl+C / exit).
"""

from __future__ import annotations

import os
import shutil
import sys
import time

from scripts.term_style import accent, brand, colors_enabled, enable_windows_ansi, mute, ok


def _frame_width():
    try:
        cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    except OSError:
        cols = 80
    return max(40, min(cols - 2, 72))


def _visible_len(text: str) -> int:
    n = 0
    for ch in text:
        n += 2 if ord(ch) > 0x2E80 else 1
    return n


def _pad_row(text, width):
    vis = _visible_len(text)
    if vis > width:
        out = ''
        for ch in text:
            trial = out + ch
            if _visible_len(trial) > width - 1:
                return out + '.'
            out = trial
        return out
    return text + (' ' * (width - vis))


def _can_box():
    enc = getattr(sys.stdout, 'encoding', None) or ''
    try:
        '╭│╰─'.encode(enc)
        return True
    except Exception:
        return False


def print_input_frame(network='auto', chat_mode='auto', session_lane='chat'):
    enable_windows_ansi()
    inner_w = _frame_width()
    tty = hasattr(sys.stdin, 'isatty') and sys.stdin.isatty()
    if chat_mode == 'auto':
        lane = '正式' if session_lane == 'work' else '日常'
        mode_tag = f'自动→{lane}'
        title_txt = f' * 自动分流  · 当前{lane}'
    else:
        mode_tag = {'chat': '钉住日常', 'work': '钉住正式'}.get(chat_mode, chat_mode)
        title_txt = {
            'chat': ' * 日常对话（已钉住）',
            'work': ' * 正式审查（已钉住）',
        }.get(chat_mode, ' * 对话')
    if sys.platform == 'win32' and _smart_input_wanted() and tty:
        hint_txt = f' {mode_tag} · 粘贴后Enter发送 · /mode auto · /exit'
    else:
        hint_txt = f' {mode_tag} · /mode auto · /paste · net={network}'
    title = _pad_row(title_txt, inner_w)
    hint = _pad_row(hint_txt, inner_w)
    print()
    if _can_box():
        top, bot, v = '╭' + '─' * inner_w + '╮', '╰' + '─' * inner_w + '╯', '│'
    else:
        top, bot, v = '+' + '-' * inner_w + '+', '+' + '-' * inner_w + '+', '|'
    try:
        print(brand(top))
        print(brand(v) + accent(title) + brand(v))
        print(brand(v) + mute(hint) + brand(v))
        print(brand(bot))
    except UnicodeEncodeError:
        print(brand('+' + '-' * inner_w + '+'))
        print(brand('|') + accent(title) + brand('|'))
        print(brand('|') + mute(hint) + brand('|'))
        print(brand('+' + '-' * inner_w + '+'))


def _smart_input_wanted() -> bool:
    """Default ON for Windows TTY; set REVIEWAGENT_SMART_INPUT=0 to force input()."""
    flag = (os.environ.get('REVIEWAGENT_SMART_INPUT') or '').strip().lower()
    if flag in ('0', 'false', 'off', 'no'):
        return False
    if flag in ('1', 'true', 'on', 'yes'):
        return True
    # default: enable on Windows interactive TTY
    return sys.platform == 'win32'


def _shift_down() -> bool:
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        # high bit set => key currently down
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
    except Exception:
        return False


def _normalize_exit(text: str) -> str:
    t = (text or '').strip().lower()
    if t in ('exit', 'quit', 'q', '/exit', '/quit', '/q'):
        return '/exit'
    return text


def _is_exit_token(text: str) -> bool:
    head = (text or '').strip().splitlines()[0].strip().lower() if text else ''
    return head in ('/exit', '/quit', '/q', 'exit', 'quit', 'q')


def _drain_stdin_lines(idle_sec: float = 0.2, extend_sec: float = 0.1) -> list:
    lines = []
    deadline = time.monotonic() + idle_sec
    while time.monotonic() < deadline:
        got = None
        try:
            if sys.platform == 'win32':
                import msvcrt
                if msvcrt.kbhit():
                    got = sys.stdin.readline()
            else:
                import select
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready:
                    got = sys.stdin.readline()
        except Exception:
            break
        if got:
            lines.append(got.rstrip('\r\n'))
            deadline = time.monotonic() + extend_sec
        else:
            time.sleep(0.015)
    return lines


def _read_paste_block():
    print()
    print(ok('╭─ 多行粘贴 ──────────────────────────────────╮'))
    print(ok('│ ') + mute('粘贴全文，然后单独一行输入 /send 发送'))
    print(ok('│ ') + mute('/cancel 取消 · /exit 退出对话'))
    print(ok('╰────────────────────────────────────────────╯'))
    lines = []
    while True:
        try:
            line = input(brand('… › ') if colors_enabled() else '..> ')
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise
        stripped = line.strip()
        if _is_exit_token(stripped):
            return '/exit'
        if stripped == '/send':
            return '\n'.join(lines).strip()
        if stripped == '/cancel':
            return ''
        lines.append(line)


def _pending_keys() -> bool:
    """True if more console keys are already buffered (typical during Ctrl+V paste)."""
    try:
        import msvcrt
        return bool(msvcrt.kbhit())
    except Exception:
        return False


def _emit_cont_prompt() -> None:
    cont = brand('… ') if colors_enabled() else '.. '
    sys.stdout.write(cont)
    sys.stdout.flush()


def _insert_newline(buf: list) -> None:
    buf.append('\n')
    sys.stdout.write('\n')
    sys.stdout.flush()
    _emit_cont_prompt()


def _read_escape_sequence() -> str:
    """Read CSI / paste markers after ESC. Returns full sequence without leading ESC."""
    import msvcrt
    parts = ['\x1b']
    # CSI often starts with '['
    try:
        nxt = msvcrt.getwch()
    except Exception:
        return ''
    parts.append(nxt)
    if nxt != '[':
        return ''.join(parts)
    # Read until letter / ~ terminator (bounded)
    for _ in range(32):
        try:
            c = msvcrt.getwch()
        except Exception:
            break
        parts.append(c)
        if c.isalpha() or c == '~':
            break
    return ''.join(parts)


def _read_windows_tty(prompt: str) -> str:
    """Enter=send; Shift+Enter / paste newlines=newline; Ctrl+C raises KeyboardInterrupt.

    Multiline Ctrl+V: newlines inside a paste must NOT submit. We detect:
    1) bracketed paste (\\x1b[200~ ... \\x1b[201~) when terminal supports it
    2) buffered keys after Enter (kbhit) — classic Windows paste flood
    """
    import msvcrt

    # Ask terminal for bracketed paste (Windows Terminal / VS Code / Cursor terminal)
    try:
        sys.stdout.write('\x1b[?2004h')
        sys.stdout.flush()
    except Exception:
        pass

    sys.stdout.write(prompt)
    sys.stdout.flush()
    buf: list[str] = []
    in_paste = False
    paste_lines_hinted = False

    try:
        while True:
            try:
                ch = msvcrt.getwch()
            except KeyboardInterrupt:
                sys.stdout.write('\n')
                sys.stdout.flush()
                raise

            if ch == '\x03':
                sys.stdout.write('\n')
                sys.stdout.flush()
                raise KeyboardInterrupt

            if ch in ('\x1a', '\x04') and not buf:
                sys.stdout.write('\n')
                sys.stdout.flush()
                raise EOFError

            # Special / function keys
            if ch in ('\x00', '\xe0'):
                try:
                    msvcrt.getwch()
                except Exception:
                    pass
                continue

            # ESC / CSI — bracketed paste or cancel
            if ch == '\x1b':
                seq = _read_escape_sequence()
                # If we only got ESC with nothing useful and no pending keys → cancel draft
                if seq in ('', '\x1b') and not _pending_keys() and not in_paste:
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    return ''
                body = seq[1:] if seq.startswith('\x1b') else seq
                if body.startswith('[200~'):
                    in_paste = True
                    continue
                if body.startswith('[201~'):
                    in_paste = False
                    if buf and not paste_lines_hinted:
                        paste_lines_hinted = True
                        sys.stdout.write('\n')
                        print(mute('已粘贴多行。再按一次 Enter 发送，Shift+Enter 继续换行。'))
                        _emit_cont_prompt()
                    continue
                # Ignore other CSI (arrows etc. already handled via \xe0)
                continue

            # Enter / Return
            if ch in ('\r', '\n'):
                # Inside bracketed paste, or more chars already queued → treat as newline
                if in_paste or _shift_down() or _pending_keys():
                    _insert_newline(buf)
                    continue
                # Brief settle: paste engines sometimes deliver \r then next char a tick later
                time.sleep(0.02)
                if _pending_keys():
                    _insert_newline(buf)
                    continue
                sys.stdout.write('\n')
                sys.stdout.flush()
                text = ''.join(buf)
                if text.count('\n') >= 1 and not paste_lines_hinted:
                    # Multi-line draft finished editing — user pressed final Enter to send
                    paste_lines_hinted = True
                if _is_exit_token(text):
                    return _normalize_exit(text.strip())
                stripped = text.strip()
                return stripped if not stripped.startswith('/') else stripped

            # Backspace
            if ch in ('\b', '\x7f'):
                if not buf:
                    continue
                removed = buf.pop()
                if removed == '\n':
                    sys.stdout.write('^H')
                    sys.stdout.flush()
                else:
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
                continue

            if ord(ch) < 32 and ch != '\t':
                continue

            buf.append(ch)
            try:
                sys.stdout.write(ch)
                sys.stdout.flush()
            except UnicodeEncodeError:
                sys.stdout.write('?')
                sys.stdout.flush()
    finally:
        try:
            sys.stdout.write('\x1b[?2004l')
            sys.stdout.flush()
        except Exception:
            pass


def _read_with_input(prompt: str) -> str:
    try:
        first = input(prompt)
    except KeyboardInterrupt:
        print()
        raise
    except EOFError:
        raise

    stripped = first.strip()
    if _is_exit_token(stripped):
        return _normalize_exit(stripped)

    if stripped.startswith('/') and stripped not in ('/paste', '/p'):
        return stripped

    if stripped in ('/paste', '/p'):
        return _read_paste_block()

    extras = _drain_stdin_lines()
    if extras:
        lines = [first] + extras
        print(mute(f'已接收 {len(lines)} 行粘贴。空行回车发送，或继续输入。'))
        try:
            more = input(brand('… › ') if colors_enabled() else '..> ')
        except KeyboardInterrupt:
            raise
        if _is_exit_token(more):
            return '/exit'
        if more.strip() not in ('', '/send'):
            lines.append(more)
            while True:
                try:
                    more = input(brand('… › ') if colors_enabled() else '..> ')
                except KeyboardInterrupt:
                    raise
                if _is_exit_token(more):
                    return '/exit'
                if more.strip() in ('', '/send'):
                    break
                lines.append(more)
        return '\n'.join(lines).strip()

    return stripped


def read_message(multiline=False, network='auto', chat_mode='auto', session_lane='chat'):
    """Read one user message."""
    enable_windows_ansi()
    # Do NOT disable bracketed paste here — Windows smart reader needs it for multiline Ctrl+V.

    print_input_frame(network=network, chat_mode=chat_mode, session_lane=session_lane)
    prompt = (brand('❯ ') if colors_enabled() else '> ')

    # Explicit multiline flag → /send protocol via input()
    # (smart Windows path enables bracketed paste itself; do not force it off here)
    if multiline:
        print(mute('多行：继续输入，/send 发送，/exit 退出'))
        try:
            first = input(prompt)
        except KeyboardInterrupt:
            print()
            raise
        if _is_exit_token(first):
            return '/exit'
        lines = [first]
        while True:
            try:
                line = input(brand('… › ') if colors_enabled() else '..> ')
            except KeyboardInterrupt:
                raise
            if _is_exit_token(line):
                return '/exit'
            if line.strip() == '/send':
                return '\n'.join(lines).strip()
            if line.strip() == '/cancel':
                return ''
            lines.append(line)

    use_smart = (
        _smart_input_wanted()
        and sys.platform == 'win32'
        and hasattr(sys.stdin, 'isatty')
        and sys.stdin.isatty()
        and hasattr(sys.stdout, 'isatty')
        and sys.stdout.isatty()
    )
    if use_smart:
        try:
            text = _read_windows_tty(prompt)
        except KeyboardInterrupt:
            raise
        if text in ('/paste', '/p'):
            return _read_paste_block()
        return text

    return _read_with_input(prompt)
