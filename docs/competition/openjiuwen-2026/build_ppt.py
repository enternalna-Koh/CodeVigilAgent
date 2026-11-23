#!/usr/bin/env python3
"""Build competition PPT for 三三队.

Strategy:
- Keep official template pages 1–4 structure and fill them.
- DELETE appendix/scoring pages.
- Append content slides as TRUE blank slides (placeholders removed from XML),
  with real live-terminal screenshots — not fake AI mockups.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TEMPLATE = ROOT / 'openJiuwen智能体创意大赛模板.pptx'
OUT = HERE / '【openJiuwen创新大赛创意作品】三三队.pptx'
ASSETS = HERE / 'assets'

DARK = RGBColor(28, 28, 28)
MUTED = RGBColor(90, 90, 90)
ACCENT = RGBColor(0, 90, 160)
WHITE = RGBColor(255, 255, 255)
CARD = RGBColor(246, 248, 251)
LINE = RGBColor(210, 218, 228)


def fill(shape, text: str, size: int = 12, bold: bool = False, color=DARK, align=PP_ALIGN.LEFT):
    if not getattr(shape, 'has_text_frame', False):
        return
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    try:
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass
    for i, line in enumerate(text.split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = '微软雅黑'


def resize(shape, left=None, top=None, width=None, height=None):
    if left is not None:
        shape.left = int(left)
    if top is not None:
        shape.top = int(top)
    if width is not None:
        shape.width = int(width)
    if height is not None:
        shape.height = int(height)


def delete_slide(prs: Presentation, index: int) -> None:
    sldIdLst = prs.slides._sldIdLst
    sldId = sldIdLst[index]
    rId = sldId.get(qn('r:id'))
    prs.part.drop_rel(rId)
    sldIdLst.remove(sldId)


def clear_all_shapes(slide) -> None:
    """Physically remove every shape (including '点击添加标题' placeholders)."""
    spTree = slide.shapes._spTree
    for child in list(spTree):
        tag = child.tag
        # keep nvGrpPr / group shape props; remove pic/sp/grpSp/cxnSp
        if tag.endswith('}sp') or tag.endswith('}pic') or tag.endswith('}grpSp') or tag.endswith('}cxnSp'):
            spTree.remove(child)


def add_blank_slide(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    clear_all_shapes(slide)
    # subtle full-bleed background wash
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), int(prs.slide_width), int(prs.slide_height)
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(252, 253, 255)
    bg.line.fill.background()
    # accent top bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), int(prs.slide_width), Emu(70_000))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    return slide


def title(slide, text: str, subtitle: str = ''):
    box = slide.shapes.add_textbox(Emu(400_000), Emu(160_000), Emu(11_200_000), Emu(480_000))
    fill(box, text, size=26, bold=True, color=ACCENT)
    if subtitle:
        sub = slide.shapes.add_textbox(Emu(400_000), Emu(620_000), Emu(11_200_000), Emu(320_000))
        fill(sub, subtitle, size=12, color=MUTED)
        return 980_000
    return 720_000


def card(slide, left, top, width, height, heading: str, body: str, body_size=12):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = CARD
    shape.line.color.rgb = LINE
    shape.line.width = Pt(1)
    hb = slide.shapes.add_textbox(left + Emu(140_000), top + Emu(90_000), width - Emu(280_000), Emu(340_000))
    fill(hb, heading, size=14, bold=True, color=ACCENT)
    bb = slide.shapes.add_textbox(
        left + Emu(140_000), top + Emu(420_000), width - Emu(280_000), height - Emu(520_000)
    )
    fill(bb, body, size=body_size, color=DARK)


def body(slide, top, text: str, size=13, height=5_000_000):
    box = slide.shapes.add_textbox(Emu(400_000), Emu(top), Emu(11_200_000), Emu(height))
    fill(box, text, size=size)
    return box


def pic(slide, path: Path, left, top, width=None, height=None):
    if not path.is_file() or path.stat().st_size < 3000:
        return None
    kwargs = {}
    if width is not None:
        kwargs['width'] = width
    if height is not None:
        kwargs['height'] = height
    return slide.shapes.add_picture(str(path), left, top, **kwargs)


def prefer(*names: str) -> Path | None:
    for n in names:
        p = ASSETS / n
        if p.is_file() and p.stat().st_size > 8000:
            return p
    return None


def fill_template_pages(prs: Presentation) -> None:
    slides = list(prs.slides)

    s1 = slides[0]
    fill(s1.shapes[0], 'CodeVigil Agent', size=36, bold=True)
    fill(
        s1.shapes[1],
        '昇腾 AI Infra 审查与排障智能体\n'
        'openJiuwen 智能体创新大赛 · 创意提交\n'
        '队伍：三三队 · 赛道：Coding（兼科研）\n'
        '开源 MIT · v1.8.0 · CLI + Windows/macOS 桌面版\n'
        '仓库：github.com/enternalna-Koh/CodeVigilAgent\n'
        '近期：自定义命令 · @文件 · /cost · MCP 信任 · 终端对齐',
        size=14,
    )

    s2 = slides[1]
    fill(s2.shapes[0], 'CodeVigil Agent', size=28, bold=True)
    fill(s2.shapes[1], '创意描述', size=16, bold=True)
    fill(s2.shapes[2], '所属主题', size=16, bold=True)
    fill(s2.shapes[3], '应用场景', size=16, bold=True)
    desc = s2.shapes[7]
    resize(desc, left=Emu(300_000), top=Emu(1_480_000), width=Emu(5_200_000), height=Emu(3_350_000))
    fill(
        desc,
        '把「能对话」的大模型，变成能在昇腾生态里真正干活的 Agent。\n\n'
        '粘贴 GitHub / GitCode PR·Issue 或昇腾关键词后，自动调换到 Infra 审查车道：'
        '拉取正文与 CI → 按算子 / 推理 / openGauss 加载 Skills → 经昇腾文档 MCP 查证 → '
        '输出可证实问题与建议。\n\n'
        '本地改动必须 /fix→预览→/apply，再经 /commit·/push·/pr 或 /ship 逐步确认，'
        '禁止 force / amend。\n\n'
        'MIT 开源，CLI 一键安装，209 项回归守护安全边界。',
        size=12,
    )
    theme = s2.shapes[8]
    resize(theme, height=Emu(700_000))
    fill(theme, '主赛道：Coding\n兼报：科研（社区知识沉淀）', size=15, bold=True)
    scene = s2.shapes[9]
    resize(scene, left=Emu(6_200_000), top=Emu(1_480_000), width=Emu(5_400_000), height=Emu(3_350_000))
    fill(
        scene,
        '面向用户\n昇腾社区贡献者 / 学生、AI Infra 工程师、社区导师；也可服务 openGauss 贡献者。\n\n'
        '三个故事\n① 算子社区任务 / API 一致性自检\n② CI / 日志归因与补丁建议\n'
        '③ 师生审核对话与门禁采集复盘\n\n'
        '痛点 → 影响\n规则散落、只聊不做、改仓不安全、经验难沉淀 →\n'
        '统一审查口径，缩短「查文档→对任务书→看 CI→提交」闭环。',
        size=12,
    )
    fill(s2.shapes[10], '三三队', size=12)

    s3 = slides[2]
    fill(s3.shapes[0], '创意方案构想', size=28, bold=True)
    fill(s3.shapes[5], '方案详情', size=16, bold=True)
    fill(s3.shapes[4], '方案优势', size=16, bold=True)
    fill(s3.shapes[6], '技术依赖', size=16, bold=True)
    core = s3.shapes[9]
    resize(core, top=Emu(1_400_000), height=Emu(1_950_000), width=Emu(11_200_000))
    fill(
        core,
        '① AI 自动调换 + 三条专业路由（算子 / 推理 / openGauss）\n'
        '② Skills × 内置昇腾 MCP（ascend-doc，固定版本 + 进程信任）\n'
        '③ 只读调查循环：web / local / GitCode / MCP\n'
        '④ 安全生产力链：/fix → 预览 → /apply → /commit|/push|/pr|/ship\n'
        '⑤ 社区采集 + 桌面版/自定义命令/@文件/pre-commit|/cost',
        size=13,
    )
    adv = s3.shapes[8]
    resize(adv, height=Emu(1_100_000))
    fill(
        adv,
        '相对通用 Chat/IDE：深耕昇腾验收口径与 GitCode 工作流。\n'
        '相对纯规则扫描：可引用社区案例与文档 MCP。\n'
        '相对自动改仓助手：默认只读 + 显式确认，适配合规。',
        size=12,
    )
    deps = s3.shapes[7]
    resize(deps, height=Emu(1_400_000))
    fill(
        deps,
        '运行时：Node 启动器 + Python 3.7+；多模型 Provider。\n'
        '依赖：自备大模型 API；可选 GITCODE_TOKEN；Node≥22。\n'
        'DEMO（晋级后）：装 CLI→贴链接→出报告→补丁预览；可选 WorkSwarm（未虚构已接入）。',
        size=12,
    )

    # slide 4: live collage / live help
    s4 = slides[3]
    fill(s4.shapes[0], '实机截图 · 本机 Windows 窗口捕获', size=24, bold=True)
    caption = s4.shapes[1]
    resize(caption, left=Emu(300_000), top=Emu(680_000), width=Emu(11_500_000), height=Emu(520_000))
    fill(
        caption,
        '以下截图来自本机 PowerShell 窗口（标题含 LIVE / RACAP），非 AI 绘图。\n'
        '命令：reviewagent --version · /help · /skill list · /mcp · unittest\n'
        '队伍：三三队 · 版本：v1.8.0 · 仓库：github.com/enternalna-Koh/ReviewAgent',
        size=11,
    )
    collage = prefer('shot_collage.png', 'shot_live_terminal.png', 'shot_live_help.png')
    if collage:
        slide_h, slide_w = int(prs.slide_height), int(prs.slide_width)
        top = 1_280_000
        max_h = slide_h - top - 160_000
        max_w = slide_w - 500_000
        # fit keeping aspect via width first
        pic(s4, collage, Emu(250_000), Emu(top), width=Emu(min(max_w, 11_700_000)))


def append_content_slides(prs: Presentation) -> None:
    # 5 architecture text + arch shot
    s = add_blank_slide(prs)
    title(s, '技术方案 · 总体架构', '对话编排 + 专业规则 + 只读工具 + 显式生产力')
    body(
        s,
        1_050_000,
        'reviewagent / ra\n'
        '  └─ ConversationAgent（AI自动调换 light / infra / general · /new /back · Skills · MCP）\n'
        '       ├─ specialist_context　operator | inference | opengauss\n'
        '       ├─ investigate　　　　web / local / fetch / mcp_call(只读)\n'
        '       ├─ Skills　　　　　　　/skill list | load | install\n'
        '       ├─ MCP　　　　　　　　内置 ascend-doc\n'
        '       └─ git_work　　　　　/fix→/apply→/commit→/push→/pr | /ship\n\n'
        'openJiuwen 概念映射（便于评委理解，非声称已接入平台）：\n'
        'ReActAgent ≈ investigate　·　WorkflowAgent ≈ /fix→/ship　·　Skills / MCP 同名能力',
        size=13,
        height=3_200_000,
    )
    arch = prefer('shot_arch.png')
    if arch:
        pic(s, arch, Emu(400_000), Emu(4_400_000), width=Emu(11_200_000))

    # 6 stories
    s = add_blank_slide(prs)
    title(s, '应用场景 · 三个故事', 'Coding 主赛道 · 科研兼报')
    w, h = Emu(3_700_000), Emu(4_800_000)
    y = Emu(1_100_000)
    card(s, Emu(300_000), y, w, h, '故事 A · 社区任务自检',
         '认领 AscendC / API 一致性任务后运行 reviewagent，粘贴 design PR。\n\n'
         '识别算子场景，加载 cann-ascendc-op-dev 等 Skills，对照红线输出 BLOCKER/WARN 与补测建议。')
    card(s, Emu(4_150_000), y, w, h, '故事 B · CI 归因修复',
         '粘贴失败日志或 /ci，启发式归类 ACL/HCCL/codecheck；必要时 MCP 查昇腾文档。\n\n'
         '确认后 /fix 生成补丁，/ship 逐步提交开 PR（不 force）。')
    card(s, Emu(8_000_000), y, w, h, '故事 C · 导师复盘',
         'collect --community opengauss 拉取讨论与 CI，按 author/reviewer 标注。\n\n'
         '服务「老师—学员」辅导与科研向知识沉淀（需 GITCODE_TOKEN）。')

    # 7 live help screenshot full
    s = add_blank_slide(prs)
    title(s, '实机 · /help（本机窗口）', 'PowerShell 实机捕获 · ReviewAgent 1.8.0')
    p = prefer('shot_live_help.png', 'shot_live_terminal.png', 'shot_help.png')
    if p:
        pic(s, p, Emu(500_000), Emu(1_050_000), width=Emu(11_000_000))

    # 8 live skill
    s = add_blank_slide(prs)
    title(s, '实机 · /skill list', '项目 Skills + 官方可装包（本机窗口）')
    p = prefer('shot_live_skill.png', 'shot_skill.png')
    if p:
        pic(s, p, Emu(500_000), Emu(1_050_000), width=Emu(11_000_000))

    # 9 live mcp
    s = add_blank_slide(prs)
    title(s, '实机 · /mcp（内置 ascend-doc）', '昇腾文档 MCP · 只读自动调用')
    p = prefer('shot_live_mcp.png', 'shot_mcp.png')
    if p:
        pic(s, p, Emu(500_000), Emu(1_050_000), width=Emu(11_000_000))

    # 10 safety + tests shot
    s = add_blank_slide(prs)
    title(s, '安全边界 · 工程验证', '默认只读 · 显式确认 · 209 回归')
    card(s, Emu(300_000), Emu(1_100_000), Emu(5_700_000), Emu(2_600_000), '工具与 Git 护栏',
         '自动调查仅只读工具（readOnlyHint）\n'
         '/apply 前必须预览补丁\n'
         '禁止 force push / amend\n'
         'Token 平台隔离（GitCode ≠ GitHub）\n'
         '预算与来源写入报告')
    card(s, Emu(6_200_000), Emu(1_100_000), Emu(5_500_000), Emu(2_600_000), '诚实边界',
         '不替代真实 NPU 上板验证\n'
         '精度/性能以任务书与实测为准\n'
         '不虚构已接入 openJiuwen WorkSwarm\n'
         '演示数据脱敏，不提交 Token')
    p = prefer('shot_live_tests.png', 'shot_live_terminal.png')
    if p:
        pic(s, p, Emu(400_000), Emu(3_900_000), width=Emu(11_200_000))
    else:
        body(s, 3_900_000, 'unittest / npm test：209 通过 · CLI v1.8.0 · MIT', size=14, height=1_500_000)

    # 11 progress / open source
    s = add_blank_slide(prs)
    title(s, '已有进展与开源', '现在就能装、能跑、能量边界')
    body(
        s,
        1_100_000,
        '仓库　https://github.com/enternalna-Koh/CodeVigilAgent\n'
        '许可　MIT　·　版本　v1.8.0　·　唤醒　reviewagent / ra　·　桌面　启动桌面版.bat\n\n'
        '已交付\n'
        '· AI 自动调换 + 多会话 /new /back /sessions\n'
        '· 算子 / 推理 / openGauss 三条专业路由 + Skills\n'
        '· 内置 ascend-doc MCP（信任确认）与 /mcp 管理\n'
        '· Git 生产力链 /fix /commit /push /pr /ship\n'
        '· 桌面版聊天/审查 · 自定义命令 · @文件 · /cost · pre-commit\n'
        '· collect 社区采集 · 大规模离线回归 + CI\n\n'
        '快速上手：安装 CLI 或双击桌面版 → 配置模型 → 粘贴链接 → 看报告 → 确认链落地',
        size=14,
        height=5_200_000,
    )

    # 12 DEMO plan
    s = add_blank_slide(prs)
    title(s, 'DEMO 计划（创意晋级后）', '创意截止 2026-11-10 · DEMO 窗口 11/25—12/27 · 初赛不强制视频')
    card(s, Emu(300_000), Emu(1_100_000), Emu(11_400_000), Emu(2_300_000), '3 分钟视频脚本（规划）',
         '0:00–0:20 痛点 + 装 CLI\n'
         '0:20–1:20 粘贴 GitCode Issue/PR → 自动调换 → 审查报告（脱敏）\n'
         '1:20–2:20 /skill /mcp + /fix 补丁预览（不 force）\n'
         '2:20–3:00 架构一图 + 开源地址 + 边界说明', body_size=13)
    card(s, Emu(300_000), Emu(3_600_000), Emu(5_700_000), Emu(2_600_000), '本阶段提交物',
         '创意 PPT（本文件，含实机截图）\n'
         '作品简介 / 应用场景 / 技术方案 PDF\n'
         '实机窗口截图补充\n'
         '演示视频：晋级 DEMO 阶段再交')
    card(s, Emu(6_200_000), Emu(3_600_000), Emu(5_500_000), Emu(2_600_000), '可选加分演进',
         '封装为 openJiuwen WorkSwarm 工具节点\n'
         'WorkflowAgent 编排取 PR→路由→报告→补丁\n'
         '材料如实标注，不虚构已接入')

    # 13 end
    s = add_blank_slide(prs)
    box = s.shapes.add_textbox(Emu(800_000), Emu(2_000_000), Emu(10_500_000), Emu(3_000_000))
    fill(
        box,
        'CodeVigil Agent\n\n'
        '队伍：三三队　·　赛道：Coding（兼科研）\n'
        'github.com/enternalna-Koh/ReviewAgent\n'
        'MIT · v1.8.0 · reviewagent\n\n'
        '智体共生 · 创新无限',
        size=22,
        bold=True,
        color=ACCENT,
        align=PP_ALIGN.CENTER,
    )


def main():
    if not TEMPLATE.is_file():
        raise SystemExit(f'missing template: {TEMPLATE}')
    prs = Presentation(str(TEMPLATE))
    fill_template_pages(prs)
    while len(prs.slides) > 4:
        delete_slide(prs, len(prs.slides) - 1)
    append_content_slides(prs)
    prs.save(str(OUT))
    print('Wrote', OUT, 'slides=', len(prs.slides), 'size=', OUT.stat().st_size)
    # sanity: no placeholder text left
    for i, s in enumerate(list(prs.slides), 1):
        for sh in s.shapes:
            if getattr(sh, 'has_text_frame', False):
                t = sh.text_frame.text or ''
                if '点击添加' in t or '必填' in t or '可选' in t and 'WorkSwarm' not in t:
                    if '点击添加' in t or '（必填）' in t or '（可选）' in t or '<500' in t:
                        print('WARN leftover on slide', i, repr(t[:60]))


if __name__ == '__main__':
    main()
