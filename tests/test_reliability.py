"""Regression tests for review reliability: diff scope, model JSON validation,
failure status and truncation coverage."""
import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import ascend_cli
from scripts.conversation_agent import ConversationAgent
from scripts.knowledge_search import KnowledgeSearch, PROJECT_ROOT
from scripts.repo_context import format_repo_prompt
from scripts.smart_reviewer import SmartReviewer, added_lines, validate_ai_result
from scripts import toml_compat as tomllib
from scripts.specialist_context import detect_scenario, load_specialist_context

DELETED_CUDA = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1,2 +1,2 @@ def migrate_to_npu(tensor):
 def migrate_to_npu(tensor):
-    return tensor.cuda()
+    return tensor.npu()
"""
ADDED_CUDA = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1,2 +1,3 @@
 def migrate_to_npu(tensor):
     x = 1
+    return tensor.cuda()
"""
CONTEXT_CUDA = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1,3 +1,3 @@
 def migrate_to_npu(tensor):
     y = tensor.cuda()
-    x = 1
+    x = 2
"""


class Silent(KnowledgeSearch):
    """Knowledge index that never reads the real data directory."""
    def __init__(self):
        super().__init__(Path(tempfile.gettempdir()) / 'reviewagent-no-such-dir')


def offline_reviewer():
    with patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')):
        return SmartReviewer(verbose=False, knowledge_search=Silent())


def ai_reviewer(response):
    with patch('scripts.smart_reviewer.get_ai_client') as factory:
        factory.return_value.chat.return_value = response
        reviewer = SmartReviewer(verbose=False, knowledge_search=Silent())
    return reviewer


def repo_meta(diff, **extra):
    return {'source': 'repository', 'repository': {'diff': diff, 'changed_files': ['m.py'], 'root': '.',
                                                   'branch': 'x', 'staged': False, 'status': '',
                                                   'diff_truncated': False, **extra}}


class DiffScopeTests(unittest.TestCase):
    def issues_for(self, diff):
        meta = repo_meta(diff)
        report = offline_reviewer().review(ascend_cli_prompt(meta), metadata=meta, verbose=False)
        return report['review_result']['issues']

    def test_deleted_cuda_is_not_reported(self):
        self.assertEqual([i for i in self.issues_for(DELETED_CUDA) if 'cuda' in i['type']], [])

    def test_added_cuda_is_reported_with_location(self):
        hits = [i for i in self.issues_for(ADDED_CUDA) if i['type'] == 'cuda call']
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['location'], 'm.py:3')

    def test_context_cuda_is_not_reported(self):
        self.assertEqual([i for i in self.issues_for(CONTEXT_CUDA) if 'cuda' in i['type']], [])

    def test_added_lines_numbers_and_headers(self):
        diff = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -5,3 +5,4 @@\n ctx\n-gone\n+new1\n"
                "+++ looks like header\n tail\n@@ -20 +21,2 @@\n+late\n \\ No newline at end of file\n")
        self.assertEqual(added_lines(diff), [('a.py', 6, 'new1'), ('a.py', 7, '++ looks like header'),
                                            ('a.py', 21, 'late')])

    def test_pasted_code_without_diff_is_still_scanned_whole(self):
        report = offline_reviewer().review('torch npu model\nx = y.cuda()\n', verbose=False)
        self.assertTrue(any(i['type'] == 'cuda call' for i in report['review_result']['issues']))


def ascend_cli_prompt(meta):
    return format_repo_prompt(meta['repository'])


class ModelJsonValidationTests(unittest.TestCase):
    def review(self, response):
        return ai_reviewer(response).review('x = 1', verbose=False)['review_result']

    def test_invalid_shapes_are_errors_not_zero_issues(self):
        bad = ['{}', '[]', '{"issues": "invalid-type"}', '{"issues": ["text"]}',
               '{"issues": [{"severity": "urgent", "title": "t"}]}',
               '{"issues": [{"severity": "high"}]}',
               '{"issues": [], "recommendation": "ship-it"}',
               '{"issues": [], "positive_points": "good"}', 'not json']
        for response in bad:
            with self.subTest(response=response):
                result = self.review(response)
                self.assertIn('error', result)
                self.assertNotIn('issues', result)

    def test_valid_results_pass_and_are_normalized(self):
        result = self.review('{"issues": [], "recommendation": "Comment"}')
        self.assertEqual((result['issues'], result['recommendation']), ([], 'comment'))
        result = self.review('```json\n{"issues": [{"severity": "HIGH", "title": "t"}]}\n```')
        self.assertEqual(result['issues'][0]['severity'], 'high')
        validate_ai_result({'issues': [{'severity': 'low', 'description': 'd'}]})

    def test_error_report_prints_without_crashing_and_cli_exits_nonzero(self):
        reviewer = ai_reviewer('{"issues": "invalid-type"}')
        report = reviewer.review('x', verbose=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            reviewer.print_report(report)
        self.assertIn('审查失败', out.getvalue())
        with temp_repo(DELETED_CUDA) as root, patch('scripts.smart_reviewer.get_ai_client') as factory:
            factory.return_value.chat.return_value = '{}'
            code, _, _ = run_cli_review(root)
        self.assertEqual(code, 1)


class temp_repo(contextlib.ContextDecorator):
    """A git repo whose working tree differs from HEAD by `lines` extra lines (or DELETED_CUDA fixture)."""
    def __init__(self, fixture=None, extra_lines=0):
        self.extra_lines, self.fixture = extra_lines, fixture

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        def git(*a):
            subprocess.run(['git', '-c', 'user.name=T', '-c', 'user.email=t@e.x', *a], cwd=root,
                           check=True, capture_output=True)
        git('init')
        (root / 'm.py').write_text('def migrate_to_npu(t):\n    return t.cuda()\n', encoding='utf-8')
        git('add', 'm.py')
        git('commit', '-m', 'base')
        body = 'def migrate_to_npu(t):\n    return t.npu()\n' + ''.join(
            f'# filler line number {i} for npu\n' for i in range(self.extra_lines))
        if self.extra_lines:
            body += 'tail = t.cuda()\n'  # new CUDA call hidden beyond the truncation point
        (root / 'm.py').write_text(body, encoding='utf-8')
        return root

    def __exit__(self, *exc):
        self.tmp.cleanup()
        return False


def run_cli_review(root, **overrides):
    params = dict(staged=False, config='unused.json', offline=False, output=None, json=True,
                  max_diff=12000, require_full=False, scenario=None, require_scenario=False)
    params.update(overrides)
    args = argparse.Namespace(**params)
    cwd, out, err = os.getcwd(), io.StringIO(), io.StringIO()
    os.chdir(root)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ascend_cli.review(args)
    finally:
        os.chdir(cwd)
    return code, out.getvalue(), err.getvalue()


class TruncationTests(unittest.TestCase):
    def test_prompt_and_report_state_truncation(self):
        with temp_repo(extra_lines=80) as root, patch('scripts.smart_reviewer.get_ai_client') as factory:
            factory.return_value.chat.return_value = '{"issues": [], "recommendation": "approve"}'
            code, out, err = run_cli_review(root, max_diff=600)
            prompt = factory.return_value.chat.call_args.kwargs['prompt']
        self.assertEqual(code, 0)
        self.assertIn('审查范围警告', prompt)
        self.assertIn('diff 已被截断', prompt)
        result = json.loads(out)['review_result']
        self.assertEqual(result['coverage'], 'partial')
        self.assertEqual(result['recommendation'], 'comment')
        self.assertIn('截断', result['coverage_note'])
        self.assertIn('coverage=partial', err)

    def test_full_diff_has_no_warning_and_full_coverage(self):
        with temp_repo(DELETED_CUDA) as root, patch('scripts.smart_reviewer.get_ai_client') as factory:
            factory.return_value.chat.return_value = '{"issues": []}'
            code, out, _ = run_cli_review(root)
            prompt = factory.return_value.chat.call_args.kwargs['prompt']
        self.assertEqual(code, 0)
        self.assertNotIn('审查范围警告', prompt)
        self.assertEqual(json.loads(out)['review_result']['coverage'], 'full')

    def test_require_full_fails_without_calling_model(self):
        with temp_repo(extra_lines=80) as root, patch('scripts.smart_reviewer.get_ai_client') as factory:
            code, out, err = run_cli_review(root, max_diff=600, require_full=True)
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('--max-diff', err)
        factory.return_value.chat.assert_not_called()

    def test_offline_deletion_only_diff_has_no_cuda_issue(self):
        with temp_repo(DELETED_CUDA) as root, \
                patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')):
            code, out, _ = run_cli_review(root, offline=True)
        issues = json.loads(out)['review_result']['issues']
        self.assertEqual(code, 0)
        self.assertEqual([i for i in issues if 'cuda' in i['type']], [])


class ChatStatusTests(unittest.TestCase):
    class Knowledge:
        warnings = []
        def search(self, query, limit=3):
            return []

    def agent(self, reply):
        client = MagicMock()
        client.chat_with_history.return_value = reply
        client.chat.side_effect = RuntimeError('planner unavailable')
        return ConversationAgent(client, self.Knowledge(), MagicMock(), network='off')

    def test_failures_clear_last_ok_and_success_restores_it(self):
        agent = self.agent('Error: HTTP 401')
        self.assertIn('AI 调用失败', agent.answer('hello'))
        self.assertFalse(agent.last_ok)
        agent.client.chat_with_history.return_value = 'fine'
        self.assertEqual(agent.answer('hello'), 'fine')
        self.assertTrue(agent.last_ok)
        agent.client.chat_with_history.side_effect = RuntimeError('boom')
        agent.answer('hello')
        self.assertFalse(agent.last_ok)

    def test_one_shot_chat_exit_code_follows_status(self):
        for reply, expected in (('Error: HTTP 401', 1), ('', 1), ('   ', 1), ('analysis done', 0)):
            with self.subTest(reply=reply), \
                    patch('ascend_cli.get_ai_client') as factory, \
                    patch('ascend_cli.ConversationAgent', lambda client, **kw: self.agent(reply)), \
                    contextlib.redirect_stdout(io.StringIO()):
                factory.return_value = MagicMock()
                args = argparse.Namespace(config='x', message='hello', multiline=False, network='off')
                self.assertEqual(ascend_cli.chat(args), expected)


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class PythonLauncherTests(unittest.TestCase):
    SCRIPT = """
const {findPython} = require(process.argv[1]);
const fake = (available) => (c) => available.includes(c.command) ? 'Python 3.13.7' : null;
const out = {};
out.pyOnly = findPython('win32', fake(['py']));
out.pythonFirst = findPython('win32', fake(['python', 'py']));
out.posix = findPython('linux', fake(['python']));
out.oldPython = findPython('win32', c => c.command === 'python' ? 'Python 2.7.18' : 'Python 3.13.7');
out.oldPython3 = findPython('linux', c => c.command === 'python3' ? 'Python 3.6.9' : 'Python 3.13.7');
try { findPython('win32', fake([])); } catch (e) { out.none = e.message; }
console.log(JSON.stringify(out));
"""

    def test_windows_falls_back_to_py_launcher_with_arguments(self):
        result = subprocess.run(['node', '-e', self.SCRIPT, str(PROJECT_ROOT / 'bin/python-launcher.js')],
                                capture_output=True, text=True, encoding='utf-8', check=True)
        out = json.loads(result.stdout)
        self.assertEqual((out['pyOnly']['command'], out['pyOnly']['args']), ('py', ['-3']))
        self.assertEqual((out['pythonFirst']['command'], out['pythonFirst']['args']), ('python', []))
        self.assertEqual(out['posix']['command'], 'python')
        self.assertEqual(out['oldPython']['command'], 'py')
        self.assertEqual(out['oldPython3']['command'], 'python')
        self.assertIn('py -3', out['none'])

    def test_wrapper_reports_version_through_real_interpreter(self):
        result = subprocess.run(['node', str(PROJECT_ROOT / 'bin/review.js'), '--version'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ReviewAgent', result.stdout)


class MissingTrainingDataTests(unittest.TestCase):
    def test_missing_loader_files_are_reported_not_silent(self):
        with tempfile.TemporaryDirectory() as empty, patch('scripts.smart_reviewer.PROJECT_ROOT', Path(empty)):
            reviewer = offline_reviewer()
            report = reviewer.review('x = 1', verbose=False)
        self.assertEqual((reviewer.ci_rules, reviewer.review_patterns, reviewer.issue_knowledge), ({}, {}, {}))
        warnings = report['knowledge_retrieval']['warnings']
        for label in ('CI 规则', 'review 模式', 'issue 知识库'):
            self.assertTrue(any(label in w for w in warnings), label)


class ConfigFileTests(unittest.TestCase):
    def test_codex_agent_toml_files_parse(self):
        for path in sorted((PROJECT_ROOT / '.codex/agents').glob('*.toml')):
            with self.subTest(file=path.name):
                data = tomllib.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(data['name'], path.stem)
                self.assertTrue(data['description'])
                self.assertIn('##', data['developer_instructions'])


class SpecialistRoutingTests(unittest.TestCase):
    def test_explicit_and_auto_and_ambiguous(self):
        op = detect_scenario('__simt_vf__ tiling', paths=['sparse/op_kernel/x.cpp'])
        self.assertEqual((op.scenario, op.status), ('operator', 'ready'))
        inf = detect_scenario('import torch_npu\nx = t.npu()', paths=['serve/infer.py'])
        self.assertEqual((inf.scenario, inf.status), ('inference', 'ready'))
        mixed = detect_scenario('__gm__ and torch_npu', paths=['op_kernel/a.cpp', 'vllm/x.py'])
        self.assertEqual(mixed.status, 'needs_context')
        none = detect_scenario('hello world', paths=['readme.md'])
        self.assertEqual(none.status, 'needs_context')
        explicit = detect_scenario('hello', paths=[], explicit='operator')
        self.assertEqual(explicit.scenario, 'operator')

    def test_load_operator_context_includes_agent(self):
        loaded = load_specialist_context('operator')
        self.assertEqual(loaded.status, 'ready')
        self.assertIn('CANN AscendC Operator Checker', loaded.text)
        self.assertTrue(any(f.get('role') == 'agent' for f in loaded.files))

    def test_cli_needs_context_exit_code(self):
        with temp_repo(DELETED_CUDA) as root, \
                patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')):
            (root / 'm.py').write_text('x = 1\n', encoding='utf-8')
            code, out, _ = run_cli_review(root, offline=True, scenario=None, require_scenario=True)
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertTrue(payload.get('needs_context'))

    def test_cli_ambiguous_defaults_to_general_review(self):
        with temp_repo(DELETED_CUDA) as root, \
                patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')):
            (root / 'm.py').write_text('x = 1\n', encoding='utf-8')
            code, out, _ = run_cli_review(root, offline=True, scenario=None)
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['specialist_context']['status'], 'skipped')

    def test_cli_explicit_scenario_offline_includes_specialist_meta(self):
        with temp_repo(DELETED_CUDA) as root, \
                patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')):
            code, out, _ = run_cli_review(root, offline=True, scenario='operator')
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['specialist_context']['scenario'], 'operator')
        self.assertEqual(report['specialist_context']['status'], 'ready')
        self.assertTrue(report['specialist_context']['text_loaded'])


if __name__ == '__main__':
    unittest.main()
