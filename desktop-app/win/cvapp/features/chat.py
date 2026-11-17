"""提问功能：底部输入框提交。

两种情况：
    普通提问 → 新起一次 `chat --message`（CLI 自己存会话）
    历史会话已打开 → 追加 `--session <name>`，新消息写回那条会话
"""
from __future__ import annotations

import os
import uuid

from .. import ROOT
from .base import Feature


def send(app, text: str) -> None:
    text = (text or '').strip()
    if not text:
        return
    if app.runner.busy:
        app.append('\n上一个任务还没结束，请等待或取消后再发送。\n', 'err')
        return
    repo = app.current_repo()
    repo = os.path.realpath(repo) if repo and os.path.isdir(repo) else ''
    if getattr(app, 'chat_repository', None) != repo or not getattr(app, 'chat_session', None):
        app.chat_repository = repo
        app.chat_session = 'desktop-win-' + uuid.uuid4().hex
    args = [
        app.runner.python(), os.path.join(ROOT, 'ascend_cli.py'),
        'chat', '--message', text, '--network', 'auto',
        '--session', app.chat_session, '--repository', repo,
    ]
    # CLI 一次性模式只打印回答、不回显提问；气泡区自己放用户消息，
    # 回复先收进 buffer，等任务结束再落成 Agent 气泡。
    buffer = app.chat_section.begin(text)
    label = '续写历史会话' if getattr(app, 'current_session', '') else '提问'
    app.run_cli(args, cwd=repo or ROOT, label=label, sink=buffer.append)


FEATURES = [
    Feature(
        id='chat.send', group='会话', label='发送', handler=send,
        placement='input', order=10,
        hint='把输入框里的问题发给 Agent（可带仓库上下文）',
    ),
]
