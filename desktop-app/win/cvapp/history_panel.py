"""右侧历史会话面板（WorkBuddy 式浮层列表）。

只做三件事：
    1. 列出会话（标题 / 时间·轮次 / 预览），支持搜索
    2. 点一条 → 把完整对话渲染进主输出区，并把它设为「当前会话」
    3. 刷新 / 删除 / 新会话

数据全部来自 cvapp.sessions（它负责调 CLI 的 JSON 接口），
本文件不直接读会话文件，也不改 CLI。
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from . import config, sessions, theme
from .widgets import FlatButton, SlimScrollbar

WIDTH = 360                 # 面板宽度（像素）
WRAP = WIDTH - 56           # 标签换行宽度，给竖条 / 内边距留位
PLACEHOLDER = '搜索标题或内容'


class HistoryCard(tk.Frame):
    """一条会话：左侧选中竖条 + 标题 / 时间·轮次 / 预览 三行。"""

    def __init__(self, parent, row: dict, on_click, on_wheel):
        super().__init__(parent, bg=theme.SIDEBAR, cursor='hand2')
        self.name = str(row.get('name') or '')
        self.row = row
        self._on_click = on_click
        self._selected = False

        self.bar = tk.Frame(self, width=3, bg=theme.SIDEBAR)
        self.bar.grid(row=0, column=0, sticky='ns')

        body = tk.Frame(self, bg=theme.SIDEBAR)
        body.grid(row=0, column=1, sticky='nsew', padx=(10, 12), pady=7)

        self.title = tk.Label(
            body, text=sessions.format_title(row), bg=theme.SIDEBAR, fg=theme.FG_DIM,
            font=theme.ui_font(10), anchor='w', justify='left', wraplength=WRAP,
        )
        self.meta = tk.Label(
            body, text=sessions.format_meta(row), bg=theme.SIDEBAR, fg=theme.FG_FAINT,
            font=theme.ui_font(8), anchor='w',
        )
        self.preview = tk.Label(
            body, text=sessions.format_preview(row), bg=theme.SIDEBAR, fg=theme.FG_FAINT,
            font=theme.ui_font(9), anchor='w', justify='left', wraplength=WRAP,
        )
        self.title.pack(fill='x')
        self.meta.pack(fill='x', pady=(1, 2))
        self.preview.pack(fill='x')

        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self._surfaces = [self, body, self.title, self.meta, self.preview]
        for widget in self._surfaces + [self.bar]:
            widget.bind('<Enter>', self._on_enter)
            widget.bind('<Leave>', self._on_leave)
            widget.bind('<Button-1>', self._clicked)
            widget.bind('<MouseWheel>', on_wheel)
            widget.bind('<Button-4>', on_wheel)      # Linux 滚轮
            widget.bind('<Button-5>', on_wheel)

        for widget in self._surfaces:
            widget.configure(cursor='hand2')

    # -------------------------------------------------- 外观
    def _paint(self, bg: str) -> None:
        for widget in self._surfaces:
            widget.configure(bg=bg)
        self.title.configure(
            fg=theme.FG if self._selected else theme.FG_DIM,
            font=theme.ui_font(10, 'bold' if self._selected else 'normal'),
        )
        self.bar.configure(bg=theme.ACCENT if self._selected else bg)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._paint(theme.PANEL_HI if selected else theme.SIDEBAR)

    # -------------------------------------------------- 交互
    def _on_enter(self, _event=None) -> None:
        if not self._selected:
            self._paint(theme.PANEL_HOVER)

    def _on_leave(self, _event=None) -> None:
        if not self._selected:
            # 光标在子标签之间移动也会触发 Leave，延迟一点再判断，
            # 否则整行颜色会闪。
            self.after(20, self._settle)

    def _settle(self) -> None:
        try:
            under = self.winfo_containing(*self.winfo_pointerxy())
        except (tk.TclError, KeyError):
            return
        if under is not None and (under is self or str(under).startswith(str(self) + '.')):
            return
        if not self._selected:
            self._paint(theme.SIDEBAR)

    def _clicked(self, _event=None) -> None:
        self._on_click(self.name)


class HistoryPanel(tk.Frame):
    """面板本体：标题栏 + 搜索 + 列表 + 底部按钮。"""

    def __init__(self, parent, app):
        super().__init__(parent, bg=theme.SIDEBAR, highlightthickness=1,
                         highlightbackground=theme.BORDER,
                         highlightcolor=theme.BORDER)
        self.app = app
        self.rows: list[dict] = []
        self.cards: dict[str, HistoryCard] = {}
        self.selected = ''
        self._empty: tk.Label | None = None
        self._placeholder = True
        self._generation = 0
        self._open_generation = 0
        self._open_token = None
        self._closed = False
        self._pending = 0
        self._pump = None
        self._search_job = None
        self._queue: queue.Queue = queue.Queue()
        self._queries = sessions.ProcessOwner()

        self._build()
        self.refresh()

    # ------------------------------------------------------------ 布局
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.SIDEBAR)
        head.pack(fill='x', padx=12, pady=(12, 8))
        tk.Label(head, text='历史会话', bg=theme.SIDEBAR, fg=theme.FG,
                 font=theme.ui_font(11, 'bold')).pack(side='left')
        FlatButton(head, '新会话', self.new_session,
                   font=theme.ui_font(9)).pack(side='right')

        box = tk.Frame(self, bg=theme.PANEL, highlightthickness=1,
                       highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT_DIM)
        box.pack(fill='x', padx=12)
        self.search = tk.Entry(
            box, bg=theme.PANEL, fg=theme.FG_FAINT, insertbackground=theme.FG,
            relief='flat', font=theme.ui_font(10),
        )
        self.search.pack(fill='x', padx=8, ipady=4)
        self.search.insert(0, PLACEHOLDER)
        self.search.bind('<FocusIn>', self._on_focus_in)
        self.search.bind('<FocusOut>', self._on_focus_out)
        self.search.bind('<KeyRelease>', self._on_key)
        self.search.bind('<Return>', lambda _e: self.refresh())

        tk.Frame(self, bg=theme.BORDER, height=1).pack(fill='x', padx=12, pady=(10, 0))

        holder = tk.Frame(self, bg=theme.SIDEBAR)
        holder.pack(fill='both', expand=True, padx=(6, 0), pady=(6, 0))
        self.canvas = tk.Canvas(holder, bg=theme.SIDEBAR, highlightthickness=0, bd=0)
        self.bar = SlimScrollbar(holder, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)

        self.inner = tk.Frame(self.canvas, bg=theme.SIDEBAR)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', self._sync_scroll)
        self.canvas.bind('<Configure>', self._sync_width)
        for widget in (self.canvas, self.inner):
            widget.bind('<MouseWheel>', self._on_wheel)
            widget.bind('<Button-4>', self._on_wheel)
            widget.bind('<Button-5>', self._on_wheel)

        foot = tk.Frame(self, bg=theme.SIDEBAR)
        foot.pack(fill='x', padx=12, pady=(6, 12))
        self.count_var = tk.StringVar(value='加载中…')
        tk.Label(foot, textvariable=self.count_var, bg=theme.SIDEBAR, fg=theme.FG_FAINT,
                 font=theme.ui_font(8), anchor='w').pack(fill='x')
        buttons = tk.Frame(foot, bg=theme.SIDEBAR)
        buttons.pack(fill='x', pady=(6, 0))
        FlatButton(buttons, '刷新', self.refresh,
                   font=theme.ui_font(9)).pack(side='left')
        FlatButton(buttons, '删除', self.delete_selected, danger=True,
                   font=theme.ui_font(9)).pack(side='right')

    # ------------------------------------------------------------ 列表
    def refresh(self) -> None:
        """按当前搜索词重新拉列表（不动正在显示的对话内容）。"""
        if self._closed:
            return
        self._cancel_search_job()
        query = self._query()
        self._generation += 1
        generation = self._generation
        self.count_var.set('加载中…')

        def done(rows, error):
            if self._closed or generation != self._generation:
                return                      # 更晚的一次请求已经覆盖这一条
            if error:
                self._apply([])
                self.count_var.set(f'加载失败：{error}')
                self.app.set_status('历史会话加载失败')
                return
            self._apply(rows)

        self._async(lambda: sessions.list_sessions(query), done)

    def _apply(self, rows: list[dict]) -> None:
        self.rows = rows
        for card in self.cards.values():
            card.destroy()
        self.cards.clear()
        if self._empty is not None:
            self._empty.destroy()
            self._empty = None

        if not rows:
            self._empty = tk.Label(
                self.inner, text='共 0 条会话', bg=theme.SIDEBAR, fg=theme.FG_FAINT,
                font=theme.ui_font(9), pady=18,
            )
            self._empty.pack(fill='x')
        else:
            for row in rows:
                card = HistoryCard(self.inner, row, self._open, self._on_wheel)
                card.pack(fill='x')
                self.cards[card.name] = card

        if self.selected not in self.cards:
            self.selected = ''
        self._paint()
        self.count_var.set(f'共 {len(rows)} 条会话')
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.canvas.yview_moveto(0)

    def _paint(self) -> None:
        for name, card in self.cards.items():
            card.set_selected(bool(self.selected) and name == self.selected)

    # ------------------------------------------------------------ 打开
    def _open(self, name: str) -> None:
        if not name or self._closed or self._task_busy():
            return
        self._open_generation += 1
        generation = self._open_generation
        session_generation = self.app._session_generation
        token = self._open_token = object()
        self.app._pending_history = token
        self.selected = name
        self._paint()
        self.app.set_status('正在恢复历史会话…')

        def done(session, error):
            if getattr(self.app, '_pending_history', None) is not token:
                return
            self.app._pending_history = None
            self._open_token = None
            if (self._closed or generation != self._open_generation
                    or session_generation != self.app._session_generation
                    or self.app.runner.busy):
                return
            self._render(name, session, error)

        self._async(lambda: sessions.show_session(name), done)

    def _task_busy(self) -> bool:
        if self.app.runner.busy:
            self.app.append('\n任务运行中，暂不能切换或删除会话。\n', 'err')
            return True
        return False

    def _render(self, name: str, session: dict | None, error: str | None) -> None:
        if error or not session:
            self.selected = ''
            self._paint()
            messagebox.showerror(
                '打开会话失败',
                f'无法恢复会话「{name}」：\n{error or "返回内容为空"}',
                parent=self.app.root,
            )
            self.app.set_status('打开历史会话失败')
            return

        app = self.app
        app.current_session = str(session.get('name') or name)
        app.session_title = str(session.get('title') or name)

        repository = str(session.get('repository') or '').strip()
        if repository and os.path.isdir(repository):
            app.repo_var.set(repository)
            config.save_last_repo(repository)

        # features/chat.py 认的是 chat_session / chat_repository：
        # 不接上这两个，续问会新开一条会话，用户看到的是「又存了一份」。
        app.chat_session = str(session.get('name') or name)
        app.chat_repository = os.path.realpath(repository) if repository and os.path.isdir(repository) else ''

        app.output.clear()
        restored = datetime.now().strftime('%Y-%m-%d %H:%M')
        for text, tag in sessions.render_chunks(session, restored):
            app.output.append(text, tag)
        # OutputPane.append 已经 see('end')，这里再兜一次底：
        # 面板刚展开时高度还没算完，see 可能落在中间。
        try:
            app.output.text.yview_moveto(1.0)
        except tk.TclError:
            pass

        total = len(session.get('messages') or [])
        self.count_var.set(f'共 {len(self.rows)} 条会话 · 已打开 {total} 条消息')
        app.set_status(f'历史会话：{app.session_title}')

    # ------------------------------------------------------------ 操作
    def reset_selection(self) -> None:
        """取消选中（切到新会话时用）。"""
        self._cancel_open()
        self._open_generation += 1
        self.selected = ''
        self._paint()

    def new_session(self) -> None:
        if not self.app.reset_session(clear_output=True):
            return
        self.count_var.set(f'共 {len(self.rows)} 条会话')

    def delete_selected(self) -> None:
        if self._closed or self._task_busy():
            return
        name = self.selected
        if not name:
            messagebox.showinfo('删除会话', '先在列表里点选一条会话。', parent=self.app.root)
            return
        card = self.cards.get(name)
        title = sessions.format_title(card.row) if card else name
        if not messagebox.askyesno(
                '删除会话',
                f'确定删除「{title}」？\n\n会话文件会从磁盘移除，无法撤销。',
                parent=self.app.root):
            return
        if self._task_busy():
            return
        try:
            sessions.delete_session(name)
        except sessions.SessionError as exc:
            messagebox.showerror('删除失败', str(exc), parent=self.app.root)
            return
        if self.app.current_session == name:
            self.app.reset_session(clear_output=True)
        self.reset_selection()
        self.refresh()

    def _cancel_open(self) -> None:
        if (self._open_token is not None
                and getattr(self.app, '_pending_history', None) is self._open_token):
            self.app._pending_history = None
        self._open_token = None

    def close(self) -> None:
        self._cancel_open()
        self._closed = True
        owner = self.__dict__.get('_queries')
        if owner is not None:
            owner.close()
        self._generation += 1
        self._open_generation += 1
        self._cancel_search_job()
        if self._pump is not None:
            try:
                self.after_cancel(self._pump)
            except tk.TclError:
                pass
            self._pump = None

    # ------------------------------------------------------------ 搜索
    def _query(self) -> str:
        return '' if self._placeholder else self.search.get().strip()

    def _on_focus_in(self, _event=None) -> None:
        if self._placeholder:
            self.search.delete(0, 'end')
            self.search.configure(fg=theme.FG)
            self._placeholder = False

    def _on_focus_out(self, _event=None) -> None:
        if not self.search.get().strip():
            self.search.insert(0, PLACEHOLDER)
            self.search.configure(fg=theme.FG_FAINT)
            self._placeholder = True

    def _on_key(self, _event=None) -> None:
        self._cancel_search_job()
        # 每敲一个字都重启 300ms 计时：连续输入只查一次，
        # 但 `sessions list --query` 会读全部会话文件，不能每键都调。
        self._search_job = self.after(300, self.refresh)

    def _cancel_search_job(self) -> None:
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except tk.TclError:
                pass
            self._search_job = None

    # ------------------------------------------------------------ 线程
    def _async(self, work, done) -> None:
        """work() 在后台线程跑，done(result, error) 回到界面线程。"""
        if self._closed:
            return
        self._pending += 1
        owner = self.__dict__.get('_queries')
        if owner is None:
            owner = self._queries = sessions.ProcessOwner()

        def runner():
            try:
                with sessions.query_scope(owner):
                    result = work()
                payload = (done, result, '')
            except Exception as exc:                  # noqa: BLE001
                payload = (done, None, str(exc))
            if not self._closed:
                self._queue.put(payload)

        threading.Thread(target=runner, daemon=True).start()
        self._schedule()

    def _schedule(self) -> None:
        if not self._closed and self._pump is None:
            self._pump = self.after(60, self._drain)

    def _drain(self) -> None:
        self._pump = None
        if self._closed:
            return
        try:
            while True:
                done, result, error = self._queue.get_nowait()
                self._pending = max(self._pending - 1, 0)
                done(result, error)
        except queue.Empty:
            pass
        except tk.TclError:
            return                                    # 窗口已关闭
        if self._pending > 0:
            self._schedule()

    # ------------------------------------------------------------ 滚动
    def _sync_scroll(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.after_idle(self._sync_bar)

    def _sync_bar(self) -> None:
        try:
            self.bar.set(*self.canvas.yview())
        except tk.TclError:
            pass

    def _sync_width(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_wheel(self, event):
        num = getattr(event, 'num', None)
        if num == 4:
            step = -1
        elif num == 5:
            step = 1
        else:
            delta = getattr(event, 'delta', 0)
            if not delta:
                return 'break'
            step = -1 if delta > 0 else 1
        self.canvas.yview_scroll(step * 2, 'units')
        return 'break'
