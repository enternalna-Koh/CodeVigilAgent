"""聊天气泡面板：用户消息右侧圆角气泡，Agent 回复左侧纯文本。

只负责画，不认识 CLI：消息由外部按顺序 add_user / add_agent 传进来。
状态行（发送中 / 请求失败 / 已取消）挂在最后一条用户消息下面。
"""
from __future__ import annotations

import math
import tkinter as tk

from . import theme
from .widgets import SlimScrollbar

BUBBLE = '#2a303d'          # 气泡底色（深色主题下的浅灰，对比 PANEL 略亮）
BUBBLE_BORDER = '#39404f'
BUBBLE_PAD_X = 12
BUBBLE_PAD_Y = 8
BUBBLE_RADIUS = 14
ROW_GAP = 12
SIDE_PAD = 12
USER_MAX_RATIO = 0.72       # 气泡最宽占可视宽度的比例
AGENT_MAX_RATIO = 0.86


def _round_rect(x1: float, y1: float, x2: float, y2: float, r: float, steps: int = 6):
    """圆角矩形的多边形顶点（顺时针），用于 Canvas.create_polygon。"""
    r = max(1.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts: list[float] = []
    corners = [
        (x1 + r, y1 + r, math.pi, math.pi / 2),          # 左上
        (x2 - r, y1 + r, -math.pi / 2, math.pi / 2),     # 右上
        (x2 - r, y2 - r, 0.0, math.pi / 2),              # 右下
        (x1 + r, y2 - r, math.pi / 2, math.pi / 2),      # 左下
    ]
    for cx, cy, start, span in corners:
        for i in range(steps + 1):
            angle = start + span * (i / steps)
            pts.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])
    return pts


class ChatPane(tk.Frame):
    """可滚动的聊天气泡区。消息条目：{role, text, status, detail}"""

    def __init__(self, parent, ui_font: tuple):
        super().__init__(parent, bg=theme.BORDER)
        self._font = (theme.UI_FAMILY, 10)
        self._small = (theme.UI_FAMILY, 10)
        self._title_font = (theme.UI_FAMILY, 13, 'bold')
        self._messages: list[dict] = []
        self._title = '新对话'
        self._repo = ''
        self._width = 0

        inner = tk.Frame(self, bg=theme.PANEL)
        inner.pack(fill='both', expand=True, padx=1, pady=1)
        self.canvas = tk.Canvas(inner, bg=theme.PANEL, highlightthickness=0, bd=0)
        self.vsb = SlimScrollbar(inner, command=self.canvas.yview, bg=theme.PANEL,
                                 thumb=theme.BORDER, thumb_hover=theme.FG_FAINT)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)

        self.canvas.bind('<Configure>', self._on_resize)
        self.canvas.bind('<MouseWheel>', self._on_wheel)
        self.canvas.bind('<Button-4>', lambda _e: self._scroll(-3))
        self.canvas.bind('<Button-5>', lambda _e: self._scroll(3))

    # ------------------------------------------------------------ 对外
    def set_header(self, title: str, repo: str) -> None:
        self._title = title or '新对话'
        self._repo = repo or ''
        self.redraw()

    def add_user(self, text: str) -> int:
        self._messages.append({'role': 'user', 'text': text, 'status': 'running', 'detail': ''})
        self.redraw(force_bottom=True)
        return len(self._messages) - 1

    def add_agent(self, text: str) -> None:
        self._messages.append({'role': 'agent', 'text': text, 'status': '', 'detail': ''})
        self.redraw(force_bottom=True)

    def finish_user(self, status: str = '', detail: str = '') -> None:
        for message in reversed(self._messages):
            if message['role'] == 'user':
                message['status'] = status
                message['detail'] = detail
                break
        self.redraw(force_bottom=True)

    def clear(self) -> None:
        self._messages.clear()
        self.redraw()

    # ------------------------------------------------------------ 绘制
    def _on_resize(self, event) -> None:
        if abs(event.width - self._width) < 4:
            return
        self._width = event.width
        self.redraw()

    def _on_wheel(self, event):
        self._scroll(-3 if event.delta > 0 else 3)
        return 'break'

    def _scroll(self, units: int) -> None:
        self.canvas.yview_scroll(units, 'units')

    def redraw(self, force_bottom: bool = False) -> None:
        canvas = self.canvas
        try:
            at_bottom = force_bottom or canvas.yview()[1] >= 0.999
        except tk.TclError:
            at_bottom = True
        canvas.delete('all')
        width = self._width or canvas.winfo_width()
        if width <= 1:
            width = 640
        y = 10

        # 标题 + 仓库：用实际文字高度推进 y，别写死行距（高 DPI 下会重叠）
        title_item = canvas.create_text(SIDE_PAD, y, text=self._title, anchor='nw',
                                        font=self._title_font, fill=theme.FG)
        title_box = canvas.bbox(title_item) or (0, y, 0, y + 20)
        y = title_box[3] + 4
        repo = self._repo or '未关联'
        repo_item = canvas.create_text(SIDE_PAD, y, text='仓库：' + repo, anchor='nw',
                                       font=self._small, fill=theme.FG_DIM)
        repo_box = canvas.bbox(repo_item) or (0, y, 0, y + 16)
        y = repo_box[3] + 16

        for message in self._messages:
            if message['role'] == 'user':
                y = self._draw_user(canvas, width, y, message)
            else:
                y = self._draw_agent(canvas, width, y, message)

        total = max(y + 8, canvas.winfo_height())
        canvas.configure(scrollregion=(0, 0, width, total))
        if at_bottom:
            canvas.yview_moveto(1.0)

    def _draw_user(self, canvas, width: int, y: int, message: dict) -> int:
        wrap = max(140, int(width * USER_MAX_RATIO) - BUBBLE_PAD_X * 2)
        item = canvas.create_text(0, 0, text=message['text'], width=wrap, anchor='nw',
                                  font=self._font, fill=theme.FG, justify='left')
        box = canvas.bbox(item) or (0, 0, 0, 0)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
        bubble_w = text_w + BUBBLE_PAD_X * 2
        bubble_h = text_h + BUBBLE_PAD_Y * 2
        x2 = width - SIDE_PAD
        x1 = x2 - bubble_w
        canvas.coords(item, x1 + BUBBLE_PAD_X, y + BUBBLE_PAD_Y)
        rect = canvas.create_polygon(
            _round_rect(x1, y, x2, y + bubble_h, BUBBLE_RADIUS),
            fill=BUBBLE, outline=BUBBLE_BORDER, width=1)
        canvas.tag_lower(rect)

        y += bubble_h
        if message['status']:
            label, color = self._status_text(message)
            status_item = canvas.create_text(x2, y + 3, text=label, anchor='ne',
                                             font=self._small, fill=color)
            status_box = canvas.bbox(status_item) or (0, y, 0, y + 18)
            y = status_box[3] + 6
        return y + ROW_GAP

    def _draw_agent(self, canvas, width: int, y: int, message: dict) -> int:
        wrap = max(200, int(width * AGENT_MAX_RATIO))
        item = canvas.create_text(SIDE_PAD, y, text=message['text'], width=wrap,
                                  anchor='nw', font=self._font, fill=theme.FG,
                                  justify='left')
        box = canvas.bbox(item) or (0, 0, 0, 0)
        return box[3] + ROW_GAP + 2

    @staticmethod
    def _status_text(message: dict):
        status = message.get('status') or ''
        detail = (message.get('detail') or '').strip()
        if status == 'running':
            return '发送中…', theme.FG_DIM
        if status == 'failed':
            text = '请求失败' if not detail else f'请求失败：{detail[:60]}'
            return text, theme.DANGER
        if status == 'interrupted':
            return '已取消', '#f59e0b'
        return '', theme.FG_DIM
