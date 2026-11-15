#!/usr/bin/env python3
"""CodeVigil Agent · 聊天回顾（独立 GUI）。

界面形态对齐 WorkBuddy：右侧一列历史会话浮层，单行标题 + 悬停高亮 +
当前会话加粗，点击即恢复完整对话；左侧是消息正文。

只依赖 Python 标准库（tkinter / json / os / subprocess / sys / pathlib）。
数据全部来自仓库根的 CLI：
    python ascend_cli.py sessions list
    python ascend_cli.py sessions show <name>
    python ascend_cli.py sessions delete <name>

用法：
    py -3 chat_reviewer.py          (Windows)
    python3 chat_reviewer.py        (macOS / Linux)

环境变量：
    REVIEWAGENT_HOME  会话目录的上级目录，默认 ~/.reviewagent
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

# ---------- 常量 ----------

APP_TITLE = "CodeVigil Agent · 聊天回顾"
ROOT = Path(__file__).resolve().parent
CLI_SCRIPT = ROOT / "ascend_cli.py"
CLI_TIMEOUT = 60        # 秒
PANEL_WIDTH = 330       # 右侧历史面板宽度
ROW_TITLE_CHARS = 16    # 单行标题可见字数（超出加 …，完整标题见右侧标题栏）

BG = "#f6f7f9"
PANEL = "#ffffff"
PANEL_HEAD = "#fbfcfd"
BORDER = "#dfe4ea"
INK = "#1f2328"
DIM = "#7a828c"
BLUE = "#1f6feb"
GREEN = "#1a7f37"
ORANGE = "#b35c00"
RED = "#b42318"
ROW_HOVER = "#f4f6f9"
ROW_ACTIVE = "#eaf1fb"


# ---------- 解释器 / 目录 ----------

def interpreter_command():
    """Windows 用 py -3，其它系统用 python3。"""
    if sys.platform.startswith("win"):
        return ["py", "-3"]
    return ["python3"]


def resolve_home() -> Path:
    """REVIEWAGENT_HOME 优先，否则 ~/.reviewagent。"""
    override = os.environ.get("REVIEWAGENT_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".reviewagent"


HOME = resolve_home()
SESSIONS_DIR = HOME / "sessions"


def ui_font(size: int = 11, bold: bool = False):
    """跨平台中文字体；缺字体时 Tk 自动回退。"""
    if sys.platform.startswith("win"):
        family = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        family = "PingFang SC"
    else:
        family = "Noto Sans CJK SC"
    return (family, size, "bold") if bold else (family, size)


# ---------- CLI ----------

def run_cli(arguments) -> tuple:
    """调用 CLI 并解析 JSON。返回 (payload, error)，二者互斥。"""
    command = interpreter_command() + [str(CLI_SCRIPT)] + [str(item) for item in arguments]
    environment = dict(os.environ)
    environment["REVIEWAGENT_HOME"] = str(HOME)
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLI_TIMEOUT,
            cwd=str(ROOT),
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return None, "CLI 超时（超过 %d 秒）" % CLI_TIMEOUT
    except FileNotFoundError:
        return None, "找不到 Python 解释器：%s" % " ".join(interpreter_command())
    except OSError as exc:
        return None, "无法启动 CLI：%s" % exc

    output = (completed.stdout or "").strip()
    if not output:
        detail = (completed.stderr or "").strip() or "CLI 无输出，退出码 %s" % completed.returncode
        return None, _one_line(detail)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        return None, "CLI 返回的不是合法 JSON：%s" % exc
    if not isinstance(payload, dict):
        return None, "CLI 返回的 JSON 不是对象"
    if not payload.get("ok"):
        return None, _one_line(str(payload.get("error") or "CLI 返回 ok=false"))
    return payload, None


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _session_file_ok(path_text: str) -> bool:
    """会话文件缺失或损坏 → False（列表跳过该条）。"""
    if not path_text:
        return True
    path = Path(path_text)
    try:
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict)


def _to_turns(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _format_saved_at(value) -> str:
    """2026-11-13T10:30:00+08:00 → 2026-11-13 10:30。"""
    text = str(value or "").strip().replace("T", " ")
    if not text:
        return "—"
    return text[:16] if len(text) >= 16 else text


def _short_time(value) -> str:
    """2026-11-13T10:30:00+08:00 → 11-13 10:30（列表行里省地方）。"""
    stamp = _format_saved_at(value)
    if len(stamp) >= 16:
        return stamp[5:]
    return stamp


def _short_title(title: str, limit: int = ROW_TITLE_CHARS) -> str:
    text = " ".join(str(title or "").split()) or "（未命名会话）"
    return text if len(text) <= limit else text[:limit] + "…"


def fetch_sessions() -> tuple:
    """读取会话列表并按 saved_at 倒序。返回 (rows, error)。"""
    payload, error = run_cli(["sessions", "list"])
    if error:
        return None, error
    raw = payload.get("sessions")
    if not isinstance(raw, list):
        return None, "sessions list 缺少 sessions 数组"

    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if not _session_file_ok(str(item.get("path") or "")):
            continue
        rows.append({
            "name": name,
            "title": str(item.get("title") or name),
            "saved_at": str(item.get("saved_at") or ""),
            "turns": _to_turns(item.get("turns")),
            "summary": str(item.get("summary") or ""),
            "repository": str(item.get("repository") or ""),
            "status": str(item.get("status") or ""),
            "path": str(item.get("path") or ""),
        })
    rows.sort(key=lambda row: row["saved_at"], reverse=True)
    return rows, None


# ---------- 可滚动列表 ----------

class ScrollList(tk.Frame):
    """Canvas + 内嵌 Frame，支持滚轮（Windows / macOS / Linux 三种事件）。"""

    def __init__(self, master, bg: str = PANEL):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync_region)
        self.canvas.bind("<Configure>", self._sync_width)
        self._bind_wheel(self.canvas)

    def _sync_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel)
        widget.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-3, "units"))
        widget.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(3, "units"))

    def _on_wheel(self, event):
        step = -3 if event.delta > 0 else 3
        self.canvas.yview_scroll(step, "units")

    def bind_wheel_deep(self, widget):
        self._bind_wheel(widget)
        for child in widget.winfo_children():
            self.bind_wheel_deep(child)

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()


class HistoryRow(tk.Frame):
    """WorkBuddy 风格的单行历史条目：标题 + 右侧淡色「时间 · N轮」。"""

    def __init__(self, master, session, on_click):
        super().__init__(master, bg=PANEL, cursor="hand2")
        self.session = session
        self.on_click = on_click
        self.selected = False

        self.accent = tk.Frame(self, width=3, bg=PANEL)
        self.accent.pack(side="left", fill="y")

        self.content = tk.Frame(self, bg=PANEL)
        self.content.pack(side="left", fill="both", expand=True, padx=(9, 8), pady=6)

        self.title_label = tk.Label(
            self.content,
            text=_short_title(session["title"]),
            bg=PANEL, fg=INK, font=ui_font(11), anchor="w", justify="left",
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        meta = "%s · %d轮" % (_short_time(session["saved_at"]), session["turns"])
        self.meta_label = tk.Label(
            self.content, text=meta, bg=PANEL, fg=DIM, font=ui_font(9), anchor="e",
        )
        self.meta_label.pack(side="right")

        self._wire_events()
        self.tooltip_text = "%s\n%s · %d 轮 · %s" % (
            session["title"], _format_saved_at(session["saved_at"]),
            session["turns"], session["repository"] or "未关联仓库",
        )

    # -- 事件 --

    def _wire_events(self):   # 不能叫 _bind：会和 tkinter 内部的 _bind 冲突
        for widget in (self, self.accent, self.content, self.title_label, self.meta_label):
            widget.bind("<Button-1>", self._clicked)
            widget.bind("<Enter>", self._entered)
            widget.bind("<Leave>", self._left)

    def _paint(self, bg: str, bold: bool, accent: str):
        for widget in (self, self.content, self.title_label, self.meta_label):
            widget.configure(bg=bg)
        self.title_label.configure(font=ui_font(11, bold=bold))
        self.accent.configure(bg=accent)

    def _clicked(self, _event=None):
        self.on_click(self.session["name"])

    def _entered(self, _event=None):
        if not self.selected:
            self._paint(ROW_HOVER, False, ROW_HOVER)

    def _left(self, event=None):
        if self.selected:
            return
        # 指针只是从标题移到右侧时间，不算离开整行
        if event is not None:
            under = self.winfo_containing(event.x_root, event.y_root)
            if under is not None and (under is self or str(under).startswith(str(self))):
                return
        self._paint(PANEL, False, PANEL)

    def set_selected(self, selected: bool):
        self.selected = selected
        if selected:
            self._paint(ROW_ACTIVE, True, BLUE)     # 当前会话：加粗 + 左侧蓝条
        else:
            self._paint(PANEL, False, PANEL)


# ---------- 主窗口 ----------

class ChatReviewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x640")
        self.minsize(800, 500)
        self.configure(bg=BG)

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", font=ui_font(10))
        style.configure("TEntry", fieldbackground=PANEL)

        self.sessions = []        # 全部会话（未过滤）
        self.visible = []         # 过滤后的展示顺序
        self.current_name = None  # 右侧正在显示的会话
        self.rows = {}            # name -> HistoryRow

        self._build_layout()
        self.after(80, self.refresh_sessions)

    # ----- 布局 -----

    def _build_layout(self):
        # 状态栏先 pack：PanedWindow 带 expand，后 pack 的控件会被挤成 0 高
        status_bar = tk.Frame(self, bg="#eceff3", height=26)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        self.status_label = tk.Label(status_bar, text="加载中…", bg="#eceff3",
                                     fg=DIM, font=ui_font(9), anchor="w", padx=10)
        self.status_label.pack(fill="x")

        self.paned = ttk.Panedwindow(self, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.paned.add(self._build_conversation(), weight=1)
        self.paned.add(self._build_history(), weight=0)

    def _build_conversation(self):
        frame = tk.Frame(self.paned, bg=BG)

        self.title_label = tk.Label(frame, text="未选择会话", bg=BG, fg=INK,
                                    font=ui_font(15, bold=True), anchor="w", justify="left")
        self.title_label.pack(fill="x")
        self.meta_label = tk.Label(frame, text="仓库 —  ·  保存 —", bg=BG, fg=DIM,
                                   font=ui_font(9), anchor="w", justify="left")
        self.meta_label.pack(fill="x", pady=(4, 8))

        body = tk.Frame(frame, bg=BORDER)
        body.pack(fill="both", expand=True)
        self.messages = tk.Text(
            body, wrap="word", bd=0, relief="flat", padx=16, pady=14,
            bg=PANEL, fg=INK, font=ui_font(11), insertwidth=0,
            spacing1=2, spacing3=2, state="disabled",
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.messages.yview)
        self.messages.configure(yscrollcommand=scrollbar.set)
        self.messages.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        scrollbar.pack(side="right", fill="y")

        self.messages.tag_configure("user_head", foreground=BLUE, font=ui_font(11, bold=True),
                                    spacing1=8, spacing3=2)
        self.messages.tag_configure("agent_head", foreground=GREEN, font=ui_font(11, bold=True),
                                    spacing1=10, spacing3=2)
        self.messages.tag_configure("body", foreground=INK, font=ui_font(11),
                                    lmargin1=6, lmargin2=6, spacing3=4)
        self.messages.tag_configure("status_running", foreground=ORANGE, font=ui_font(10))
        self.messages.tag_configure("status_failed", foreground=RED, font=ui_font(10))
        self.messages.tag_configure("placeholder", foreground=DIM, font=ui_font(10), spacing1=10)
        return frame

    def _build_history(self):
        shell = tk.Frame(self.paned, bg=BORDER, width=PANEL_WIDTH)
        shell.pack_propagate(False)

        panel = tk.Frame(shell, bg=PANEL)
        panel.pack(fill="both", expand=True, padx=1, pady=1)

        head = tk.Frame(panel, bg=PANEL_HEAD)
        head.pack(fill="x")
        caption = tk.Label(head, text="历史会话", bg=PANEL_HEAD, fg=DIM,
                           font=ui_font(9), anchor="w")
        caption.pack(fill="x", padx=12, pady=(10, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.apply_filter())
        self.search_entry = ttk.Entry(head, textvariable=self.search_var)
        self.search_entry.pack(fill="x", padx=10, pady=(0, 10))

        self.list_view = ScrollList(panel)
        self.list_view.pack(fill="both", expand=True)

        foot = tk.Frame(panel, bg=PANEL_HEAD)
        foot.pack(fill="x")
        tk.Frame(foot, bg=BORDER, height=1).pack(fill="x")
        buttons = tk.Frame(foot, bg=PANEL_HEAD)
        buttons.pack(fill="x", padx=8, pady=6)
        self.refresh_button = ttk.Button(buttons, text="刷新", command=self.refresh_sessions)
        self.refresh_button.pack(side="left")
        self.delete_button = ttk.Button(buttons, text="删除", command=self.delete_current)
        self.delete_button.pack(side="left", padx=(6, 0))
        return shell

    # ----- 状态 -----

    def set_status(self, text: str):
        self.status_label.configure(text="%s   ｜    会话目录：%s" % (text, SESSIONS_DIR))

    # ----- 列表 -----

    def refresh_sessions(self):
        self.set_status("加载中…")
        self.update_idletasks()
        rows, error = fetch_sessions()
        if error:
            self.sessions = []
            self.visible = []
            self._render_rows()
            self.set_status("加载失败：%s" % error)
            return
        self.sessions = rows
        self.apply_filter()
        self.set_status("共 %d 条会话" % len(rows))

    def apply_filter(self):
        keyword = self.search_var.get().strip().casefold()
        if keyword:
            self.visible = [
                row for row in self.sessions
                if keyword in row["title"].casefold() or keyword in row["summary"].casefold()
            ]
        else:
            self.visible = list(self.sessions)
        self._render_rows()
        if keyword:
            self.set_status("匹配 %d / %d 条会话" % (len(self.visible), len(self.sessions)))

    def _render_rows(self):
        self.list_view.clear()
        self.rows = {}
        if not self.visible:
            empty = tk.Label(self.list_view.inner,
                             text="没有匹配的会话" if self.search_var.get().strip() else "还没有历史会话",
                             bg=PANEL, fg=DIM, font=ui_font(10), pady=18)
            empty.pack(fill="x")
            self.list_view.bind_wheel_deep(empty)
            self.list_view.canvas.yview_moveto(0.0)
            return
        for session in self.visible:
            row = HistoryRow(self.list_view.inner, session, self.select_session)
            row.pack(fill="x")
            self.list_view.bind_wheel_deep(row)
            self.rows[session["name"]] = row
        self._highlight_current()
        self.list_view.canvas.yview_moveto(0.0)   # 倒序，最新在最上面

    def _highlight_current(self):
        for name, row in self.rows.items():
            row.set_selected(name == self.current_name)

    def select_session(self, name: str):
        if name == self.current_name:
            return
        self.load_session(name)

    # ----- 详情 -----

    def load_session(self, name: str):
        self.set_status("加载中…")
        self.update_idletasks()
        payload, error = run_cli(["sessions", "show", name])
        if error:
            self.set_status("加载失败：%s" % error)
            messagebox.showerror("加载失败", "无法读取会话「%s」。\n\n%s" % (name, error), parent=self)
            self.current_name = None
            self._clear_detail("加载失败，右侧已清空。")
            self._highlight_current()
            return

        session = payload.get("session") or {}
        messages = session.get("messages")
        if not isinstance(messages, list):
            self.set_status("加载失败：session.messages 不是数组")
            messagebox.showerror("加载失败", "会话「%s」缺少 messages 数组。" % name, parent=self)
            self.current_name = None
            self._clear_detail("加载失败，右侧已清空。")
            self._highlight_current()
            return

        self.current_name = name
        title = str(session.get("title") or name)
        repository = str(session.get("repository") or "").strip() or "未关联"
        saved_at = _format_saved_at(session.get("saved_at"))
        self.title_label.configure(text=title or "（未命名会话）")
        self.meta_label.configure(text="仓库 %s  ·  保存 %s" % (repository, saved_at))
        self._render_messages(messages)
        self._highlight_current()
        self.set_status("已加载 %s（%d 条消息）" % (name, len(messages)))

    def _clear_detail(self, hint: str = "在右侧选一条历史会话，就能看到完整对话。"):
        self.title_label.configure(text="未选择会话")
        self.meta_label.configure(text="仓库 —  ·  保存 —")
        self.messages.configure(state="normal")
        self.messages.delete("1.0", "end")
        self.messages.insert("end", hint, ("placeholder",))
        self.messages.configure(state="disabled")

    def _render_messages(self, messages):
        self.messages.configure(state="normal")
        self.messages.delete("1.0", "end")
        if not messages:
            self.messages.insert("end", "这个会话还没有消息。", ("placeholder",))
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            content = str(message.get("content") or "").strip()
            state = str(message.get("status") or "completed")
            if role == "user":
                self.messages.insert("end", "● 你\n", ("user_head",))
                self.messages.insert("end", (content or "（空消息）") + "\n", ("body",))
                if state == "running":
                    self.messages.insert("end", "（进行中…）\n", ("status_running",))
                elif state == "failed":
                    self.messages.insert("end", "（回复失败）\n", ("status_failed",))
            elif role == "assistant":
                self.messages.insert("end", "● Agent\n", ("agent_head",))
                self.messages.insert("end", (content or "（空回复）") + "\n", ("body",))
                if state == "running":
                    self.messages.insert("end", "（进行中…）\n", ("status_running",))
                elif state == "failed":
                    self.messages.insert("end", "（回复失败）\n", ("status_failed",))
        self.messages.configure(state="disabled")
        self.messages.see("end")        # 自动滚到最新消息

    # ----- 删除 -----

    def delete_current(self):
        name = self.current_name
        if not name:
            messagebox.showinfo("删除会话", "请先在右侧选择一条历史会话。", parent=self)
            return
        if not messagebox.askyesno("删除会话",
                                   "确定删除会话「%s」？\n\n删除后无法恢复。" % name,
                                   parent=self):
            return
        self.set_status("正在删除…")
        self.update_idletasks()
        _payload, error = run_cli(["sessions", "delete", name])
        if error:
            self.set_status("删除失败：%s" % error)
            messagebox.showerror("删除失败", error, parent=self)
            return
        self.current_name = None
        self._clear_detail("会话已删除。")
        self.refresh_sessions()
        self.set_status("已删除 %s" % name)


# ---------- 入口 ----------

def main() -> int:
    if not CLI_SCRIPT.is_file():
        print("找不到 CLI：%s" % CLI_SCRIPT)
        return 1
    # 中文路径下 Windows 控制台默认 GBK，显式切 UTF-8 避免打印报错
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        app = ChatReviewerApp()
    except tk.TclError as exc:
        print("无法启动图形界面（没有可用显示）：%s" % exc)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
