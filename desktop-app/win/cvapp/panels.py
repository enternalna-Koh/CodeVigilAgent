"""右侧面板槽位：按需创建、显示 / 隐藏、任务结束后刷新。

为什么单列一层：
    面板是「布局」；面板里装什么由功能模块（features/*.py 的 panel_factory）决定。
    shell 只把侧边栏按钮转成 toggle，不需要认识任何一个具体面板 ——
    以后再加第二个右侧面板（比如「审查记录」）不用动 shell。

约定：
    面板是个 tk 控件，可选实现 refresh()，由本模块在「显示」和「任务结束」时调用。
"""
from __future__ import annotations

import tkinter as tk

from . import theme


class PanelHost:
    def __init__(self, parent, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.BG, width=theme.PANEL_WIDTH)
        # 面板是 pack 进来的，必须用 pack_propagate；用 grid_propagate 不生效，
        # 槽位会被内容撑到 395px（实测），固定宽度就白设了。
        self.frame.pack_propagate(False)
        self.panels: dict[str, tk.Widget] = {}
        self.active = ''                          # 当前显示的面板 id

    # ------------------------------------------------------------ 控制
    def toggle(self, feature) -> None:
        panel = self.panels.get(feature.id)
        if panel is not None and panel.winfo_manager():
            panel.pack_forget()
            self.frame.grid_remove()
            self.active = ''
            self.app.set_status('就绪')
            return

        self._hide_all()
        if panel is None:
            try:
                panel = feature.panel_factory(self.frame, self.app)
            except Exception as exc:              # noqa: BLE001
                self.app.append(f'\n[{feature.label}] 打开失败：{exc}\n', 'err')
                return
            self.panels[feature.id] = panel

        self.frame.grid()
        panel.pack(fill='both', expand=True)
        self.active = feature.id
        self.refresh(feature.id)

    def hide(self, feature_id: str) -> None:
        panel = self.panels.get(feature_id)
        if panel is not None:
            panel.pack_forget()
        if self.active == feature_id:
            self.frame.grid_remove()
            self.active = ''

    def refresh(self, feature_id: str) -> None:
        panel = self.panels.get(feature_id)
        callback = getattr(panel, 'refresh', None)
        if callable(callback):
            callback()

    def refresh_visible(self) -> None:
        """任务结束后调用：只刷列表，不动正在显示的对话内容。"""
        for feature_id, panel in self.panels.items():
            if panel.winfo_manager():
                self.refresh(feature_id)

    # ------------------------------------------------------------ 内部
    def _hide_all(self) -> None:
        for panel in self.panels.values():
            if panel.winfo_manager():
                panel.pack_forget()
