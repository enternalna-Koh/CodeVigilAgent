"""Persist / resume chat sessions under ~/.reviewagent/sessions/."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.agent_home import ensure_home, home_dir

LATEST_NAME = 'latest.json'
PREVIOUS_NAME = 'previous.json'


def sessions_dir() -> Path:
    ensure_home()
    path = home_dir() / 'sessions'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp() -> str:
    import uuid
    return datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid.uuid4().hex[:8]


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
        'skill_names': [sk['name'] for sk in getattr(agent, 'active_skills', [])],
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
    agent.active_skills = []
    agent.last_tools = []
    agent.session_name = data.get('session_name')


def _session_filename(name: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in name.strip())[:64]
    return f'{safe or "session"}.json'


def save_session(agent, name: Optional[str] = None) -> Path:
    payload = serialize_agent(agent)
    if name:
        if name.strip().isdigit() or name.strip().lower() in (
                'latest', 'previous', 'prev', 'back', '上一个', '上一会话'):
            raise ValueError('会话名为保留名称或编号，请使用其他名字')
        payload['session_name'] = name.strip()
    elif getattr(agent, 'session_name', None):
        payload['session_name'] = agent.session_name
    root = sessions_dir()
    if name:
        target = root / _session_filename(name)
    else:
        target = root / f'session-{_stamp()}.json'
    text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    target.write_text(text, encoding='utf-8')
    (root / LATEST_NAME).write_text(text, encoding='utf-8')
    return target


def mark_previous_from_path(path: Path) -> Path:
    """Copy a saved session to previous.json for /back."""
    root = sessions_dir()
    prev = root / PREVIOUS_NAME
    data = Path(path).read_text(encoding='utf-8')
    prev.write_text(data, encoding='utf-8')
    return prev


def start_new_conversation(agent, name: Optional[str] = None) -> Path:
    """Save current dialogue (for /back), then clear agent for a fresh chat."""
    saved = save_session(agent, name)
    mark_previous_from_path(saved)
    agent.clear()
    agent.session_name = None
    return saved


def load_session(path: Optional[str] = None) -> Dict[str, Any]:
    root = sessions_dir()
    if path is None or str(path).strip() == '':
        p = root / LATEST_NAME
    elif str(path).strip().lower() in ('previous', 'prev', 'back', '上一个', '上一会话'):
        p = root / PREVIOUS_NAME
    elif str(path).strip().isdigit():
        # 1-based index into list_sessions()
        idx = int(str(path).strip())
        rows = list_sessions(50)
        if idx < 1 or idx > len(rows):
            raise FileNotFoundError(f'没有编号为 {idx} 的会话，请先 /sessions 查看')
        p = Path(rows[idx - 1]['path'])
    else:
        p = Path(path).expanduser()
        # Bare session names take precedence over same-named files in cwd.
        if Path(path).name == path:
            saved = root / (path if Path(path).suffix == '.json' else _session_filename(path))
            if saved.is_file():
                p = saved
    if not p.is_file():
        raise FileNotFoundError(f'未找到会话文件: {path or LATEST_NAME}')
    data = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('会话文件内容无效')
    data['_path'] = str(p.resolve())
    return data


def list_sessions(limit: int = 10) -> List[Dict[str, str]]:
    root = sessions_dir()
    skip = {LATEST_NAME, PREVIOUS_NAME}
    files = sorted(
        [p for p in root.glob('*.json') if p.name not in skip],
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
            title = data.get('session_name') or p.stem
        except Exception:
            turns, saved, ctx, title = 0, '', 0, p.stem
        rows.append({
            'name': p.stem,
            'title': title,
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
    specials = {LATEST_NAME, PREVIOUS_NAME}
    files = sorted(
        [p for p in root.glob('*.json') if p.name not in specials],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted: List[str] = []
    kept: List[str] = []
    if wipe_all:
        for p in files:
            p.unlink()
            deleted.append(p.name)
        for name in specials:
            sp = root / name
            if sp.exists():
                sp.unlink()
                deleted.append(name)
        return {'deleted': deleted, 'kept': kept, 'keep': 0}

    keep_n = max(0, min(int(keep), 100))
    for i, p in enumerate(files):
        if i < keep_n:
            kept.append(p.name)
        else:
            p.unlink()
            deleted.append(p.name)
    return {'deleted': deleted, 'kept': kept, 'keep': keep_n}
