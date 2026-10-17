"""Persist / resume chat sessions under ~/.reviewagent/sessions/."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.agent_home import ensure_home, home_dir

LATEST_NAME = 'latest.json'


def sessions_dir() -> Path:
    ensure_home()
    path = home_dir() / 'sessions'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S-%f')


def serialize_agent(agent) -> Dict[str, Any]:
    pending = None
    if getattr(agent, 'pending_fix', None) is not None:
        fix = agent.pending_fix
        pending = {
            'summary': getattr(fix, 'summary', ''),
            'scenario': getattr(fix, 'scenario', ''),
            'files': [edit.as_dict() for edit in fix.files],
        }
    return {
        'version': 1,
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'chat_mode': getattr(agent, 'chat_mode', 'auto'),
        'session_lane': getattr(agent, 'session_lane', 'chat'),
        'network': getattr(agent, 'network', 'auto'),
        'last_turn': getattr(agent, 'last_turn', None),
        'last_user_text': getattr(agent, 'last_user_text', None),
        'last_reply': getattr(agent, 'last_reply', None),
        'history': list(getattr(agent, 'history', []) or [])[-16:],
        'contexts': list(getattr(agent, 'contexts', []) or []),
        'pending_fix': pending,
        'work_root': str(getattr(agent, 'work_root', '')),
    }


def apply_to_agent(agent, data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError('会话数据格式无效')
    root = data.get('work_root')
    if not isinstance(root, str) or not root or not Path(root).is_absolute():
        raise ValueError('会话工作目录缺失或无效，请重新分析后保存')
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('会话工作目录不是目录')
    for key, choices in (('chat_mode', ('auto', 'chat', 'work')),
                         ('session_lane', ('chat', 'work')),
                         ('network', ('auto', 'on', 'off'))):
        if data.get(key, choices[0]) not in choices:
            raise ValueError(f'会话 {key} 无效')
    for key in ('history', 'contexts'):
        rows = data.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'会话 {key} 格式无效')
    agent.work_root = root
    agent.chat_mode = data.get('chat_mode') or 'auto'
    agent.session_lane = data.get('session_lane') or 'chat'
    network = data.get('network') or 'auto'
    if network in ('auto', 'on', 'off'):
        agent.network = network
    agent.last_turn = data.get('last_turn')
    agent.last_user_text = data.get('last_user_text')
    agent.last_reply = data.get('last_reply')
    agent.history = list(data.get('history') or [])
    agent.contexts = list(data.get('contexts') or [])
    # Pending fixes contain structured FileEdit objects — do not revive from JSON.
    agent.pending_fix = None


def save_session(agent, name: Optional[str] = None) -> Path:
    payload = serialize_agent(agent)
    root = sessions_dir()
    if name:
        safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in name.strip())[:64]
        target = root / f'{safe or "session"}.json'
    else:
        target = root / f'session-{_stamp()}.json'
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    latest = root / LATEST_NAME
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return target


def load_session(path: Optional[str] = None) -> Dict[str, Any]:
    root = sessions_dir()
    if path:
        p = Path(path).expanduser()
        # Bare session names take precedence over same-named files in cwd.
        if Path(path).name == path:
            saved = root / (path if Path(path).suffix else f'{path}.json')
            if saved.is_file():
                p = saved
    else:
        p = root / LATEST_NAME
    if not p.is_file():
        raise FileNotFoundError(f'未找到会话文件: {path or LATEST_NAME}')
    data = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('会话文件内容无效')
    data['_path'] = str(p.resolve())
    return data


def list_sessions(limit: int = 10) -> List[Dict[str, str]]:
    root = sessions_dir()
    files = sorted(
        [p for p in root.glob('*.json') if p.name != LATEST_NAME],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    rows = []
    for p in files[: max(1, min(limit, 50))]:
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            turns = len(data.get('history') or []) // 2
            saved = data.get('saved_at') or ''
            ctx = len(data.get('contexts') or [])
        except Exception:
            turns, saved, ctx = 0, '', 0
        rows.append({
            'name': p.stem,
            'path': str(p),
            'saved_at': saved,
            'turns': str(turns),
            'contexts': str(ctx),
        })
    return rows


def clean_sessions(keep: int = 5, *, wipe_all: bool = False) -> Dict[str, Any]:
    """Delete old session JSON files. Keeps `latest.json` unless wipe_all.

    keep: number of newest named session-*.json / custom saves to retain.
    """
    root = sessions_dir()
    files = sorted(
        [p for p in root.glob('*.json') if p.name != LATEST_NAME],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted: List[str] = []
    kept: List[str] = []
    if wipe_all:
        for p in files:
            p.unlink()
            deleted.append(p.name)
        latest = root / LATEST_NAME
        if latest.exists():
            latest.unlink()
            deleted.append(LATEST_NAME)
        return {'deleted': deleted, 'kept': kept, 'keep': 0}

    keep_n = max(0, min(int(keep), 100))
    for i, p in enumerate(files):
        if i < keep_n:
            kept.append(p.name)
        else:
            p.unlink()
            deleted.append(p.name)
    return {'deleted': deleted, 'kept': kept, 'keep': keep_n}
