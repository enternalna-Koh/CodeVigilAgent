# -*- coding: utf-8 -*-
"""文字输入控件的右键菜单：剪切 / 复制 / 粘贴 / 全选。

不自己操作剪贴板，四项都转发 tk 自带的虚拟事件
（<<Cut>> / <<Copy>> / <<Paste>> / <<SelectAll>>），
所以菜单的行为、只读状态和选区规则与键盘快捷键完全一致，
不会出现「菜单粘贴」和 Ctrl+V 结果不同的情况。

单独成文件，避免把交互代码塞进 app.py 或 ui_kit.py。
"""
from __future__ import annotations

import sys
import tkinter as tk

from ui_kit import FAINT, INK, PANEL, PANEL_HI, ui_font

# macOS 的右键在 Tk 里是 Button-2（触控板双指点按）或 Control+左键；
# X11 上 Button-2 是中键粘贴，所以只有 macOS 才绑这两个。
_RIGHT_CLICK = (
    ("<Button-3>", "<Button-2>", "<Control-Button-1>")
    if sys.platform == "darwin" else ("<Button-3>",)
)

_NORMAL = "normal"
_DISABLED = "disabled"

_CUT, _COPY, _PASTE, _SEPARATOR, _SELECT_ALL = 0, 1, 2, 3, 4

_VIRTUAL_EVENT = {
    _CUT: "<<Cut>>",
    _COPY: "<<Copy>>",
    _PASTE: "<<Paste>>",
    _SELECT_ALL: "<<SelectAll>>",
}


def _has_selection(widget) -> bool:
    """Text 与 Entry 都支持 sel.first 索引；无选区时抛 TclError。"""
    try:
        widget.index("sel.first")
        return True
    except (tk.TclError, ValueError, AttributeError):
        return False


def _is_editable(widget) -> bool:
    """只读或禁用时不允许剪切、粘贴，但复制与全选仍可用。"""
    try:
        return str(widget.cget("state")) == _NORMAL
    except (tk.TclError, AttributeError):
        return True


def _clipboard_has_text(widget) -> bool:
    """剪贴板为空（或只放了图片）时把「粘贴」置灰，而不是点了没反应。"""
    try:
        widget.clipboard_get()
        return True
    except (tk.TclError, AttributeError):
        return False


class EditMenu(tk.Menu):
    """挂在单个文字控件上的右键菜单；控件销毁时菜单随之销毁。"""

    def __init__(self, widget):
        super().__init__(widget, tearoff=0, bd=0, font=ui_font(10),
                         bg=PANEL_HI, fg=INK,
                         activebackground=PANEL, activeforeground=INK,
                         disabledforeground=FAINT)
        self.widget = widget
        for index, label in ((_CUT, "剪切"), (_COPY, "复制"), (_PASTE, "粘贴"),
                             (_SELECT_ALL, "全选")):
            self.add_command(label=label,
                             command=lambda i=index: self._invoke(i))
            if index == _PASTE:
                self.add_separator()
        for sequence in _RIGHT_CLICK:
            widget.bind(sequence, self._popup, add="+")

    # ------------------------------------------------------------ 弹出
    def _popup(self, event):
        try:
            self.widget.focus_set()
            self._place_cursor(event)
        except tk.TclError:
            return "break"
        self.sync_state()
        try:
            self.tk_popup(event.x_root, event.y_root)
        finally:
            self.grab_release()
        return "break"

    def _place_cursor(self, event):
        """右键把插入点挪到点击处，但不动已有选区，否则复制前选区先没了。"""
        if _has_selection(self.widget):
            return
        try:
            self.widget.mark_set(
                "insert", self.widget.index(f"@{event.x},{event.y}"))
        except (tk.TclError, ValueError, AttributeError):
            pass

    def sync_state(self):
        """按当前选区、可编辑状态和剪贴板内容刷新菜单项。"""
        selected = _has_selection(self.widget)
        editable = _is_editable(self.widget)
        enabled = {
            _CUT: selected and editable,
            _COPY: selected,
            _PASTE: editable and _clipboard_has_text(self.widget),
            # 空文本上全选无害，不做区分，少一个会出错的分支。
            _SELECT_ALL: True,
        }
        for index, ok in enabled.items():
            self.entryconfigure(index, state=_NORMAL if ok else _DISABLED)

    def _invoke(self, index):
        try:
            self.widget.focus_set()
            if index == _SELECT_ALL and isinstance(self.widget, tk.Text):
                # Tk 自带的 <<SelectAll>> 选到 end，而 Text 会在末尾自动补一个换行，
                # 复制出来就会多一个空行；这里收到最后一个真实字符。
                self.widget.tag_remove("sel", "1.0", "end")
                self.widget.tag_add("sel", "1.0", "end-1c")
                self.widget.mark_set("insert", "end-1c")
                self.widget.see("insert")
            else:
                self.widget.event_generate(_VIRTUAL_EVENT[index])
        except (tk.TclError, AttributeError):
            pass


def attach_edit_menu(widget) -> EditMenu:
    """给文字输入控件挂上右键菜单，返回菜单对象；调用方必须持有引用。"""
    return EditMenu(widget)
