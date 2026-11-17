"""聊天区装配：气泡面板 + 一轮问答的缓冲区管理。

Shell 只留三行：建区、开始一轮、结束一轮；细节全在这里，
免得 shell.py 越加越胖（结构守卫会拦）。
"""
from __future__ import annotations

from . import theme
from .chat_pane import ChatPane


class ChatSection:
    def __init__(self, parent, shell):
        self.shell = shell
        self.pane = ChatPane(parent, shell.font_ui)
        self.pane.grid(row=2, column=0, sticky='nsew', pady=(theme.GAP, 0))
        self._buffer: list | None = None
        self._cancelled = False
        self.pane.set_header('新对话', shell.current_repo())

    # ------------------------------------------------------------ 一轮问答
    def begin(self, text: str) -> list:
        """用户消息进气泡，返回给 runner 收回复的缓冲区。"""
        self.pane.set_header(self.shell.session_title or '新对话', self.shell.current_repo())
        self.pane.add_user(text)
        self._buffer = []
        self._cancelled = False
        return self._buffer

    def cancel(self) -> None:
        self._cancelled = True
        self.shell.runner.cancel()

    def finish(self, code: int) -> None:
        """任务结束：成功落 Agent 气泡，失败/取消把状态挂到用户气泡下面。"""
        buffer = self._buffer
        if buffer is None:
            return
        self._buffer = None
        reply = ''.join(buffer).strip()
        if code == 0 and reply:
            self.pane.add_agent(reply)
            self.pane.finish_user('')
        elif self._cancelled:
            self.pane.finish_user('interrupted')
        else:
            detail = reply.splitlines()[-1] if reply else ''
            self.pane.finish_user('failed', detail)

    def clear(self) -> None:
        self.pane.clear()
        self.pane.set_header('新对话', self.shell.current_repo())
