"""Pretty thinking / progress steps for chat (Claude Code–ish)."""
from __future__ import annotations

import time
from typing import List, Optional

from scripts.term_style import accent, brand, c, enable_windows_ansi, mute, ok


class ThinkPanel:
    """Collects progress steps and renders a colored thinking block."""

    def __init__(self):
        self.steps: List[str] = []
        self._open = False
        self._started = 0.0

    def start(self, title: str = '思考中') -> None:
        enable_windows_ansi()
        self.steps.clear()
        self._open = True
        self._started = time.time()
        print()
        print(brand('╭─ ') + accent(f'◆ {title}') + brand(' ' + '─' * 28 + '╮'))

    def step(self, message: str) -> None:
        enable_windows_ansi()
        if not self._open:
            self.start()
        self.steps.append(message)
        n = len(self.steps)
        # alternating accent for rhythm
        diamond = accent('◆') if n % 2 else brand('◇')
        print(brand('│ ') + diamond + ' ' + c('97', message))

    def close(self, ok_msg: str = '完成') -> None:
        if not self._open:
            return
        elapsed = time.time() - self._started
        print(brand('│ ') + ok('✓ ') + mute(f'{ok_msg} · {elapsed:.1f}s'))
        print(brand('╰' + '─' * 42 + '╯'))
        self._open = False


# Module-level panel used by chat()
_PANEL: Optional[ThinkPanel] = None


def begin_think(title: str = '思考中') -> ThinkPanel:
    global _PANEL
    _PANEL = ThinkPanel()
    _PANEL.start(title)
    return _PANEL


def think_progress(message: str) -> None:
    global _PANEL
    if _PANEL is None or not _PANEL._open:
        begin_think()
    assert _PANEL is not None
    _PANEL.step(message)


def end_think(ok_msg: str = '完成') -> None:
    global _PANEL
    if _PANEL is not None:
        _PANEL.close(ok_msg)
        _PANEL = None
