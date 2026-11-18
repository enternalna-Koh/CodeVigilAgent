"""会话历史的数据层：只调 CLI 取 JSON，不 import tkinter。

为什么单列一层：
    CLI 的 `sessions list/show/delete` 输出 JSON 这个契约只在这里实现一次，
    右侧面板（history_panel）只消费整理好的数据。
    这样格式化逻辑可以脱离界面单测，也方便以后换界面（比如 macOS 版）。

约定（与 ascend_cli.py 的 sessions_cmd 一致）：
    list   → {"ok": true, "sessions": [{name,title,saved_at,turns,summary,repository,status}]}
    show   → {"ok": true, "session": {name,title,repository,saved_at,messages:[{role,content,status}]}}
    delete → {"ok": true, "deleted": name}
    turns 是字符串；saved_at 是 ISO 时间字符串，可能为空。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
import threading
from datetime import datetime, timezone

from . import ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from scripts.process_tree import ProcessOwner

_query_context = threading.local()


@contextmanager
def query_scope(owner):
    previous = getattr(_query_context, 'owner', None)
    _query_context.owner = owner
    try:
        yield
    finally:
        _query_context.owner = previous


CLI_PATH = os.path.join(ROOT, 'ascend_cli.py')
TIMEOUT = 60          # 秒；读本地文件正常远小于这个值

TITLE_LIMIT = 24      # 右侧面板一行标题的显示上限（超过加 …）
PREVIEW_LIMIT = 40    # 预览最多两行，按面板宽度反推的字数上限
RULE_WIDTH = 44       # 分隔线宽度


class SessionError(RuntimeError):
    """CLI 没交出可用结果。消息可以直接显示给用户，不需要再包一层。"""


# ------------------------------------------------------------------ 调用
def _run(args: list[str]) -> dict:
    """跑一次 sessions 子命令并返回解析后的 JSON。"""
    cmd = [sys.executable, CLI_PATH] + args
    try:
        owner = getattr(_query_context, 'owner', None)
        run = owner.run if owner is not None else subprocess.run
        proc = run(cmd, cwd=ROOT, capture_output=True, text=True,
                   encoding='utf-8', errors='replace', timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise SessionError(f'读取会话历史超时（{TIMEOUT} 秒没有响应）')
    except OSError as exc:
        raise SessionError(f'无法启动 CLI：{exc}')

    raw = (proc.stdout or '').strip()
    if not raw:
        detail = (proc.stderr or '').strip().splitlines()
        message = detail[-1] if detail else f'CLI 没有输出（退出码 {proc.returncode}）'
        raise SessionError(message)

    try:
        payload = json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError as exc:
        # CLI 崩溃时 stderr 里才有真正原因（缺依赖、配置坏），带上最后一行
        detail = (proc.stderr or '').strip().splitlines()
        hint = f'（{detail[-1]}）' if detail else ''
        raise SessionError(f'CLI 输出不是 JSON{hint}：{exc}')
    if not isinstance(payload, dict):
        raise SessionError('CLI 返回结构异常')
    if not payload.get('ok'):
        raise SessionError(str(payload.get('error') or '未知错误'))
    return payload


def list_sessions(query: str = '') -> list[dict]:
    """返回会话行，按保存时间倒序；空壳与损坏文件会被跳过。"""
    args = ['sessions', 'list']
    if query:
        args += ['--query', query]
    rows = _run(args).get('sessions') or []
    return sort_rows([row for row in rows if isinstance(row, dict) and keep_row(row)])


def show_session(name: str) -> dict:
    """取一条会话的完整消息列表。"""
    session = _run(['sessions', 'show', name]).get('session')
    if not isinstance(session, dict):
        raise SessionError(f'会话「{name}」返回结构异常')
    messages = [row for row in (session.get('messages') or []) if isinstance(row, dict)]
    session['messages'] = messages
    session.setdefault('name', name)
    return session


def delete_session(name: str) -> None:
    """从磁盘删掉一条会话（CLI 内部已做路径校验）。"""
    _run(['sessions', 'delete', name])


def sessions_dir() -> str:
    """会话目录，仅用于状态栏提示。与 scripts.agent_home 同一套优先级。"""
    home = os.environ.get('REVIEWAGENT_HOME', '').strip()
    root = os.path.expanduser(home) if home else os.path.join(
        os.path.expanduser('~'), '.reviewagent')
    return os.path.join(root, 'sessions')


# ------------------------------------------------------------------ 纯函数
def clip(text, limit: int) -> str:
    """压成单行并按字数截断（加 …）。中文按字符数算，够用且可预测。"""
    flat = ' '.join(str(text or '').split())
    return flat if len(flat) <= limit else flat[:limit] + '…'


def turns_of(row: dict) -> int:
    try:
        return max(int(str(row.get('turns') or 0)), 0)
    except (TypeError, ValueError):
        return 0


def keep_row(row: dict) -> bool:
    """空会话（退出时自动存的 0 轮空壳）和读不出来的文件都跳过。

    损坏文件在 CLI 侧被降级成 turns=0 / summary='' / saved_at=''，
    与「刚打开就退出的空会话」同形，一起挡掉，用户点开就不会必然报错。
    """
    return turns_of(row) > 0 or bool(str(row.get('summary') or '').strip())


def friendly_time(stamp) -> str:
    """ISO 时间 → `2026-11-13 15:13`；解析不了就原样返回。"""
    text = str(stamp or '').strip()
    if not text:
        return '时间未知'
    return text.replace('T', ' ')[:16]


def _stamp(row: dict) -> datetime:
    text = str(row.get('saved_at') or '').strip().replace('Z', '+00:00')
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    # 有的会话没存时区，混着比会 TypeError；统一按 UTC 处理
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def sort_rows(rows: list[dict]) -> list[dict]:
    """按 saved_at 倒序。

    CLI 是按文件 mtime 排的，与 saved_at 偶有出入（复制 / 同步过文件就会乱），
    这里再排一次；时间解析不出来的排最后，保持相对顺序。
    """
    return sorted(rows, key=_stamp, reverse=True)


def format_title(row: dict) -> str:
    return clip(row.get('title') or row.get('name') or '（未命名会话）', TITLE_LIMIT)


def format_meta(row: dict) -> str:
    """副标题：时间 · 轮次（失败会话补一句）。"""
    turns = turns_of(row)
    parts = [friendly_time(row.get('saved_at'))]
    if turns:
        parts.append(f'{turns} 轮')
    if str(row.get('status') or '') == 'failed':
        parts.append('回复失败')
    return ' · '.join(parts)


def format_preview(row: dict) -> str:
    """预览：CLI 的 summary 就是最后一条非空消息（成功=最后回复，失败=最后提问）。"""
    return clip(row.get('summary') or '（空对话）', PREVIEW_LIMIT)


def describe(row: dict) -> str:
    """悬停提示：完整标题 / 仓库 / 状态。"""
    repository = str(row.get('repository') or '').strip() or '未关联仓库'
    return '\n'.join(filter(None, [
        str(row.get('title') or row.get('name') or ''),
        f'仓库：{repository}',
        f'状态：{row.get("status") or "completed"}',
    ]))


def render_chunks(session: dict, restored_at: str = '') -> list[tuple[str, str]]:
    """把会话展开成 (文本, 样式) 片段，供 OutputPane.append 逐段写入。

    样式名与 widgets.OutputPane 里注册的 tag 对应：accent/dim/user/agent/err。
    """
    title = str(session.get('title') or session.get('name') or '会话')
    repository = str(session.get('repository') or '').strip() or '未关联'
    chunks: list[tuple[str, str]] = [
        (f'── 历史会话：{title} ' + '─' * RULE_WIDTH + '\n', 'accent'),
        (f'仓库 {repository}  ·  保存 {friendly_time(session.get("saved_at"))}\n', 'dim'),
    ]
    if restored_at:
        chunks.append((f'恢复于 {restored_at} · 之后的新提问会追加到这条会话\n', 'dim'))
    chunks.append(('\n', ''))

    messages = [m for m in (session.get('messages') or []) if isinstance(m, dict)]
    if not messages:
        chunks.append(('（这条会话没有保存任何消息）\n', 'dim'))
        return chunks

    for message in messages:
        role = str(message.get('role') or '')
        content = str(message.get('content') or '').strip()
        state = str(message.get('status') or 'completed')
        if role == 'user':
            chunks.append(('● 你\n', 'user'))
        elif role == 'assistant':
            chunks.append(('● Agent\n', 'agent'))
        else:
            continue
        if content:
            chunks.append((content + '\n', ''))
        if state == 'running':
            chunks.append(('（进行中…）\n\n', 'dim'))
        elif state == 'failed':
            chunks.append(('（回复失败）\n\n', 'err'))
        else:
            chunks.append(('\n', ''))
    return chunks
