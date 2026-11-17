"""窗口与会话生命周期；不涉及控件布局。"""
from __future__ import annotations

import tkinter as tk


class ShellLifecycle:
    def reset_session(self, clear_output: bool = False) -> bool:
        if self.runner.busy:
            self.append('\n任务运行中，请先取消或等任务结束后再开始新对话。\n', 'err')
            return False
        self._session_generation += 1
        self.current_session = ''
        self.session_title = ''
        self.chat_session = None
        self.chat_repository = None
        panel = self.panels.get('history.panel')
        if panel is not None:
            panel.reset_selection()
        if clear_output:
            self.output.clear()
            self.chat_section.clear()
            self.append('── 新会话 ──\n', 'accent')
        self.set_status('就绪')
        return True

    def close(self) -> None:
        if getattr(self, '_closing', False):
            return
        self._closing = True
        self._session_generation += 1
        for panel in self.panels.values():
            close = getattr(panel, 'close', None)
            if callable(close):
                close()
        try:
            self.runner.close()
        finally:
            # 卡片悬停与滚动的短期 after 也必须在销毁 Tcl 命令前撤销。
            for job in self.root.tk.call('after', 'info'):
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            self.root.destroy()
