#!/usr/bin/env python3
"""Batch-collect GitCode community issues/PRs/CI/review dialogs into data/."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.conversation_agent import ContextFetcher  # noqa: E402

COMMUNITIES_DIR = PROJECT_ROOT / 'data' / 'communities'
RAW_DIR = PROJECT_ROOT / 'data' / 'raw'
CI_DIR = PROJECT_ROOT / 'data' / 'ci_runs'
DIALOG_DIR = PROJECT_ROOT / 'data' / 'review_dialogs'


def load_community(community_id: str) -> Dict[str, Any]:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', community_id):
        raise ValueError('非法社区 id')
    path = COMMUNITIES_DIR / f'{community_id}.json'
    if not path.is_file():
        raise FileNotFoundError(f'未找到社区注册表: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('repos'), list) or not data['repos']:
        raise ValueError('社区注册表必须包含非空 repos 列表')
    for repo in data['repos']:
        if not isinstance(repo, dict) or any(
            not isinstance(repo.get(key), str)
            or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', repo[key])
            for key in ('owner', 'repo')
        ):
            raise ValueError('社区注册表的 owner/repo 非法')
        collect = repo.get('collect', ['issues', 'pulls'])
        if not isinstance(collect, list) or not collect or any(
            item not in ('issues', 'pulls', 'ci', 'dialogs') for item in collect
        ):
            raise ValueError('社区注册表的 collect 必须是有效采集类型列表')
    return data


def _login(user: Any) -> Optional[str]:
    if not isinstance(user, dict):
        return None
    return user.get('login') or user.get('name') or user.get('username')


def _role_for(login: Optional[str], author: Optional[str], staff: set) -> str:
    if not login:
        return 'unknown'
    if author and login == author:
        return 'author'
    if login in staff:
        return 'reviewer'
    return 'participant'


def _staff_logins(item: Dict[str, Any]) -> set:
    names: set = set()
    for key in ('assignee',):
        login = _login(item.get(key))
        if login:
            names.add(login)
    for key in ('assignees', 'testers', 'reviewers'):
        for entry in item.get(key) or []:
            login = _login(entry) if isinstance(entry, dict) else str(entry)
            if login:
                names.add(login)
    reviewer = item.get('reviewer') or item.get('user_reviews')
    if isinstance(reviewer, list):
        for entry in reviewer:
            login = _login(entry) if isinstance(entry, dict) else str(entry)
            if login:
                names.add(login)
    elif isinstance(reviewer, str) and reviewer:
        names.add(reviewer)
    return names


def fetch_list(fetcher: ContextFetcher, endpoint: str, pages: int = 2) -> List[Dict]:
    items: List[Dict] = []
    for page in range(1, pages + 1):
        data = fetcher.fetch_gitcode_api(f'{endpoint}?state=all&per_page=100&page={page}')
        if isinstance(data, dict) and data.get('error'):
            raise RuntimeError(f'{endpoint}: {data["error"]}')
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise RuntimeError(f'{endpoint}: 响应格式异常')
        items.extend(data)
        if len(data) < 100:
            break
    return items


def collect_check_runs(fetcher: ContextFetcher, owner: str, repo: str,
                       pr: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort CI summary for a PR (check-runs / commits status)."""
    number = pr.get('number') or pr.get('id')
    head = pr.get('head') if isinstance(pr.get('head'), dict) else {}
    sha = head.get('sha') or pr.get('merge_commit_sha') or ''
    base = f'/repos/{owner}/{repo}'
    result: Dict[str, Any] = {
        'pr_number': number,
        'head_sha': sha,
        'check_runs': [],
        'warnings': [],
        'ok': False,
    }
    if sha:
        data = fetcher.fetch_gitcode_api(f'{base}/commits/{sha}/check-runs')
        if isinstance(data, dict) and not data.get('error'):
            runs = data.get('check_runs', data.get('values'))
            if isinstance(runs, list):
                result['check_runs'] = runs[:50]
                result['ok'] = True
                return result
        if isinstance(data, list):
            result['check_runs'] = data[:50]
            result['ok'] = True
            return result
        if isinstance(data, dict) and data.get('error'):
            result['warnings'].append(str(data['error']))
    # Fallback: PR-level check endpoint if present
    if number is not None:
        data = fetcher.fetch_gitcode_api(f'{base}/pulls/{number}/check-runs')
        if isinstance(data, dict) and not data.get('error'):
            runs = data.get('check_runs', data.get('values'))
            if isinstance(runs, list):
                result['check_runs'] = runs[:50]
                result['ok'] = True
        elif isinstance(data, list):
            result['check_runs'] = data[:50]
            result['ok'] = True
        elif isinstance(data, dict) and data.get('error'):
            result['warnings'].append(str(data['error']))
    if not result['ok'] and not result['warnings']:
        result['warnings'].append('CI 响应格式异常或缺少 PR 标识')
    return result


def collect_dialogs(fetcher: ContextFetcher, owner: str, repo: str,
                    kind: str, items: Sequence[Dict], limit: int = 20) -> List[Dict]:
    base = f'/repos/{owner}/{repo}'
    out: List[Dict] = []
    for item in list(items)[:limit]:
        number = item.get('number')
        if number is None:
            continue
        author = _login(item.get('user'))
        staff = _staff_logins(item)
        comments = []
        warnings = []
        for page in range(1, 3):
            data = fetcher.fetch_gitcode_api(
                f'{base}/issues/{number}/comments?per_page=50&page={page}')
            if not isinstance(data, list) or any(not isinstance(c, dict) for c in data):
                warnings.append(str(data.get('error', '讨论响应格式异常'))
                                if isinstance(data, dict) else '讨论响应格式异常')
                break
            for c in data:
                login = _login(c.get('user'))
                comments.append({
                    'body': c.get('body') or '',
                    'author': login,
                    'role': _role_for(login, author, staff),
                    'created_at': c.get('created_at'),
                    'url': c.get('html_url'),
                })
            if len(data) < 50:
                break
        inline = []
        if kind == 'pull':
            data = fetcher.fetch_gitcode_api(
                f'{base}/pulls/{number}/comments?per_page=50')
            if isinstance(data, list) and all(isinstance(c, dict) for c in data):
                for c in data:
                    login = _login(c.get('user'))
                    inline.append({
                        'body': c.get('body') or '',
                        'author': login,
                        'role': _role_for(login, author, staff),
                        'file': c.get('path') or c.get('file'),
                        'line': c.get('line'),
                        'created_at': c.get('created_at'),
                        'url': c.get('html_url'),
                    })
            else:
                warnings.append(str(data.get('error', '行内评论响应格式异常'))
                                if isinstance(data, dict) else '行内评论响应格式异常')
        thread = sorted(
            comments + inline,
            key=lambda x: x.get('created_at') or '',
        )
        out.append({
            'kind': kind,
            'number': number,
            'title': item.get('title'),
            'url': item.get('html_url'),
            'author': author,
            'staff': sorted(staff),
            'state': item.get('state') or item.get('issue_state'),
            'thread': thread,
            'reviewer_turns': sum(1 for t in thread if t.get('role') == 'reviewer'),
            'author_turns': sum(1 for t in thread if t.get('role') == 'author'),
            'warnings': warnings,
        })
        time.sleep(0.2)
    return out


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def collect_repo(fetcher: ContextFetcher, community_id: str, repo_cfg: Dict,
                 pages: int, dialog_limit: int) -> Dict[str, Any]:
    owner = repo_cfg['owner']
    repo = repo_cfg['repo']
    collect = set(repo_cfg.get('collect') or ['issues', 'pulls'])
    if collect == {'dialogs'}:
        collect.update(('issues', 'pulls'))
    summary: Dict[str, Any] = {'owner': owner, 'repo': repo, 'files': {}, 'warnings': []}
    prefix = f'gitcode_{community_id}_{owner}_{repo}'

    issues: List[Dict] = []
    prs: List[Dict] = []

    if 'issues' in collect:
        issues = fetch_list(fetcher, f'/repos/{owner}/{repo}/issues', pages=pages)
        # Drop PR-shaped issues when API embeds pull_request
        real_issues = [i for i in issues if 'pull_request' not in i]
        path = RAW_DIR / f'{prefix}_issues.json'
        write_json(path, real_issues)
        summary['files']['issues'] = str(path.relative_to(PROJECT_ROOT))
        summary['issues'] = len(real_issues)
        time.sleep(0.3)

    if 'pulls' in collect or 'ci' in collect:
        prs = fetch_list(fetcher, f'/repos/{owner}/{repo}/pulls', pages=pages)
        path = RAW_DIR / f'{prefix}_prs.json'
        write_json(path, prs)
        summary['files']['prs'] = str(path.relative_to(PROJECT_ROOT))
        summary['prs'] = len(prs)
        time.sleep(0.3)

    if 'ci' in collect and prs:
        ci_rows = []
        for pr in prs[:dialog_limit]:
            ci_rows.append(collect_check_runs(fetcher, owner, repo, pr))
            time.sleep(0.2)
        path = CI_DIR / f'{prefix}_ci.json'
        errors = [w for row in ci_rows if not row['ok'] for w in row['warnings']]
        if errors:
            summary['warnings'].extend(errors)
        else:
            write_json(path, ci_rows)
            summary['files']['ci'] = str(path.relative_to(PROJECT_ROOT))
        summary['ci'] = len(ci_rows)

    if 'dialogs' in collect:
        dialogs = []
        if prs:
            dialogs.extend(collect_dialogs(fetcher, owner, repo, 'pull', prs, dialog_limit))
        if issues:
            real_issues = [i for i in issues if 'pull_request' not in i]
            dialogs.extend(collect_dialogs(
                fetcher, owner, repo, 'issue', real_issues, dialog_limit))
        path = DIALOG_DIR / f'{prefix}_dialogs.json'
        errors = [w for row in dialogs for w in row['warnings']]
        if errors:
            summary['warnings'].extend(errors)
        else:
            write_json(path, dialogs)
            summary['files']['dialogs'] = str(path.relative_to(PROJECT_ROOT))
        summary['dialogs'] = len(dialogs)

    summary['ok'] = not summary['warnings']
    return summary


def collect_community(community_id: str, *, pages: int = 2, dialog_limit: int = 20,
                      token: Optional[str] = None) -> Dict[str, Any]:
    cfg = load_community(community_id)
    if pages < 1 or dialog_limit < 0:
        raise ValueError('pages 必须大于 0，dialog_limit 不得为负数')
    token = token or os.getenv('GITCODE_TOKEN')
    result: Dict[str, Any] = {
        'community': community_id,
        'name': cfg.get('name'),
        'ok': False,
        'repos': [],
        'error': None,
    }
    if not token:
        result['error'] = '缺少 GITCODE_TOKEN，未采集。不会写入假数据。'
        empty_note = {
            'community': community_id,
            'error': result['error'],
            'items': [],
        }
        note_path = RAW_DIR / f'gitcode_{community_id}_collect_error.json'
        write_json(note_path, empty_note)
        result['note'] = str(note_path.relative_to(PROJECT_ROOT))
        return result

    fetcher = ContextFetcher(gitcode_token=token)
    for repo_cfg in cfg.get('repos') or []:
        try:
            repo_result = collect_repo(fetcher, community_id, repo_cfg, pages, dialog_limit)
        except (OSError, ValueError, RuntimeError) as exc:
            repo_result = {'owner': repo_cfg['owner'], 'repo': repo_cfg['repo'],
                           'ok': False, 'error': str(exc)}
        result['repos'].append(repo_result)
    result['ok'] = all(repo['ok'] for repo in result['repos'])
    if not result['ok']:
        result['error'] = '部分仓库采集失败或不完整，已有对应数据文件未被失败响应覆盖。'
    summary_path = PROJECT_ROOT / 'data' / 'reports' / f'{community_id}_collect_summary.json'
    write_json(summary_path, result)
    result['summary'] = str(summary_path.relative_to(PROJECT_ROOT))
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Collect GitCode community data')
    parser.add_argument('--community', default='opengauss',
                        help='社区 id（对应 data/communities/<id>.json）')
    parser.add_argument('--pages', type=int, default=2)
    parser.add_argument('--dialog-limit', type=int, default=20)
    args = parser.parse_args(argv)
    try:
        result = collect_community(
            args.community, pages=args.pages, dialog_limit=args.dialog_limit)
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
