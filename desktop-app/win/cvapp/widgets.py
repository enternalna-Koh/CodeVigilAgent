"""可复用控件：按钮、分组标题、输出面板。

这些控件不认识「审查」「设置」这些业务概念，只负责长得一致。
"""
from __future__ import annotations

import tkinter as tk

from . import ansi_term, theme


class FlatButton(tk.Button):
    """扁平按钮：无边框，悬停变色，支持 accent（强调）/ danger（危险）。"""

    def __init__(self, parent, text: str, command, accent: bool = False,
                 danger: bool = False, font: tuple | None = None, **kwargs):
        self._fg = theme.ACCENT if accent else (theme.DANGER if danger else theme.FG)
        super().__init__(
            parent, text=text, command=command, bg=theme.PANEL_HI, fg=self._fg,
            relief='flat', font=font or theme.ui_font(11), padx=12, pady=6,
            cursor='hand2', activebackground=theme.BG, activeforeground=self._fg,
            borderwidth=0, anchor='w' if kwargs.pop('left', False) else 'center',
            **kwargs,
        )
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

    def _on_enter(self, _event=None) -> None:
        if str(self['state']) == 'normal':
            self.config(bg=theme.BG)

    def _on_leave(self, _event=None) -> None:
        self.config(bg=theme.PANEL_HI if str(self['state']) == 'normal' else theme.PANEL)


def section_label(parent, text: str) -> tk.Label:
    """侧边栏分组标题：小号、灰色、全大写观感。"""
    return tk.Label(
        parent, text=text, bg=theme.SIDEBAR, fg=theme.FG_FAINT,
        font=theme.ui_font(8), anchor='w', padx=10, pady=2,
    )


def divider(parent) -> tk.Frame:
    return tk.Frame(parent, bg=theme.BORDER, height=1)


class SlimScrollbar(tk.Canvas):
    """自绘细滚动条（竖/横通用），内容装得下时只留底色。

    Tk 在 Windows 上会把原生滚动条画成浅灰、还带箭头，
    放在深色面板里像贴了一条白胶带；这里只画 6px 圆角滑块，
    底色跟随所在面板，悬停时略微提亮。
    """

    def __init__(self, parent, command, width: int = 9, orient: str = 'vertical',
                 bg: str = theme.SIDEBAR, thumb: str = theme.BORDER,
                 thumb_hover: str = theme.FG_FAINT):
        self._vertical = orient == 'vertical'
        if self._vertical:
            super().__init__(parent, width=width, bg=bg, highlightthickness=0, bd=0)
        else:
            super().__init__(parent, height=width, bg=bg, highlightthickness=0, bd=0)
        self._command = command
        self._first, self._last = 0.0, 1.0
        self._drag = None
        self._thumb = thumb
        self._thumb_hover = thumb_hover
        self._hover = False
        self.bind('<Configure>', lambda _e: self._redraw())
        self.bind('<Button-1>', self._on_press)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', lambda _e: setattr(self, '_drag', None))
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

    def set(self, first, last) -> None:
        self._first, self._last = float(first), float(last)
        self._redraw()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._redraw()

    def _track(self) -> tuple[float, float]:
        size = self.winfo_height() if self._vertical else self.winfo_width()
        return 4.0, max(size - 4.0, 5.0)

    def _redraw(self) -> None:
        self.delete('all')
        if self._last - self._first >= 0.999:
            return                                    # 装得下，不显示滑块
        top, bottom = self._track()
        span = max(bottom - top, 1.0)
        start = top + span * self._first
        end = max(start + 24.0, top + span * self._last)
        color = self._thumb_hover if self._hover else self._thumb
        if self._vertical:
            x = self.winfo_width() / 2
            self.create_line(x, start, x, end, width=6, capstyle='round', fill=color)
        else:
            y = self.winfo_height() / 2
            self.create_line(start, y, end, y, width=6, capstyle='round', fill=color)

    def _pos(self, event) -> float:
        return event.y if self._vertical else event.x

    def _on_press(self, event) -> None:
        top, bottom = self._track()
        span = max(bottom - top, 1.0)
        start = top + span * self._first
        end = top + span * self._last
        pos = self._pos(event)
        if start <= pos <= end:
            self._drag = pos - start                # 按住滑块
        else:
            self._drag = (end - start) / 2          # 点空白：滑块跳过去
            self._jump(pos)

    def _on_drag(self, event) -> None:
        if self._drag is not None:
            self._jump(self._pos(event))

    def _jump(self, pos: float) -> None:
        top, bottom = self._track()
        span = max(bottom - top, 1.0)
        ratio = (pos - (self._drag or 0) - top) / span
        self._command('moveto', max(0.0, min(ratio, 1.0)))


class OutputPane(tk.Frame):
    """带细滚动条的只读输出区，负责把 ANSI 颜色翻译成 tkinter tag。"""

    def __init__(self, parent, mono_font: tuple):
        super().__init__(parent, bg=theme.BORDER)
        self._font = mono_font
        inner = tk.Frame(self, bg=theme.PANEL)
        inner.pack(fill='both', expand=True, padx=1, pady=1)

        self.text = tk.Text(
            inner, bg=theme.PANEL, fg=theme.FG, insertbackground=theme.FG,
            relief='flat', font=mono_font, wrap='none', padx=12, pady=10,
            spacing1=1, spacing3=1, undo=False, state='normal',
        )
        # 滚动条跟面板同色：原生 ttk 的浅灰条放在深色区里太跳
        self.vsb = SlimScrollbar(inner, command=self.text.yview,
                                 bg=theme.PANEL, thumb=theme.BORDER,
                                 thumb_hover=theme.FG_FAINT)
        self.hsb = SlimScrollbar(inner, command=self.text.xview, orient='horizontal',
                                 bg=theme.PANEL, thumb=theme.BORDER,
                                 thumb_hover=theme.FG_FAINT)
        self.text.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.hsb.pack(side='bottom', fill='x')
        self.vsb.pack(side='right', fill='y')
        self.text.pack(side='left', fill='both', expand=True)

        self.text.tag_config('dim', foreground=theme.FG_DIM)
        self.text.tag_config('accent', foreground=theme.ACCENT)
        self.text.tag_config('err', foreground=theme.DANGER)
        self.text.tag_config('user', foreground=theme.ROLE_USER)
        self.text.tag_config('agent', foreground=theme.ROLE_AGENT)
        self.text.tag_config('bold', font=(mono_font[0], mono_font[1], 'bold'))

        self.text.bind('<MouseWheel>', self._on_wheel)
        self.text.bind('<Button-4>', lambda _e: self.text.yview_scroll(-3, 'units'))
        self.text.bind('<Button-5>', lambda _e: self.text.yview_scroll(3, 'units'))

    def _on_wheel(self, event):
        """滚轮：默认每次 3 行；按住 Shift 横向滚。"""
        step = -1 if getattr(event, 'delta', 0) > 0 else 1
        if getattr(event, 'state', 0) & 0x1:
            self.text.xview_scroll(step * 2, 'units')
        else:
            self.text.yview_scroll(step * 3, 'units')
        return 'break'

    def columns(self, minimum: int = 40, maximum: int = 200) -> int:
        """按当前像素宽度算出 CLI 应该用多少列，避免横条常驻。"""
        import tkinter.font as tkfont
        width = self.text.winfo_width()
        if width <= 1:
            width = max(self.winfo_toplevel().winfo_width() - 260, 320)
        try:
            char_width = tkfont.Font(font=self._font).measure('0') or 8
        except Exception:                              # noqa: BLE001
            char_width = 8
        usable = max(width - 24 - 6, 200)              # 左右内边距 + 竖条
        return max(minimum, min(maximum, usable // char_width))

    def append(self, text: str, tag: str | None = None) -> None:
        if not text:
            return
        # 用户往上翻看历史时不要强制跳回底部，否则滚动会“打架”
        at_bottom = self.text.yview()[1] >= 0.999
        for seg, color, bold in ansi_term.parse(text):
            tags = []
            if color:
                name = 'c_' + color.replace('#', '')
                self.text.tag_config(name, foreground=color)
                tags.append(name)
            if bold:
                tags.append('bold')
            if tag and not tags:
                tags.append(tag)
            self.text.insert('end', seg, tuple(tags) if tags else ())
        if at_bottom:
            self.text.see('end')

    def clear(self) -> None:
        self.text.delete('1.0', 'end')

