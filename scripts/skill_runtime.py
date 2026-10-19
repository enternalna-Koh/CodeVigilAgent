"""List / load / install Agent skills for ReviewAgent chat and review."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.agent_home import ensure_home, home_dir
from scripts.knowledge_search import PROJECT_ROOT
from scripts.specialist_context import MAX_BYTES, MAX_CHARS, _extract_sections

GITCODE_API = 'https://api.gitcode.com/api/v5'
ASCEND_SKILLS_REPO = 'Ascend/pytorch-ecosystem'
ASCEND_SKILLS_PREFIX = '01_tasks/resources/tools/agent_skills'

OFFICIAL_CATALOG = (
    'torch-npu-pr-review',
    'torch-npu-api-target-analyse',
    'torch-npu-doc-writer',
    'torch-npu-remote-runner',
    'torch-npu-server-runner',
)


@dataclass
class SkillInfo:
    name: str
    path: Path
    source: str
    description: str = ''

    def as_dict(self) -> Dict:
        return {
            'name': self.name,
            'path': str(self.path),
            'source': self.source,
            'description': self.description,
        }


@dataclass
class SkillLoad:
    name: str
    status: str  # ready | missing | incomplete
    text: str = ''
    path: Optional[str] = None
    omitted: List[str] = field(default_factory=list)
    chars: int = 0

    def as_dict(self) -> Dict:
        return {
            'name': self.name,
            'status': self.status,
            'path': self.path,
            'omitted': self.omitted,
            'chars': self.chars or len(self.text),
            'utf8_bytes': len(self.text.encode('utf-8')),
        }


def _skill_roots() -> List[Tuple[str, Path]]:
    ensure_home()
    return [
        ('project.cursor', PROJECT_ROOT / '.cursor' / 'skills'),
        ('project.agents', PROJECT_ROOT / '.agents' / 'skills'),
        ('user.reviewagent', Path(home_dir()) / 'skills'),
        ('user.cursor', Path.home() / '.cursor' / 'skills'),
    ]


def _frontmatter_desc(text: str) -> str:
    if not text.startswith('---'):
        return ''
    end = text.find('\n---', 3)
    if end < 0:
        return ''
    block = text[3:end]
    for line in block.splitlines():
        if line.strip().lower().startswith('description:'):
            return line.split(':', 1)[1].strip().strip('"\'')
    # multiline description after description: >
    m = re.search(r'^description:\s*[>|]?\s*\n((?:  .*\n)+)', block, re.M)
    if m:
        return ' '.join(ln.strip() for ln in m.group(1).splitlines() if ln.strip())[:200]
    return ''


def list_skills() -> List[SkillInfo]:
    seen = set()
    out: List[SkillInfo] = []
    for source, root in _skill_roots():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            skill_md = child / 'SKILL.md' if child.is_dir() else None
            if not skill_md or not skill_md.is_file():
                continue
            name = child.name
            if name in seen:
                continue
            seen.add(name)
            try:
                text = skill_md.read_text(encoding='utf-8')
            except OSError:
                text = ''
            out.append(SkillInfo(
                name=name,
                path=skill_md,
                source=source,
                description=_frontmatter_desc(text) or text.splitlines()[0][:120] if text else '',
            ))
    return out


def find_skill(name: str) -> Optional[SkillInfo]:
    name = (name or '').strip()
    if not name:
        return None
    for info in list_skills():
        if info.name == name or info.name.replace('_', '-') == name.replace('_', '-'):
            return info
    return None


def load_skill(name: str, sections: Optional[Sequence[str]] = None,
               max_chars: int = MAX_CHARS, max_bytes: int = MAX_BYTES) -> SkillLoad:
    info = find_skill(name)
    if not info:
        return SkillLoad(name=name, status='missing')
    text = info.path.read_text(encoding='utf-8')
    if sections:
        text = _extract_sections(text, list(sections))
    omitted: List[str] = []
    if len(text) > max_chars or len(text.encode('utf-8')) > max_bytes:
        # Prefer head + 红线 sections rather than mid-cut a rule
        keep = text[: max(0, max_chars - 80)]
        while len(keep.encode('utf-8')) > max_bytes and keep:
            keep = keep[:-200]
        omitted.append('budget_truncated')
        text = keep + '\n\n…[skill truncated by budget]…\n'
    return SkillLoad(
        name=info.name,
        status='incomplete' if omitted else 'ready',
        text=text,
        path=str(info.path),
        omitted=omitted,
        chars=len(text),
    )


def _http_get_json(url: str, token: Optional[str] = None) -> Dict:
    headers = {'Accept': 'application/json', 'User-Agent': 'ReviewAgent/1.8'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
        headers['PRIVATE-TOKEN'] = token
        sep = '&' if '?' in url else '?'
        url = f'{url}{sep}access_token={token}'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _download_blob_text(owner_repo: str, path: str, token: Optional[str] = None) -> str:
    """Fetch file content via GitCode contents API (base64 or download_url)."""
    import base64
    owner, repo = owner_repo.split('/', 1)
    api = f'{GITCODE_API}/repos/{owner}/{repo}/contents/{path}'
    data = _http_get_json(api, token=token)
    if isinstance(data, list):
        raise FileNotFoundError(f'{path} 是目录而非文件')
    if not isinstance(data, dict):
        raise RuntimeError('GitCode contents 响应异常')
    if data.get('encoding') == 'base64' and data.get('content'):
        return base64.b64decode(data['content']).decode('utf-8')
    download = data.get('download_url')
    if download:
        req = urllib.request.Request(download, headers={'User-Agent': 'ReviewAgent/1.8'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8')
    # Fallback: blobs API
    sha = data.get('sha')
    if not sha:
        raise RuntimeError(f'无法读取 {path}')
    blob = _http_get_json(f'{GITCODE_API}/repos/{owner}/{repo}/git/blobs/{sha}', token=token)
    return base64.b64decode(blob['content']).decode('utf-8')


def _list_dir(owner_repo: str, path: str, token: Optional[str] = None) -> List[Dict]:
    owner, repo = owner_repo.split('/', 1)
    api = f'{GITCODE_API}/repos/{owner}/{repo}/contents/{path}'
    data = _http_get_json(api, token=token)
    if not isinstance(data, list):
        raise RuntimeError(f'{path} 不是目录')
    return data


def install_skill(name: str, *, token: Optional[str] = None,
                  catalog: str = ASCEND_SKILLS_REPO,
                  prefix: str = ASCEND_SKILLS_PREFIX) -> Dict:
    """Install SKILL.md (+ references/*.md if small) into ~/.reviewagent/skills/<name>/."""
    import os
    name = (name or '').strip()
    if not name:
        return {'ok': False, 'error': '用法: /skill install <name>'}
    if name not in OFFICIAL_CATALOG and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,80}', name):
        return {'ok': False, 'error': f'非法 skill 名: {name}'}
    token = token or os.getenv('GITCODE_TOKEN') or os.getenv('GITHUB_TOKEN')
    ensure_home()
    dest = Path(home_dir()) / 'skills' / name
    dest.mkdir(parents=True, exist_ok=True)
    remote_skill = f'{prefix}/{name}/SKILL.md'
    try:
        skill_text = _download_blob_text(catalog, remote_skill, token=token)
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, RuntimeError, FileNotFoundError) as exc:
        return {'ok': False, 'error': f'拉取失败: {exc}', 'remote': remote_skill}
    (dest / 'SKILL.md').write_text(skill_text, encoding='utf-8')
    saved = ['SKILL.md']
    # Optional small references
    try:
        entries = _list_dir(catalog, f'{prefix}/{name}/references', token=token)
        ref_dir = dest / 'references'
        ref_dir.mkdir(exist_ok=True)
        for entry in entries:
            if entry.get('type') != 'file':
                continue
            fname = entry.get('name') or ''
            if not fname.endswith('.md'):
                continue
            if int(entry.get('size') or 0) > 200_000:
                continue
            body = _download_blob_text(catalog, f'{prefix}/{name}/references/{fname}', token=token)
            (ref_dir / fname).write_text(body, encoding='utf-8')
            saved.append(f'references/{fname}')
    except Exception:
        pass
    meta = {
        'name': name,
        'source': catalog,
        'prefix': prefix,
        'files': saved,
        'url': f'https://gitcode.com/{catalog}/tree/master/{prefix}/{name}',
    }
    (dest / 'install.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'ok': True, 'path': str(dest), 'meta': meta}


def format_skill_list(skills: Optional[Sequence[SkillInfo]] = None) -> str:
    skills = list(skills if skills is not None else list_skills())
    if not skills:
        return '未发现 skill。可 /skill install torch-npu-pr-review'
    lines = ['可用 Skills:']
    for s in skills:
        desc = (s.description or '')[:80]
        lines.append(f'  • {s.name}  [{s.source}]' + (f' — {desc}' if desc else ''))
    lines.append('官方可装: ' + ', '.join(OFFICIAL_CATALOG))
    return '\n'.join(lines)
