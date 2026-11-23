#!/usr/bin/env python3
"""Build PDFs for supporting docs and pack desktop zip for 三三队."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUPPORT = HERE / 'supporting'
UI = SUPPORT / '界面示意'
ASSETS = HERE / 'assets'
PDF_DIR = HERE / 'pdf'
PDF_SUPPORT = HERE / 'pdf' / '其他配套文件'

# reuse md→pdf helpers
import sys

sys.path.insert(0, str(HERE))
from build_pdfs import make_styles, md_to_pdf, register_font  # noqa: E402


CREATIVE_MD = [
    (HERE / '创意说明-作品名称与简介.md', PDF_DIR / '创意说明-作品名称与简介.pdf', '创意说明'),
    (HERE / '03-技术方案.md', PDF_DIR / '技术方案.pdf', '技术方案（创意说明补充）'),
]

SUPPORT_MD = [
    (SUPPORT / '00-配套文件说明.md', PDF_SUPPORT / '00-配套文件说明.pdf', '配套文件说明'),
    (SUPPORT / '01-系统架构说明.md', PDF_SUPPORT / '01-系统架构说明.pdf', '系统架构说明'),
    (SUPPORT / '02-技术落地可行性方案.md', PDF_SUPPORT / '02-技术落地可行性方案.pdf', '技术落地可行性方案'),
    (SUPPORT / '03-需求与场景分析.md', PDF_SUPPORT / '03-需求与场景分析.pdf', '需求与场景分析'),
    (SUPPORT / '04-创意亮点说明.md', PDF_SUPPORT / '04-创意亮点说明.pdf', '创意亮点说明'),
    (SUPPORT / '05-数据来源与合规说明.md', PDF_SUPPORT / '05-数据来源与合规说明.pdf', '数据来源与合规说明'),
    (SUPPORT / '06-参考文档.md', PDF_SUPPORT / '06-参考文档.pdf', '参考文档'),
]

LIVE_SHOTS = [
    'shot_live_help.png',
    'shot_live_skill.png',
    'shot_live_mcp.png',
    'shot_live_tests.png',
    'shot_live_terminal.png',
    'shot_collage.png',
    'shot_arch.png',
]


def desktop_dir() -> Path:
    import os

    # Prefer Windows redirected Desktop (User Shell Folders)
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders',
        ) as k:
            val, _ = winreg.QueryValueEx(k, 'Desktop')
            p = Path(os.path.expandvars(val))
            if p.is_dir():
                return p
    except Exception:
        pass
    return Path.home() / 'Desktop'


def build_pdfs():
    regular, bold = register_font()
    styles = make_styles(regular, bold)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    PDF_SUPPORT.mkdir(parents=True, exist_ok=True)
    for md, pdf, note in CREATIVE_MD + SUPPORT_MD:
        if not md.is_file():
            print('skip', md)
            continue
        md_to_pdf(md, pdf, styles, f'openJiuwen · 三三队 · {note}')


def stage_ui():
    UI.mkdir(parents=True, exist_ok=True)
    # architecture diagram
    from supporting.render_arch_diagram import main as render_arch

    render_arch()
    # copy live shots with Chinese names for评审 readability
    mapping = {
        'shot_live_help.png': '界面示意-help命令.png',
        'shot_live_skill.png': '界面示意-skill列表.png',
        'shot_live_mcp.png': '界面示意-mcp.png',
        'shot_live_tests.png': '界面示意-unittest.png',
        'shot_live_terminal.png': '界面示意-综合终端.png',
        'shot_collage.png': '界面示意-截图拼图.png',
    }
    for src_name, dst_name in mapping.items():
        src = ASSETS / src_name
        if src.is_file() and src.stat().st_size > 5000:
            shutil.copy2(src, UI / dst_name)
            print('ui', dst_name)


def pack_zip():
    desk = desktop_dir()
    zip_path = desk / '【openJiuwen创新大赛创意作品】三三队.zip'
    ppt = HERE / '【openJiuwen创新大赛创意作品】三三队.pptx'
    staging = HERE / '_submit_staging'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    # root: 创意说明 + PPT
    shutil.copy2(PDF_DIR / '创意说明-作品名称与简介.pdf', staging / '创意说明-作品名称与简介.pdf')
    if ppt.is_file():
        shutil.copy2(ppt, staging / ppt.name)
    else:
        print('WARN missing ppt')

    # 其他配套文件/
    other = staging / '其他配套文件'
    other.mkdir()
    for pdf in sorted(PDF_SUPPORT.glob('*.pdf')):
        shutil.copy2(pdf, other / pdf.name)
    # also put 技术方案 into supporting as technical supplement
    tech = PDF_DIR / '技术方案.pdf'
    if tech.is_file():
        shutil.copy2(tech, other / '07-技术方案详述.pdf')

    ui_dst = other / '界面示意'
    shutil.copytree(UI, ui_dst)

    # readme at root
    (staging / '提交内容说明.txt').write_text(
        'openJiuwen 智能体创新大赛 · 初赛提交 · 队伍：三三队\n'
        '作品：CodeVigil Agent\n\n'
        '本压缩包结构：\n'
        '1) 创意说明-作品名称与简介.pdf\n'
        '2) 【openJiuwen创新大赛创意作品】三三队.pptx　← 创意PPT\n'
        '3) 其他配套文件/　← PPT 以外的补充说明\n'
        '   - 系统架构 / 可行性 / 需求场景 / 亮点 / 合规 / 参考文档（PDF）\n'
        '   - 界面示意/（本机实机截图 + 系统架构图）\n'
        '   - 技术方案详述.pdf\n\n'
        '不含 .env、Token、私钥、未脱敏日志。\n',
        encoding='utf-8',
    )

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in staging.rglob('*'):
            if p.is_file():
                zf.write(p, p.relative_to(staging).as_posix())

    # mirror to USERPROFILE Desktop if different
    alt = Path.home() / 'Desktop' / zip_path.name
    if alt.parent.is_dir() and alt.resolve() != zip_path.resolve():
        shutil.copy2(zip_path, alt)
        print('Also', alt)

    print('ZIP', zip_path, 'MB', round(zip_path.stat().st_size / 1024 / 1024, 2))
    with zipfile.ZipFile(zip_path) as zf:
        for n in zf.namelist():
            print(' ', n)
    shutil.rmtree(staging, ignore_errors=True)
    return zip_path


def main():
    build_pdfs()
    stage_ui()
    pack_zip()


if __name__ == '__main__':
    main()
