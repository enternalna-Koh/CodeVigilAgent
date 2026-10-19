"""Safe git / gh productivity helpers for chat (/git /commit /push /pr /ship).

Never force-pushes. Never amends. Never skips hooks. Commits/pushes need explicit confirm.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _root(cwd: Optional[str] = None) -> Path:
    return Path(cwd or os.getcwd()).expanduser().resolve()


def run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 120) -> Dict:
    git = shutil.which('git')
    if not git:
        return {'ok': False, 'code': 127, 'out': '未找到 git，请先安装并加入 PATH。', 'cmd': ['git', *args]}
    try:
        proc = subprocess.run(
            [git, *args],
            cwd=str(_root(cwd)),
            text=True,
            encoding='utf-8',
            errors='replace',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return {
            'ok': proc.returncode == 0,
            'code': proc.returncode,
            'out': (proc.stdout or '').rstrip(),
            'cmd': ['git', *args],
        }
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': None, 'out': 'git 命令超时', 'cmd': ['git', *args]}
    except OSError as exc:
        return {'ok': False, 'code': 127, 'out': str(exc), 'cmd': ['git', *args]}


def run_gh(args: List[str], cwd: Optional[str] = None, timeout: int = 180) -> Dict:
    gh = shutil.which('gh')
    if not gh:
        return {'ok': False, 'code': 127, 'out': '未找到 gh（GitHub CLI）。安装: https://cli.github.com/', 'cmd': ['gh', *args]}
    try:
        proc = subprocess.run(
            [gh, *args],
            cwd=str(_root(cwd)),
            text=True,
            encoding='utf-8',
            errors='replace',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return {
            'ok': proc.returncode == 0,
            'code': proc.returncode,
            'out': (proc.stdout or '').rstrip(),
            'cmd': ['gh', *args],
        }
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': None, 'out': 'gh 命令超时', 'cmd': ['gh', *args]}
    except OSError as exc:
        return {'ok': False, 'code': 127, 'out': str(exc), 'cmd': ['gh', *args]}


def ensure_repo(cwd: Optional[str] = None) -> Tuple[bool, str]:
    r = run_git(['rev-parse', '--is-inside-work-tree'], cwd=cwd)
    if not r['ok'] or (r['out'] or '').strip() != 'true':
        return False, '当前目录不是 git 仓库。请先 cd 到目标项目再执行。'
    return True, str(_root(cwd))


def status_report(cwd: Optional[str] = None) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    branch = run_git(['branch', '--show-current'], cwd=cwd)
    upstream = run_git(['status', '-sb'], cwd=cwd)
    porcelain = run_git(['status', '--porcelain'], cwd=cwd)
    lines = [
        '## Git 状态',
        '',
        f"- 目录: `{msg}`",
        f"- 分支: `{branch['out'] or '(detached)'}`",
        '',
        '```',
        upstream['out'] or '(clean)',
        '```',
    ]
    dirty = [ln for ln in (porcelain['out'] or '').splitlines() if ln.strip()]
    lines.append(f"\n变更文件数: **{len(dirty)}**")
    if dirty:
        lines.append('\n下一步: `/git diff` 查看 · `/commit "说明"` 提交 · `/push` 推送 · `/pr` 开 PR')
    return '\n'.join(lines)


def diff_report(cwd: Optional[str] = None, staged: bool = False, max_chars: int = 12000) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    args = ['diff', '--stat']
    if staged:
        args = ['diff', '--cached', '--stat']
    stat = run_git(args, cwd=cwd)
    full_args = ['diff']
    if staged:
        full_args = ['diff', '--cached']
    full = run_git(full_args, cwd=cwd)
    body = full['out'] or ''
    truncated = False
    if len(body) > max_chars:
        body = body[:max_chars] + '\n…(已截断)'
        truncated = True
    title = '暂存区 diff' if staged else '工作区 diff'
    lines = [f'## {title}', '', '```', stat['out'] or '(empty)', '```', '']
    if body.strip():
        lines.extend(['```diff', body, '```'])
    else:
        lines.append('（无差异）')
    if truncated:
        lines.append('\n> diff 过长已截断；完整内容请在终端 `git diff`。')
    return '\n'.join(lines)


def create_branch(name: str, cwd: Optional[str] = None, checkout: bool = True) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    name = (name or '').strip()
    if not re.match(r'^[A-Za-z0-9._/\-]+$', name):
        return '分支名不合法。仅允许字母数字 . _ / -'
    if checkout:
        r = run_git(['checkout', '-b', name], cwd=cwd)
    else:
        r = run_git(['branch', name], cwd=cwd)
    if r['ok']:
        return f"已创建并切换到分支 `{name}`。" if checkout else f"已创建分支 `{name}`。"
    # already exists → try switch
    if checkout:
        sw = run_git(['checkout', name], cwd=cwd)
        if sw['ok']:
            return f"分支已存在，已切换到 `{name}`。"
        return f"失败: {r['out'] or sw['out']}"
    return f"失败: {r['out']}"


def stage_paths(paths: Optional[List[str]] = None, cwd: Optional[str] = None) -> Dict:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return {'ok': False, 'out': msg}
    if paths:
        return run_git(['add', '--', *paths], cwd=cwd)
    # careful: add -u tracks modifications/deletes of tracked files; also add untracked with -A is broader
    return run_git(['add', '-A'], cwd=cwd)


def commit_changes(message: str, cwd: Optional[str] = None, add_all: bool = True) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    message = (message or '').strip()
    if not message:
        return '请提供提交说明：`/commit 修复 HCCL 超时`'
    if add_all:
        staged = stage_paths(cwd=cwd)
        if not staged['ok']:
            return f"暂存失败: {staged['out']}"
    # git diff --cached --quiet: 0 = empty, 1 = has staged changes
    check = run_git(['diff', '--cached', '--quiet'], cwd=cwd)
    if check['code'] == 0:
        return '没有可提交的暂存改动。先改文件或 `/fix`→`/apply`，再用 `/commit ...`。'
    if check['code'] not in (0, 1):
        return f"检查暂存区失败: {check['out']}"

    r = run_git(['commit', '-m', message], cwd=cwd)
    if not r['ok']:
        return f"提交失败 (code={r['code']}):\n{r['out']}"
    head = run_git(['log', '-1', '--oneline'], cwd=cwd)
    return f"已提交: `{head['out']}`\n\n下一步: `/push` 推送 · `/pr` 开 PR"


def push_branch(cwd: Optional[str] = None, set_upstream: bool = True) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    branch = (run_git(['branch', '--show-current'], cwd=cwd)['out'] or '').strip()
    if not branch:
        return '当前处于 detached HEAD，无法安全推送。请先 `/git branch <名>`。'
    args = ['push']
    if set_upstream:
        args = ['push', '-u', 'origin', 'HEAD']
    r = run_git(args, cwd=cwd, timeout=300)
    if not r['ok']:
        hint = ''
        out = r['out'] or ''
        if 'could not read Username' in out or 'Authentication failed' in out or 'Permission denied' in out:
            hint = (
                '\n\n认证失败时可试：\n'
                '- `/git ssh` 把 origin 改成 SSH\n'
                '- `gh auth login`\n'
                '- 或配置 SSH key: `ssh-keygen` → 公钥加到 GitHub'
            )
        if 'SSL' in out or '443' in out:
            hint += '\n\n若 HTTPS/SSL 不稳：优先 `/git ssh` 后重试 `/push`。'
        return f"推送失败 (code={r['code']}):\n{out}{hint}"
    return f"已推送分支 `{branch}` 到 origin。\n\n{r['out']}\n\n下一步: `/pr` 创建 Pull Request"


def remote_report(cwd: Optional[str] = None) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    r = run_git(['remote', '-v'], cwd=cwd)
    return '## Git remotes\n\n```\n' + (r['out'] or '(none)') + '\n```\n\n可用 `/git ssh` 将 GitHub HTTPS 转为 SSH。'


def to_ssh_origin(cwd: Optional[str] = None) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    url = run_git(['remote', 'get-url', 'origin'], cwd=cwd)
    if not url['ok']:
        return f"读取 origin 失败: {url['out']}"
    current = (url['out'] or '').strip()
    ssh = https_to_ssh(current)
    if not ssh:
        if current.startswith('git@'):
            return f'origin 已是 SSH：`{current}`'
        return f'无法识别的 origin URL：`{current}`（仅支持 github.com HTTPS）'
    r = run_git(['remote', 'set-url', 'origin', ssh], cwd=cwd)
    if not r['ok']:
        return f"设置失败: {r['out']}"
    return f"已将 origin 改为 SSH：\n`{current}`\n→ `{ssh}`\n\n可 `/git test-ssh` 验证，再 `/push`。"


def https_to_ssh(url: str) -> Optional[str]:
    u = (url or '').strip()
    m = re.match(r'https://github\.com/([^/]+)/([^/.]+)(?:\.git)?/?$', u)
    if m:
        return f'git@github.com:{m.group(1)}/{m.group(2)}.git'
    m = re.match(r'https://([^/]+)/([^/]+)/([^/.]+)(?:\.git)?/?$', u)
    # generic forge: only auto-convert github.com
    return None


def test_ssh(host: str = 'git@github.com') -> str:
    ssh = shutil.which('ssh')
    if not ssh:
        return '未找到 ssh 客户端。'
    target = host
    if host.startswith('git@'):
        # ssh -T git@github.com
        cmd = [ssh, '-T', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes', host]
    else:
        cmd = [ssh, '-T', '-o', 'BatchMode=yes', f'git@{host}']
        target = f'git@{host}'
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding='utf-8',
            errors='replace',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        out = (proc.stdout or '').strip()
        # GitHub returns 1 even on success ("Hi user! You've successfully authenticated")
        if 'successfully authenticated' in out.lower() or 'Hi ' in out:
            return f"SSH 认证成功（{target}）:\n{out}"
        if proc.returncode == 0:
            return f"SSH 连接完成（{target}）:\n{out or '(no output)'}"
        return f"SSH 测试未通过 (code={proc.returncode})（{target}）:\n{out}\n\n请检查密钥是否加入 ssh-agent / GitHub。"
    except Exception as exc:
        return f'SSH 测试异常: {exc}'


def create_pull_request(
    title: str,
    body: str = '',
    cwd: Optional[str] = None,
    draft: bool = False,
) -> str:
    ok, msg = ensure_repo(cwd)
    if not ok:
        return msg
    title = (title or '').strip()
    if not title:
        # default from last commit
        last = run_git(['log', '-1', '--pretty=%s'], cwd=cwd)
        title = (last['out'] or '').strip() or 'Update'
    args = ['pr', 'create', '--title', title, '--body', body or title]
    if draft:
        args.append('--draft')
    # ensure pushed
    status = run_git(['status', '-sb'], cwd=cwd)
    if 'ahead' in (status['out'] or '') or 'have diverged' in (status['out'] or '').lower():
        pass  # still try; gh may ask to push
    r = run_gh(args, cwd=cwd)
    if not r['ok']:
        out = r['out'] or ''
        hint = ''
        if 'to create a pull request' in out.lower() or 'must be pushed' in out.lower():
            hint = '\n\n请先 `/push`，再 `/pr`。'
        if 'gh' in out.lower() and 'auth' in out.lower():
            hint += '\n\n请运行 `gh auth login`。'
        return f"创建 PR 失败 (code={r['code']}):\n{out}{hint}"
    return f"PR 已创建:\n{r['out']}"


def suggest_commit_message(agent=None) -> str:
    if agent is not None and getattr(agent, 'pending_fix', None) and getattr(agent.pending_fix, 'summary', ''):
        return agent.pending_fix.summary.strip()[:72]
    if agent is not None and getattr(agent, 'last_user_text', None):
        t = agent.last_user_text.strip().splitlines()[0]
        return t[:72]
    last = run_git(['log', '-1', '--pretty=%s'])
    return (last['out'] or 'Update').strip()[:72]


def format_cmd_help() -> str:
    return '''## 生产力命令（真正改仓库）

工作流：`/fix` → `/apply` → `/commit ...` → `/push` → `/pr`

| 命令 | 作用 |
|------|------|
| `/git` / `/git status` | 看分支与脏文件 |
| `/git diff` `[staged]` | 看 diff |
| `/git branch <名>` | 新建并切换分支 |
| `/git remote` | 看 remote |
| `/git ssh` | GitHub origin HTTPS→SSH |
| `/git test-ssh` | 测 `git@github.com` |
| `/commit <说明>` | `git add -A` + commit（不 amend、不跳过 hook） |
| `/push` | `git push -u origin HEAD`（不 force） |
| `/pr` `[标题]` | `gh pr create` |
| `/pr draft [标题]` | 创建草稿 PR |
| `/ship <说明>` | 引导：status→commit→push→pr（逐步确认） |

安全：不 force push、不 amend、不改 git config、不自动跳过 hooks。
'''
