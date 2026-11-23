"""Natural-language work plans: draft once, confirm once, then execute for real."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts import git_work
from scripts.work_clone import (
    clone_or_fetch_pr,
    ensure_sticky_pr_context,
    extract_pr_url,
    parse_pr_url,
)

CONFIRM_RE = re.compile(
    r'^(确认|好的?|执行|开始执行|同意|可以|行|ok|okay|yes|y|go|do it)[\s!！。.~～]*$',
    re.I,
)
CANCEL_RE = re.compile(
    r'^(取消|不要|算了|停止|放弃|cancel|no|n|stop)[\s!！。.~～]*$',
    re.I,
)

CLONE_HINTS = ('clone', '拉取', '拉下来', '下载到本地', 'checkout', '检出', '克隆', '拉到本地')
# 避免单字「改/修」误伤「分析」等；要明确改码意图
FIX_HINTS = (
    '修复', '修改', '优化代码', '优化pr', '优化这个', '帮我优化', '改代码', '改一下',
    '打补丁', '补丁', 'apply', '/fix', '写盘', '落地', '按审查意见', '按你的建议改',
    '帮我改', '给出补丁', '生成补丁',
)
SHIP_HINTS = ('提交并', 'commit', 'push', '推送', '开pr', '开 pr', 'pull request', '合并请求', '/ship', 'ship')
# 仅审查/提问：绝不能走 clone 计划
REVIEW_ONLY_HINTS = (
    '分析', '质量', '审查', '看看', '怎么样', '如何', '怎么样', '评估', '有没有问题',
    'review', 'analyze', 'quality', '总结', '讲讲', '介绍',
)


@dataclass
class WorkStep:
    kind: str  # clone_pr | propose_and_apply | commit | push | create_pr
    detail: str = ''


@dataclass
class WorkPlan:
    intent: str
    steps: List[WorkStep] = field(default_factory=list)
    pr_url: Optional[str] = None
    commit_message: str = ''
    user_text: str = ''
    host: Optional[str] = None  # github | gitcode


def is_confirm(text: str) -> bool:
    return bool(CONFIRM_RE.match((text or '').strip()))


def is_cancel(text: str) -> bool:
    return bool(CANCEL_RE.match((text or '').strip()))


def detect_intent(text: str) -> str:
    """Return clone | fix | ship | clone_fix | none.

    仅贴 PR 链接 / 「分析这个PR」→ none（走正常审查对话）。
    必须有明确 clone/改码/提交意图才出生产力计划。
    """
    t = (text or '').strip()
    if not t or is_confirm(t) or is_cancel(t):
        return 'none'
    lower = t.lower()
    has_pr = bool(extract_pr_url(t))
    review_only = any(h in lower for h in REVIEW_ONLY_HINTS)
    wants_clone = any(h in lower for h in CLONE_HINTS)
    wants_fix = any(h in lower for h in FIX_HINTS)
    wants_ship = any(h in lower for h in SHIP_HINTS)

    # 「分析/质量如何」优先走审查，即使带了链接
    if review_only and not wants_clone and not wants_fix and not wants_ship:
        return 'none'

    if wants_clone and wants_fix:
        return 'clone_fix'
    if wants_ship and not wants_clone:
        return 'ship'
    # 有 PR + 明确要改码，但没说 clone：若本地可能已有仓，仍出 clone_fix（可复用已有目录）
    if wants_fix and has_pr:
        return 'clone_fix'
    if wants_clone:
        return 'clone'
    if wants_fix:
        return 'fix'
    # 仅有链接、无动词 → 审查，不出计划
    return 'none'


def _guess_commit_message(text: str, agent=None) -> str:
    t = (text or '').strip()
    # strip URL
    t2 = PR_URL_STRIP.sub('', t).strip()
    t2 = re.sub(r'^(帮我|请|麻烦)?(拉取|clone|下载|修复|修改|优化|提交并?)?', '', t2, flags=re.I).strip()
    if len(t2) >= 4:
        return t2[:72]
    return git_work.suggest_commit_message(agent)


PR_URL_STRIP = re.compile(
    r'https://(?:www\.)?(?:github|gitcode)\.com/\S+',
    re.I,
)


def build_plan(agent, text: str, intent: Optional[str] = None) -> Optional[WorkPlan]:
    intent = intent or detect_intent(text)
    if intent == 'none':
        return None
    pr_url = extract_pr_url(text)
    if not pr_url and agent is not None:
        for ctx in getattr(agent, 'contexts', None) or []:
            u = (ctx.get('url') or '') if isinstance(ctx, dict) else ''
            if extract_pr_url(u):
                pr_url = extract_pr_url(u)
                break
    has_context = bool(getattr(agent, 'contexts', None)) if agent is not None else False
    meta = parse_pr_url(pr_url) if pr_url else None
    host = (meta or {}).get('host')
    msg = _guess_commit_message(text, agent)
    steps: List[WorkStep] = []
    if intent in ('clone', 'clone_fix'):
        # 本地已有上下文且目录已是该仓时，不必再强制 clone 步骤
        need_clone = True
        if intent == 'clone_fix' and has_context and pr_url:
            wr = str(getattr(agent, 'work_root', '') or '')
            if meta and meta['repo'].lower() in wr.lower():
                need_clone = False
        if need_clone:
            if not pr_url:
                return None
            steps.append(WorkStep('clone_pr', f'克隆/更新仓库并检出 PR → {pr_url}'))
    if intent in ('fix', 'clone_fix'):
        if intent == 'fix' and not has_context and not pr_url:
            return None
        if intent == 'fix' and not has_context and pr_url:
            # 有链接但还没上下文：先 clone 再改
            steps.insert(0, WorkStep('clone_pr', f'克隆/更新仓库并检出 PR → {pr_url}'))
        steps.append(WorkStep('propose_and_apply', '根据当前 PR/上下文生成补丁并写入工作区'))
    if intent == 'ship':
        steps.append(WorkStep('commit', f'git commit: {msg}'))
        steps.append(WorkStep('push', 'git push -u origin HEAD（不 force）'))
        if host == 'gitcode' or (agent and str(getattr(agent, 'work_root', '')).find('gitcode') >= 0):
            # detect gitcode from remote later in execute; mark create_pr specially
            steps.append(WorkStep('create_pr', '创建 PR（GitHub 用 gh；GitCode 给出网页链接）'))
        else:
            steps.append(WorkStep('create_pr', f'创建 PR：{msg}'))
    if not steps:
        return None
    return WorkPlan(
        intent=intent,
        steps=steps,
        pr_url=pr_url,
        commit_message=msg,
        user_text=text,
        host=host,
    )


def format_plan(plan: WorkPlan, agent=None) -> str:
    lines = [
        '## 待确认的工作计划',
        '',
        '确认后将**真实执行**下列步骤（不会 force / amend）。',
        '回复 **确认** 开始；回复 **取消** 放弃。',
        '',
    ]
    if plan.pr_url:
        lines.append(f'- PR: `{plan.pr_url}`')
    if plan.commit_message and plan.intent == 'ship':
        lines.append(f'- 提交说明: `{plan.commit_message}`')
    if any(s.kind == 'clone_pr' for s in plan.steps):
        from scripts.work_clone import parse_pr_url, resolve_clone_parent, workspace_path
        parent = resolve_clone_parent(agent)
        meta = parse_pr_url(plan.pr_url) if plan.pr_url else None
        dest = workspace_path(meta, agent=agent) if meta else (parent / '<owner>_<repo>')
        lines.append(f'- 克隆父目录（你选的文件夹）: `{parent}`')
        lines.append(f'- 将克隆到: `{dest}`')
    lines.append('')
    for i, step in enumerate(plan.steps, 1):
        lines.append(f'{i}. **{step.kind}** — {step.detail}')
    lines.append('')
    lines.append('> 斜杠命令 `/fix` `/apply` `/ship` 仍可用。')
    return '\n'.join(lines)


def _remote_host(cwd: Optional[str]) -> Optional[str]:
    r = git_work.run_git(['remote', 'get-url', 'origin'], cwd=cwd)
    if not r['ok']:
        return None
    url = (r['out'] or '').lower()
    if 'gitcode.com' in url:
        return 'gitcode'
    if 'github.com' in url:
        return 'github'
    return None


def execute_plan(agent, plan: WorkPlan, progress=None) -> str:
    """Run all steps; stop on first hard failure. Never pretends success."""
    progress = progress or getattr(agent, 'progress', None) or (lambda m: None)
    logs: List[str] = ['## 执行结果', '']
    cwd = str(getattr(agent, 'work_root', None) or Path.cwd())

    for i, step in enumerate(plan.steps, 1):
        progress(f'执行计划 {i}/{len(plan.steps)} · {step.kind}')
        if step.kind == 'clone_pr':
            url = plan.pr_url or ''
            result = clone_or_fetch_pr(url, agent=agent)
            logs.append(f'### {i}. clone_pr')
            logs.append(result.get('message') or '')
            logs.append('')
            if not result.get('ok'):
                logs.append('**已停止**：clone/拉 PR 失败，后续步骤未执行。')
                return '\n'.join(logs)
            cwd = result.get('path') or cwd
            continue

        if step.kind == 'propose_and_apply':
            logs.append(f'### {i}. propose_and_apply')
            if not getattr(agent, 'contexts', None):
                logs.append('没有 PR/Issue 上下文，无法生成补丁。请先贴链接或完成 clone。')
                logs.append('**已停止**。')
                return '\n'.join(logs)
            preview = agent.propose_fix()
            logs.append(preview)
            if not getattr(agent, 'pending_fix', None) or not agent.pending_fix.files:
                logs.append('**已停止**：未得到有效补丁。')
                return '\n'.join(logs)
            applied = agent.apply_pending_fix(confirm=True)
            logs.append(applied)
            logs.append('')
            if not getattr(agent, 'last_ok', True):
                logs.append('**已停止**：写盘失败。')
                return '\n'.join(logs)
            continue

        if step.kind == 'commit':
            logs.append(f'### {i}. commit')
            out = git_work.commit_changes(plan.commit_message, cwd=cwd)
            logs.append(out)
            logs.append('')
            if not out.startswith('已提交: '):
                logs.append('**已停止**：提交失败，未 push / 开 PR。')
                return '\n'.join(logs)
            continue

        if step.kind == 'push':
            logs.append(f'### {i}. push')
            out = git_work.push_branch(cwd=cwd)
            logs.append(out)
            logs.append('')
            if not out.startswith('已推送分支 '):
                logs.append('**已停止**：推送失败，未开 PR。')
                return '\n'.join(logs)
            continue

        if step.kind == 'create_pr':
            logs.append(f'### {i}. create_pr')
            host = plan.host or _remote_host(cwd)
            body = (getattr(agent, 'last_reply', None) or '')[:4000]
            if host == 'gitcode':
                meta = parse_pr_url(plan.pr_url) if plan.pr_url else None
                # After push of a feature branch, suggest opening MR on GitCode
                branch = (git_work.run_git(['branch', '--show-current'], cwd=cwd)['out'] or '').strip()
                if meta:
                    web = (
                        f"https://gitcode.com/{meta['owner']}/{meta['repo']}/pulls/new"
                    )
                else:
                    web = '（请在 GitCode 网页从当前分支新建合并请求）'
                logs.append(
                    f'GitCode 无 `gh` 等价一键开 PR。分支 `{branch}` 已推送的话，请打开：\n{web}\n'
                    f'标题建议：`{plan.commit_message}`'
                )
            else:
                out = git_work.create_pull_request(
                    plan.commit_message, body=body, cwd=cwd, draft=False)
                logs.append(out)
            logs.append('')
            continue

        logs.append(f'### {i}. 未知步骤 `{step.kind}` — 已跳过')
        logs.append('')

    logs.append('全部计划步骤已跑完。')
    return '\n'.join(logs)


def handle_nl_work(agent, text: str) -> Optional[str]:
    """Intercept confirm / cancel / new work intent. Return reply or None to fall through."""
    text = (text or '').strip()
    if not text:
        return None

    pending = getattr(agent, 'pending_work_plan', None)

    if is_cancel(text):
        if pending:
            agent.pending_work_plan = None
            return '已取消待执行计划。'
        return None

    if is_confirm(text):
        if not pending:
            return None  # not our concern
        agent.pending_work_plan = None
        try:
            return execute_plan(agent, pending)
        except Exception as exc:
            return f'执行计划时异常：{exc}'

    # Recover PR context from local checkout before drafting plans
    ensure_sticky_pr_context(agent)

    intent = detect_intent(text)
    if intent == 'none':
        return None

    plan = build_plan(agent, text, intent=intent)
    if plan is None:
        if intent in ('clone', 'clone_fix'):
            return '需要带 **PR 链接**（GitHub `/pull/数字` 或 GitCode `/pulls/数字`）才能制定拉取计划。'
        if intent == 'fix':
            return (
                '已识别「优化/改代码」意图，但当前没有可用的 PR 上下文。\n'
                '请先贴 PR 链接，或确认本地已 clone 到选中目录后再说「帮我优化PR」。'
            )
        return None
    agent.pending_work_plan = plan
    return format_plan(plan, agent=agent)
