"""Terminal colors that actually work on Windows PowerShell / Windows Terminal."""
from __future__ import annotations

import os
import sys

_VT_ENABLED = False


def enable_windows_ansi() -> bool:
    """Turn on VT100 processing for Win32 consoles (needed for color + box drawing)."""
    global _VT_ENABLED
    if _VT_ENABLED:
        return True
    if os.name != 'nt':
        _VT_ENABLED = True
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # STD_OUTPUT_HANDLE = -11, STD_ERROR_HANDLE = -12
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
                continue
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            # ENABLE_PROCESSED_OUTPUT = 0x0001
            new_mode = mode.value | 0x0001 | 0x0004
            kernel32.SetConsoleMode(handle, new_mode)
        # Also help child processes / Python
        os.environ.setdefault('TERM', 'xterm-256color')
        os.environ.setdefault('COLORTERM', 'truecolor')
        _VT_ENABLED = True
        return True
    except Exception:
        return False


def colors_enabled() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes', 'on'):
        return True
    if os.environ.get('REVIEWAGENT_NODE_UI') == '1':
        # Launched from reviewagent.js with inherited console — prefer color
        return True
    # Windows often has empty TERM — do NOT treat that as "no color"
    term = os.environ.get('TERM', '').lower()
    if term == 'dumb':
        return False
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return True


def c(code: str, text: str) -> str:
    if not colors_enabled():
        return text
    return f'\033[{code}m{text}\033[0m'


# Palette (bright — visible on dark Windows Terminal)
def brand(text: str) -> str:
    return c('96', text)  # bright cyan


def accent(text: str) -> str:
    return c('95', text)  # bright magenta


def ok(text: str) -> str:
    return c('92', text)  # bright green


def warn(text: str) -> str:
    return c('93', text)  # bright yellow


def mute(text: str) -> str:
    return c('90', text)


def ink(text: str) -> str:
    return c('97', text)  # bright white


def progress_line(message: str) -> str:
    return f"  {accent('◆')} {brand(message)}"


def ensure_utf8_stdio() -> None:
    if sys.platform != 'win32':
        return
    import io
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            if isinstance(stream, io.TextIOWrapper) and (stream.encoding or '').lower() == 'utf-8':
                continue
            buf = stream.buffer
            setattr(sys, name, io.TextIOWrapper(buf, encoding='utf-8', errors='replace', line_buffering=True))
        except Exception:
            pass
