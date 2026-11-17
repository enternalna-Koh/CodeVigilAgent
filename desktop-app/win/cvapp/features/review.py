"""审查功能：当前改动 / 离线模式。"""
from __future__ import annotations

import os

from .. import ROOT
from .base import Feature


def _run(app, offline: bool) -> None:
    args = [app.runner.python(), os.path.join(ROOT, 'ascend_cli.py'), 'review']
    if offline:
        args.append('--offline')
    app.run_cli(
        args, cwd=app.current_repo(),
        label='离线审查（不联网）' if offline else '审查当前改动',
    )


FEATURES = [
    Feature(
        id='review.diff', group='审查', label='审查当前改动',
        handler=lambda app: _run(app, offline=False),
        order=10, kind='accent', requires_repo=True, shortcut='<F5>', placement='toolbar',
        hint='对所选仓库的 git diff 跑一遍 AI 审查',
    ),
    Feature(
        id='review.offline', group='审查', label='离线审查',
        handler=lambda app: _run(app, offline=True),
        order=20, requires_repo=True, shortcut='<Shift-F5>', placement='toolbar',
        hint='不调用远端模型，只用本地规则与知识库检查',
    ),
]
