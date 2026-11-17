"""Persist / resume chat sessions under ~/.reviewagent/sessions/."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.agent_home import ensure_home, home_dir

LATEST_NAME = 'latest.json'
PREVIOUS_NAME = 'previous.json'
_KEY_PATTERNS = (
    re.compile(r'(?i)\bsk-(?:ant-)?[A-Za-z0-9_-]{12,}\b'),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~-]{12,}'),
)


def sessions_dir() -> Path:
    ensure_home()
    path = home_dir() / 'sessions'
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _stamp() -> str:
    import uuid
    return datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid.uuid4().hex[:8]


def _api_keys(agent=None) -> List[str]:
    values = [os.environ.get(name, '') for name in (
        'AI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')]
    if agent is not None:
        client = getattr(agent, 'client', None)
        provider = getattr(client, 'provider', None)
        values.extend((getattr(client, 'api_key', ''), getattr(provider, 'api_key', '')))
    try:
        from scripts.ai_adapter import load_config_from_env
        from scripts.agent_home import CONFIG_NAME, DEFAULT_HOME_NAME
        config_path = Path(os.environ.get('REVIEWAGENT_CONFIG', '')).expanduser() if os.environ.get(
            'REVIEWAGENT_CONFIG') else Path(os.environ.get('REVIEWAGENT_HOME') or Path.home() /
                                             DEFAULT_HOME_NAME) / CONFIG_NAME
        if config_path.is_file():
            config = json.loads(config_path.read_text(encoding='utf-8'))
            values.append(config.get('api_key', '') if isinstance(config, dict) else '')
        values.append(load_config_from_env().get('api_key', ''))
    except Exception:
        pass
    return sorted({value for value in values if isinstance(value, str) and len(value) >= 6},
                  key=len, reverse=True)


def redact_secrets(value: Any, agent=None) -> Any:
    secrets = _api_keys(agent)

    def clean(item):
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, '[API Key 已隐藏]')
            for pattern in _KEY_PATTERNS:
                item = pattern.sub('[API Key 已隐藏]', item)
            return item
        if isinstance(item, list):
            return [clean(entry) for entry in item]
        if isinstance(item, dict):
            return {key: clean(entry) for key, entry in item.items()}
        return item

    return clean(value)


def serialize_agent(agent, *, include_all_history: bool = False) -> Dict[str, Any]:
    pending = None
    if getattr(agent, 'pending_fix', None) is not None:
        fix = agent.pending_fix
        pending = {
            'summary': getattr(fix, 'summary', ''),
            'scenario': getattr(fix, 'scenario', ''),
            'files': [edit.as_dict() for edit in fix.files],
        }
    history = list(getattr(agent, 'history', []) or [])
    messages = list(getattr(agent, 'desktop_messages', []) or [])
    if not messages:
        for row in history:
            if isinstance(row, dict) and row.get('role') in ('user', 'assistant'):
                messages.append({
                    'role': row['role'], 'content': row.get('content', ''),
                    'status': 'completed',
                })
    payload = {
        'version': 1,
        'saved_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'chat_mode': getattr(agent, 'chat_mode', 'auto'),
        'session_lane': getattr(agent, 'session_lane', 'chat'),
        'network': getattr(agent, 'network', 'auto'),
        'last_turn': getattr(agent, 'last_turn', None),
        'last_user_text': getattr(agent, 'last_user_text', None),
        'last_user_source': getattr(getattr(agent, 'last_user_text', None), 'source_text', None),
        'last_reply': getattr(agent, 'last_reply', None),
        'history': history if include_all_history else history[-16:],
        'contexts': list(getattr(agent, 'contexts', []) or []),
        'pending_fix': pending,
        'skill_names': [sk['name'] for sk in getattr(agent, 'active_skills', [])],
        'work_root': str(getattr(agent, 'work_root', '')),
        'desktop_messages': messages,
        'desktop_title': getattr(agent, 'desktop_title', None),
        'desktop_repository': getattr(agent, 'desktop_repository', None),
    }
    return redact_secrets(payload, agent)


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
    if isinstance(agent.last_user_text, str) and isinstance(data.get('last_user_source'), str):
        from scripts.conversation_agent import UserMessage
        agent.last_user_text = UserMessage(agent.last_user_text, data['last_user_source'])
    agent.last_reply = data.get('last_reply')
    agent.history = list(data.get('history') or [])
    agent.contexts = list(data.get('contexts') or [])
    agent.desktop_messages = list(data.get('desktop_messages') or [])
    agent.desktop_title = data.get('desktop_title')
    agent.desktop_repository = data.get('desktop_repository') or str(root)
    # Pending fixes contain structured FileEdit objects — do not revive from JSON.
    agent.pending_fix = None
    agent.active_skills = []
    agent.last_tools = []
    agent.session_name = data.get('session_name')


def _session_filename(name: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in name.strip())[:64]
    return f'{safe or "session"}.json'


def save_session(agent, name: Optional[str] = None, *, update_latest: bool = True,
                 include_all_history: bool = False) -> Path:
    payload = serialize_agent(agent, include_all_history=include_all_history)
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
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(target)
    target.chmod(0o600)
    if update_latest:
        _write_session(root / LATEST_NAME, payload)
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
    changed = _recover_pending(data)
    sanitized = redact_secrets(data)
    if changed or sanitized != data:
        _write_session(p, sanitized)
    data = sanitized
    data['_path'] = str(p.resolve())
    return data


def _message_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages = data.get('desktop_messages')
    if isinstance(messages, list):
        return [row for row in messages if isinstance(row, dict)]
    history = data.get('history') or []
    return [dict(row, status='completed') for row in history
            if isinstance(row, dict) and row.get('role') in ('user', 'assistant')]


def _session_title(data: Dict[str, Any], path: Path) -> str:
    title = data.get('desktop_title')
    if isinstance(title, str) and title.strip():
        return title.strip()
    first_user = next((row.get('content', '') for row in _message_rows(data)
                       if row.get('role') == 'user'), '')
    if first_user:
        return ' '.join(str(first_user).split())[:64]
    return str(data.get('session_name') or path.stem)


def _recover_pending(data: Dict[str, Any]) -> bool:
    changed = False
    history = data.setdefault('history', [])
    for row in _message_rows(data):
        if row.get('status') == 'running':
            row['status'] = 'interrupted'
            row['updated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
            content = row.get('content')
            if content and (not history or history[-1].get('role') != 'user' or
                            history[-1].get('content') != content):
                history.append({'role': 'user', 'content': content})
            changed = True
    if changed and isinstance(data.get('desktop_messages'), list):
        data['desktop_messages'] = _message_rows(data)
    return changed


def _write_session(path: Path, data: Dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(redact_secrets(data), ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)
    path.chmod(0o600)


def list_sessions(limit: Optional[int] = 10, query: str = '') -> List[Dict[str, str]]:
    root = sessions_dir()
    skip = {LATEST_NAME, PREVIOUS_NAME}
    files = sorted(
        [p for p in root.glob('*.json') if p.name not in skip],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    rows = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if _recover_pending(data):
                _write_session(p, data)
            sanitized = redact_secrets(data)
            if sanitized != data:
                _write_session(p, sanitized)
            data = sanitized
            messages = _message_rows(data)
            turns = sum(1 for row in messages if row.get('role') == 'user')
            saved = data.get('saved_at') or datetime.fromtimestamp(
                p.stat().st_mtime).astimezone().isoformat(timespec='seconds')
            ctx = len(data.get('contexts') or [])
            title = _session_title(data, p)
            summary = next((str(row.get('content', '')).strip() for row in reversed(messages)
                            if row.get('content')), '')
            repository = data.get('desktop_repository')
            if not isinstance(repository, str):
                repository = data.get('work_root') or ''
            status = next((str(row.get('status')) for row in reversed(messages)
                           if row.get('role') == 'user'), 'completed')
        except Exception:
            turns, saved, ctx, title, summary, repository, status, messages = 0, '', 0, p.stem, '', '', 'failed', []
        if query and query.casefold() not in (title + '\n' + '\n'.join(
                str(row.get('content', '')) for row in messages)).casefold():
            continue
        rows.append({
            'name': p.stem,
            'title': title,
            'path': str(p),
            'saved_at': saved,
            'turns': str(turns),
            'contexts': str(ctx),
            'summary': ' '.join(summary.split())[:180],
            'repository': str(repository),
            'status': status,
        })
    if limit is not None:
        rows = rows[:max(1, limit)]
    return rows


def _session_path(name: str) -> Path:
    if not name or name in (LATEST_NAME[:-5], PREVIOUS_NAME[:-5], 'latest', 'previous'):
        raise ValueError('不能管理 latest/previous 会话别名')
    safe = _session_filename(name)
    path = sessions_dir() / safe
    if path.name != safe or not path.is_file():
        raise FileNotFoundError(f'未找到会话: {name}')
    return path


def rename_session(name: str, title: str) -> Dict[str, str]:
    title = ' '.join((title or '').split())
    if not title:
        raise ValueError('标题不能为空')
    if len(title) > 120:
        raise ValueError('标题不能超过 120 个字符')
    path = _session_path(name)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['desktop_title'] = title
    _write_session(path, data)
    return {'name': path.stem, 'title': title}


def delete_session(name: str) -> bool:
    _session_path(name).unlink()
    return True


def session_markdown(name: str) -> str:
    data = load_session(name)
    messages = _message_rows(data)
    title = _session_title(data, Path(name))
    lines = [f'# {title}', '', f'- 最近更新：{data.get("saved_at", "未记录")}']
    repository = data.get('desktop_repository')
    if not isinstance(repository, str):
        repository = data.get('work_root')
    if repository:
        lines.append(f'- 仓库：`{repository}`')
    lines.extend(['', '---', ''])
    for row in messages:
        role = '用户' if row.get('role') == 'user' else 'Agent'
        status = row.get('status', 'completed')
        lines.extend([f'## {role}（{status}）', '', str(row.get('content') or row.get('error') or ''), ''])
    return '\n'.join(lines).rstrip() + '\n'


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
