"""顶部工具栏与输入行按钮：把功能注册表里的按钮摆成横排药丸（对齐 macOS 版观感）。"""
from __future__ import annotations

import tkinter as tk

from . import theme
from .widgets import PillButton


def build_toolbar(parent, shell) -> None:
    """仓库行下面的一排：审查当前改动 / 离线审查 / 模型设置。"""
    features = sorted((f for f in shell.features if f.placement == 'toolbar'),
                      key=lambda f: f.order)
    if not features:
        return
    bar = tk.Frame(parent, bg=theme.BG)
    bar.grid(row=1, column=0, sticky='w', pady=(theme.GAP, 0))
    for feature in features:
        button = PillButton(bar, feature.label, lambda f=feature: shell._invoke(f),
                            accent=feature.kind == 'accent', font=shell.font_ui)
        button.pack(side='left', padx=(0, 8))
        shell.buttons[feature.id] = button


def build_input_actions(parent, shell) -> None:
    """输入行右侧：取消 / 清空显示。"""
    features = sorted((f for f in shell.features if f.placement == 'input-action'),
                      key=lambda f: f.order)
    for feature in features:
        button = PillButton(parent, feature.label, lambda f=feature: shell._invoke(f),
                            accent=feature.kind == 'accent', font=shell.font_ui)
        button.pack(side='left', padx=(8, 0))
        if feature.only_while_running:
            button.config(state='disabled')
        shell.buttons[feature.id] = button
