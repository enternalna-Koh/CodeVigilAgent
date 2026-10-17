"""Run a local repository review from chat (/review)."""

from __future__ import annotations

import json
from typing import Optional, Tuple

from scripts.repo_context import RepoContextError, collect_repo_context, format_repo_prompt
from scripts.smart_reviewer import SmartReviewer
from scripts.specialist_context import resolve_specialist


def run_local_review(
    config_file: Optional[str] = None,
    *,
    staged: bool = False,
    offline: bool = True,
    max_diff: int = 12000,
    scenario: Optional[str] = None,
) -> Tuple[str, dict]:
    """Return (markdown_or_message, report_dict). report may be empty on soft failures."""
    try:
        context = collect_repo_context(staged=staged, max_diff_chars=max_diff)
    except RepoContextError as exc:
        return f'无法收集仓库上下文: {exc}', {}

    if not (context.get('diff') or '').strip():
        tip = '暂存区没有可审查的 diff。' if staged else '没有可审查的已跟踪文件 diff（未跟踪文件不在范围内）。'
        return tip + ' 可先 `git add`，或使用 `/review staged`。', {}

    warn = ''
    if context.get('diff_truncated'):
        warn = (
            f"\n\n> 注意: diff 共 {context.get('diff_total_chars')} 字符，"
            f"已截断到 {max_diff}（coverage=partial）。\n"
        )

    prompt = format_repo_prompt(context)
    paths = context.get('changed_files') or []
    specialist = resolve_specialist(prompt, paths=paths, explicit=scenario)
    if specialist.status == 'ready':
        meta = specialist.as_dict()
        meta['text_loaded'] = bool(specialist.text)
        specialist_text = specialist.text or ''
    else:
        meta = specialist.as_dict()
        meta['status'] = 'skipped'
        meta['text_loaded'] = False
        specialist_text = ''

    reviewer = SmartReviewer(config_file or 'unused.json', verbose=False)
    if offline:
        reviewer.has_ai = False
    report = reviewer.review(
        prompt,
        metadata={'source': 'chat-/review', 'repository': context},
        verbose=False,
        specialist_text=specialist_text,
        specialist_meta=meta,
    )
    result = report.get('review_result') or {}
    md = _format_report(report, staged=staged, offline=offline, warn=warn)
    if result.get('error'):
        md = f"审查出错: {result.get('error')}\n\n" + md
    return md, report


def _format_report(report: dict, *, staged: bool, offline: bool, warn: str) -> str:
    result = report.get('review_result') or {}
    issues = result.get('issues') or []
    lines = [
        '## 本地 Git 审查',
        '',
        f"- 范围: {'staged' if staged else '工作区已跟踪 diff'}",
        f"- 模式: {'offline 规则+案例' if offline else 'AI'}",
        f"- 问题数: {len(issues)}",
    ]
    meta = result.get('specialist_meta') or report.get('specialist_meta') or {}
    if meta:
        lines.append(f"- 专业路由: {meta.get('scenario') or meta.get('status') or '-'}")
    lines.append(warn.rstrip() if warn else '')
    lines.append('')
    if not issues:
        lines.append('未发现规则命中问题（不代表无逻辑缺陷）。')
        summary = result.get('summary') or result.get('recommendation')
        if summary:
            lines.extend(['', str(summary)])
        return '\n'.join(lines).strip() + '\n'

    lines.append('### 问题列表')
    lines.append('')
    for i, issue in enumerate(issues[:20], 1):
        sev = issue.get('severity') or issue.get('level') or 'info'
        title = issue.get('title') or issue.get('message') or issue.get('description') or 'issue'
        loc = issue.get('file') or issue.get('path') or ''
        line_no = issue.get('line')
        loc_s = f" `{loc}`" + (f":{line_no}" if line_no else '') if loc else ''
        lines.append(f"{i}. **[{sev}]** {title}{loc_s}")
        detail = issue.get('description') or issue.get('suggestion') or ''
        if detail and detail != title:
            lines.append(f"   - {_short(detail)}")
    if len(issues) > 20:
        lines.append(f"\n… 另有 {len(issues) - 20} 条未展开。")
    lines.append('')
    lines.append('可用 `/export` 保存；要改代码可继续对话或 `/fix`（需先有 PR/粘贴上下文）。')
    return '\n'.join(lines)


def _short(text: str, n: int = 200) -> str:
    t = (text or '').replace('\n', ' ').strip()
    return t if len(t) <= n else t[: n - 1] + '…'
