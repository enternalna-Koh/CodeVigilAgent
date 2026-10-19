"""List / load / install Agent skills for ReviewAgent chat and review."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse
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
            value = line.split(':', 1)[1].strip().strip('"\'')
            if value and value not in ('>', '|'):
                return value
            break
    # multiline description after description: >
    m = re.search(r'^description:[ \t]*[>|]?[ \t]*\n((?:[ \t]{2,}[^\n]*(?:\n|$))+)', block, re.M)
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
            except (OSError, UnicodeError):
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
    try:
        text = info.path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        return SkillLoad(name=info.name, status='incomplete', path=str(info.path),
                         omitted=[f'无法读取 skill: {exc}'])
    if sections:
        text = _extract_sections(text, list(sections))
    omitted: List[str] = []
    if not text.strip():
        omitted.append('SKILL.md 为空')
    if len(text) > max_chars or len(text.encode('utf-8')) > max_bytes:
        marker = '\n\n…[skill truncated by budget]…\n'
        marker = marker[:max(0, max_chars)].encode('utf-8')[:max(0, max_bytes)].decode('utf-8', 'ignore')
        keep = text[:max(0, max_chars - len(marker))]
        keep = keep.encode('utf-8')[:max(0, max_bytes - len(marker.encode('utf-8')))].decode('utf-8', 'ignore')
        omitted.append('budget_truncated')
        text = keep + marker
    meta_path = info.path.parent / 'install.json'
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            omitted.extend(meta.get('omitted') or [])
        except (OSError, ValueError, AttributeError):
            omitted.append('无法读取安装元数据')
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
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise RuntimeError('GitCode 响应超过 4 MB 限制')
        return json.loads(payload.decode('utf-8'))


def _download_blob_text(owner_repo: str, path: str, token: Optional[str] = None) -> str:
    """Fetch file content via GitCode contents API (base64 or download_url)."""
    import base64
    owner, repo = owner_repo.split('/', 1)
    api = f'{GITCODE_API}/repos/{owner}/{repo}/contents/{quote(path, safe="/")}'
    data = _http_get_json(api, token=token)
    if isinstance(data, list):
        raise FileNotFoundError(f'{path} 是目录而非文件')
    if not isinstance(data, dict):
        raise RuntimeError('GitCode contents 响应异常')
    if data.get('encoding') == 'base64' and data.get('content'):
        return base64.b64decode(data['content']).decode('utf-8')
    download = data.get('download_url')
    if download:
        if not isinstance(download, str):
            raise RuntimeError('GitCode download_url 格式异常')
        parsed = urlparse(download)
        if parsed.scheme != 'https' or not (
            parsed.hostname == 'gitcode.com' or (parsed.hostname or '').endswith('.gitcode.com')
        ):
            raise RuntimeError('拒绝非 GitCode HTTPS 下载地址')
        req = urllib.request.Request(download, headers={'User-Agent': 'ReviewAgent/1.8'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read(4 * 1024 * 1024 + 1)
            if len(payload) > 4 * 1024 * 1024:
                raise RuntimeError('Skill 文件超过 4 MB 限制')
            return payload.decode('utf-8')
    # Fallback: blobs API
    sha = data.get('sha')
    if not sha:
        raise RuntimeError(f'无法读取 {path}')
    blob = _http_get_json(f'{GITCODE_API}/repos/{owner}/{repo}/git/blobs/{sha}', token=token)
    if not isinstance(blob, dict) or not isinstance(blob.get('content'), str):
        raise RuntimeError('GitCode blob 响应格式异常')
    return base64.b64decode(blob['content']).decode('utf-8')


def _list_dir(owner_repo: str, path: str, token: Optional[str] = None) -> List[Dict]:
    owner, repo = owner_repo.split('/', 1)
    api = f'{GITCODE_API}/repos/{owner}/{repo}/contents/{quote(path, safe="/")}'
    data = _http_get_json(api, token=token)
    if not isinstance(data, list):
        raise RuntimeError(f'{path} 不是目录')
    return data


def install_skill(name: str, *, token: Optional[str] = None,
                  catalog: str = ASCEND_SKILLS_REPO,
                  prefix: str = ASCEND_SKILLS_PREFIX) -> Dict:
    """Install SKILL.md (+ references/*.md if small) into ~/.reviewagent/skills/<name>/."""
    name = (name or '').strip()
    if not name:
        return {'ok': False, 'error': '用法: /skill install <name>'}
    if name not in OFFICIAL_CATALOG and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,80}', name):
        return {'ok': False, 'error': f'非法 skill 名: {name}'}
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*', catalog) or any(
        part in ('', '.', '..') for part in prefix.split('/')
    ) or '\\' in prefix:
        return {'ok': False, 'error': '非法 skill 来源路径'}
    token = token or os.getenv('GITCODE_TOKEN')
    try:
        ensure_home()
    except OSError as exc:
        return {'ok': False, 'error': f'创建用户目录失败: {exc}'}
    dest = Path(home_dir()) / 'skills' / name
    remote_skill = f'{prefix}/{name}/SKILL.md'
    try:
        # Resolve every target before writing so remote filenames/symlinks cannot escape the skill.
        skill_root = (Path(home_dir()) / 'skills').resolve()
        if dest.is_symlink() or dest.resolve().parent != skill_root:
            raise RuntimeError('Skill 目标路径越界')
        skill_text = _download_blob_text(catalog, remote_skill, token=token)
        if not skill_text.strip():
            raise RuntimeError('SKILL.md 为空')
        files = {'SKILL.md': skill_text}
        omitted = []
        try:
            entries = _list_dir(catalog, f'{prefix}/{name}/references', token=token)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError('references 目录响应格式异常')
            if entry.get('type') != 'file':
                omitted.append(f'references/{entry.get("name", "?")}: 非文件，未安装')
                continue
            fname = entry.get('name') or ''
            if not isinstance(fname, str) or '/' in fname or '\\' in fname or ':' in fname or fname in ('.', '..'):
                raise RuntimeError('references 包含非法文件名')
            if not fname.endswith('.md'):
                omitted.append(f'references/{fname}: 仅支持 Markdown，未安装')
                continue
            if int(entry.get('size') or 0) > 200_000:
                omitted.append(f'references/{fname}: 超过 200 KB 限制')
                continue
            body = _download_blob_text(catalog, f'{prefix}/{name}/references/{fname}', token=token)
            if len(body.encode('utf-8')) > 200_000:
                omitted.append(f'references/{fname}: 超过 200 KB 限制')
                continue
            files[f'references/{fname}'] = body
        for relative in list(files) + ['install.json']:
            target = (dest / relative).resolve()
            target.relative_to(dest.resolve())
            if (dest / relative).is_symlink():
                raise RuntimeError('Skill 文件为符号链接，拒绝覆盖')
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        return {'ok': False, 'error': f'拉取失败: {exc}', 'remote': remote_skill}
    meta = {
        'name': name,
        'source': catalog,
        'prefix': prefix,
        'files': list(files),
        'omitted': omitted,
        'url': f'https://gitcode.com/{catalog}/tree/master/{prefix}/{name}',
    }
    files['install.json'] = json.dumps(meta, ensure_ascii=False, indent=2)
    try:
        for relative, body in files.items():
            path = dest / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding='utf-8')
    except OSError as exc:
        return {'ok': False, 'error': f'写入失败: {exc}', 'path': str(dest)}
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
