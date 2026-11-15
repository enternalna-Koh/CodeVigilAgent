"""视觉常量的唯一来源：改颜色 / 字体只改这里。"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

# ---------------------------------------------------------------- 颜色
BG = '#0f1117'
SIDEBAR = '#12151c'
PANEL = '#171a22'
PANEL_HI = '#1f232d'
BORDER = '#2a2f3a'
FG = '#e6e9ef'
FG_DIM = '#8b93a1'
FG_FAINT = '#5b6270'
ACCENT = '#5eead4'
ACCENT_DIM = '#2dd4bf'
DANGER = '#f87171'

# 历史会话面板与消息角色
ROLE_USER = '#7dd3fc'       # 用户提问（蓝）
ROLE_AGENT = ACCENT         # Agent 回复（青绿，与强调色一致）
PANEL_HOVER = '#1b1f28'     # 历史列表悬停底色
SELECTED = '#212634'        # 历史列表选中底色

# ---------------------------------------------------------------- 尺寸
PAD_OUTER = 16         # 窗口外边距
GAP = 10               # 区块之间的垂直间距
SIDEBAR_WIDTH = 176    # 侧边栏宽度（像素）
PANEL_WIDTH = 360      # 右侧历史会话面板宽度（像素）

# ---------------------------------------------------------------- 字体
UI_FAMILY = 'Microsoft YaHei UI'
# 「中文两格宽」的等宽字体候选：ASCII 半角 + 汉字全角 = 1:2，
# CLI 补空格对齐的框线才能整齐。Consolas 没有汉字字形，仅作兜底。
MONO_CANDIDATES = ['新宋体', 'NSimSun', 'Sarasa Mono SC', 'Consolas']


def ui_font(size: int = 11, weight: str = 'normal') -> tuple:
    return (UI_FAMILY, size, weight)


def pick_mono_font(root: tk.Misc, size: int = 12) -> tuple:
    """挑一个「中文两格宽」的等宽字体，保证框线对齐。"""
    families = set(tkfont.families(root))
    for name in MONO_CANDIDATES:
        if name in families:
            return (name, size)
    return ('Courier New', size)
