"""Regression checks for the v1.6.2 update; isolated homes and fake models only."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import ascend_cli
from scripts.chat_review import _format_report, run_local_review
from scripts.conversation_agent import ConversationAgent
from scripts.patch_fix import FileEdit, ProposedFix
from scripts.session_store import apply_to_agent, load_session, save_session, serialize_agent
from scripts.specialist_context import SpecialistLoad
from test_reliability import ADDED_CUDA, Silent, repo_meta, temp_repo


def agent():
    return ConversationAgent(MagicMock(), MagicMock(), MagicMock())


class SessionRegressionTests(unittest.TestCase):
    def test_save_alias_preserves_cwd_file_and_resumes_json_with_pending_fix(self):
        current = agent()
        current.pending_fix = ProposedFix(files=[FileEdit('a.txt', 'create', replace='patch')])
        current.history = [{'role': 'user', 'content': 'question'}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'REVIEWAGENT_HOME': tmp}):
            target = Path(tmp) / 'LICENSE'
            target.write_text('MIT original', encoding='utf-8')
            previous = Path.cwd()
            try:
                os.chdir(tmp)
                current.work_root = Path(tmp)
                with redirect_stdout(io.StringIO()) as output:
                    ascend_cli.handle_chat_slash('/save LICENSE', current)
                self.assertEqual(target.read_text(encoding='utf-8'), 'MIT original')
                self.assertIn('会话已保存', output.getvalue())
                saved = load_session('LICENSE')
                self.assertEqual(saved['pending_fix']['files'][0]['path'], 'a.txt')
                other = agent()
                with redirect_stdout(io.StringIO()) as output:
                    ascend_cli.handle_chat_slash('/resume LICENSE', other)
                self.assertEqual(other.history, current.history)
                self.assertEqual(other.work_root, Path(tmp).resolve())
                self.assertIsNone(other.pending_fix)
                self.assertIn('原待确认补丁未自动恢复', output.getvalue())
            finally:
                os.chdir(previous)

    def test_resume_restores_original_root_before_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'A', Path(tmp) / 'B'
            a.mkdir(); b.mkdir()
            for root in (a, b):
                (root / 'same.txt').write_text('before', encoding='utf-8')
            first, other = agent(), agent()
            first.work_root = a
            other.work_root = b
            apply_to_agent(other, serialize_agent(first))
            other.pending_fix = ProposedFix(files=[FileEdit('same.txt', 'replace', 'before', 'after')])
            other.apply_pending_fix(confirm=True)
            self.assertEqual((a / 'same.txt').read_text(encoding='utf-8'), 'after')
            self.assertEqual((b / 'same.txt').read_text(encoding='utf-8'), 'before')

    def test_invalid_session_is_rejected_before_mutation(self):
        current = agent()
        current.history = [{'role': 'user', 'content': 'keep'}]
        original = serialize_agent(current)
        for changes in ({'work_root': ''}, {'work_root': 'relative'},
                        {'work_root': str(Path.cwd() / 'missing-session-root')},
                        {'work_root': str(Path(__file__).resolve())},
                        {'history': 'bad'}, {'contexts': [23]}, {'chat_mode': 'bad'}):
            with self.subTest(changes=changes):
                with self.assertRaises((ValueError, OSError)):
                    apply_to_agent(current, dict(original, **changes))
                self.assertEqual(serialize_agent(current)['history'], original['history'])
                self.assertEqual(current.work_root, Path(original['work_root']))
                self.assertEqual(current.chat_mode, original['chat_mode'])

    def test_autosave_with_patch_and_failure_visibility(self):
        current = agent()
        current.pending_fix = ProposedFix(files=[FileEdit('a.txt', 'create', replace='patch')])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'REVIEWAGENT_HOME': tmp}):
            with redirect_stdout(io.StringIO()) as output:
                ascend_cli._autosave_session(current)
            self.assertIn('已自动保存', output.getvalue())
            self.assertEqual(load_session()['pending_fix']['files'][0]['replace'], 'patch')
        with patch('ascend_cli.save_session', side_effect=OSError('disk full')):
            with redirect_stdout(io.StringIO()) as output:
                ascend_cli._autosave_session(current)
            self.assertIn('自动保存失败', output.getvalue())
            self.assertIn('disk full', output.getvalue())

    def test_quick_unnamed_saves_have_distinct_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'REVIEWAGENT_HOME': tmp}):
            self.assertNotEqual(save_session(agent()), save_session(agent()))


class ChatReviewRegressionTests(unittest.TestCase):
    def local_review(self, context, **kwargs):
        with patch('scripts.chat_review.collect_repo_context', return_value=context), \
                patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')), \
                patch('scripts.smart_reviewer.KnowledgeSearch', Silent):
            return run_local_review(**kwargs)

    def test_missing_ai_shows_rule_fallback_and_real_metadata(self):
        text, report = self.local_review(repo_meta(ADDED_CUDA)['repository'], offline=False)
        self.assertEqual(report['engine'], 'rules')
        self.assertIn('offline 规则+案例', text)
        self.assertIn('回退', text)
        self.assertIn('专业路由: - · skipped', text)

    def test_incomplete_or_missing_specialist_blocks_model(self):
        context = repo_meta(ADDED_CUDA)['repository']
        for status in ('missing_agent', 'incomplete', 'needs_context'):
            with self.subTest(status=status), \
                    patch('scripts.chat_review.collect_repo_context', return_value=context), \
                    patch('scripts.chat_review.resolve_specialist', return_value=SpecialistLoad(
                        scenario='operator', status=status, reason='required rules unavailable')), \
                    patch('scripts.chat_review.SmartReviewer') as reviewer:
                text, report = run_local_review(offline=False, scenario='operator')
                self.assertEqual(report['specialist_context']['status'], status)
                self.assertIn('专业审查未完成', text)
                self.assertNotIn('review_result', report)
                reviewer.assert_not_called()

    def test_route_uses_diff_not_branch_or_removed_code(self):
        diff = ('diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n'
                '@@ -1 +1 @@\n-import torch_npu\n+value = 1\n')
        context = repo_meta(diff)['repository']
        context.update(root='/torch_npu/project', branch='tiling')
        _, report = self.local_review(context)
        self.assertEqual(report['specialist_context']['status'], 'skipped')
        self.assertIsNone(report['specialist_context']['scenario'])

    def test_truncation_cannot_approve_and_source_is_visible(self):
        context = repo_meta(ADDED_CUDA, diff_truncated=True, diff_total_chars=90000)['repository']
        text, report = self.local_review(context, scenario='operator')
        self.assertEqual(report['review_result']['coverage'], 'partial')
        self.assertNotEqual(report['review_result'].get('recommendation'), 'approve')
        self.assertIn('coverage=partial', text)
        self.assertIn('operator · ready', text)
        self.assertIn('未由模型执行', text)

    def test_active_client_is_used_and_errors_are_not_success(self):
        client = MagicMock()
        client.chat.return_value = 'Error: unavailable'
        text, report = self.local_review(repo_meta(ADDED_CUDA)['repository'], offline=False, client=client)
        self.assertEqual(report['engine'], 'ai')
        self.assertIn('审查出错', text)
        self.assertIn('error', report['review_result'])
        self.assertFalse(report['fallback_reason'])
        client.chat.assert_called_once()

    def test_readable_report_includes_omissions(self):
        text = _format_report({'engine': 'rules', 'review_result': {}, 'specialist_context': {
            'scenario': 'operator', 'status': 'ready', 'omitted': ['optional examples']}},
            staged=False, warn='')
        self.assertIn('optional examples', text)

    def test_real_git_review_uses_requested_root(self):
        with temp_repo(extra_lines=2) as root, \
                patch('scripts.smart_reviewer.get_ai_client', side_effect=ValueError('no ai')), \
                patch('scripts.smart_reviewer.KnowledgeSearch', Silent):
            _, report = run_local_review(path=root)
            self.assertEqual(Path(report['metadata']['repository']['root']), root)
            self.assertEqual(report['engine'], 'rules')

    def test_slash_review_and_status_use_active_session(self):
        current = agent()
        current.model_config = {'provider': 'glm', 'model': 'active-model'}
        with patch('ascend_cli.run_local_review', return_value=('report', {})) as review, \
                patch('ascend_cli.begin_think'), patch('ascend_cli.end_think'), \
                patch('ascend_cli._print_agent_reply'), redirect_stdout(io.StringIO()):
            ascend_cli.handle_chat_slash('/review online', current, config_file='explicit.json')
        review.assert_called_once_with('explicit.json', path=current.work_root, client=current.client,
                                       staged=False, offline=False, scenario=None)
        with patch('ascend_cli.read_config', return_value={}) as read, \
                patch('ascend_cli.load_config_from_env', return_value={}), redirect_stdout(io.StringIO()) as out:
            ascend_cli.handle_chat_slash('/status', current, config_file='explicit.json')
        read.assert_called_once_with('explicit.json')
        self.assertIn('glm/active-model', out.getvalue())


class ModelCommandTests(unittest.TestCase):
    def test_noninteractive_model_status_uses_file_and_env(self):
        import argparse
        with patch('ascend_cli.read_config', return_value={'provider': 'openai', 'model': 'file-model'}), \
                patch('ascend_cli.load_config_from_env', return_value={'model': 'env-model'}), \
                patch('ascend_cli.ensure_home'), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ascend_cli.model_cmd(argparse.Namespace(provider=None, name=None, base_url=None)), 0)
        self.assertIn('env-model', out.getvalue())


class NpmRunnerTests(unittest.TestCase):
    def test_runner_uses_py_launcher_and_propagates_status_and_errors(self):
        source = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const code = fs.readFileSync('bin/test.js', 'utf8');
for (const result of [{status: 0}, {status: 7}, {status: null}, {error: new Error('spawn failed')}]) {
  const calls = [];
  const errors = [];
  const proc = {};
  vm.runInNewContext(code, {
    __dirname: path.resolve('bin'), process: proc, console: {error: m => errors.push(m)},
    require: name => name === 'path' ? path : name === './python-launcher'
      ? {findPython: () => ({command: 'py', args: ['-3']})}
      : {spawnSync: (...args) => {calls.push(args); return result;}},
  });
  assert.strictEqual(calls[0][0], 'py');
  assert.strictEqual(JSON.stringify(calls[0][1]), JSON.stringify(['-3', '-m', 'unittest', 'discover', '-s', 'tests', '-q']));
  assert.strictEqual(calls[0][2].cwd, process.cwd());
  assert.strictEqual(proc.exitCode, result.error || result.status === null ? 1 : result.status);
  if (result.error) assert.deepStrictEqual(errors, ['spawn failed']);
}
const proc = {};
const errors = [];
vm.runInNewContext(code, {process: proc, console: {error: m => errors.push(m)},
  require: name => name === 'path' ? path : name === './python-launcher'
    ? {findPython: () => {throw new Error('no interpreter');}} : {},
});
assert.strictEqual(proc.exitCode, 1);
assert.deepStrictEqual(errors, ['no interpreter']);
"""
        result = subprocess.run(['node', '-e', source], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(Path('package.json').read_text(encoding='utf-8'))['scripts']['test'],
                         'node bin/test.js')


if __name__ == '__main__':
    unittest.main()
