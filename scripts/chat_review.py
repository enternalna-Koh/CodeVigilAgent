"""Run a local repository review from chat (/review)."""

from __future__ import annotations

from pathlib import Path
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
    path: Optional[Path] = None,
    client=None,
) -> Tuple[str, dict]:
    """Return (markdown_or_message, report_dict). report may be empty on soft failures."""
    try:
        context = collect_repo_context(path=path or Path.cwd(), staged=staged, max_diff_chars=max_diff)
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
    specialist = resolve_specialist(context['diff'], paths=paths, explicit=scenario)
    if specialist.status in ('missing_agent', 'incomplete') or (scenario and specialist.status == 'needs_context'):
        meta = specialist.as_dict()
        meta['text_loaded'] = False
        message = specialist.question or specialist.reason
        return (f"专业审查未完成（{specialist.status}）: {message}\n"
                '请补齐必要规则，或明确 operator|inference 场景后重试。',
                {'needs_context': specialist.status == 'needs_context', 'specialist_context': meta})
    if specialist.status == 'ready':
        meta = specialist.as_dict()
        meta['text_loaded'] = bool(specialist.text)
        specialist_text = specialist.text or ''
    else:
        meta = specialist.as_dict()
        meta['status'] = 'skipped'
        meta['text_loaded'] = False
        specialist_text = ''

    reviewer = SmartReviewer(config_file, verbose=False)
    if client is not None and not offline:
        reviewer.ai_client = client
        reviewer.has_ai = True
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
    report['fallback_reason'] = ('AI 未配置，已回退本地规则'
                                 if not offline and report['engine'] == 'rules' else '')
    md = _format_report(report, staged=staged, warn=warn)
    if result.get('error'):
        md = f"审查出错: {result.get('error')}\n\n" + md
    return md, report


def _format_report(report: dict, *, staged: bool, warn: str) -> str:
    result = report.get('review_result') or {}
    issues = result.get('issues') or []
    lines = [
        '## 本地 Git 审查',
        '',
        f"- 范围: {'staged' if staged else '工作区已跟踪 diff'}",
        f"- 模式: {'AI' if report.get('engine') == 'ai' else 'offline 规则+案例'}",
        f"- 问题数: {len(issues)}",
    ]
    if report.get('fallback_reason'):
        lines.append(f"- 回退: {report['fallback_reason']}")
    meta = report.get('specialist_context') or {}
    if meta:
        lines.append(f"- 专业路由: {meta.get('scenario') or '-'} · {meta.get('status') or '-'}")
        if meta.get('reason'):
            lines.append(f"- 路由说明: {meta['reason']}")
        if meta.get('omitted'):
            lines.append('- 省略规则: ' + '; '.join(meta['omitted']))
        if report.get('engine') == 'rules' and meta.get('text_loaded'):
            lines.append('- 专业规则来源已记录；离线模式未由模型执行专业 Agent 正文')
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
