"""Natural-language work plan: intent, confirm, execute (mocked)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.nl_work_plan import (
    WorkPlan,
    WorkStep,
    build_plan,
    detect_intent,
    execute_plan,
    format_plan,
    handle_nl_work,
    is_cancel,
    is_confirm,
)
from scripts.work_clone import extract_pr_url, parse_pr_url, resolve_clone_parent, workspace_path


class ParseUrlTests(unittest.TestCase):
    def test_github_pull(self):
        meta = parse_pr_url('https://github.com/foo/bar/pull/12')
        self.assertEqual(meta['host'], 'github')
        self.assertEqual(meta['owner'], 'foo')
        self.assertEqual(meta['repo'], 'bar')
        self.assertEqual(meta['number'], 12)

    def test_gitcode_pulls(self):
        meta = parse_pr_url('https://gitcode.com/OpenNoesis/vllm/pulls/6')
        self.assertEqual(meta['host'], 'gitcode')
        self.assertEqual(meta['number'], 6)

    def test_issue_rejected(self):
        self.assertIsNone(parse_pr_url('https://github.com/foo/bar/issues/9'))

    def test_extract_from_sentence(self):
        u = extract_pr_url('帮我拉取 https://gitcode.com/OpenNoesis/vllm/pulls/6 并修改')
        self.assertTrue(u.endswith('/pulls/6'))

    def test_clone_parent_follows_selected_folder(self):
        agent = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            agent.desktop_repository = td
            agent.work_root = Path(r'C:\Users\fake\.reviewagent')
            parent = resolve_clone_parent(agent)
            self.assertEqual(parent, Path(td).resolve())
            meta = {'owner': 'OpenNoesis', 'repo': 'vllm'}
            dest = workspace_path(meta, agent=agent)
            self.assertEqual(dest.parent, Path(td).resolve())
            self.assertEqual(dest.name, 'OpenNoesis_vllm')


class IntentTests(unittest.TestCase):
    def test_clone_fix(self):
        t = '帮我拉取 https://gitcode.com/OpenNoesis/vllm/pulls/6 并按审查意见修改 hf_api'
        self.assertEqual(detect_intent(t), 'clone_fix')

    def test_ship(self):
        self.assertEqual(detect_intent('提交并开 PR，说明修复私有 API'), 'ship')

    def test_clone_only(self):
        self.assertEqual(
            detect_intent('clone https://github.com/a/b/pull/3'),
            'clone',
        )

    def test_analyze_pr_is_review_not_clone(self):
        self.assertEqual(
            detect_intent('https://gitcode.com/OpenNoesis/vllm/pull/6，帮我分析这个PR'),
            'none',
        )
        self.assertEqual(
            detect_intent('https://gitcode.com/OpenNoesis/vllm/pull/6，这个PR的质量如何'),
            'none',
        )

    def test_optimize_pr_is_fix(self):
        self.assertEqual(detect_intent('帮我优化PR'), 'fix')
        self.assertEqual(detect_intent('优化这个PR'), 'fix')

    def test_chitchat(self):
        self.assertEqual(detect_intent('你好'), 'none')
        self.assertEqual(detect_intent('今天天气怎么样'), 'none')

    def test_confirm_cancel(self):
        self.assertTrue(is_confirm('确认'))
        self.assertTrue(is_confirm('yes'))
        self.assertTrue(is_cancel('取消'))
        self.assertFalse(is_confirm('确认一下再看看'))  # too long / not exact


class PlanBuildTests(unittest.TestCase):
    def test_build_clone_fix_steps(self):
        agent = MagicMock()
        agent.contexts = []
        plan = build_plan(
            agent,
            '拉取 https://github.com/a/b/pull/8 并修复',
            intent='clone_fix',
        )
        self.assertIsNotNone(plan)
        kinds = [s.kind for s in plan.steps]
        self.assertEqual(kinds, ['clone_pr', 'propose_and_apply'])
        text = format_plan(plan)
        self.assertIn('确认', text)
        self.assertIn('clone_pr', text)

    def test_clone_without_url(self):
        plan = build_plan(MagicMock(contexts=[]), '帮我拉取仓库并修改', intent='clone_fix')
        self.assertIsNone(plan)

    def test_fix_with_sticky_context_no_url(self):
        agent = MagicMock()
        agent.contexts = [{'url': 'https://gitcode.com/OpenNoesis/vllm/pull/6', 'title': 'PR #6'}]
        plan = build_plan(agent, '帮我优化PR', intent='fix')
        self.assertIsNotNone(plan)
        self.assertEqual([s.kind for s in plan.steps], ['propose_and_apply'])
        self.assertEqual(plan.pr_url, 'https://gitcode.com/OpenNoesis/vllm/pull/6')


class HandleNlTests(unittest.TestCase):
    def test_draft_then_cancel(self):
        agent = MagicMock()
        agent.contexts = []
        agent.pending_work_plan = None
        reply = handle_nl_work(
            agent,
            '拉取 https://github.com/a/b/pull/1 并修改',
        )
        self.assertIn('待确认', reply)
        self.assertIsNotNone(agent.pending_work_plan)
        cancel = handle_nl_work(agent, '取消')
        self.assertIn('已取消', cancel)
        self.assertIsNone(agent.pending_work_plan)

    def test_confirm_without_plan_passthrough(self):
        agent = MagicMock()
        agent.pending_work_plan = None
        self.assertIsNone(handle_nl_work(agent, '确认'))

    def test_optimize_pr_uses_sticky_context(self):
        agent = MagicMock()
        agent.contexts = [{'url': 'https://gitcode.com/OpenNoesis/vllm/pull/6'}]
        agent.pending_work_plan = None
        agent.work_root = Path('.')
        reply = handle_nl_work(agent, '帮我优化PR')
        self.assertIsNotNone(reply)
        self.assertIn('待确认', reply)
        self.assertIn('propose_and_apply', reply)
        self.assertIsNotNone(agent.pending_work_plan)


class ExecutePlanTests(unittest.TestCase):
    def test_stops_if_clone_fails(self):
        agent = MagicMock()
        agent.progress = lambda m: None
        agent.work_root = Path('.')
        plan = WorkPlan(
            intent='clone_fix',
            steps=[
                WorkStep('clone_pr', 'x'),
                WorkStep('propose_and_apply', 'y'),
            ],
            pr_url='https://github.com/a/b/pull/1',
        )
        with patch('scripts.nl_work_plan.clone_or_fetch_pr', return_value={
            'ok': False, 'message': 'boom', 'path': None,
        }):
            out = execute_plan(agent, plan)
        self.assertIn('boom', out)
        self.assertIn('已停止', out)
        agent.propose_fix.assert_not_called()

    def test_clone_then_fix_order(self):
        agent = MagicMock()
        agent.progress = lambda m: None
        agent.work_root = Path('/tmp/ws')
        agent.contexts = [{'url': 'https://github.com/a/b/pull/1'}]
        agent.pending_fix = MagicMock(files=[{'path': 'a.py'}])
        agent.last_ok = True
        agent.propose_fix.return_value = 'preview'
        agent.apply_pending_fix.return_value = 'applied'

        plan = WorkPlan(
            intent='clone_fix',
            steps=[
                WorkStep('clone_pr', 'x'),
                WorkStep('propose_and_apply', 'y'),
            ],
            pr_url='https://github.com/a/b/pull/1',
        )
        with patch('scripts.nl_work_plan.clone_or_fetch_pr', return_value={
            'ok': True, 'message': 'cloned', 'path': '/tmp/ws',
        }) as clone:
            out = execute_plan(agent, plan)
        clone.assert_called_once()
        agent.propose_fix.assert_called_once()
        agent.apply_pending_fix.assert_called_once_with(confirm=True)
        self.assertIn('cloned', out)
        self.assertIn('全部计划步骤已跑完', out)

    def test_ship_commit_push_pr(self):
        agent = MagicMock()
        agent.progress = lambda m: None
        agent.work_root = Path('/tmp/ws')
        agent.last_reply = 'body'
        plan = WorkPlan(
            intent='ship',
            steps=[
                WorkStep('commit', 'c'),
                WorkStep('push', 'p'),
                WorkStep('create_pr', 'pr'),
            ],
            commit_message='fix api',
            host='github',
        )
        with patch('scripts.nl_work_plan.git_work.commit_changes', return_value='已提交: `abc`') as c, \
                patch('scripts.nl_work_plan.git_work.push_branch', return_value='已推送分支 `pr-1` 到 origin。\n\nok') as p, \
                patch('scripts.nl_work_plan.git_work.create_pull_request', return_value='PR 已创建:\nurl') as pr:
            out = execute_plan(agent, plan)
        c.assert_called_once()
        p.assert_called_once()
        pr.assert_called_once()
        self.assertIn('PR 已创建', out)


if __name__ == '__main__':
    unittest.main()
