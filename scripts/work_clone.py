"""Clone / fetch GitHub or GitCode PR branches into the user-selected folder."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from scripts.git_work import run_git


PR_URL_RE = re.compile(
    r'https://(?:www\.)?(github\.com|gitcode\.com)/([\w.-]+)/([\w.-]+)/(pulls?|issues|merge_requests)/(\d+)',
    re.I,
)


def reviewagent_home() -> Path:
    raw = os.environ.get('REVIEWAGENT_HOME')
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / '.reviewagent').resolve()


def resolve_clone_parent(agent=None, explicit: Optional[str] = None) -> Path:
    """Parent directory for clones: whatever folder the user selected.

    Priority:
      1. explicit path
      2. REVIEWAGENT_CLONE_ROOT
      3. agent.desktop_repository (desktop 「选择目录」)
      4. agent.work_root
      5. cwd
    Never silently fall back to ~/.reviewagent on another drive when a
    selection exists.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get('REVIEWAGENT_CLONE_ROOT') or os.environ.get('REVIEWAGENT_WORKROOT')
    if env:
        candidates.append(env)
    if agent is not None:
        for attr in ('desktop_repository', 'work_root'):
            val = getattr(agent, attr, None)
            if val:
                candidates.append(str(val))
    candidates.append(os.getcwd())
    for raw in candidates:
        try:
            p = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if p.is_file():
            p = p.parent
        if p.is_dir():
            return p
    return Path.cwd().resolve()


def workspaces_root(agent=None, explicit: Optional[str] = None) -> Path:
    """Clone parent = selected folder (not ~/.reviewagent/workspaces)."""
    root = resolve_clone_parent(agent=agent, explicit=explicit)
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_pr_url(url: str) -> Optional[Dict]:
    """Parse a PR (not Issue) URL from GitHub or GitCode."""
    u = (url or '').strip()
    if not u:
        return None
    m = PR_URL_RE.search(u)
    if not m:
        # also accept bare path-style via urlparse
        parsed = urlparse(u)
        host = (parsed.netloc or '').lower().replace('www.', '')
        if host not in ('github.com', 'gitcode.com'):
            return None
        match = re.fullmatch(
            r'/([\w.-]+)/([\w.-]+)/(pulls?|issues|merge_requests)/(\d+)/?',
            parsed.path or '',
            re.I,
        )
        if not match:
            return None
        owner, repo, kind, number = match.groups()
        kind_l = kind.lower()
        if kind_l == 'issues':
            return None
        return {
            'host': 'github' if host == 'github.com' else 'gitcode',
            'owner': owner,
            'repo': repo.rstrip('.git'),
            'number': int(number),
            'url': u.split('#')[0].rstrip('/'),
        }
    host_raw, owner, repo, kind, number = m.groups()
    kind_l = kind.lower()
    if kind_l == 'issues':
        return None
    host = 'github' if 'github' in host_raw.lower() else 'gitcode'
    return {
        'host': host,
        'owner': owner,
        'repo': repo.rstrip('.git'),
        'number': int(number),
        'url': m.group(0).split('#')[0].rstrip('/'),
    }


def extract_pr_url(text: str) -> Optional[str]:
    if not text:
        return None
    m = PR_URL_RE.search(text)
    if not m:
        return None
    kind = m.group(4).lower()
    if kind == 'issues':
        return None
    return m.group(0).rstrip('/')


def clone_url_for(meta: Dict) -> str:
    if meta['host'] == 'github':
        return f"https://github.com/{meta['owner']}/{meta['repo']}.git"
    return f"https://gitcode.com/{meta['owner']}/{meta['repo']}.git"


def workspace_path(meta: Dict, agent=None, explicit_parent: Optional[str] = None) -> Path:
    safe = f"{meta['owner']}_{meta['repo']}".replace('..', '_')
    return workspaces_root(agent=agent, explicit=explicit_parent) / safe


def _ensure_clone(meta: Dict, dest: Path) -> Tuple[bool, str]:
    git = shutil.which('git')
    if not git:
        return False, '未找到 git，请先安装并加入 PATH。'
    url = clone_url_for(meta)
    if dest.is_dir() and (dest / '.git').exists():
        fetch = run_git(['fetch', 'origin'], cwd=str(dest), timeout=600)
        if not fetch['ok']:
            return False, f"git fetch 失败:\n{fetch['out']}"
        return True, f'已更新已有工作区 `{dest}`'
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not (dest / '.git').exists():
        return False, f'路径已存在且不是 git 仓库: `{dest}`'
    import subprocess
    try:
        p = subprocess.run(
            [git, 'clone', url, str(dest)],
            text=True,
            encoding='utf-8',
            errors='replace',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False,
        )
        if p.returncode != 0 or not (dest / '.git').exists():
            return False, f"git clone 失败:\n{(p.stdout or '').rstrip()}"
    except Exception as exc:
        return False, f'git clone 异常: {exc}'
    return True, f'已克隆到 `{dest}`'


def _detach_if_on_branch(dest: Path, branch: str) -> None:
    """Cannot fetch into a branch that is currently checked out."""
    cur = (run_git(['branch', '--show-current'], cwd=str(dest)).get('out') or '').strip()
    if cur == branch:
        # prefer switching to default branch; else detach
        for fallback in ('main', 'master', 'develop'):
            sw = run_git(['checkout', fallback, '--'], cwd=str(dest))
            if sw['ok']:
                return
        run_git(['checkout', '--detach'], cwd=str(dest))


def _fetch_pr_refs(meta: Dict, dest: Path) -> Tuple[bool, str, str]:
    """Fetch PR head into local branch pr-<n>. Returns (ok, message, branch)."""
    n = meta['number']
    branch = f'pr-{n}'
    remote_ref = f'refs/remotes/origin/{branch}'
    # Fetch into remote-tracking ref first (safe even if local pr-N is checked out)
    remote_candidates = [
        f'pull/{n}/head:{remote_ref}',
        f'pulls/{n}/head:{remote_ref}',
        f'merge-requests/{n}/head:{remote_ref}',
    ]
    last_err = ''
    fetched = False
    used = ''
    for refspec in remote_candidates:
        r = run_git(['fetch', 'origin', refspec], cwd=str(dest), timeout=300)
        if r['ok']:
            fetched = True
            used = refspec
            break
        last_err = r['out'] or ''
    if not fetched:
        # Fallback: leave current branch, fetch to FETCH_HEAD
        _detach_if_on_branch(dest, branch)
        for src in (f'pull/{n}/head', f'pulls/{n}/head', f'merge-requests/{n}/head'):
            r = run_git(['fetch', 'origin', src], cwd=str(dest), timeout=300)
            if r['ok']:
                co = run_git(['checkout', '-B', branch, 'FETCH_HEAD'], cwd=str(dest))
                if co['ok']:
                    return True, f'已检出 PR #{n} → 分支 `{branch}`（{src}）', branch
                last_err = co['out'] or r['out']
            else:
                last_err = r['out'] or last_err
        return False, f'无法拉取 PR #{n} 的远端 ref。最后错误:\n{last_err}', branch

    _detach_if_on_branch(dest, branch)
    co = run_git(['checkout', '-B', branch, f'origin/{branch}'], cwd=str(dest))
    if not co['ok']:
        # origin/pr-N might need explicit path
        co = run_git(['checkout', '-B', branch, remote_ref], cwd=str(dest))
    if not co['ok']:
        return False, f'已 fetch 但检出失败:\n{co["out"]}', branch
    return True, f'已检出 PR #{n} → 分支 `{branch}`（ref `{used}`）', branch


def build_local_pr_context(meta: Dict, dest: Path, branch: str) -> Dict:
    """Build a review context from the local checkout when GitCode/GitHub API fails."""
    cwd = str(dest)
    log = run_git(['log', '-5', '--oneline'], cwd=cwd)
    base = None
    for cand in ('origin/main', 'origin/master', 'main', 'master'):
        chk = run_git(['rev-parse', '--verify', cand], cwd=cwd)
        if chk['ok']:
            base = cand
            break
    files = []
    body_parts = [
        f"本地检出: `{dest}` 分支 `{branch}`",
        f"PR: {meta.get('url')}",
        '',
        '### 最近提交',
        log.get('out') or '(无)',
    ]
    if base:
        stat = run_git(['diff', '--stat', f'{base}...HEAD'], cwd=cwd)
        body_parts.extend(['', f'### Diff stat vs {base}', stat.get('out') or '(empty)'])
        full = run_git(['diff', f'{base}...HEAD'], cwd=cwd, timeout=120)
        diff_text = full.get('out') or ''
        if len(diff_text) > 60000:
            diff_text = diff_text[:60000] + '\n…(本地 diff 已截断)'
        body_parts.extend(['', '### Diff', '```diff', diff_text, '```'])
        name_only = run_git(['diff', '--name-status', f'{base}...HEAD'], cwd=cwd)
        for line in (name_only.get('out') or '').splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                files.append({'filename': parts[-1], 'status': parts[0], 'patch': ''})
    return {
        'type': 'pr',
        'title': f"PR #{meta['number']} {meta['owner']}/{meta['repo']} (local)",
        'url': meta['url'],
        'host': meta['host'],
        'body': '\n'.join(body_parts),
        'state': 'local-checkout',
        'comments': [],
        'files': files,
        'reviews': [],
        'inline_comments': [],
        'warnings': [
            '上下文来自本地 clone（API 限流或失败时的兜底）；文件级 patch 可能不完整。',
        ],
        'local_checkout': cwd,
        'local_branch': branch,
    }


def infer_pr_meta_from_work_root(work_root) -> Optional[Dict]:
    """Recover PR meta from a local checkout (remote URL + pr-N branch)."""
    if not work_root:
        return None
    dest = Path(work_root)
    if not (dest / '.git').exists():
        return None
    cwd = str(dest)
    remote = run_git(['remote', 'get-url', 'origin'], cwd=cwd)
    url = (remote.get('out') or '').strip()
    branch = (run_git(['branch', '--show-current'], cwd=cwd).get('out') or '').strip()
    m = re.search(r'pr-(\d+)$', branch)
    if not m:
        return None
    number = int(m.group(1))
    host = 'gitcode' if 'gitcode.com' in url.lower() else 'github'
    owner = repo = None
    gm = re.search(r'(?:gitcode\.com|github\.com)[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$', url, re.I)
    if gm:
        owner, repo = gm.group(1), gm.group(2).rstrip('.git')
    if not owner or not repo:
        parts = dest.name.split('_', 1)
        if len(parts) == 2:
            owner, repo = parts[0], parts[1]
    if not owner or not repo:
        return None
    pr_url = (
        f'https://{"github.com" if host == "github" else "gitcode.com"}'
        f'/{owner}/{repo}/pull/{number}'
    )
    return {
        'host': host,
        'owner': owner,
        'repo': repo,
        'number': number,
        'url': pr_url,
        'branch': branch,
        'path': cwd,
    }


def ensure_sticky_pr_context(agent) -> bool:
    """If contexts empty but work_root has a PR checkout, rebuild local context."""
    if agent is None:
        return False
    if getattr(agent, 'contexts', None):
        return True
    meta = None
    last_url = getattr(agent, 'last_pr_url', None)
    if isinstance(last_url, str) and last_url.strip():
        meta = parse_pr_url(last_url)
    wr = getattr(agent, 'work_root', None)
    if not isinstance(wr, (str, Path)):
        wr = None
    inferred = infer_pr_meta_from_work_root(wr)
    if meta is None and inferred:
        meta = inferred
    if meta is None:
        return False
    dest = Path(inferred['path']) if inferred and inferred.get('path') else (
        Path(wr) if wr else workspace_path(meta, agent=agent)
    )
    if not (dest / '.git').exists():
        return False
    branch = (inferred or {}).get('branch') or f"pr-{meta['number']}"
    try:
        agent.contexts = [build_local_pr_context(meta, dest, branch)]
        agent.session_lane = 'work'
        agent.last_pr_url = meta['url']
        return True
    except Exception:
        return False


def context_from_local_or_api(agent, url: str) -> Optional[Dict]:
    """Fetch PR context; on API failure fall back to local clone if present."""
    meta = parse_pr_url(url)
    if not meta:
        return None
    data = None
    err = None
    if agent is not None and getattr(agent, 'fetcher', None):
        try:
            raw = agent.fetcher.fetch_url(url)
            if isinstance(raw, dict) and raw.get('error'):
                err = raw.get('error')
            elif isinstance(raw, dict):
                data = raw
        except Exception as exc:
            err = str(exc)
    dest = workspace_path(meta, agent=agent)
    wr = getattr(agent, 'work_root', None) if agent else None
    if wr and meta['repo'].lower() in str(wr).lower() and (Path(wr) / '.git').exists():
        dest = Path(wr)
    branch = f"pr-{meta['number']}"
    if (dest / '.git').exists():
        cur = (run_git(['branch', '--show-current'], cwd=str(dest)).get('out') or '').strip()
        if cur:
            branch = cur
        local = build_local_pr_context(meta, dest, branch)
        if data:
            data.setdefault('warnings', [])
            data['local_checkout'] = str(dest)
            data['local_branch'] = branch
            if not data.get('files') and local.get('files'):
                data['files'] = local['files']
            if len(data.get('body') or '') < 500:
                data['body'] = (data.get('body') or '') + '\n\n' + local.get('body', '')
            return data
        if err:
            local.setdefault('warnings', []).append(f'在线获取失败（{err}），已改用本地检出。')
        return local
    return data


def clone_or_fetch_pr(url: str, agent=None) -> Dict:
    """Clone repo (if needed), fetch PR head, switch work_root.

    Returns dict: ok, message, path, meta, branch
    """
    meta = parse_pr_url(url)
    if not meta:
        return {
            'ok': False,
            'message': '需要 GitHub/GitCode 的 **PR** 链接（issues 链接请先审查，不自动 clone）。',
            'path': None,
            'meta': None,
            'branch': None,
        }
    parent = resolve_clone_parent(agent=agent)
    dest = workspace_path(meta, agent=agent)
    ok, msg = _ensure_clone(meta, dest)
    if not ok:
        return {'ok': False, 'message': msg, 'path': str(dest), 'meta': meta, 'branch': None}
    ok2, msg2, branch = _fetch_pr_refs(meta, dest)
    if not ok2:
        return {'ok': False, 'message': f'{msg}\n{msg2}', 'path': str(dest), 'meta': meta, 'branch': None}
    if agent is not None:
        agent.work_root = Path(dest).resolve()
        if not getattr(agent, 'desktop_repository', None):
            agent.desktop_repository = str(parent)
        agent.session_lane = 'work'
        agent.last_pr_url = meta['url']
        ctx = None
        try:
            ctx = context_from_local_or_api(agent, meta['url'])
        except Exception:
            ctx = None
        agent.contexts = [ctx] if ctx else [build_local_pr_context(meta, dest, branch)]
    return {
        'ok': True,
        'message': (
            f'{msg}\n{msg2}\n'
            f'克隆父目录（你选的文件夹）: `{parent}`\n'
            f'仓库目录: `{dest}`'
        ),
        'path': str(dest),
        'meta': meta,
        'branch': branch,
        'parent': str(parent),
    }
