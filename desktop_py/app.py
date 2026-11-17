# -*- coding: utf-8 -*-
"""CodeVigil Agent · Windows / 跨平台桌面客户端（纯 tkinter，无第三方依赖）。

布局：左侧会话列表 + 顶部仓库与操作按钮 + 中部消息气泡 + 底部多行输入。
后端：调用仓库根的 ascend_cli.py（review / chat / sessions），只读它的 JSON 输出。
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# UI 基础件（配色 / 字体 / 圆角按钮 / 滚动容器）在 ui_kit 里，弹窗模块共用同一份。
from ui_kit import (AGENT_INK, BG, BORDER, BTN_BORDER, BTN_DISABLED_BG,  # noqa: F401
                    BTN_DISABLED_INK, BTN_H, BTN_HOVER, BTN_MIN_W, BTN_PAD,
                    BTN_PRESS, BTN_BG, BUBBLE_BG, BUBBLE_BORDER, BUBBLE_INK, FAIL_INK,
                    FAINT, INK, IS_WIN, MINT, PANEL, PANEL_HI, RADIUS_BTN,
                    RADIUS_BUBBLE, ROOT, SUB, WARN_INK, RoundButton, ScrollArea,
                    SidebarToggleButton, Tooltip, round_rect, ui_font, ui_mono)
from settings_dialog import (CUSTOM_FALLBACK_TITLE, SettingsDialog,  # noqa: F401
                             load_ai_config, load_model_choices, save_ai_config)


def cli_prefix():
    """Windows 用 py -3，其它平台用 python3。"""
    return ["py", "-3"] if IS_WIN else ["python3"]


def cli_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def parse_json(text: str):
    """容忍前后夹带提示文字：先整体解析，失败后截取第一个 { 到最后一个 }。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:                                    # noqa: BLE001
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except Exception:                            # noqa: BLE001
                return None
    return None


def err_line(err: str, limit: int = 120) -> str:
    """stderr 取最后一条非空行，供单行状态栏显示（不记录完整报错/密钥）。"""
    lines = [ln.strip() for ln in (err or "").splitlines() if ln.strip()]
    return lines[-1][:limit] if lines else ""


# ---------------------------------------------------------------- 计时与时间
def format_seconds(seconds: float) -> str:
    """与终端 end_think 同一口径：一位小数；超过 60 秒写成 1m 05.3s。"""
    value = max(0.0, float(seconds))
    if value < 60:
        return f"{value:.1f}s"
    minutes = int(value // 60)
    return f"{minutes}m {value - minutes * 60:04.1f}s"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def elapsed_seconds(message) -> float:
    """从消息里取耗时（秒）。旧会话没有 elapsed_ms 时返回 None：不显示 0.0s。"""
    if not isinstance(message, dict):
        return None
    value = message.get("elapsed_ms")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value) / 1000.0


# ---------------------------------------------------------------- 界面偏好
UI_STATE_NAME = "desktop_ui.json"


def ui_state_path() -> Path:
    """界面偏好（侧栏是否折叠）存在 REVIEWAGENT_HOME 下，和会话文件同一层。"""
    root = os.environ.get("REVIEWAGENT_HOME") or str(Path.home() / ".reviewagent")
    return Path(root).expanduser() / UI_STATE_NAME


def load_ui_state() -> dict:
    try:
        data = json.loads(ui_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_state(**changes) -> None:
    """只合并本次要改的键，读不到文件时按空白处理，写失败不影响界面。"""
    data = load_ui_state()
    data.update(changes)
    try:
        path = ui_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- 消息组件
class UserBubble(tk.Frame):
    """右侧圆角气泡：半透明观感的深色底 + 浅色文字。

    宽度由外部传入再随时可调（set_max_width）：窗口/侧栏宽度变了只重画这一个气泡，
    不再整段会话重绘；也就不会出现「恢复会话后气泡被压成一条、文字糊成一团」的问题。
    """

    def __init__(self, parent, text: str, font, max_width: int):
        super().__init__(parent, bg=BG)
        self._text = text
        self._font = font
        self._canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self._canvas.pack(side="top", anchor="e", padx=(0, 12))
        self.set_max_width(max_width)

    def set_max_width(self, max_width: int) -> None:
        wrap = max(120, int(max_width) - 24)
        c = self._canvas
        c.delete("all")
        item = c.create_text(12, 8, text=self._text, width=wrap, anchor="nw",
                             font=self._font, fill=BUBBLE_INK, justify="left")
        box = c.bbox(item) or (0, 0, 0, 0)
        bw = max(48, box[2] - box[0] + 24)
        bh = max(34, box[3] - box[1] + 16)
        c.configure(width=bw, height=bh)
        c.create_polygon(round_rect(0.5, 0.5, bw - 0.5, bh - 0.5, RADIUS_BUBBLE),
                         fill=BUBBLE_BG, outline=BUBBLE_BORDER, width=1, tags="bubble_bg")
        c.tag_lower("bubble_bg")


class AgentText(tk.Frame):
    """左侧纯文字，不加气泡；换行宽度可随时刷新。"""

    def __init__(self, parent, text: str, font, wrap: int):
        super().__init__(parent, bg=BG)
        self._label = tk.Label(self, text=text, bg=BG, fg=AGENT_INK, font=font,
                               justify="left", anchor="w", wraplength=wrap)
        self._label.pack(side="left", padx=(12, 12), pady=(3, 3))

    def set_wrap(self, wrap: int) -> None:
        self._label.configure(wraplength=max(240, int(wrap)))


class ThinkRow(tk.Frame):
    """等待提示行：只刷新自己这一行文字，不重绘整个会话。"""

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.label = tk.Label(self, text="思考中…", bg=BG, fg=SUB,
                              font=ui_font(10), anchor="w", justify="left")
        self.label.pack(side="left", padx=(12, 12), pady=(2, 2))

    def update_seconds(self, seconds) -> None:
        text = "思考中…" if seconds is None else f"思考中… {format_seconds(seconds)}"
        self.label.configure(text=text)


class StatusRow(tk.Frame):
    """回复之后的状态行：完成 / 失败 / 已取消 + 耗时；失败时下一行给原因。"""

    def __init__(self, parent, text: str, color: str, detail: str = "", wrap: int = 400):
        super().__init__(parent, bg=BG)
        tk.Label(self, text=text, bg=BG, fg=color, font=ui_font(10), anchor="w",
                 justify="left").pack(side="top", anchor="w", padx=(12, 12))
        if detail:
            tk.Label(self, text=detail, bg=BG, fg=FAINT, font=ui_font(9), anchor="w",
                     justify="left", wraplength=max(200, wrap)).pack(
                side="top", anchor="w", padx=(12, 12))


# ---------------------------------------------------------------- 主窗口
class App(tk.Tk):
    # 收起历史栏后留下的窄边宽度：只够放那个 24×24 的折叠按钮
    RAIL_WIDTH = 36

    def __init__(self):
        super().__init__()
        self.title("CodeVigil Agent")
        # 初始尺寸别超过屏幕：小屏 / 300% 缩放的笔记本上，700pt 高会把底部
        # 状态栏顶到屏幕外（被任务栏盖住），窗口还拖不上来。
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(1100, max(860, screen_w - 60))
        height = min(700, max(560, screen_h - 90))
        self.geometry(f"{width}x{height}")
        self.minsize(min(900, width), min(600, height))
        self.configure(bg=BG)

        self.repo_var = tk.StringVar(value=str(ROOT))
        self.status_var = tk.StringVar(value="就绪")
        self.session_title_var = tk.StringVar(value="")
        self.session_repo_var = tk.StringVar(value="")
        self.font_body = ui_font(12)
        self.font_small = ui_font(10)

        self.session_name = None
        self.messages = []
        self.proc = None
        self.cancel_flag = False
        self._resize_job = None
        self._task_label = ""
        self._done_queue: "queue.Queue" = queue.Queue()
        # 每点一次「新对话」+1。在飞的 show_session / chat 回调只在代次没变时
        # 才把结果写回界面，否则会把刚清空的对话又填回旧会话。
        self._conversation_epoch = 0
        # 长任务（提问/审查）占用中：期间「新对话」置灰，避免上下文串台。
        self._running = False
        # 本轮提问的计时状态：同一时间只允许一个定时器。
        # _chat_started 由 CLI 的 [think] start 标记写入（与终端同一时刻起算），
        # 之前一直为 None 表示进程还在启动，界面只显示「思考中…」不带秒数。
        self._chat_started = None
        self._chat_timer = None
        self._think_row = None
        self._chat_active = False      # 本轮是否还在等待
        self._sidebar_collapsed = False   # 历史侧栏是否收起（_build 里按存档还原）
        self._sidebar_width_cache = 0     # 上一次按窗口算出的侧栏宽度
        # 已渲染的消息控件：窗口变宽/变窄时只重画它们的换行宽度，不重建整段会话
        self._bubbles: list = []
        self._agent_texts: list = []
        self._outputs: list = []
        # 最后一条用户消息所在的行：失败/取消时只改这一行的状态，不重建整段会话。
        self._last_user_row = None
        # 滚动到底的合并句柄：连续追加多条消息只滚一次，避免长会话卡主线程。
        self._scroll_job = None
        self._scroll_settle = None
        # 整段重建时的临时容器：新内容先建在它里面，建好再一次性换上去。
        self._render_parent = None

        self._build()
        self.bind("<Control-b>", self._toggle_sidebar_shortcut)
        self.bind("<Configure>", self._on_window_configure, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._pump_done)
        self.after(120, self.load_sessions)
        self.after(60, self.show_welcome)

    # ------------------------------------------------------------ 布局
    def _build(self):
        bar = tk.Frame(self, bg=PANEL_HI)
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, textvariable=self.status_var, bg=PANEL_HI, fg=SUB,
                 font=ui_font(10), anchor="w").pack(fill="x", padx=12, pady=4)

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        # 两个面板用 grid：折叠时 grid_remove() 把侧栏整列隐藏，展开时 grid() 原样回来。
        # 之前用 pack/pack_forget 反复切换，连点十几次后 pack 顺序会乱（内容被挤成半宽），
        # grid_remove 会记住原配置，重复切换也不会出错。
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        self._build_sidebar(outer)
        right = tk.Frame(outer, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self._main_panel = right
        self._build_top(right)
        self._build_transcript(right)
        self._build_input(right)
        # 上次退出时是折叠状态就保持折叠（默认展开）
        self.set_sidebar_collapsed(bool(load_ui_state().get("history_sidebar_collapsed")),
                                   persist=False)

    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=PANEL, width=self._sidebar_width())
        side.grid(row=0, column=0, sticky="ns")
        # 侧栏里的子控件是 pack 的：关掉 pack 传播，宽度才定得住；
        # 之前误用 grid_propagate(False)，侧栏被内容撑到 395pt（占页面 36%）。
        side.pack_propagate(False)
        self.sidebar = side

        # 顶行：折叠按钮 + 搜索框。按钮属于历史栏自己，不再挤在主界面标题旁边；
        # 收起后侧栏缩成一条 36pt 窄边、只留这个按钮，所以随时点得回来。
        head = tk.Frame(side, bg=PANEL)
        head.pack(fill="x", padx=8, pady=(8, 4))
        self._sidebar_head = head

        self.sidebar_button = SidebarToggleButton(head,
                                                  command=self.toggle_history_sidebar,
                                                  bg=PANEL)
        self.sidebar_button.pack(side="left", padx=(0, 6), pady=(1, 0))
        self.sidebar_tip = Tooltip(self.sidebar_button, "隐藏历史侧栏（Ctrl+B）")

        self.search_var = tk.StringVar()
        search = tk.Entry(head, textvariable=self.search_var, bg=PANEL, fg=FAINT,
                          insertbackground=INK, relief="flat", font=ui_font(9),
                          highlightthickness=1, highlightbackground=BORDER)
        search.insert(0, "搜索标题和消息")
        self.search_entry = search
        search.bind("<FocusIn>", self._clear_search_placeholder)
        search.bind("<FocusOut>", self._restore_search_placeholder)
        search.pack(side="left", fill="x", expand=True, ipady=5)
        search.bind("<Return>", lambda _e: self.render_sessions(self._sessions_cache))

        self.session_area = ScrollArea(side, bg=PANEL)
        self.session_area.pack(fill="both", expand=True, padx=(2, 0), pady=(4, 8))
        self._sessions_cache = []
        # 打开过的会话按名字缓存消息：CLI 往返要一秒左右，缓存后切回来是瞬开。
        self._session_cache = {}
        self._pending_session = None       # 正在读取的会话（先高亮，避免点了没反应）

    def _clear_search_placeholder(self, _event=None):
        if self.search_var.get() == "搜索标题和消息":
            self.search_var.set("")
            self.search_entry.configure(fg=INK)

    def _restore_search_placeholder(self, _event=None):
        if not self.search_var.get().strip():
            self.search_var.set("搜索标题和消息")
            self.search_entry.configure(fg=FAINT)

    def _build_top(self, parent):
        # 标题行：薄荷绿主标题 + 灰色副标题 + 右侧状态（折叠按钮在历史栏里）
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="CodeVigil Agent", bg=BG, fg=MINT,
                 font=ui_font(17, True), anchor="w").pack(side="left")
        tk.Label(head, text="昇腾 AI Infra 代码审查与问题诊断", bg=BG, fg=FAINT,
                 font=ui_font(9), anchor="w").pack(side="left", padx=(10, 0), pady=(6, 0))
        tk.Label(head, text="已恢复对话", bg=BG, fg=FAINT,
                 font=ui_font(9), anchor="e").pack(side="right", pady=(6, 0))

        # 仓库行：仓库 + 只读路径 + 选择目录（在右侧）
        box = tk.Frame(parent, bg=BG)
        box.pack(fill="x", pady=(6, 0))
        tk.Label(box, text="仓库", bg=BG, fg=SUB, font=ui_font(9)).pack(side="left")
        entry = tk.Entry(box, textvariable=self.repo_var, fg=INK, bg=PANEL,
                         readonlybackground=PANEL, relief="flat", font=ui_font(9),
                         highlightthickness=1, highlightbackground=BORDER)
        entry.configure(state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=8, ipady=5)
        RoundButton(box, "选择目录", self.choose_repo, bg=BG).pack(side="right")

        # 操作按钮行：审查当前改动 / 离线审查 / 模型设置
        ops = tk.Frame(parent, bg=BG)
        ops.pack(fill="x", pady=(8, 0))
        RoundButton(ops, "审查当前改动", self.review_online, bg=BG).pack(side="left")
        RoundButton(ops, "离线审查", self.review_offline, bg=BG).pack(side="left", padx=(8, 0))
        RoundButton(ops, "模型设置", self.open_settings, bg=BG).pack(side="left", padx=(8, 0))

    def _build_transcript(self, parent):
        # 会话标题头已移除：该区域让给消息区，会话名/状态由底部状态栏与历史侧栏体现。
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True, pady=(10, 0))
        self.transcript = ScrollArea(frame, bg=BG)
        self.transcript.pack(fill="both", expand=True)
        self.transcript.canvas.bind("<Configure>", self._on_resize, add="+")

    def _set_session_header(self, title, repo):
        self.session_title_var.set(title)
        self.session_repo_var.set(repo)

    def _build_input(self, parent):
        box = tk.Frame(parent, bg=BG)
        box.pack(fill="x", pady=(10, 0))
        self.input = tk.Text(box, height=3, width=1, bg=PANEL_HI, fg=INK, insertbackground=INK,
                             relief="flat", font=ui_font(12), wrap="word",
                             highlightthickness=1, highlightbackground=BORDER,
                             padx=8, pady=6)
        self.input.pack(side="left", fill="both", expand=True)
        self.input.bind("<Return>", self._on_enter)

        buttons = tk.Frame(box, bg=BG)
        buttons.pack(side="left", padx=(8, 0))
        RoundButton(buttons, "发送", self.send).pack(side="left")
        self.cancel_button = RoundButton(buttons, "取消", self.cancel, enabled=False)
        self.cancel_button.pack(side="left", padx=(8, 0))
        # 置灰时点击也要有可见反馈，否则就是「点了没反应」。
        self.new_button = RoundButton(buttons, "新对话", self.new_conversation,
                                      on_disabled=self._new_conversation_blocked)
        self.new_button.pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------ 侧栏折叠
    def toggle_history_sidebar(self):
        self.set_sidebar_collapsed(not self._sidebar_collapsed)

    def _toggle_sidebar_shortcut(self, _event=None):
        self.toggle_history_sidebar()
        return "break"

    def _sidebar_width(self) -> int:
        """历史栏 = 窗口宽度的四分之一（夹 200~320，窄窗不至于挤、宽窗不至于太肥）。"""
        width = self.winfo_width()
        if width <= 1:
            width = 1100
        return max(200, min(320, int(width * 0.25)))

    def _on_window_configure(self, event):
        if event.widget is not self:
            return
        width = self._sidebar_width()
        if abs(width - self._sidebar_width_cache) < 8:
            return
        self._sidebar_width_cache = width
        if not self._sidebar_collapsed:
            self.sidebar.configure(width=width)
        self._schedule_rewrap(120)

    def _schedule_rewrap(self, delay: int = 160):
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:                            # noqa: BLE001
                pass
        self._resize_job = self.after(delay, self._rewrap)

    def set_sidebar_collapsed(self, collapsed: bool, persist: bool = True):
        """折叠 = 侧栏收成 36pt 窄边（只留折叠按钮）；展开 = 回到窗口 1/4 宽。

        按钮本身在历史栏里，所以收起后必须留一条窄边，否则就点不回来了。
        列表控件不销毁，选中项和滚动位置都保持原样。
        """
        collapsed = bool(collapsed)
        if collapsed == self._sidebar_collapsed:
            return
        self._sidebar_collapsed = collapsed
        if collapsed:
            self.search_entry.pack_forget()
            self.session_area.pack_forget()
            self.sidebar.configure(width=self.RAIL_WIDTH)
            self._sidebar_head.pack_configure(padx=(6, 6), pady=(8, 4))
            self.sidebar_button.pack_configure(padx=(0, 0))   # 窄边里居中，别被挤窄
        else:
            self.sidebar.configure(width=self._sidebar_width())
            self._sidebar_head.pack_configure(padx=8, pady=(8, 4))
            self.sidebar_button.pack_configure(padx=(0, 6))
            self.search_entry.pack(side="left", fill="x", expand=True, ipady=5)
            self.session_area.pack(fill="both", expand=True, padx=(2, 0), pady=(4, 8))
        self._main_panel.grid_configure(padx=(8, 0) if collapsed else (10, 0))
        if getattr(self, "sidebar_tip", None) is not None:
            self.sidebar_tip.set_text("显示历史侧栏（Ctrl+B）" if collapsed
                                      else "隐藏历史侧栏（Ctrl+B）")
        if persist:
            save_ui_state(history_sidebar_collapsed=collapsed)
        self.set_status("已收起历史侧栏（Ctrl+B 切换）" if collapsed
                        else "已展开历史侧栏（Ctrl+B 切换）")
        # 宽度变了要重新折行：气泡与正文的 wraplength 都按新宽度重算
        self._schedule_rewrap(80)
        # 侧栏重新出现时，列表里的行可能是在「收起状态」下建的（宽度只有 1px），
        # 补一次刷新让它们按真实宽度重排，不然会变成一行一个字。
        if not collapsed:
            self.after(60, self.session_area.refresh)

    def show_welcome(self):
        self._set_session_header("CodeVigil Agent", f"仓库：{self.repo_var.get()}")
        self.append_output("欢迎使用 CodeVigil Agent。\n"
                           "选择仓库后点「审查当前改动」，或在下方输入问题直接对话。")

    # ------------------------------------------------------------ 事件
    def _on_enter(self, event):
        if event.state & 0x0001:            # Shift+Enter 换行
            return None
        self.send()
        return "break"

    def _on_resize(self, _event=None):
        self._schedule_rewrap(180)

    def _rewrap(self):
        """宽度变了只重画已有气泡/正文的换行宽度，不重建整段会话。

        以前这里调 rerender()：会话一长就闪一下、滚动位置乱跳，而且重建瞬间
        画布宽度还没量出来，气泡会被压成一条（恢复会话后最明显）。
        """
        self._resize_job = None
        was_at_bottom = self._is_at_bottom()
        bubble_w, agent_w = self.bubble_wrap(), self.agent_wrap()
        for bubble in list(self._bubbles):
            if bubble.winfo_exists():
                bubble.set_max_width(bubble_w)
        for text in list(self._agent_texts):
            if text.winfo_exists():
                text.set_wrap(agent_w)
        for label in list(self._outputs):
            if label.winfo_exists():
                label.configure(wraplength=agent_w)
        self.transcript.refresh()
        if was_at_bottom:
            # 重新折行会改总高度：原来停在底部的话，重排后也要回到底部，
            # 否则最后一条回复会被界面下沿切掉半截（看着像「拦腰截断」）。
            self.transcript.to_bottom()

    def _is_at_bottom(self, tolerance: float = 0.002) -> bool:
        try:
            return self.transcript.canvas.yview()[1] >= 1.0 - tolerance
        except tk.TclError:
            return True

    def set_status(self, text: str):
        self.status_var.set(text)

    def bubble_wrap(self) -> int:
        width = self.transcript.canvas.winfo_width()
        if width < 60:
            # 画布还没排版（刚恢复会话/刚启动）：按窗口宽度估一个，别用 1px 去算
            width = max(600, self.winfo_width() - self._sidebar_width() - 80)
        return max(160, int(width * 0.72))

    def agent_wrap(self) -> int:
        width = self.transcript.canvas.winfo_width()
        if width < 60:
            width = max(600, self.winfo_width() - self._sidebar_width() - 80)
        return max(240, int(width * 0.86))

    # ------------------------------------------------------------ 消息
    def append_user(self, text: str, status: str = "running") -> None:
        self.messages.append({"role": "user", "content": text, "status": status,
                              "sent_at": iso_now()})
        self._render_one(self.messages[-1])

    def append_agent(self, text: str, elapsed_ms=None, finished_at: str = "") -> None:
        self.messages.append({"role": "assistant", "content": text, "status": "completed",
                              "elapsed_ms": elapsed_ms,
                              "finished_at": finished_at or iso_now()})
        self._render_one(self.messages[-1])

    def append_output(self, text: str) -> None:
        self.messages.append({"role": "output", "content": text, "status": "completed"})
        self._render_one(self.messages[-1])

    def _render_one(self, message, scroll: bool = True):
        row = tk.Frame(self._render_parent or self.transcript.body, bg=BG)
        row.pack(fill="x", pady=(4 if message["role"] == "user" else 2, 2))
        role = message["role"]
        try:
            if role == "user":
                bubble = UserBubble(row, message["content"], self.font_body,
                                    self.bubble_wrap())
                bubble.pack(fill="x")
                self._bubbles.append(bubble)
                self._last_user_row = row
                self._render_user_status(row, message)
            elif role == "output":
                # 审查/离线审查的结果用等宽字体（Consolas）+ 比正文（雅黑 12）
                # 小一号的字号：肉眼一照面就能和主聊天分开，字号又足够大到读着不累。
                label = tk.Label(row, text=message["content"], bg=BG, fg=AGENT_INK,
                                 font=ui_mono(11), justify="left", anchor="w",
                                 wraplength=self.agent_wrap(), pady=6)
                label.pack(fill="x", padx=12)
                self._outputs.append(label)
            else:
                text_row = AgentText(row, message["content"], self.font_body,
                                     self.agent_wrap())
                text_row.pack(fill="x")
                self._agent_texts.append(text_row)
                self._render_agent_meta(row, message)
        except Exception as exc:                          # noqa: BLE001
            # 单条消息画不出来时只废掉这一行：以前一旦抛错，整段会话就停在
            # 「重建到一半」的状态，界面看着像卡死，还怎么点都不动。
            self._render_broken_row(row, exc)
        if scroll:
            self._request_scroll_bottom()

    def _render_broken_row(self, row, exc):
        """消息内容异常时的兜底行：保留位置，不把整段会话搞坏。"""
        try:
            for child in list(row.winfo_children()):
                child.destroy()
            tk.Label(row, text=f"（这条消息无法显示：{exc}）", bg=BG, fg=FAIL_INK,
                     font=ui_font(10), anchor="w", justify="left",
                     wraplength=self.agent_wrap()).pack(fill="x", padx=12, pady=2)
        except tk.TclError:
            pass

    def _render_user_status(self, row, message):
        """失败 / 已取消写在气泡下方（左侧），失败原因另起一行；正常不占位。"""
        status = message.get("status") or ""
        if status not in ("failed", "interrupted"):
            return
        label = "失败" if status == "failed" else "已取消"
        seconds = elapsed_seconds(message)
        if seconds is not None:
            label += f" {format_seconds(seconds)}"
        detail = ""
        if status == "failed":
            detail = message.get("detail") or ""
        StatusRow(row, label, FAIL_INK if status == "failed" else WARN_INK,
                  detail=detail, wrap=self.agent_wrap()).pack(fill="x")

    def _render_agent_meta(self, row, message):
        """回复正文之后只留一行「已完成 X.Xs」；旧会话没有 elapsed_ms 就不显示，绝不补 0.0s。"""
        seconds = elapsed_seconds(message)
        if seconds is not None:
            StatusRow(row, f"已完成 {format_seconds(seconds)}", SUB).pack(fill="x")

    def _request_scroll_bottom(self):
        """把连续追加的消息合并成「一次」滚动到底。

        以前每加一行就同步滚一次（每次都 update_idletasks 等布局），
        40 多条消息时要卡 3 秒以上，窗口看起来像卡死；合并后只滚一次。
        """
        if self._scroll_job is not None:
            return
        self._scroll_job = self.after_idle(self._flush_scroll_bottom)

    def _flush_scroll_bottom(self):
        self._scroll_job = None
        try:
            if not self.transcript.winfo_exists():
                return
            self.transcript.to_bottom()
        except tk.TclError:
            return
        # 长文本的行高有时晚一帧才定下来：补一次校正，否则会停在离底部
        # 还差几十像素的位置，最后一条回复看着像被下沿切掉半截。
        self._scroll_settle = self.after(70, self._resettle_scroll)

    def _resettle_scroll(self):
        self._scroll_settle = None
        try:
            if not self.transcript.winfo_exists():
                return
            if not self._is_at_bottom():
                self.transcript.to_bottom()
        except tk.TclError:
            pass

    def _cancel_scroll_job(self):
        for attr in ("_scroll_job", "_scroll_settle"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:                        # noqa: BLE001
                    pass
                setattr(self, attr, None)

    def rerender(self):
        """整段重画：新内容先建在临时容器里，建好再一次性换上去。

        旧写法是先 clear() 再一行一行建：每销毁一个控件 Windows 就立刻重绘
        暴露出来的区域，切会话时能看到文字被一条条切开、甚至只剩半截。
        现在旧内容一直留到最后一刻，换上去时才重绘一次。
        """
        snapshot = list(self.messages)
        holder = tk.Frame(self.transcript.body, bg=BG)
        self._cancel_scroll_job()
        self._think_row = None
        self._bubbles = []
        self._agent_texts = []
        self._outputs = []
        self._last_user_row = None
        self.messages = []
        # 关闭新容器（以及最后一刻的 body）的几何传播：否则每加一行都要把
        # 已有内容重新量一遍，43 条消息实测 1.15s → 0.20s。
        holder.pack_propagate(False)
        self._render_parent = holder
        try:
            for message in snapshot:
                self.messages.append(message)
                self._render_one(message, scroll=False)
        finally:
            self._render_parent = None
        body = self.transcript.body
        body.pack_propagate(False)
        try:
            self.transcript.swap_body(holder, show=False)
            holder.pack_propagate(True)
        finally:
            body.pack_propagate(True)
        # 尺寸都定下来之后再显示，避免先闪一下空白再撑开
        self.transcript.show_body()
        if self._chat_active:
            self._attach_think_row()
        self._request_scroll_bottom()

    def _mark_last_user(self, status: str, detail: str = "", seconds=None):
        """失败 / 取消：只改最后一条用户消息，并且只重画它那一行的状态。

        这里以前调 rerender()（整段会话销毁重建），回复迟到或报错的瞬间
        主线程会卡住好几秒，界面看上去就是「AI 回复卡住」。
        """
        target = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                target = i
                break
        if target is None:
            return
        self.messages[target]["status"] = status
        if detail:
            self.messages[target]["detail"] = detail
        if seconds is not None:
            self.messages[target]["elapsed_ms"] = int(round(seconds * 1000))
            self.messages[target]["finished_at"] = iso_now()
        self._refresh_last_user_status(self.messages[target])

    def _settle_last_user(self):
        """成功回复：只把最后一条用户消息标成完成，界面不需要重画。"""
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                if self.messages[i].get("status") == "running":
                    self.messages[i]["status"] = "completed"
                return

    def _refresh_last_user_status(self, message):
        """只重画最后一条用户消息下方的状态行（气泡本体保持不动）。"""
        row = self._last_user_row
        try:
            alive = row is not None and row.winfo_exists()
        except tk.TclError:
            alive = False
        if not alive:
            # 找不到对应控件（例如刚切过会话）：退回整段重建，至少状态是对的。
            self.rerender()
            return
        for child in list(row.winfo_children())[1:]:      # 第 0 个是气泡本体
            child.destroy()
        try:
            self._render_user_status(row, message)
        except tk.TclError:
            pass
        self._request_scroll_bottom()

    def clear_transcript(self):
        self.stop_chat_timing()
        self._cancel_scroll_job()
        self.transcript.clear()
        self.messages = []
        self._bubbles = []
        self._agent_texts = []
        self._outputs = []
        self._last_user_row = None

    # ------------------------------------------------------------ 计时
    def begin_chat_timing(self, start=None):
        """开始等待计时，返回起点值（同一个 perf_counter 也要传给 CLI）。

        起点由 send() 在「按下发送」那一行取好传进来：之前是从 CLI 打出
        [think] start 才起算，白白漏掉进程启动的一秒多；后来改成发送即起算，
        但渲染用户气泡也要几十毫秒，仍然比真实等待短一截。现在起点就是点击瞬间。
        """
        self.stop_chat_timing()
        self._chat_active = True
        self._chat_started = time.perf_counter() if start is None else start
        self._attach_think_row()
        self._tick_chat()
        return self._chat_started

    def _attach_think_row(self):
        if self._think_row_alive():
            return
        row = ThinkRow(self.transcript.body)
        row.pack(fill="x", pady=(2, 2))
        row.update_seconds(None)
        self._think_row = row
        self.transcript.to_bottom()

    def _think_row_alive(self) -> bool:
        try:
            return self._think_row is not None and self._think_row.winfo_exists()
        except tk.TclError:
            return False

    def _tick_chat(self):
        self._chat_timer = None
        if not self._chat_active:
            return                          # 已停表，不再排下一次
        if not self._think_row_alive():
            self._attach_think_row()
        if self._think_row_alive():
            start = self._chat_started
            self._think_row.update_seconds(None if start is None else time.perf_counter() - start)
        self._chat_timer = self.after(200, self._tick_chat)

    def stop_chat_timing(self):
        """停表并清掉等待行；返回本轮已等待秒数（未起算时返回 None）。

        成功 / 失败 / 取消 / 关窗 / 切会话这五条路径都要经过这里。
        """
        seconds = None
        if self._chat_started is not None:
            seconds = max(0.0, time.perf_counter() - self._chat_started)
        if self._chat_timer is not None:
            try:
                self.after_cancel(self._chat_timer)
            except Exception:                            # noqa: BLE001
                pass
            self._chat_timer = None
        self._chat_started = None
        self._chat_active = False
        if self._think_row is not None:
            try:
                self._think_row.destroy()
            except tk.TclError:
                pass
            self._think_row = None
        return seconds

    def _on_close(self):
        self.stop_chat_timing()             # 关窗前停表，避免定时器打到已销毁的控件
        self.destroy()

    # ------------------------------------------------------------ 后端
    def run_cli(self, *args, timeout: int = 120, track: bool = True, extra_env=None):
        """同步跑一次 CLI，返回 (code, stdout, stderr)。track=False 时不占用取消句柄。

        extra_env 用来给这一次调用补环境变量（提问时传 REVIEWAGENT_CLIENT_START，
        让 CLI 用同一个单调时钟从「点发送」那一刻算耗时）。
        """
        env = cli_env()
        if extra_env:
            env.update({str(k): str(v) for k, v in extra_env.items()})
        base = cli_prefix() + [str(ROOT / "ascend_cli.py")] + [str(a) for a in args]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
        try:
            proc = subprocess.Popen(base, cwd=str(ROOT), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
        except FileNotFoundError:
            base = [sys.executable, str(ROOT / "ascend_cli.py")] + [str(a) for a in args]
            proc = subprocess.Popen(base, cwd=str(ROOT), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
        if track:
            self.proc = proc
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            out, err = proc.communicate()
            err = (err or "") + f"\n[超时 {timeout}s]"
        code = proc.returncode
        if track:
            self.proc = None
        return code, out or "", err or ""

    def run_async(self, work, done, label: str, cancellable: bool = False):
        """后台线程跑 CLI；结果放队列，由主线程的 _pump_done 取出执行（tkinter 不是线程安全的）。

        cancellable=True 仅用于长任务（提问/审查）：这类调用 track=True 持有 proc 句柄，
        取消按钮才真正生效；会话读写是短任务，取消按钮保持禁用，避免点了没反应。
        """
        self._task_label = label
        if cancellable:
            self.cancel_flag = False
            self._running = True
            self.new_button.set_enabled(False)
        self.set_status(f"{label} 运行中…")
        self.cancel_button.set_enabled(cancellable)

        def runner():
            try:
                result = work()
            except Exception as exc:                     # noqa: BLE001
                result = ("error", str(exc))
            self._done_queue.put((done, result, cancellable))

        threading.Thread(target=runner, daemon=True).start()

    def _pump_done(self):
        try:
            while True:
                done, result, cancellable = self._done_queue.get_nowait()
                if cancellable:
                    # 只有长任务结束才放开「新对话」；短的会话读取不能提前解锁。
                    self._running = False
                    self._task_label = ""
                    self.cancel_button.set_enabled(False)
                    self.new_button.set_enabled(True)
                try:
                    done(result)
                except Exception as exc:                 # noqa: BLE001
                    self.set_status(f"回调失败：{exc}")
        except queue.Empty:
            pass
        self.after(50, self._pump_done)

    # ------------------------------------------------------------ 动作
    def choose_repo(self):
        path = filedialog.askdirectory(title="选择 Git 仓库", initialdir=self.repo_var.get())
        if path:
            self.repo_var.set(str(Path(path).resolve()))
            self._set_session_header(self.session_title_var.get(),
                                     f"仓库：{self.repo_var.get()}")

    def open_settings(self):
        """弹出模型设置对话框（与旧版一致，应用内自选服务商/模型）。

        弹窗构造失败（缺 scripts 模块、Tk 主题异常等）时降级为「用记事本打开配置文件」，
        保证按钮永远有可见反应，不会像之前那样静默失灵。
        """
        try:
            SettingsDialog(self)
            return
        except Exception as exc:                         # noqa: BLE001
            self.set_status(f"设置弹窗打开失败，改用配置文件：{exc}")

        config = Path.home() / ".reviewagent" / "ai_config.json"
        if not config.exists():
            self.set_status(f"模型配置不存在：{config}")
            messagebox.showinfo("模型设置", f"还没有配置文件：\n{config}")
            return

        candidates = []
        if IS_WIN:
            # 记事本一定存在；DETACHED_PROCESS 避免关掉主程序时连带关闭编辑器。
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0)
            candidates.append(["notepad.exe", str(config)])
            candidates.append(["write.exe", str(config)])
        elif sys.platform == "darwin":
            candidates.append(["open", "-a", "TextEdit", str(config)])
            candidates.append(["open", str(config)])
        else:
            candidates.append(["xdg-open", str(config)])

        opened = False
        for cmd in candidates:
            try:
                subprocess.Popen(cmd, creationflags=(flags if IS_WIN else 0),
                                 close_fds=True)
                opened = True
                break
            except (OSError, FileNotFoundError):
                continue
        if not opened and IS_WIN:
            # 最后回退：系统默认关联（若用户自定义过 .json 关联则可用）。
            try:
                os.startfile(str(config))                # noqa: S606
                opened = True
            except OSError:
                pass

        if opened:
            self.set_status(f"已打开模型配置：{config}")
        else:
            self.set_status("无法自动打开配置，请手动编辑")
            messagebox.showinfo("模型设置",
                                f"没有找到可用的文本编辑器，请手动打开：\n{config}")

    def review_online(self):
        self._review(False)

    def review_offline(self):
        self._review(True)

    def _review(self, offline: bool):
        args = ["review"] + (["--offline"] if offline else [])
        label = "离线审查" if offline else "审查当前改动"

        def done(result):
            if result[0] == "error":
                self.set_status(f"{label}失败")
                return
            if self.cancel_flag:
                self.set_status("已取消")
                return
            code, out, err = result
            text = (out or err).strip() or f"{label}没有输出。"
            self.append_output(text)
            self.set_status(f"{label}完成（退出码 {code}）")

        self.run_async(lambda: self.run_cli(*args, timeout=180), done, label,
                       cancellable=True)

    def send(self):
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        if self._running:
            self.set_status("上一个任务还没结束，请先取消或等它结束")
            return
        self.input.delete("1.0", "end")
        self.cancel_flag = False
        # 计时起点就取在「按下发送」这一行（单调时钟）；渲染气泡、启动进程都算在
        # 用户等待里。同一个起点也传给 CLI，这样界面上的秒数、存进会话的
        # elapsed_ms、历史里回看的数字是同一个数。
        client_start = time.perf_counter()
        self.append_user(text, "running")
        self.begin_chat_timing(client_start)

        # 新对话第一次发送才生成会话名：CLI 只有拿到 --session 才会落盘并记住上下文，
        # 之前这里留空，等于每句都是无记忆的一次性提问，历史列表也永远不出现新条目。
        if not self.session_name:
            self.session_name = "desktop-win-" + uuid.uuid4().hex
        session = self.session_name
        repo = self.repo_var.get().strip()
        epoch = self._conversation_epoch

        def work():
            args = ["chat", "--message", text, "--network", "auto", "--json",
                    "--session", session]
            if repo:
                args += ["--repository", repo]
            return self.run_cli(*args, timeout=180,
                                extra_env={"REVIEWAGENT_CLIENT_START":
                                           f"{client_start:.6f}"})

        def done(result):
            # 不管走哪条分支都先停表：成功 / 失败 / 取消 / 代次已变，一个定时器都不留。
            ui_seconds = self.stop_chat_timing()
            if epoch != self._conversation_epoch:
                return                      # 期间已点「新对话」，这条回复不再写回界面
            if result[0] == "error":
                self._mark_last_user("failed", str(result[1]), ui_seconds)
                self.set_status("请求失败")
                return
            code, out, err = result
            parsed = parse_json(out)
            payload = parsed or {}
            # 界面显示以自己量的真实等待为准（和等待行最后那个数字连续）；
            # CLI 拿老版本、没写耗时字段时才退回它给的值。
            seconds = ui_seconds
            if seconds is None:
                seconds = elapsed_seconds(payload)
            if self.cancel_flag:
                self._mark_last_user("interrupted", "", seconds)
                self.set_status("已取消")
                return
            reply = payload.get("reply")
            if payload.get("ok") and reply:
                elapsed_ms = payload.get("elapsed_ms")
                if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, (int, float)):
                    elapsed_ms = int(round((seconds or 0) * 1000))
                self._settle_last_user()        # 成功路径：只改数据，不重建会话
                self.append_agent(str(reply), elapsed_ms=elapsed_ms,
                                  finished_at=payload.get("finished_at") or "")
                self.session_name = (payload.get("session") or payload.get("session_name")
                                     or session)
                # 这条会话刚被 CLI 追加了消息，缓存已经过期，下次打开要重新读
                self._forget_session(self.session_name)
                self.set_status("就绪")
                self.load_sessions()
            else:
                reason = payload.get("error") or ""
                if not reason and err.strip():
                    reason = err_line(err) or "未知错误"
                self._mark_last_user("failed", reason or "未知错误", seconds)
                # JSON 解析失败时把 stderr 末行显示在状态栏，便于定位（不含密钥）。
                self.set_status(err_line(err) if parsed is None and err_line(err)
                                else "请求失败")

        self.run_async(work, done, "提问", cancellable=True)

    def cancel(self):
        if self.proc is None:
            return
        self.cancel_flag = True
        self.set_status("正在取消…")
        try:
            self.proc.terminate()
        except Exception:                                # noqa: BLE001
            pass

    def new_conversation(self):
        if self._running:
            self._new_conversation_blocked()
            return
        self._conversation_epoch += 1       # 让在飞的历史读取结果作废
        self.session_name = None
        self.clear_transcript()
        self._set_session_header("新对话", f"仓库：{self.repo_var.get()}")
        self.input.delete("1.0", "end")
        self.input.focus_set()
        self.set_status("新对话")
        self.render_sessions(self._sessions_cache)

    def _new_conversation_blocked(self):
        self.set_status("任务运行中，先取消或等它结束再开新对话")

    # ------------------------------------------------------------ 会话
    def load_sessions(self):
        epoch = self._conversation_epoch
        # 列表是后台刷新：如果期间状态栏已被别的动作改写（取消 / 新对话 …），
        # 回来时就不要用「就绪」把它盖掉。比较的是状态文本，不依赖时序。
        pending = "读取会话列表 运行中…"

        def done(result):
            if result[0] == "error":
                if epoch == self._conversation_epoch and self.status_var.get() == pending:
                    self.set_status("会话列表读取失败")
                return
            code, out, err = result
            parsed = parse_json(out)
            payload = parsed or {}
            self._sessions_cache = payload.get("sessions") or []
            self.render_sessions(self._sessions_cache)
            if epoch == self._conversation_epoch and self.status_var.get() == pending:
                self.set_status(err_line(err) if parsed is None and err_line(err)
                                else "就绪")

        self.run_async(lambda: self.run_cli("sessions", "list", timeout=60,
                                            track=False),
                       done, "读取会话列表")

    def render_sessions(self, sessions):
        raw = self.search_var.get().strip()
        query = "" if raw == "搜索标题和消息" else raw.lower()
        self.session_area.clear()
        shown = [s for s in sessions
                 if not query or query in str(s.get("title") or s.get("name") or "").lower()
                 or query in str(s.get("summary") or "").lower()]
        if not shown:
            tk.Label(self.session_area.body, text="（没有会话）", bg=PANEL, fg=FAINT,
                     font=ui_font(9)).pack(anchor="w", padx=12, pady=8)
            return
        for item in shown:
            title = item.get("title") or item.get("name") or "(未命名)"
            when = self._short_time(item)
            turns = str(item.get("turns") or "0")
            summary = " ".join(str(item.get("summary") or "").split())
            detail = f"{when} · {turns} 轮 · {summary}" if summary else f"{when} · {turns} 轮"
            if len(detail) > 26:                          # 侧栏两行卡片，摘要单行截断
                detail = detail[:25] + "…"
            selected = (item.get("name") == self.session_name
                        or item.get("name") == self._pending_session)
            row = tk.Frame(self.session_area.body,
                           bg=PANEL_HI if selected else PANEL, cursor="hand2")
            row.pack(fill="x", pady=1)
            text_width = max(120, self._sidebar_width() - 22)
            tk.Label(row, text=title, bg=row["bg"], fg=INK, font=ui_font(9),
                     anchor="w", justify="left", wraplength=text_width).pack(
                fill="x", padx=10, pady=(6, 0))
            tk.Label(row, text=detail, bg=row["bg"], fg=FAINT, font=ui_font(8),
                     anchor="w", justify="left", wraplength=text_width).pack(
                fill="x", padx=10, pady=(1, 6))
            name = item.get("name")
            parts = (row, *row.winfo_children())
            if not selected:
                # 悬停提亮：鼠标扫过就知道哪一行能点，点起来不会「没反馈」
                for widget in parts:
                    widget.bind("<Enter>",
                                lambda _e, ws=parts: [w.configure(bg=BTN_HOVER) for w in ws])
                    widget.bind("<Leave>",
                                lambda _e, ws=parts: [w.configure(bg=PANEL) for w in ws])
            for widget in parts:
                widget.bind("<Button-1>", lambda _e, n=name: self.show_session(n))
                widget.bind("<Button-3>",
                            lambda e, n=name: self._session_menu(e, n))

    def _short_time(self, item):
        """会话时间显示成「刚刚 / 昨天 / 11-13」这类短标签。"""
        raw = (item.get("saved_at") or item.get("updated_at") or "").strip()
        if not raw:
            return ""
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            now = datetime.now().astimezone()
            days = (now.date() - dt.date()).days
            if days == 0:
                return "刚刚"
            if days == 1:
                return "昨天"
            return dt.strftime("%m-%d")
        except Exception:                                # noqa: BLE001
            return raw.replace("T", " ")[:16]

    def _session_menu(self, event, name):
        """右键菜单保留 sessions delete 入口，侧栏不常驻删除按钮。"""
        menu = tk.Menu(self, tearoff=0, bg=PANEL_HI, fg=INK,
                       activebackground=BTN_HOVER, activeforeground=MINT,
                       font=ui_font(9))
        menu.add_command(label="删除会话",
                         command=lambda: self.delete_session(name))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def delete_session(self, name):
        """删除会话：sessions delete <name>；删除当前会话则清空对话区。"""
        if not name:
            return
        self._forget_session(name)
        # 先把这行从列表里摘掉：CLI 往返要一秒左右，等它回来那行还杵在那儿，
        # 看着像「点了没删掉」。失败时 done() 会重新拉一次列表回滚。
        self._sessions_cache = [s for s in self._sessions_cache
                                if s.get("name") != name]
        self.render_sessions(self._sessions_cache)
        self.set_status(f"正在删除会话：{name}")

        def done(result):
            if result[0] == "error":
                self.set_status(f"删除失败：{result[1]}")
                self.load_sessions()
                return
            code, out, err = result
            if code != 0 and not (parse_json(out) or {}).get("ok"):
                self.set_status(f"删除失败：{err_line(err) or '未知错误'}")
                self.load_sessions()
                return
            if self.session_name == name:
                self._conversation_epoch += 1
                self.session_name = None
                self.clear_transcript()
                self._set_session_header("新对话", f"仓库：{self.repo_var.get()}")
            # 先刷列表再写状态：load_sessions 会先把状态改成「读取会话列表…」，
            # 顺序反了的话「已删除会话」会被它盖掉。
            self.load_sessions()
            self.set_status(f"已删除会话：{name}")

        self.run_async(lambda: self.run_cli("sessions", "delete", name, timeout=60,
                                            track=False), done, "删除会话")

    def show_session(self, name):
        if not name:
            return
        # 打开过的会话直接拿缓存渲染：CLI 一次往返接近一秒，切回来没必要再等。
        cached = self._session_cache.get(name)
        if cached is not None:
            session, parsed, err = cached
            self._apply_session(name, session, parsed, err, from_cache=True)
            return

        # 先高亮被点的那一行：读取要等 CLI，没反馈的话会像「点了没反应」。
        self._pending_session = name
        self.render_sessions(self._sessions_cache)
        self.set_status(f"正在打开会话：{name}")
        epoch = self._conversation_epoch

        def done(result):
            # 点开历史后用户又点了「新对话」：这次结果已经过期，不能再把旧会话
            # 的标题 / 消息写回来（否则界面会闪一下新对话又弹回旧的）。
            if epoch != self._conversation_epoch:
                self._pending_session = None
                return
            if result[0] == "error":
                self._pending_session = None
                self.render_sessions(self._sessions_cache)
                self.set_status("读取会话失败")
                return
            code, out, err = result
            parsed = parse_json(out)
            payload = parsed or {}
            session = payload.get("session") or {}
            self._apply_session(name, session, parsed, err)

        self.run_async(lambda: self.run_cli("sessions", "show", name, timeout=60,
                                            track=False),
                       done, "读取会话")

    def _apply_session(self, name, session, parsed=None, err="", from_cache=False):
        """把一条会话铺到聊天区。缓存命中与 CLI 返回走同一条路径，行为一致。"""
        self._pending_session = None
        self._remember_session(name, session, parsed, err)
        messages = session.get("messages") or []
        self.session_name = name
        self._set_session_header(
            session.get("title") or name,
            f"仓库：{session.get('repository') or self.repo_var.get()}")
        self.stop_chat_timing()             # 切会话：停掉上一轮的等待计时
        # 不在这里 clear()：rerender 会把新内容建好再一次性替换，
        # 先清空的话中途会看到一片空白或半截文字。
        self.messages = []
        for message in messages:
            role = message.get("role")
            content = message.get("content") or ""
            if role == "user":
                # 旧会话没有 started_at 时留空，时间标签不显示，也不报错。
                self.messages.append({"role": "user", "content": content,
                                      "status": message.get("status") or "",
                                      "detail": message.get("error") or "",
                                      "sent_at": (message.get("started_at")
                                                  or message.get("updated_at")),
                                      "elapsed_ms": message.get("elapsed_ms")})
            elif role == "assistant":
                self.messages.append({"role": "assistant", "content": content,
                                      "status": "completed",
                                      "elapsed_ms": message.get("elapsed_ms"),
                                      "finished_at": (message.get("finished_at")
                                                      or message.get("updated_at"))})
        self.rerender()
        # 恢复后画布宽度可能刚变过：补一帧按真实宽度重排气泡，避免留下窄气泡
        self._schedule_rewrap(60)
        # 列表按 session_name 决定高亮，不重绘的话点开的会话看不出被选中。
        self.render_sessions(self._sessions_cache)
        note = "（缓存）" if from_cache else ""
        self.set_status(err_line(err) if parsed is None and err_line(err)
                        else f"已打开会话：{name}{note}")

    def _remember_session(self, name, session, parsed, err):
        """只缓存最近打开的几条，避免会话一多把内存撑起来。"""
        self._session_cache.pop(name, None)
        self._session_cache[name] = (session, parsed, err)
        while len(self._session_cache) > 6:
            oldest = next(iter(self._session_cache))
            self._session_cache.pop(oldest, None)

    def _forget_session(self, name):
        self._session_cache.pop(name, None)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
