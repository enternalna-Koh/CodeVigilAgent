"""历史会话：右侧回顾面板 + 新会话。

数据全走 `python ascend_cli.py sessions ...`（JSON），面板自己不认识 CLI 参数；
这里只负责把面板挂到右侧、以及「新会话」这个动作。
"""
from __future__ import annotations

from ..history_panel import HistoryPanel
from .base import Feature


def toggle_history(app) -> None:
    """兜底：面板类功能由 shell.toggle_panel 处理，正常走不到这里。"""
    feature = next((f for f in app.features if f.id == 'history.panel'), None)
    if feature is not None:
        app.toggle_panel(feature)


def new_session(app) -> None:
    if not app.reset_session(clear_output=True):
        return
    panel = app.panels.get('history.panel')
    if panel is None:
        return
    refresh = getattr(panel, 'refresh', None)
    if callable(refresh):
        refresh()


FEATURES = [
    Feature(
        id='history.panel', group='会话', label='历史会话',
        handler=toggle_history, panel_factory=HistoryPanel,
        order=10, shortcut='<Control-h>',
        hint='在右侧回顾以前的对话；点开可继续提问',
    ),
    Feature(
        id='history.new', group='会话', label='新会话',
        handler=new_session, order=20, shortcut='<Control-n>',
        hint='结束当前历史会话，之后提问写进一条新会话',
    ),
]
