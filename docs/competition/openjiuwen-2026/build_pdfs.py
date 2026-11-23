#!/usr/bin/env python3
"""Convert competition markdown materials to PDF (Chinese). Team: 三三队."""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / 'pdf'


def register_font() -> tuple[str, str]:
    candidates = [
        (r'C:\Windows\Fonts\msyh.ttc', 'MSYH', 0),
        (r'C:\Windows\Fonts\msyhbd.ttc', 'MSYHBD', 0),
        (r'C:\Windows\Fonts\simhei.ttf', 'SimHei', None),
        (r'C:\Windows\Fonts\simsun.ttc', 'SimSun', 0),
    ]
    regular = bold = None
    for path, name, sub in candidates:
        p = Path(path)
        if not p.is_file():
            continue
        try:
            if sub is None:
                pdfmetrics.registerFont(TTFont(name, str(p)))
            else:
                pdfmetrics.registerFont(TTFont(name, str(p), subfontIndex=sub))
            if regular is None:
                regular = name
            if 'bd' in path.lower() or name.endswith('BD') or name == 'SimHei':
                bold = name
        except Exception as e:
            print('font skip', path, e)
    if regular is None:
        raise SystemExit('No Chinese font found under C:\\Windows\\Fonts')
    if bold is None:
        bold = regular
    return regular, bold


def md_inline(text: str) -> str:
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font face="Courier" size="9">\1</font>', text)
    return text


def parse_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?', c.replace(' ', '')) for c in cells):
            continue
        rows.append(cells)
    return rows


def build_story(md_text: str, styles) -> list:
    story = []
    lines = md_text.replace('\r\n', '\n').split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('# '):
            story.append(Paragraph(md_inline(line[2:].strip()), styles['TitleCN']))
            story.append(Spacer(1, 6 * mm))
            i += 1
            continue
        if line.startswith('## '):
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph(md_inline(line[3:].strip()), styles['H1CN']))
            story.append(Spacer(1, 2 * mm))
            i += 1
            continue
        if line.startswith('### '):
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(md_inline(line[4:].strip()), styles['H2CN']))
            story.append(Spacer(1, 1.5 * mm))
            i += 1
            continue
        if line.startswith('```'):
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1  # closing
            code = '\n'.join(buf)
            story.append(Preformatted(code, styles['CodeCN']))
            story.append(Spacer(1, 3 * mm))
            continue
        if line.strip().startswith('|') and i + 1 < len(lines) and '|' in lines[i + 1]:
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl_lines.append(lines[i])
                i += 1
            rows = parse_table(tbl_lines)
            if rows:
                data = [[Paragraph(md_inline(c), styles['CellCN']) for c in r] for r in rows]
                col_n = max(len(r) for r in rows)
                w = 17 * cm / col_n
                t = Table(data, colWidths=[w] * col_n, hAlign='LEFT')
                t.setStyle(
                    TableStyle(
                        [
                            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.92, 0.94, 0.97)),
                            ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.7, 0.75, 0.8)),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 4),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                            ('TOPPADDING', (0, 0), (-1, -1), 4),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(t)
                story.append(Spacer(1, 3 * mm))
            continue
        if re.match(r'^[-*] ', line) or re.match(r'^\d+\. ', line):
            items = []
            while i < len(lines) and (re.match(r'^[-*] ', lines[i]) or re.match(r'^\d+\. ', lines[i])):
                raw = re.sub(r'^([-*] |\d+\. )', '', lines[i])
                items.append(ListItem(Paragraph(md_inline(raw), styles['BodyCN']), leftIndent=8, value='•'))
                i += 1
            story.append(ListFlowable(items, bulletType='bullet', start='•', leftIndent=12))
            story.append(Spacer(1, 2 * mm))
            continue
        if line.strip() == '---':
            story.append(Spacer(1, 4 * mm))
            i += 1
            continue
        # paragraph (maybe multi-line)
        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith('#') and not lines[i].startswith('|') and not lines[i].startswith('```') and not re.match(r'^[-*] ', lines[i]) and not re.match(r'^\d+\. ', lines[i]) and lines[i].strip() != '---':
            buf.append(lines[i])
            i += 1
        story.append(Paragraph(md_inline(' '.join(x.strip() for x in buf)), styles['BodyCN']))
        story.append(Spacer(1, 2 * mm))
    return story


def make_styles(regular: str, bold: str):
    base = getSampleStyleSheet()
    styles = {
        'TitleCN': ParagraphStyle(
            'TitleCN',
            parent=base['Title'],
            fontName=bold,
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        'H1CN': ParagraphStyle(
            'H1CN', parent=base['Heading1'], fontName=bold, fontSize=14, leading=20, textColor=colors.Color(0, 0.35, 0.62)
        ),
        'H2CN': ParagraphStyle(
            'H2CN', parent=base['Heading2'], fontName=bold, fontSize=12, leading=17, textColor=colors.Color(0.15, 0.15, 0.15)
        ),
        'BodyCN': ParagraphStyle(
            'BodyCN', parent=base['BodyText'], fontName=regular, fontSize=10.5, leading=16, alignment=TA_JUSTIFY
        ),
        'CellCN': ParagraphStyle(
            'CellCN', parent=base['BodyText'], fontName=regular, fontSize=9, leading=13, alignment=TA_LEFT
        ),
        'CodeCN': ParagraphStyle(
            'CodeCN',
            parent=base['Code'],
            fontName=regular,
            fontSize=8.5,
            leading=12,
            backColor=colors.Color(0.95, 0.95, 0.96),
            leftIndent=4,
            rightIndent=4,
        ),
        'FooterCN': ParagraphStyle(
            'FooterCN', parent=base['Normal'], fontName=regular, fontSize=8, textColor=colors.grey, alignment=TA_CENTER
        ),
    }
    return styles


DOCS = [
    ('01-作品名称与简介.md', '01-作品名称与简介.pdf', '作品名称与项目简介'),
    ('02-应用场景说明.md', '02-应用场景说明.pdf', '应用场景说明'),
    ('03-技术方案.md', '03-技术方案.pdf', '技术方案'),
]


def md_to_pdf(md_path: Path, pdf_path: Path, styles, cover_note: str):
    text = md_path.read_text(encoding='utf-8')
    story = []
    story.append(Paragraph(cover_note, styles['FooterCN']))
    story.append(Spacer(1, 3 * mm))
    story.extend(build_story(text, styles))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(styles['FooterCN'].fontName, 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1.2 * cm, 'openJiuwen · 三三队 · CodeVigil Agent')
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'{doc.page}')
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2 * cm,
        title=pdf_path.stem,
        author='三三队',
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print('Wrote', pdf_path)


def main():
    regular, bold = register_font()
    styles = make_styles(regular, bold)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for md_name, pdf_name, note in DOCS:
        md_path = HERE / md_name
        if not md_path.is_file():
            print('skip missing', md_path)
            continue
        md_to_pdf(md_path, OUT_DIR / pdf_name, styles, f'openJiuwen 智能体创新大赛 · 三三队 · {note}')
    # also combined pack
    combined = OUT_DIR / '三三队-创意材料合集.pdf'
    story = []
    for idx, (md_name, _, note) in enumerate(DOCS):
        md_path = HERE / md_name
        if not md_path.is_file():
            continue
        if idx:
            story.append(PageBreak())
        story.append(Paragraph(f'openJiuwen · 三三队 · {note}', styles['FooterCN']))
        story.append(Spacer(1, 3 * mm))
        story.extend(build_story(md_path.read_text(encoding='utf-8'), styles))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(styles['FooterCN'].fontName, 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1.2 * cm, 'openJiuwen · 三三队 · CodeVigil Agent')
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'{doc.page}')
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(combined),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2 * cm,
        title='三三队-创意材料合集',
        author='三三队',
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print('Wrote', combined)


if __name__ == '__main__':
    main()
