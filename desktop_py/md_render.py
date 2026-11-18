# -*- coding: utf-8 -*-
"""Markdown 消息块：只读、可选中复制的 Text，渲染常见 Markdown 语法。

为什么不直接用 Label：Label 的文字不能选中复制，也不能分样式；
Text（state=disabled）既能选中复制，又能用 tag 做粗体/代码/列表等样式。
"""
from __future__ import annotations

import math
import re
import tkinter as tk
import tkinter.font as tkfont

from ui_kit import (AGENT_INK, BG, BORDER, BUBBLE_BG, BUBBLE_BORDER, BUBBLE_INK,
                    FAINT, INK, MINT, RADIUS_BUBBLE, SUB, ScrollArea, round_rect,
                    ui_mono)

CODE_BG = "#0C0E13"
CODE_INK = "#C8D0DC"
SEL_BG = "#2F4B6E"

_INLINE = re.compile(
    r"(?P<escape>\\[\\`*_{}\[\]()#+.\-!>~])"
    r"|(?P<code>`[^`\n]+`)"
    r"|(?P<link>\[[^\]\n]+\]\([^)\s]+\))"
    r"|(?P<bold>\*\*[^\n]+?\*\*|__[^\n]+?__)"
    r"|(?P<ital>\*(?!\*)[^*\n]+\*|(?<![A-Za-z0-9])_[^_\n]+_(?![A-Za-z0-9]))"
    r"|(?P<strike>~~[^~\n]+~~)"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_FENCE = re.compile(r"^\s*```")


def _table_cells(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip().replace(r"\|", "|")
            for cell in re.split(r"(?<!\\)\|", line)]


def _table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


class MarkdownBlock(tk.Frame):
    """一个消息块：内部是只读 Text，高度按内容行数自适应。"""

    def __init__(self, parent, content: str, font, wrap: int,
                 markdown: bool = True):
        super().__init__(parent, bg=BG)
        self._markdown = markdown
        self._font = tkfont.Font(family=font[0], size=font[1],
                                 weight=font[2] if len(font) > 2 else "normal")
        self._fit_job = None
        self._fit_width = None
        self._source = content or ""
        self.text = tk.Text(self, bg=BG, fg=AGENT_INK, bd=0, highlightthickness=0,
                            wrap="word", padx=12, pady=3, height=1, width=1,
                            cursor="xterm", selectbackground=SEL_BG,
                            selectforeground="#FFFFFF", insertwidth=0, font=self._font)
        self.text.pack(fill="both", expand=True)
        self._setup_tags()
        self._fill(content or "")
        self.text.configure(state="disabled")
        self.text.bind("<Configure>", self._schedule_fit, add="+")
        self.text.bind("<MouseWheel>", self._scroll_parent, add="+")
        self.text.bind("<Button-4>", self._scroll_parent, add="+")
        self.text.bind("<Button-5>", self._scroll_parent, add="+")
        self.text.bind("<Button-3>", self._popup)
        for modifier in ("Control", "Command"):
            self.text.bind(f"<{modifier}-a>", self._select_all)
            self.text.bind(f"<{modifier}-c>", self._copy_event)
        self.text.bind("<<Copy>>", self._copy_event)
        self._menu = tk.Menu(self.text, tearoff=0)
        self._menu.add_command(label="复制选中", command=self.copy_selection)
        self._menu.add_command(label="全选", command=self._select_all)
        self._menu.add_command(label="复制全部", command=self.copy_all)
        if self._markdown:
            self._menu.add_command(label="复制 Markdown 原文", command=self.copy_source)

    # ------------------------------------------------------------ 尺寸
    def set_wrap(self, wrap: int) -> None:
        # 实际宽度由父容器决定，空闲时重新测量排版。
        self._schedule_fit()

    def _schedule_fit(self, event=None) -> None:
        if event is not None and event.width == self._fit_width:
            return
        if self._fit_job is None:
            self._fit_job = self.after_idle(self._fit)

    def _fit(self) -> None:
        self._fit_job = None
        if not self.text.winfo_ismapped() or self.text.winfo_width() <= 1:
            return
        self._fit_width = self.text.winfo_width()
        # 按实际排版像素计算；标题、代码块和混合字体的行高可能不同。
        pixels = int(self.text.tk.call(self.text._w, "count", "-update", "-ypixels",
                                       "1.0", "end"))
        line_height = max(1, self._font.metrics("linespace"))
        height = max(1, math.ceil(pixels / line_height))
        if int(self.text.cget("height")) != height:
            self.text.configure(height=height)
        self.text.yview_moveto(0)

    def _scroll_parent(self, event):
        parent = self.master
        while parent is not None:
            if isinstance(parent, ScrollArea):
                if getattr(event, "delta", 0):
                    parent._on_wheel(event)
                else:
                    parent._on_wheel_linux(event)
                return "break"
            parent = getattr(parent, "master", None)
        return None

    # ------------------------------------------------------------ 样式
    def _setup_tags(self) -> None:
        t = self.text
        family = self._font.actual("family")
        size = self._font.actual("size")
        t.tag_configure("bold", font=(family, size, "bold"), foreground=INK)
        self._italic_font = tkfont.Font(family=family, size=size, slant="italic")
        self._bold_italic_font = tkfont.Font(family=family, size=size,
                                            weight="bold", slant="italic")
        t.tag_configure("italic", font=self._italic_font)
        t.tag_configure("bold_italic", font=self._bold_italic_font)
        t.tag_configure("strike", overstrike=True, foreground=FAINT)
        mono_font = ui_mono(max(9, size - 1))
        t.tag_configure("code", font=mono_font,
                        background="#232833", foreground=CODE_INK)
        t.tag_configure("codeblock", font=mono_font,
                        background=CODE_BG, foreground=CODE_INK,
                        lmargin1=18, lmargin2=18, rmargin=18, spacing1=3, spacing3=3)
        t.tag_configure("h1", font=(family, size + 5, "bold"), foreground=INK,
                        spacing1=10, spacing3=4)
        t.tag_configure("h2", font=(family, size + 3, "bold"), foreground=INK,
                        spacing1=8, spacing3=3)
        t.tag_configure("h3", font=(family, size + 1, "bold"), foreground=INK,
                        spacing1=6, spacing3=2)
        t.tag_configure("quote", lmargin1=18, lmargin2=18, foreground=SUB)
        t.tag_configure("bullet", lmargin1=18, lmargin2=32)
        t.tag_configure("rule", foreground=BORDER)
        t.tag_configure("table_header", font=(family, size, "bold"), foreground=INK)
        t.tag_configure("table_separator", foreground=FAINT)
        t.tag_configure("link", foreground=MINT, underline=True)
        t.tag_configure("url", foreground=FAINT)

    # ------------------------------------------------------------ 填充
    def _fill(self, content: str) -> None:
        self._pending_inserts = []
        self._render_content(content)
        # 限制每次传给 Tk 的参数数量，避免超长回复触发 Tcl 的参数上限。
        for start in range(0, len(self._pending_inserts), 1000):
            self.text.tk.call(self.text._w, "insert", "end",
                              *self._pending_inserts[start:start + 1000])
        del self._pending_inserts

    def _insert(self, value: str, tags=()) -> None:
        self._pending_inserts.extend((value, tags))

    def _render_content(self, content: str) -> None:
        if not self._markdown:
            self._insert(content, ("codeblock",))
            return
        lines = (content or "").replace("\r\n", "\n").split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if _FENCE.match(line):
                i += 1
                block = []
                while i < len(lines) and not _FENCE.match(lines[i]):
                    block.append(lines[i])
                    i += 1
                i += 1
                self._insert("\n".join(block) + "\n", ("codeblock",))
                continue
            if not line.strip():
                self._insert("\n")
                i += 1
                continue
            heading = _HEADING.match(line)
            if heading:
                level = min(len(heading.group(1)), 3)
                self._inline(heading.group(2), (f"h{level}",))
                self._insert("\n", (f"h{level}",))
                i += 1
                continue
            if _RULE.match(line):
                self._insert("─" * 40 + "\n", ("rule",))
                i += 1
                continue
            quote = _QUOTE.match(line)
            if quote:
                self._inline(quote.group(1), ("quote",))
                self._insert("\n", ("quote",))
                i += 1
                continue
            bullet = _BULLET.match(line)
            if bullet:
                indent = "  " * (len(bullet.group(1)) // 2)
                self._insert(f"{indent}• ", ("bullet",))
                self._inline(bullet.group(2), ("bullet",))
                self._insert("\n", ("bullet",))
                i += 1
                continue
            if "|" in line and i + 1 < len(lines) and _table_separator(lines[i + 1]):
                columns = _table_cells(line)
                rows = [columns]
                i += 2
                while i < len(lines) and "|" in lines[i] and lines[i].strip():
                    rows.append(_table_cells(lines[i]))
                    i += 1
                self._table(rows)
                continue
            ordered = _ORDERED.match(line)
            if ordered:
                self._insert(f"{ordered.group(1)}{ordered.group(2)} ", ("bullet",))
                self._inline(ordered.group(3), ("bullet",))
                self._insert("\n", ("bullet",))
                i += 1
                continue
            self._inline(line, ())
            self._insert("\n")
            i += 1
        # 每个文本段会额外插入一个末尾换行；去掉它，保留原有空行。
        if self._pending_inserts and self._pending_inserts[-2].endswith("\n"):
            self._pending_inserts[-2] = self._pending_inserts[-2][:-1]

    def _table(self, rows) -> None:
        for row_index, cells in enumerate(rows):
            base = ("table_header",) if row_index == 0 else ()
            for index, cell in enumerate(cells):
                if index:
                    self._insert("  │  ", ("table_separator",))
                self._inline(cell, base)
            self._insert("\n", base)

    def _inline(self, line: str, base: tuple) -> None:
        pos = 0
        for match in _INLINE.finditer(line):
            if match.start() > pos:
                self._insert(line[pos:match.start()], base)
            token = match.group(0)
            if match.group("escape"):
                self._insert(token[1:], base)
            elif match.group("code"):
                self._insert(token[1:-1], base + ("code",))
            elif match.group("bold"):
                self._inline(token[2:-2], base + ("bold",))
            elif match.group("ital"):
                if "bold" in base:
                    self._insert(token[1:-1], base + ("bold_italic",))
                else:
                    self._insert(token[1:-1], base + ("italic",))
            elif match.group("strike"):
                self._insert(token[2:-2], base + ("strike",))
            elif match.group("link"):
                label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
                self._insert(label, base + ("link",))
                self._insert(f" ({url})", base + ("url",))
            pos = match.end()
        if pos < len(line):
            self._insert(line[pos:], base)

    # ------------------------------------------------------------ 复制
    def destroy(self):
        if self._fit_job is not None:
            self.after_cancel(self._fit_job)
            self._fit_job = None
        super().destroy()

    def copy_selection(self) -> None:
        try:
            selected = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return
        self.clipboard_clear()
        self.clipboard_append(selected)

    def copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def copy_source(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._source)

    def _copy_event(self, _event=None):
        self.copy_selection()
        return "break"

    def _select_all(self, _event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _popup(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()


class UserBubble(tk.Frame):
    """右侧圆角气泡，内嵌只读文字以支持鼠标选择和复制。"""

    def __init__(self, parent, text: str, font, max_width: int):
        super().__init__(parent, bg=BG)
        self._font = tkfont.Font(family=font[0], size=font[1],
                                 weight=font[2] if len(font) > 2 else "normal")
        self._canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self._canvas.pack(side="top", anchor="e", padx=(0, 12))
        self.text = tk.Text(self._canvas, bg=BUBBLE_BG, fg=BUBBLE_INK, font=self._font,
                            wrap="word", relief="flat", bd=0, highlightthickness=0,
                            padx=0, pady=0, height=1, width=1, cursor="xterm",
                            selectbackground=SEL_BG, selectforeground="#FFFFFF",
                            insertwidth=0)
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        self._window = self._canvas.create_window(12, 8, window=self.text, anchor="nw")
        self._menu = tk.Menu(self.text, tearoff=0)
        self._menu.add_command(label="复制选中", command=self.copy_selection)
        self._menu.add_command(label="全选", command=self._select_all)
        self._menu.add_command(label="复制全部", command=self.copy_all)
        self.text.bind("<Button-3>", self._popup)
        for modifier in ("Control", "Command"):
            self.text.bind(f"<{modifier}-a>", self._select_all)
            self.text.bind(f"<{modifier}-c>", self._copy_event)
        self.text.bind("<<Copy>>", self._copy_event)
        self.text.bind("<MouseWheel>", self._scroll_parent, add="+")
        self.text.bind("<Button-4>", self._scroll_parent, add="+")
        self.text.bind("<Button-5>", self._scroll_parent, add="+")
        self._fit_job = None
        self._fit_width = None
        self.text.bind("<Map>", self._schedule_fit, add="+")
        self.text.bind("<Configure>", self._schedule_fit, add="+")
        self.set_max_width(max_width)

    def set_max_width(self, max_width: int) -> None:
        max_width = max(120, int(max_width))
        text = self.text.get("1.0", "end-1c")
        longest = max((self._font.measure(line) for line in text.split("\n")), default=0)
        width = max(24, min(max_width - 24, longest + 3))
        self._canvas.itemconfigure(self._window, width=width)
        self._canvas.configure(width=width + 24)
        self._schedule_fit()

    def _schedule_fit(self, event=None):
        if event is not None and hasattr(event, "width") and event.width == self._fit_width:
            return
        if self._fit_job is None:
            self._fit_job = self.after_idle(self._fit)

    def _fit(self):
        self._fit_job = None
        if not self.text.winfo_ismapped() or self.text.winfo_width() <= 1:
            return
        self._fit_width = self.text.winfo_width()
        height = int(self.text.tk.call(self.text._w, "count", "-update", "-ypixels",
                                       "1.0", "end"))
        height = max(self._font.metrics("linespace"), height)
        self._canvas.itemconfigure(self._window, height=height)
        width = int(self._canvas.winfo_reqwidth())
        bubble_height = max(34, height + 16)
        self._canvas.configure(height=bubble_height)
        self._canvas.delete("bubble_bg")
        self._canvas.create_polygon(
            round_rect(0.5, 0.5, width - 0.5, bubble_height - 0.5, RADIUS_BUBBLE),
            fill=BUBBLE_BG, outline=BUBBLE_BORDER, width=1, tags="bubble_bg")
        self._canvas.tag_lower("bubble_bg")
        self.text.yview_moveto(0)

    def destroy(self):
        if self._fit_job is not None:
            self.after_cancel(self._fit_job)
            self._fit_job = None
        super().destroy()

    def _scroll_parent(self, event):
        parent = self.master
        while parent is not None:
            if isinstance(parent, ScrollArea):
                if getattr(event, "delta", 0):
                    parent._on_wheel(event)
                else:
                    parent._on_wheel_linux(event)
                return "break"
            parent = getattr(parent, "master", None)
        return None

    def copy_selection(self):
        try:
            selected = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return
        self.clipboard_clear()
        self.clipboard_append(selected)

    def copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def _copy_event(self, _event=None):
        self.copy_selection()
        return "break"

    def _select_all(self, _event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _popup(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
