"""Reproductions from the 2026-10-15 review; no real credentials or network."""
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
from scripts.ai_adapter import get_ai_client
from scripts.conversation_agent import ConversationAgent, resolve_turn_mode
from scripts.patch_fix import FileEdit, ProposedFix, apply_fix, parse_fix_json
from scripts.repo_context import collect_repo_context, decode_git_path
from scripts.smart_reviewer import added_lines
from scripts.specialist_context import detect_scenario, load_specialist_context, resolve_specialist
from test_reliability import run_cli_review, temp_repo


class ModelSwitchTests(unittest.TestCase):
    def test_cross_vendor_switch_reloads_despite_environment_and_uses_active_config(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'OPENAI_API_KEY': 'fake-openai-key',
                'OPENAI_MODEL': 'fake-old-model',
                'OPENAI_BASE_URL': 'https://gateway.example/v1',
                'REVIEWAGENT_HOME': tmp}, clear=True):
            config = Path(tmp) / 'explicit.json'
            config.write_text('{}', encoding='utf-8')
            agent = ConversationAgent(get_ai_client(str(config)), MagicMock(), MagicMock())
            before = dict(os.environ)
            with patch('builtins.input', return_value='fake-glm-key'), redirect_stdout(io.StringIO()) as output:
                ascend_cli.handle_chat_slash('/model glm', agent, config_file=str(config))
            self.assertIn('已切换', output.getvalue())
            self.assertEqual(agent.client.provider_name, 'glm')
            self.assertEqual(agent.client.model_name, 'glm-4-flash')
            self.assertEqual(agent.client.provider.api_key, 'fake-glm-key')
            self.assertEqual(json.loads(config.read_text(encoding='utf-8'))['provider'], 'glm')
            self.assertEqual(dict(os.environ), before)
            # Startup still honors cc-switch; /model only overrides this conversation.
            self.assertEqual(get_ai_client(str(config)).model_name, 'fake-old-model')
            with patch('builtins.input') as key_input, redirect_stdout(io.StringIO()) as output:
                ascend_cli.handle_chat_slash('/model glm-4-plus', agent, config_file=str(config))
                ascend_cli.handle_chat_slash('/model', agent, config_file=str(config))
            key_input.assert_not_called()
            self.assertEqual(agent.client.model_name, 'glm-4-plus')
            self.assertIn('glm-4-plus', output.getvalue())

    def test_custom_model_keeps_environment_gateway_and_key(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'OPENAI_API_KEY': 'fake-key', 'OPENAI_MODEL': 'old',
                'OPENAI_BASE_URL': 'https://gateway.example/v1',
                'REVIEWAGENT_HOME': tmp}, clear=True):
            config = Path(tmp) / 'explicit.json'
            config.write_text('{}', encoding='utf-8')
            agent = ConversationAgent(get_ai_client(str(config)), MagicMock(), MagicMock())
            reloaded = []
            def reload_client(data):
                agent.client = get_ai_client(str(config), overrides=data)
                reloaded.append(agent.client.model_name)
            with redirect_stdout(io.StringIO()):
                ascend_cli.handle_chat_slash('/model local-test-model', agent,
                                             reload_client=reload_client, config_file=str(config))
            self.assertEqual(reloaded, ['local-test-model'])
            self.assertEqual(agent.client.provider.api_key, 'fake-key')
            self.assertIn('gateway.example', agent.client.provider.get_api_url())


class SpecialistBoundaryTests(unittest.TestCase):
    def test_real_inference_load_has_all_required_files(self):
        load = load_specialist_context('inference')
        self.assertEqual(load.status, 'ready')
        self.assertEqual(load.omitted, [])
        self.assertTrue(all(f['status'] == 'loaded' for f in load.files))
        self.assertIn('迁移验收标准', load.text)
        self.assertLessEqual(len(load.text), 16000)
        self.assertLessEqual(len(load.text.encode('utf-8')), 32768)

    def test_budget_cannot_mark_omitted_agent_as_loaded(self):
        with patch('scripts.specialist_context.MAX_CHARS', 100), \
                patch('scripts.specialist_context.MAX_BYTES', 100):
            load = resolve_specialist('tiling', explicit='operator')
        self.assertEqual(load.status, 'incomplete')
        self.assertEqual(load.text, '')
        self.assertTrue(all(f['status'] == 'omitted_budget' for f in load.files))
        self.assertIn('未完整加载', load.reason)

    def test_missing_required_skill_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = root / '.cursor/agents/cann-op-checker.md'
            agent.parent.mkdir(parents=True)
            agent.write_text('operator rules', encoding='utf-8')
            with patch('scripts.specialist_context.PROJECT_ROOT', root), \
                    patch('scripts.specialist_context.Path.home', return_value=root):
                load = load_specialist_context('operator')
            self.assertEqual(load.status, 'incomplete')
            self.assertTrue(any(f['status'] == 'missing' for f in load.files))

    def test_home_fallback_records_source_without_relative_path_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / 'home'
            for name in ['agents/cann-op-checker.md',
                         'skills/cann-ascendc-op-dev/SKILL.md',
                         'skills/cann-ascendc-op-dev/pitfalls.md']:
                path = home / '.cursor' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture rules', encoding='utf-8')
            with patch('scripts.specialist_context.PROJECT_ROOT', root / 'package'), \
                    patch('scripts.specialist_context.Path.home', return_value=home):
                load = load_specialist_context('operator')
            self.assertEqual(load.status, 'ready')
            self.assertTrue(all(f['path'].startswith('~/.cursor/') for f in load.files))

    def test_deleted_code_and_prompt_metadata_do_not_select_scenario(self):
        diff = ('diff --git a/model.py b/model.py\n--- a/model.py\n+++ b/model.py\n'
                '@@ -1 +1 @@\n-import torch_npu\n+value = 1\n')
        prompt = 'root: /torch_npu/project\nbranch: tiling\n' + diff
        self.assertEqual(detect_scenario(prompt, ['model.py']).status, 'needs_context')
        current = diff.replace('-import torch_npu\n+value = 1',
                               ' import torch_npu\n+value = 1')
        self.assertEqual(detect_scenario(current, ['model.py']).scenario, 'inference')

    def test_cli_blocks_incomplete_context_before_model_call(self):
        with temp_repo() as root, patch('scripts.specialist_context.MAX_CHARS', 100), \
                patch('scripts.smart_reviewer.get_ai_client') as client:
            code, out, _ = run_cli_review(root, scenario='operator')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['specialist_context']['status'], 'incomplete')
        client.assert_not_called()


class PatchBoundaryTests(unittest.TestCase):
    def agent(self, raw):
        client = MagicMock()
        client.chat.return_value = raw
        agent = ConversationAgent(client, MagicMock(), MagicMock())
        agent.contexts = [{'type': 'pr', 'title': 't', 'body': '', 'files': []}]
        return agent

    def test_wrong_json_types_are_rejected_as_retryable_failure(self):
        malformed = [None, '', '{}', '{"files":23}', '{"files":{"path":"a.py"}}',
                     '{"files":[{"path":"a.py","action":["replace"]}]}',
                     '{"files":[{"path":"a.py","replace":null}]}',
                     '{"files":[{"path":"a.py","replace":42}]}']
        for raw in malformed:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_fix_json(raw)
                agent = self.agent(raw)
                agent.pending_fix = ProposedFix(files=[FileEdit('old.txt', 'create', replace='old')])
                agent.propose_fix()
                self.assertFalse(agent.last_ok)
                self.assertIsNone(agent.pending_fix)

    def test_incomplete_specialist_blocks_fix_and_full_rules_are_not_sliced(self):
        raw = '{"files":[]}'
        agent = self.agent(raw)
        with patch('scripts.specialist_context.MAX_CHARS', 100):
            self.assertIn('未就绪', agent.propose_fix(explicit_scenario='inference'))
        agent.client.chat.assert_not_called()
        agent.propose_fix(explicit_scenario='inference')
        payload = json.loads(agent.client.chat.call_args.args[0])
        self.assertEqual(payload['specialist_rules'], load_specialist_context('inference').text)

    def test_apply_preserves_existing_newline_bytes(self):
        for newline in [b'\n', b'\r\n', b'\r']:
            with self.subTest(newline=newline), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / 'a.py'
                original = b'value = OLD' + newline + b'second = 2' + newline
                target.write_bytes(original)
                fix = ProposedFix(files=[FileEdit('a.py', 'replace',
                    search='value = OLD\nsecond = 2', replace='value = NEW\nsecond = 2')])
                self.assertEqual(apply_fix(fix, root=root)['applied'], 1)
                self.assertEqual(target.read_bytes(), original.replace(b'OLD', b'NEW'))

    def test_create_keeps_requested_newline_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fix = ProposedFix(files=[FileEdit('a.py', 'create', replace='a\nb\n')])
            apply_fix(fix, root=root)
            self.assertEqual((root / 'a.py').read_bytes(), b'a\nb\n')


class RoutingBoundaryTests(unittest.TestCase):
    def test_bare_error_code_uses_infra_but_unqualified_version_needs_context(self):
        self.assertEqual(resolve_turn_mode('auto', '507049 怎么排查？', False, False), 'infra')
        client, knowledge = MagicMock(), MagicMock()
        agent = ConversationAgent(client, knowledge, MagicMock())
        self.assertIn('哪个组件', agent.answer('查版本'))
        client.chat.assert_not_called()
        client.chat_with_history.assert_not_called()
        self.assertFalse(agent.last_ok)
        self.assertEqual(resolve_turn_mode('auto', '查版本', True, False, session_lane='work'), 'infra')


class GitPathBoundaryTests(unittest.TestCase):
    def test_c_quoted_utf8_and_control_characters_decode(self):
        self.assertEqual(decode_git_path(r'"b/\346\250\241\345\236\213.py"'), 'b/模型.py')
        self.assertEqual(decode_git_path(r'"b/a\tb.py"'), 'b/a\tb.py')
        diff = ('diff --git a/x b/x\n--- a/x\n'
                '+++ "b/\\346\\250\\241\\345\\236\\213.py"\n@@ -1 +1 @@\n-old\n+new\n')
        self.assertEqual(added_lines(diff), [('模型.py', 1, 'new')])

    def test_real_git_chinese_paths_remain_openable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                *args], cwd=root, capture_output=True, check=True)
            git('init')
            git('config', 'core.quotepath', 'true')
            target = root / '模型.py'
            target.write_bytes(b'x = 1\n')
            git('add', '.')
            git('commit', '-m', 'fixture')
            target.write_bytes(b'x = 1\nt.cuda()\n')
            context = collect_repo_context(str(root))
            self.assertEqual(context['changed_files'], ['模型.py'])
            self.assertEqual(added_lines(context['diff']), [('模型.py', 2, 't.cuda()')])
            self.assertTrue((root / context['changed_files'][0]).is_file())


if __name__ == '__main__':
    unittest.main()
