"""主窗口骨架：标题栏 + 左侧功能栏 + 右侧工作区。

这一层只做三件事：
    1. 把注册表里的功能摆成侧边栏按钮
    2. 提供工作区（仓库 / 输出 / 输入）
    3. 把按钮点击转成功能调用

它不认识任何具体业务，所以加功能不需要改这里。
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from . import VERSION, config, theme
from .action_bar import build_input_actions, build_toolbar
from .chat_section import ChatSection
from .panels import PanelHost
from .lifecycle import ShellLifecycle
from .runner import Runner
from .features.base import group_order
from .widgets import FlatButton, OutputPane, PillButton, caption_label, divider, section_label

class Shell(ShellLifecycle):
    def __init__(self, root: tk.Tk, features: list, load_errors: list[str] | None = None):
        self.root = root
        self.features = features
        self.load_errors = load_errors or []
        self.buttons: dict[str, FlatButton] = {}
        self.chat_session: str | None = None
        self.chat_repository: str | None = None
        self.repo_var = tk.StringVar(value=config.load_last_repo())
        self.status_var = tk.StringVar(value='就绪')
        self.font_ui = theme.ui_font(11)
        self.font_mono = theme.pick_mono_font(root, 12)
        # 当前打开的历史会话（空 = 新会话）。由功能层写，chat 发送时读。
        self.current_session = ''
        self.session_title = ''
        self._session_generation = 0
        self.runner = Runner(root, self.append, self._on_start, self._on_done)
        root.protocol('WM_DELETE_WINDOW', self.close)

        root.title('CodeVigil Agent')
        root.geometry('1200x860')
        root.minsize(940, 620)
        root.configure(bg=theme.BG)
        # 不用 zoomed：最大化后窗口比工作区高，底部输入行会被顶到任务栏下面。
        root.geometry('%dx%d+40+20' % (max(940, root.winfo_screenwidth() - 80),
                                       max(560, root.winfo_screenheight() - 160)))

        self._build()
        self._bind_shortcuts()
        self._welcome()

    # ------------------------------------------------------------ 布局
    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=theme.BG)
        outer.pack(fill='both', expand=True, padx=theme.PAD_OUTER, pady=14)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        self._build_header(outer)

        body = tk.Frame(outer, bg=theme.BG)
        body.grid(row=1, column=0, sticky='nsew', pady=(14, 0))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, minsize=theme.SIDEBAR_WIDTH)
        body.grid_columnconfigure(1, weight=1)

        self._build_sidebar(body)
        self._build_workspace(body)

    def _build_header(self, parent) -> None:
        head = tk.Frame(parent, bg=theme.BG)
        head.grid(row=0, column=0, sticky='ew')
        tk.Label(head, text='CodeVigil Agent', bg=theme.BG, fg=theme.ACCENT,
                 font=theme.ui_font(20, 'bold')).pack(side='left')
        tk.Label(head, text='昇腾 AI Infra 代码审查与问题诊断', bg=theme.BG,
                 fg=theme.FG_DIM, font=theme.ui_font(10)).pack(
            side='left', padx=(14, 0), pady=(8, 0))
        tk.Label(head, textvariable=self.status_var, bg=theme.BG, fg=theme.FG_DIM,
                 font=theme.ui_font(9)).pack(side='right', pady=(10, 0))

    def _build_sidebar(self, parent) -> None:
        side = tk.Frame(parent, bg=theme.SIDEBAR, width=theme.SIDEBAR_WIDTH)
        side.grid(row=0, column=0, sticky='ns', padx=(0, 14))
        side.grid_propagate(False)                       # 固定宽度，不被按钮文字撑开

        tk.Label(side, text='功能', bg=theme.SIDEBAR, fg=theme.FG,
                 font=theme.ui_font(12, 'bold'), anchor='w').pack(
            fill='x', padx=12, pady=(12, 0))
        divider(side).pack(fill='x', padx=12, pady=(8, 0))

        for group in group_order([f for f in self.features if f.placement == 'sidebar']):
            members = [f for f in self.features if f.placement == 'sidebar' and f.group == group]
            if not members:
                continue
            section_label(side, group).pack(fill='x', padx=6, pady=(12, 2))
            for feature in members:
                button = FlatButton(
                    side, feature.label, lambda f=feature: self._invoke(f),
                    accent=feature.kind == 'accent', danger=feature.kind == 'danger',
                    font=self.font_ui, left=True,
                )
                button.pack(fill='x', padx=8, pady=2)
                if feature.only_while_running:
                    button.config(state='disabled')
                self.buttons[feature.id] = button

        tk.Label(side, text=f'v{VERSION}', bg=theme.SIDEBAR, fg=theme.FG_FAINT,
                 font=theme.ui_font(8), anchor='w').pack(
            side='bottom', fill='x', padx=14, pady=10)

    def _build_workspace(self, parent) -> None:
        main = tk.Frame(parent, bg=theme.BG)
        main.grid(row=0, column=1, sticky='nsew')
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=4, minsize=240)   # 聊天区吃大头
        main.grid_rowconfigure(4, weight=1, minsize=100)   # 输出区留一小块

        # 右侧面板列：默认不占位，功能按钮展开时才出现
        self.panel_host = PanelHost(main, self)
        self.panel_host.frame.grid(row=0, column=2, rowspan=6, sticky='ns',
                                   padx=(theme.GAP, 0))
        self.panel_host.frame.grid_remove()

        # ---- 仓库行 ----
        repo_row = tk.Frame(main, bg=theme.BG)
        repo_row.grid(row=0, column=0, sticky='ew')
        tk.Label(repo_row, text='仓库', bg=theme.BG, fg=theme.FG_DIM,
                 font=self.font_ui).pack(side='left')
        entry = tk.Entry(
            repo_row, textvariable=self.repo_var, bg=theme.PANEL, fg=theme.FG,
            insertbackground=theme.FG, relief='flat', font=self.font_ui,
            highlightthickness=1, highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT_DIM,
        )
        entry.pack(side='left', fill='x', expand=True, padx=10, ipady=6)
        FlatButton(repo_row, '选择目录', self.pick_repo, accent=True,
                   font=self.font_ui).pack(side='left')

        build_toolbar(main, self)

        # ---- 聊天区（气泡）----
        self.chat_section = ChatSection(main, self)
        self.chat = self.chat_section.pane

        # ---- 输出区 ----
        caption_label(main, '审查结果 / 运行输出').grid(row=3, column=0, sticky='ew', pady=(theme.GAP, 2))
        self.output = OutputPane(main, self.font_mono)
        self.output.grid(row=4, column=0, sticky='nsew')

        # ---- 输入行 ----
        chat = tk.Frame(main, bg=theme.BG)
        chat.grid(row=5, column=0, sticky='ew', pady=(theme.GAP, 0))
        self.entry = tk.Entry(
            chat, bg=theme.PANEL, fg=theme.FG, insertbackground=theme.FG,
            relief='flat', font=self.font_ui, highlightthickness=1,
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT_DIM,
        )
        self.entry.pack(side='left', fill='x', expand=True, ipady=7)
        self.entry.bind('<Return>', lambda _e: self.submit())
        PillButton(chat, '发送', self.submit, accent=True,
                   font=self.font_ui).pack(side='left', padx=(8, 0))
        build_input_actions(chat, self)
        self.entry.focus_set()

    # ------------------------------------------------------------ 功能调度
    def _invoke(self, feature) -> None:
        if feature.panel_factory is not None:
            self.panel_host.toggle(feature)
            return
        if feature.requires_repo and not self.require_repo():
            return
        try:
            feature.handler(self)
        except Exception as exc:                       # noqa: BLE001
            self.append(f'\n[{feature.label}] 出错：{exc}\n', 'err')

    @property
    def panels(self) -> dict:
        """已创建的右侧面板（id → 控件），供功能模块按需取用。"""
        return self.panel_host.panels

    def submit(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        if self.runner.busy:
            self.append('\n上一个任务还没结束，请等待或取消后再发送。\n', 'err')
            return
        self.entry.delete(0, 'end')
        feature = next((f for f in self.features if f.placement == 'input'), None)
        if feature is None:
            self.append('\n没有登记输入处理功能（features/*.py 的 placement="input"）\n', 'err')
            return
        try:
            feature.handler(self, text)
        except Exception as exc:                       # noqa: BLE001
            self.append(f'\n[输入] 出错：{exc}\n', 'err')

    def _bind_shortcuts(self) -> None:
        for feature in self.features:
            if not feature.shortcut:
                continue
            try:
                self.root.bind(feature.shortcut, lambda _e, f=feature: self._invoke(f))
            except tk.TclError:
                pass

    # ------------------------------------------------------------ 工作区 API
    def append(self, text: str, tag: str | None = None) -> None:
        self.output.append(text, tag)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def current_repo(self) -> str:
        return self.repo_var.get().strip()

    def require_repo(self) -> bool:
        repo = self.current_repo()
        if not repo or not os.path.isdir(repo):
            messagebox.showwarning('仓库无效', '请先在顶部选择一个存在的目录。',
                                   parent=self.root)
            return False
        return True

    def pick_repo(self) -> None:
        path = filedialog.askdirectory(title='选择要审查的 Git 仓库目录')
        if path:
            path = os.path.normpath(path)
            self.repo_var.set(path)
            config.save_last_repo(path)

    def run_cli(self, args: list, cwd: str, label: str, sink=None) -> None:
        columns = self.output.columns()
        if not self.runner.start(args, cwd, label, columns=columns, sink=sink):
            messagebox.showinfo('正在运行', '上一个任务还没结束，先点「取消任务」或等它跑完。',
                                parent=self.root)

    # ------------------------------------------------------------ 运行状态
    def _on_start(self, label: str) -> None:
        self._session_generation += 1
        self.append(f'\n── {label} ' + '─' * 40 + '\n', 'accent')
        self.set_status(f'{label} 运行中…')
        self._toggle_running_buttons(True)

    def _on_done(self, code: int) -> None:
        self.chat_section.finish(code)
        if code == 0:
            self.append('\n── 完成 ──\n', 'accent')
            self.set_status('就绪')
        else:
            self.append(f'\n── 结束（退出码 {code}）──\n', 'err')
            self.set_status(f'结束，退出码 {code}')
        self._toggle_running_buttons(False)
        # 面板里的会话列表跟着任务结果更新（轮次 / 预览变了）。
        # 只刷列表，不动正在显示的对话内容。
        self.panel_host.refresh_visible()

    def _toggle_running_buttons(self, running: bool) -> None:
        for feature in self.features:
            if not feature.only_while_running:
                continue
            button = self.buttons.get(feature.id)
            if button is not None:
                button.config(state='normal' if running else 'disabled')

    # ------------------------------------------------------------ 首屏
    def _welcome(self) -> None:
        model = config.load_config().get('model') or '未配置'
        self.append('欢迎使用 CodeVigil Agent。\n', 'accent')
        self.append(f'当前模型：{model}\n', 'dim')
        self.append('选择 Git 仓库后点「审查当前改动」；或在底部输入问题直接对话。\n', 'dim')
        if self.load_errors:
            self.append('\n以下功能模块加载失败（其余功能不受影响）：\n', 'err')
            for error in self.load_errors:
                self.append(f'  · {error}\n', 'err')
            self.set_status(f'{len(self.load_errors)} 个功能模块加载失败')

def main() -> None:
    from .features import load

    root = tk.Tk()
    features, errors = load()
    Shell(root, features, errors)
    root.mainloop()
