#!/usr/bin/env python3
"""Build competition PPTX from HTML slide screenshots (16:9 full-bleed)."""
from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu, Inches

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'assets' / 'html-slides' / 'manifest.json'
OUT = HERE / '【openJiuwen创新大赛创意作品】三三队.pptx'

# 16:9 widescreen
SLIDE_W = Inches(13.333333)
SLIDE_H = Inches(7.5)


def main():
    data = json.loads(MANIFEST.read_text(encoding='utf-8'))
    files = [Path(p) for p in data['files']]
    if not files:
        raise SystemExit('no slide images — run render_html_slides.mjs first')

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    for img in files:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(img), Emu(0), Emu(0), width=SLIDE_W, height=SLIDE_H)
        print('added', img.name)

    prs.save(str(OUT))
    print('Wrote', OUT, 'slides=', len(files), 'bytes=', OUT.stat().st_size)


if __name__ == '__main__':
    main()
