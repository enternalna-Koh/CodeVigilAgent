# -*- coding: utf-8 -*-
"""桌面客户端的共用 UI 基础件：配色、字体、圆角按钮、滚动容器。

app.py 与 settings_dialog.py 都从这里取，避免互相 import 形成环。
纯标准库 tkinter，无第三方依赖。
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
IS_WIN = os.name == "nt"

INK = "#E6E6E6"
SUB = "#9AA0AA"
FAINT = "#6B7280"
PANEL = "#12141A"
PANEL_HI = "#181B23"
BORDER = "#2A2E38"
BG = "#0E1015"

MINT = "#7AEBC7"
BTN_BG = "#1F1F1F"
BTN_HOVER = "#2E2E2E"
BTN_PRESS = "#141414"
BTN_BORDER = "#474747"
BTN_DISABLED_BG = "#191919"
BTN_DISABLED_INK = "#3F6B5B"

BUBBLE_BG = "#1E222B"        # 比 PANEL 略亮一点的深灰，看起来像半透明叠在背景上
BUBBLE_BORDER = "#2E3441"
BUBBLE_INK = "#E8EAED"
AGENT_INK = "#E4E6EA"
FAIL_INK = "#F87171"
WARN_INK = "#F59E0B"

RADIUS_BTN = 7
RADIUS_BUBBLE = 14
BTN_H = 28
BTN_PAD = 12
BTN_MIN_W = 64


def round_rect(x1: float, y1: float, x2: float, y2: float, r: float, steps: int = 6):
    """圆角矩形顶点，给 Canvas.create_polygon 用。"""
    import math

    r = max(1.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    corners = [(x1 + r, y1 + r, math.pi, math.pi / 2),
               (x2 - r, y1 + r, -math.pi / 2, math.pi / 2),
               (x2 - r, y2 - r, 0.0, math.pi / 2),
               (x1 + r, y2 - r, math.pi / 2, math.pi / 2)]
    pts = []
    for cx, cy, start, span in corners:
        for i in range(steps + 1):
            angle = start + span * (i / steps)
            pts.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])
    return pts


def _pick_family(candidates, fallback):
    """挑第一个系统里真实存在的字体族；查不到（比如还没有根窗口）就用兜底名。

    Tk 对不存在的字体族不会报错，只会退回默认字体；这里主动挑一次是为了
    让三套系统都尽量用上合适的字（Windows 雅黑、macOS 苹方、Linux Noto）。
    """
    try:
        available = set(tkfont.families())
    except Exception:                                    # noqa: BLE001
        return fallback
    for name in candidates:
        if name in available:
            return name
    return fallback


_FAMILY_CACHE: dict = {}


def _families():
    if not _FAMILY_CACHE:
        if sys.platform == "darwin":
            ui = ["PingFang SC", "Hiragino Sans GB", "STHeiti"]
            mono = ["Menlo", "Monaco", "Courier New"]
        elif IS_WIN:
            ui = ["Microsoft YaHei UI", "Microsoft YaHei", "SimSun"]
            mono = ["Consolas", "Courier New"]
        else:
            ui = ["Noto Sans CJK SC", "Source Han Sans SC",
                  "WenQuanYi Micro Hei", "DejaVu Sans"]
            mono = ["DejaVu Sans Mono", "Liberation Mono", "Courier New"]
        _FAMILY_CACHE["ui"] = _pick_family(ui, ui[0])
        _FAMILY_CACHE["mono"] = _pick_family(mono, mono[0])
    return _FAMILY_CACHE["ui"], _FAMILY_CACHE["mono"]


def ui_font(size: int = 10, bold: bool = False):
    family, _ = _families()
    return (family, size, "bold" if bold else "normal")


def ui_mono(size: int = 9):
    _, family = _families()
    return (family, size)


class RoundButton(tk.Canvas):
    """深色扁平圆角按钮：1pt 描边 + 薄荷绿文字；悬停/按下只换底色。"""

    def __init__(self, parent, text: str, command=None, enabled: bool = True,
                 bg: str = BG, font_size: int = 13, min_w: int = BTN_MIN_W,
                 on_disabled=None):
        self._text = text
        self._command = command
        self._on_disabled = on_disabled
        self._enabled = enabled
        self._hover = False
        self._pressed = False
        self._font = tkfont.Font(family=ui_font(font_size)[0], size=font_size,
                                 weight="normal")
        self._min_w = min_w
        width = max(min_w, self._font.measure(text) + BTN_PAD * 2)
        super().__init__(parent, width=width, height=BTN_H, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_text(self, text: str) -> None:
        """换标题（侧栏折叠按钮在「隐藏历史」/「显示历史」之间切换），并按新文字重算宽度。"""
        if text == self._text:
            return
        self._text = text
        self.configure(width=max(self._min_w, self._font.measure(text) + BTN_PAD * 2))
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        if not self._enabled:
            fill, outline, ink = BTN_DISABLED_BG, BTN_BORDER, BTN_DISABLED_INK
        else:
            fill = BTN_PRESS if self._pressed else (BTN_HOVER if self._hover else BTN_BG)
            outline, ink = BTN_BORDER, MINT
        self.create_polygon(round_rect(0.5, 0.5, w - 0.5, h - 0.5, RADIUS_BTN),
                            fill=fill, outline=outline, width=1)
        self.create_text(w / 2, h / 2, text=self._text, fill=ink, font=self._font)

    def _on_enter(self, _event=None):
        if self._enabled:
            self._hover = True
            self._draw()

    def _on_leave(self, _event=None):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None):
        if self._enabled:
            self._pressed = True
            self._draw()

    def _on_release(self, _event=None):
        if not self._enabled:
            # 置灰时也给一句可见反馈，避免用户以为按钮坏了。
            if self._on_disabled is not None:
                self._on_disabled()
            return
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and self._command is not None:
            self._command()


class SidebarToggleButton(tk.Canvas):
    """顶栏那个小方框图标：圆角矩形 + 左侧竖条，点一下折叠/展开历史栏。

    尺寸固定 24×24，只有文字按钮的四分之一大；悬停时描边提亮。
    """

    SIZE = 24

    def __init__(self, parent, command=None, bg: str = BG):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._hover = False
        self._pressed = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self) -> None:
        self.delete("all")
        size = self.SIZE
        if self._pressed:
            ink = MINT
        elif self._hover:
            ink = INK
        else:
            ink = SUB
        self.create_polygon(round_rect(3.5, 3.5, size - 3.5, size - 3.5, 6.0),
                            fill=BTN_BG, outline=ink, width=1.6)
        # 左侧竖条：和系统「侧栏」图标同一个意思
        self.create_line(10.0, 7.5, 10.0, size - 7.5, fill=ink, width=1.8,
                         capstyle="round")

    def _on_enter(self, _event=None):
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None):
        self._pressed = True
        self._draw()

    def _on_release(self, _event=None):
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self._command is not None:
            self._command()


class Tooltip:
    """轻量气泡提示：鼠标停留 400ms 后在控件下方弹一个 Toplevel。"""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._tip = None
        self._job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress-1>", self.hide, add="+")

    def set_text(self, text: str) -> None:
        self.text = text

    def _schedule(self, _event=None):
        self._cancel()
        self._job = self.widget.after(400, self._show)

    def _show(self):
        self._job = None
        if self._tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(tip, text=self.text, bg=PANEL_HI, fg=INK, font=ui_font(8),
                 padx=8, pady=3, bd=1, relief="solid").pack()
        self._tip = tip

    def hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None


class ScrollArea(tk.Frame):
    """Canvas + 内嵌 Frame：内容超过高度时出现竖向滚动条。"""

    def __init__(self, parent, bg=PANEL):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Dark.Vertical.TScrollbar", background=PANEL_HI, troughcolor=bg,
                        bordercolor=bg, arrowcolor=SUB, darkcolor=PANEL_HI,
                        lightcolor=PANEL_HI, width=9)
        style.map("Dark.Vertical.TScrollbar",
                  background=[("active", BORDER)], arrowcolor=[("active", INK)])
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                 style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        # 滚轮覆盖整个滚动区：指针落在气泡、文字、行间隙上都有效。
        # 绑在 toplevel 的 all 标签上（而不是逐个控件绑），这样鼠标直接落到
        # 内嵌 Label / Canvas 上也能收到；每次滚动先核对指针是否真的在本区域内，
        # 不在就放行，绝不抢输入框或别的区域的滚轮。
        toplevel = self.winfo_toplevel()
        toplevel.bind_all("<MouseWheel>", self._on_wheel, add="+")
        toplevel.bind_all("<Button-4>", self._on_wheel_linux, add="+")
        toplevel.bind_all("<Button-5>", self._on_wheel_linux, add="+")

    def _on_body(self, _event=None):
        self._sync_region()

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync_region()

    def _content_height(self) -> int:
        box = self.canvas.bbox("all")
        return (box[3] - box[1]) if box else 0

    def _sync_region(self):
        """把滚动范围夹到至少一屏：内容不足一屏时拖不出上方/下方空白。"""
        view_w = max(1, self.canvas.winfo_width())
        view_h = max(1, self.canvas.winfo_height())
        # 内嵌窗口的宽度必须跟画布一致。侧栏收起时渲染出来的行会拿到 1px 宽，
        # 展开后如果只等 <Configure>，那些行就一直是「一行一个字」——这里自愈。
        try:
            current = int(float(self.canvas.itemcget(self._window, "width") or 0))
        except (tk.TclError, ValueError):
            current = 0
        if view_w > 1 and current != view_w:
            self.canvas.itemconfigure(self._window, width=view_w)
        box = self.canvas.bbox("all")
        if not box:
            self.canvas.configure(scrollregion=(0, 0, view_w, view_h))
            return
        width = max(box[2] - box[0], view_w)
        height = max(box[3] - box[1], view_h)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _pointer_inside(self) -> bool:
        """指针是否还在本滚动区里（内嵌子控件也算）。"""
        try:
            px, py = self.winfo_pointerxy()
            widget = self.winfo_containing(px, py)
        except tk.TclError:
            return False
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _scroll_by(self, steps: int):
        if not steps:
            return "break"
        if self._content_height() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0.0)   # 不足一屏：任何方向都不动
            return "break"
        self.canvas.yview_scroll(steps, "units")
        return "break"

    def _on_wheel(self, event):
        if not self._pointer_inside():
            return None
        delta = getattr(event, "delta", 0) or 0
        steps = int(-delta / 120) if IS_WIN else int(-delta)
        if steps == 0:
            steps = -1 if delta > 0 else 1
        return self._scroll_by(steps)

    def _on_wheel_linux(self, event):
        if not self._pointer_inside():
            return None
        return self._scroll_by(-1 if getattr(event, "num", 0) == 4 else 1)

    def refresh(self):
        """重排内容后刷新滚动范围（保持当前滚动位置）。"""
        self.canvas.update_idletasks()
        self._sync_region()

    def to_bottom(self):
        self.canvas.update_idletasks()
        self._sync_region()
        # 长文本的 Label 高度可能晚一帧才定下来：再走一遍，避免底部几十像素
        # 被旧的滚动范围挡住（回复看起来像「显示到一半停住」）。
        self.canvas.update_idletasks()
        self._sync_region()
        if self._content_height() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0.0)
        else:
            self.canvas.yview_moveto(1.0)

    def clear(self):
        for child in list(self.body.winfo_children()):
            child.destroy()
        # 清空后必须把滚动位置和范围一起重置，否则会停在旧内容的高度上，
        # 切到短会话时整片区域看着是空的。
        self.canvas.yview_moveto(0.0)
        self._sync_region()

    def swap_body(self, keep, show=True):
        """整段换内容：只留下 keep（新内容已经建好），其余全销毁。

        销毁子控件会让 Windows 立刻重绘暴露出来的区域，一帧一帧地画就能
        看到「文字被拦腰截断」；这里先把内嵌窗口藏起来，换完再显示，
        用户只会看到一次干净的切换。
        """
        self.canvas.itemconfigure(self._window, state="hidden")
        for child in list(self.body.winfo_children()):
            if child is not keep:
                child.destroy()
        keep.pack(fill="x")
        self.canvas.yview_moveto(0.0)
        self._sync_region()
        if show:
            self.show_body()

    def show_body(self):
        """把内嵌内容显示出来（配合 swap_body(show=False) 用）。"""
        self.canvas.itemconfigure(self._window, state="normal")
        self._sync_region()
