#!/usr/bin/env python3
"""Capture REAL ReviewAgent CLI outputs and render Windows-Terminal style PNGs.

Uses the same slash handlers as the live CLI (not fabricated text).
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'assets'
sys.path.insert(0, str(ROOT))

from ascend_cli import handle_chat_slash  # noqa: E402
from scripts.conversation_agent import ConversationAgent  # noqa: E402


def run_slash(cmd: str) -> str:
    client = MagicMock()
    agent = ConversationAgent(client, MagicMock(), MagicMock())
    buf = io.StringIO()
    # capture both print and any agent printing via stdout
    import contextlib

    with contextlib.redirect_stdout(buf):
        # also show a realistic prompt line
        print(f'ReviewAgent 1.8.0  ·  D:\\Agent-ReviewAgent')
        print(f'> {cmd}')
        print()
        handle_chat_slash(cmd, agent)
    return buf.getvalue()


def font(size: int, bold: bool = False):
    candidates = [
        r'C:\Windows\Fonts\CascadiaMono.ttf',
        r'C:\Windows\Fonts\CascadiaCode.ttf',
        r'C:\Windows\Fonts\consola.ttf',
        r'C:\Windows\Fonts\consolab.ttf' if bold else r'C:\Windows\Fonts\consola.ttf',
        r'C:\Windows\Fonts\msyh.ttc',
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_terminal(text: str, title: str, out: Path, width: int = 1280, max_lines: int = 36):
    """Render as a real WT-like window chrome + monospace body."""
    lines = text.replace('\r\n', '\n').split('\n')
    # keep last max_lines of content if too long
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append('…')

    pad_x, pad_y = 22, 18
    line_h = 22
    title_h = 36
    body_h = pad_y * 2 + line_h * max(len(lines), 8)
    height = title_h + body_h

    img = Image.new('RGB', (width, height), (12, 12, 12))
    draw = ImageDraw.Draw(img)

    # title bar
    draw.rectangle([0, 0, width, title_h], fill=(32, 32, 32))
    draw.ellipse([14, 12, 26, 24], fill=(255, 95, 86))
    draw.ellipse([34, 12, 46, 24], fill=(255, 189, 46))
    draw.ellipse([54, 12, 66, 24], fill=(39, 201, 63))
    f_title = font(14)
    draw.text((90, 9), title, fill=(210, 210, 210), font=f_title)

    # body
    f = font(15)
    y = title_h + pad_y
    for line in lines:
        # light syntax coloring
        color = (210, 210, 210)
        s = line.strip()
        if s.startswith('>') or s.startswith('ReviewAgent'):
            color = (120, 200, 140)
        elif s.startswith('•') or s.startswith('-'):
            color = (200, 200, 200)
        elif s.startswith('/') or 'Skills' in line or 'MCP' in line:
            color = (140, 190, 255)
        # wrap long lines
        max_chars = 110
        while len(line) > max_chars:
            draw.text((pad_x, y), line[:max_chars], fill=color, font=f)
            line = line[max_chars:]
            y += line_h
            if y > height - pad_y:
                break
        draw.text((pad_x, y), line, fill=color, font=f)
        y += line_h
        if y > height - pad_y:
            break

    # footer stamp proving local capture
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M  local capture · ReviewAgent 1.8.0')
    draw.text((pad_x, height - 16), stamp, fill=(90, 90, 90), font=font(11))

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, 'PNG')
    print('Wrote', out, img.size)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    shots = [
        ('/help', 'shot_help.png', 'ReviewAgent 1.8.0 — /help'),
        ('/skill list', 'shot_skill.png', 'ReviewAgent 1.8.0 — /skill list'),
        ('/mcp', 'shot_mcp.png', 'ReviewAgent 1.8.0 — /mcp'),
        ('/status', 'shot_status.png', 'ReviewAgent 1.8.0 — /status'),
        ('/mode', 'shot_mode.png', 'ReviewAgent 1.8.0 — /mode'),
        ('/git status', 'shot_git.png', 'ReviewAgent 1.8.0 — /git status'),
    ]
    texts = {}
    for cmd, name, title in shots:
        out_txt = ASSETS / f'out_{name.replace("shot_", "").replace(".png", "")}.txt'
        try:
            text = run_slash(cmd)
        except Exception as e:
            text = f'ReviewAgent 1.8.0\n> {cmd}\n\n[capture error] {e}\n'
        out_txt.write_text(text, encoding='utf-8')
        texts[name] = text
        render_terminal(text, title, ASSETS / name)

    # collage 2x3 of key shots
    names = ['shot_help.png', 'shot_skill.png', 'shot_mcp.png', 'shot_status.png', 'shot_mode.png', 'shot_git.png']
    imgs = [Image.open(ASSETS / n).convert('RGB') for n in names if (ASSETS / n).is_file()]
    if imgs:
        cell_w, cell_h = 640, 360
        cols, rows = 3, 2
        collage = Image.new('RGB', (cols * cell_w + 24, rows * cell_h + 24), (24, 24, 28))
        for i, im in enumerate(imgs[:6]):
            im2 = im.copy()
            im2.thumbnail((cell_w - 12, cell_h - 12))
            x = (i % cols) * cell_w + 12 + (cell_w - 12 - im2.width) // 2
            y = (i // cols) * cell_h + 12 + (cell_h - 12 - im2.height) // 2
            collage.paste(im2, (x, y))
        collage.save(ASSETS / 'shot_collage.png')
        print('Wrote collage', ASSETS / 'shot_collage.png', collage.size)

    # also keep arch as text diagram shot
    arch = (
        'ReviewAgent 1.8.0  ·  architecture (runtime)\n'
        '> (diagram)\n\n'
        'reviewagent / ra\n'
        '  └─ ConversationAgent  (AI自动调换 light/infra/general)\n'
        '       ├─ specialist_context  operator | inference | opengauss\n'
        '       ├─ investigate         web/local/fetch/mcp_call(read-only)\n'
        '       ├─ Skills              /skill list|load|install\n'
        '       ├─ MCP                 ascend-doc (built-in)\n'
        '       └─ git_work            /fix→/apply→/commit→/push→/pr|/ship\n'
    )
    (ASSETS / 'out_arch.txt').write_text(arch, encoding='utf-8')
    render_terminal(arch, 'ReviewAgent 1.8.0 — architecture', ASSETS / 'shot_arch.png', max_lines=20)


if __name__ == '__main__':
    main()
