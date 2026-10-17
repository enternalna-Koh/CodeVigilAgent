"""Compare multiple active PR/Issue/paste contexts into one markdown report."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


def _clip(text: str, n: int = 160) -> str:
    t = re.sub(r'\s+', ' ', (text or '').strip())
    return t if len(t) <= n else t[: n - 1] + '…'


def _labels(contexts: List[Dict]) -> List[str]:
    labels = []
    for i, ctx in enumerate(contexts, 1):
        kind = (ctx.get('type') or 'item').upper()
        labels.append(f'A{i}:{kind}')
    return labels


def _file_set(ctx: Dict) -> Set[str]:
    files = set()
    for row in ctx.get('files') or []:
        name = row.get('file') or row.get('filename') or row.get('path')
        if name:
            files.add(str(name))
    return files


def _kw_hits(text: str) -> List[str]:
    keys = (
        'hccl', 'npu', 'torch_npu', 'cann', 'acl', '精度', 'perf', 'oom',
        'codecheck', 'tiling', 'vllm', '算子', '910', '报错', 'fail',
    )
    lower = (text or '').lower()
    return [k for k in keys if k.lower() in lower]


def compare_contexts(contexts: List[Dict[str, Any]], max_items: int = 8) -> Dict[str, Any]:
    items = list(contexts or [])[: max(2, min(max_items, 20))]
    if len(items) < 2:
        return {
            'ok': False,
            'message': '对比至少需要 2 个上下文。请一次粘贴多个 GitHub/GitCode 链接后再 /compare。',
            'items': [],
        }

    rows = []
    all_files: List[Set[str]] = []
    for i, ctx in enumerate(items):
        body = ctx.get('body') or ''
        title = ctx.get('title') or '(untitled)'
        files = _file_set(ctx)
        all_files.append(files)
        comments = ctx.get('comments') or []
        reviews = ctx.get('reviews') or []
        rows.append({
            'index': i + 1,
            'type': ctx.get('type') or 'unknown',
            'title': title,
            'url': ctx.get('url') or '',
            'state': ctx.get('state') or '',
            'host': ctx.get('host') or '',
            'body_chars': len(body),
            'files': sorted(files)[:12],
            'file_count': len(files),
            'comments': len(comments),
            'reviews': len(reviews),
            'warnings': list(ctx.get('warnings') or [])[:5],
            'keywords': _kw_hits(title + '\n' + body[:4000]),
            'excerpt': _clip(body, 200),
        })

    shared = set.intersection(*all_files) if all_files and all(all_files) else set()
    # If some have empty file sets (issues), shared across non-empty only
    nonempty = [s for s in all_files if s]
    if len(nonempty) >= 2:
        shared = set.intersection(*nonempty)
    else:
        shared = set()

    unique = []
    for i, files in enumerate(all_files):
        others = set().union(*[f for j, f in enumerate(all_files) if j != i]) if len(all_files) > 1 else set()
        unique.append(sorted(files - others)[:10])

    return {
        'ok': True,
        'count': len(rows),
        'items': rows,
        'shared_files': sorted(shared)[:20],
        'unique_files': unique,
        'keyword_union': sorted({k for r in rows for k in r['keywords']}),
    }


def format_compare_report(result: Dict[str, Any]) -> str:
    if not result.get('ok'):
        return result.get('message') or '无法对比。'

    lines = [
        f"## 多链接对比（{result['count']} 项）",
        '',
        '| # | 类型 | 状态 | 文件 | 评论 | 关键词 | 标题 |',
        '|---|------|------|------|------|--------|------|',
    ]
    for row in result['items']:
        kws = ','.join(row['keywords'][:4]) or '-'
        title = _clip(row['title'], 40).replace('|', '/')
        lines.append(
            f"| {row['index']} | {row['type']} | {row['state'] or '-'} | "
            f"{row['file_count']} | {row['comments']} | {kws} | {title} |"
        )

    lines.extend(['', '### 链接', ''])
    for row in result['items']:
        lines.append(f"{row['index']}. [{row['type']}] {row['title']}")
        if row['url']:
            lines.append(f"   - {row['url']}")
        if row['excerpt']:
            lines.append(f"   - 摘要: {row['excerpt']}")

    shared = result.get('shared_files') or []
    lines.extend(['', '### 共同改动文件', ''])
    if shared:
        for f in shared:
            lines.append(f'- `{f}`')
    else:
        lines.append('- （无，或均为 Issue/粘贴无 patch）')

    lines.extend(['', '### 独有文件', ''])
    for i, uniq in enumerate(result.get('unique_files') or [], 1):
        if uniq:
            lines.append(f'- A{i}: ' + ', '.join(f'`{x}`' for x in uniq[:8]))
        else:
            lines.append(f'- A{i}: （无独有文件）')

    kws = result.get('keyword_union') or []
    lines.extend(['', '### 关键词并集', ''])
    lines.append(', '.join(kws) if kws else '（未命中常用 Infra 关键词）')
    lines.extend([
        '',
        '### 建议',
        '',
        '- 先对齐共同文件上的冲突改法，再分别处理独有路径。',
        '- 需要补丁时对「主」链接继续追问，或 `/fix`（基于当前上下文）。',
        '- `/export` 可带走本报告。',
    ])
    return '\n'.join(lines)
