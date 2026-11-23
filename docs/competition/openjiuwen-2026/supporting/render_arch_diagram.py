#!/usr/bin/env python3
"""Render a clean architecture PNG for submission (not AI photo mock)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / '界面示意' / '系统架构图.png'


def font(size: int, bold: bool = False):
    for p in (
        r'C:\Windows\Fonts\msyhbd.ttc' if bold else r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\arial.ttf',
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def box(draw, xy, text, fill, outline, tf, pad=12):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=12, fill=fill, outline=outline, width=2)
    # center-ish text
    lines = text.split('\n')
    lh = 22
    total = lh * len(lines)
    ty = y1 + (y2 - y1 - total) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=tf)
        tw = bbox[2] - bbox[0]
        tx = x1 + (x2 - x1 - tw) // 2
        draw.text((tx, ty + i * lh), line, fill=(30, 30, 30), font=tf)


def arrow(draw, x1, y1, x2, y2):
    draw.line((x1, y1, x2, y2), fill=(0, 90, 160), width=3)
    # simple arrow head
    draw.polygon([(x2, y2), (x2 - 8, y2 - 10), (x2 + 8, y2 - 10)], fill=(0, 90, 160))


def main():
    w, h = 1400, 900
    img = Image.new('RGB', (w, h), (252, 253, 255))
    draw = ImageDraw.Draw(img)
    title_f = font(28, True)
    body_f = font(16)
    small_f = font(14)

    draw.text((40, 24), 'CodeVigil Agent · 系统架构图（三三队）', fill=(0, 90, 160), font=title_f)
    draw.text((40, 64), '对话编排 + 专业规则 + 只读工具 + 显式生产力  ·  v1.8.0', fill=(90, 90, 90), font=small_f)

    # layers
    box(draw, (400, 110, 1000, 190), '用户终端\nreviewagent / ra', (230, 240, 250), (0, 90, 160), body_f)
    arrow(draw, 700, 190, 700, 230)

    box(draw, (250, 230, 1150, 340),
        'ConversationAgent\nAI自动调换 light/infra/general · /new /back · Skills · MCP',
        (235, 245, 255), (0, 90, 160), body_f)
    arrow(draw, 480, 340, 480, 390)
    arrow(draw, 920, 340, 920, 390)

    box(draw, (80, 390, 650, 520),
        '专业路由 specialist_context\noperator | inference | opengauss\n→ agents + skills',
        (245, 248, 252), (100, 130, 160), body_f)
    box(draw, (750, 390, 1320, 520),
        '调查循环 investigate\nweb / local / fetch / mcp_call(只读)',
        (245, 248, 252), (100, 130, 160), body_f)

    arrow(draw, 365, 520, 365, 570)
    arrow(draw, 1035, 520, 700, 570)

    box(draw, (250, 570, 1150, 680),
        'SmartReviewer / patch_fix\n审查报告 · 补丁预览 · 来源与预算可追溯',
        (235, 250, 240), (40, 130, 90), body_f)
    arrow(draw, 700, 680, 700, 730)

    box(draw, (250, 730, 1150, 840),
        'git_work 生产力链\n/fix → /apply → /commit → /push → /pr 或 /ship（逐步确认，禁 force/amend）',
        (255, 245, 235), (180, 100, 40), body_f)

    draw.text((40, 860), '说明：openJiuwen WorkSwarm 为 DEMO 阶段可选演进，创意材料不虚构已接入。',
              fill=(110, 110, 110), font=small_f)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print('Wrote', OUT)


if __name__ == '__main__':
    main()
