"""Lightweight Markdown → ANSI for terminal replies (no external deps)."""
from __future__ import annotations

import re
from typing import Iterable, List

from scripts.term_style import accent, brand, c, colors_enabled, mute, ok, warn


def _inline(text: str) -> str:
    """Bold / italic / code / links — order matters."""
    if not text:
        return text

    def code(m):
        return c('93', m.group(1))  # yellow inline code

    def bold(m):
        return c('1;97', m.group(1))  # bright bold white

    def italic(m):
        return c('3;96', m.group(1))

    def link(m):
        label, url = m.group(1), m.group(2)
        return f"{brand(label)}{mute(' (' + url + ')')}"

    text = re.sub(r'`([^`]+)`', code, text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    text = re.sub(r'\*\*([^*]+)\*\*', bold, text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', italic, text)
    text = re.sub(r'(?<!_)_([^_]+)_(?!_)', italic, text)
    return text


def render_markdown(md: str, width: int = 72) -> List[str]:
    """Return list of ANSI-colored lines ready to print inside a box."""
    if not md:
        return ['(empty)']
    out: List[str] = []
    in_code = False
    code_lang = ''
    for raw in md.replace('\r\n', '\n').split('\n'):
        line = raw.rstrip()

        if line.startswith('```'):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                label = f' code {code_lang} '.rstrip()
                out.append(mute('┌' + '─' * max(8, width - 2) + '┐'))
                if code_lang:
                    out.append(mute('│') + warn(label) + mute(''))
            else:
                in_code = False
                out.append(mute('└' + '─' * max(8, width - 2) + '┘'))
            continue

        if in_code:
            out.append(mute('│ ') + c('92', line))
            continue

        # headings
        if line.startswith('### '):
            out.append('')
            out.append(accent('▸ ') + c('1;95', line[4:].strip()))
            out.append(mute('  ' + '─' * min(40, width - 4)))
            continue
        if line.startswith('## '):
            out.append('')
            out.append(brand('◆ ') + c('1;96', line[3:].strip()))
            out.append(mute('  ' + '═' * min(44, width - 4)))
            continue
        if line.startswith('# '):
            out.append('')
            out.append(ok('★ ') + c('1;92', line[2:].strip()))
            out.append(mute('  ' + '═' * min(48, width - 4)))
            continue

        # hr
        if re.fullmatch(r'-{3,}|\*{3,}|_{3,}', line.strip()):
            out.append(mute('  ' + '─' * min(48, width - 4)))
            continue

        # blockquote
        if line.startswith('> '):
            out.append(mute('  │ ') + c('90', _inline(line[2:])))
            continue

        # unordered list
        m = re.match(r'^(\s*)([-*+])\s+(.*)$', line)
        if m:
            indent, _, body = m.groups()
            pad = '  ' * (len(indent) // 2)
            out.append(f"{pad}{accent('•')} {_inline(body)}")
            continue

        # ordered list
        m = re.match(r'^(\s*)(\d+)\.\s+(.*)$', line)
        if m:
            indent, num, body = m.groups()
            pad = '  ' * (len(indent) // 2)
            out.append(f"{pad}{brand(num + '.')} {_inline(body)}")
            continue

        if not line.strip():
            out.append('')
            continue

        out.append(_inline(line))

    # drop leading empties
    while out and out[0] == '':
        out.pop(0)
    return out or ['(empty)']


def print_markdown_box(md: str, title: str = 'Agent') -> None:
    """Print markdown inside a green rounded box with rendered formatting."""
    from scripts.term_style import enable_windows_ansi
    enable_windows_ansi()
    lines = render_markdown(md)
    width = 58
    top = f"╭─ {title} " + '─' * max(4, width - len(title) - 4) + '╮'
    bot = '╰' + '─' * width + '╯'
    print()
    try:
        print(ok(top))
        for line in lines:
            # avoid breaking on very long lines — still prefix bar
            print(ok('│ ') + (line if colors_enabled() else _strip_ansi(line)))
        print(ok(bot))
    except UnicodeEncodeError:
        print(ok(f'+-- {title} ' + '-' * 40))
        for line in lines:
            print(_strip_ansi(line))
        print(ok('+' + '-' * 50))


_ANSI_RE = re.compile(r'\033\[[0-9;]*m')


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub('', s)
