"""Regression: slash commands must use exact tokens (/model ≠ /mode)."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from ascend_cli import _slash_cmd, handle_chat_slash
from scripts.conversation_agent import ConversationAgent


class SlashCmdParseTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(_slash_cmd('/model'), ('/model', ''))
        self.assertEqual(_slash_cmd('/model MiniMax-M1'), ('/model', 'MiniMax-M1'))
        self.assertEqual(_slash_cmd('/mode auto'), ('/mode', 'auto'))
        self.assertEqual(_slash_cmd('hello'), (None, 'hello'))
        self.assertEqual(_slash_cmd('/fix operator'), ('/fix', 'operator'))


class SlashDispatchTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.agent = ConversationAgent(self.client, MagicMock(), MagicMock())

    def _run(self, text, **kwargs):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = handle_chat_slash(text, self.agent, **kwargs)
        return result, buf.getvalue()

    def test_model_not_eaten_by_mode(self):
        with patch('ascend_cli.read_config', return_value={'provider': 'x', 'model': 'old'}), \
                patch('ascend_cli.load_config_from_env', return_value={}), \
                patch('ascend_cli.merge_config', side_effect=lambda a, b: {**a, **b}), \
                patch('ascend_cli.config_path', return_value='C:/tmp/ai_config.json'):
            result, out = self._run('/model')
        self.assertEqual(result, 'handled')
        self.assertIn('当前模型', out)
        self.assertNotIn('当前对话模式', out)
        self.assertNotIn('自动分流', out.split('当前模型')[0] if '当前模型' in out else out)

    def test_mode_still_works(self):
        result, out = self._run('/mode')
        self.assertEqual(result, 'handled')
        self.assertIn('当前对话模式', out)
        self.assertIn('AI自动调换', out)

    def test_model_switch_same_gateway_no_key_prompt(self):
        written = {}

        def fake_write(data, path):
            written.clear()
            written.update(data)
            return path

        reload_client = MagicMock()
        cfg = {
            'provider': 'openai',
            'model': 'MiniMax-Text-01',
            'base_url': 'https://api.minimax.chat/v1',
            'api_key': 'sk-old',
        }
        with patch('ascend_cli.read_config', return_value=dict(cfg)), \
                patch('ascend_cli.load_config_from_env', return_value={}), \
                patch('ascend_cli.merge_config', side_effect=lambda a, b: {**a, **b}), \
                patch('ascend_cli.config_path', return_value='C:/tmp/ai_config.json'), \
                patch('ascend_cli.write_config', side_effect=fake_write), \
                patch('ascend_cli.ensure_home'):
            result, out = self._run('/model MiniMax-M1', reload_client=reload_client)
        self.assertEqual(result, 'handled')
        self.assertEqual(written.get('model'), 'MiniMax-M1')
        self.assertIn('立即生效', out)
        reload_client.assert_called_once_with(written)

    def test_model_switch_cross_vendor_requires_key(self):
        written = {}

        def fake_write(data, path):
            written.clear()
            written.update(data)
            return path

        reload_client = MagicMock()
        cfg = {
            'provider': 'openai',
            'model': 'MiniMax-Text-01',
            'base_url': 'https://api.minimax.chat/v1',
            'api_key': 'sk-minimax',
        }
        with patch('ascend_cli.read_config', return_value=dict(cfg)), \
                patch('ascend_cli.load_config_from_env', return_value={}), \
                patch('ascend_cli.merge_config', side_effect=lambda a, b: {**a, **b}), \
                patch('ascend_cli.config_path', return_value='C:/tmp/ai_config.json'), \
                patch('ascend_cli.write_config', side_effect=fake_write), \
                patch('ascend_cli.ensure_home'), \
                patch('builtins.input', return_value='sk-glm-new'):
            result, out = self._run('/model glm', reload_client=reload_client)
        self.assertEqual(result, 'handled')
        self.assertEqual(written.get('provider'), 'glm')
        self.assertEqual(written.get('model'), 'glm-4-flash')
        self.assertEqual(written.get('api_key'), 'sk-glm-new')
        self.assertEqual(written.get('base_url'), '')
        self.assertIn('API Key 已更新', out)

    def test_model_switch_cancel_without_key(self):
        written = {}

        def fake_write(data, path):
            written.update(data)
            return path

        cfg = {
            'provider': 'openai',
            'model': 'MiniMax-Text-01',
            'base_url': 'https://api.minimax.chat/v1',
            'api_key': 'sk-minimax',
        }
        with patch('ascend_cli.read_config', return_value=dict(cfg)), \
                patch('ascend_cli.load_config_from_env', return_value={}), \
                patch('ascend_cli.merge_config', side_effect=lambda a, b: {**a, **b}), \
                patch('ascend_cli.config_path', return_value='C:/tmp/ai_config.json'), \
                patch('ascend_cli.write_config', side_effect=fake_write), \
                patch('ascend_cli.ensure_home'), \
                patch('builtins.input', return_value=''):
            result, out = self._run('/model glm')
        self.assertEqual(result, 'handled')
        self.assertEqual(written, {})
        self.assertIn('已取消', out)

    def test_chat_work_clear_network_help_exit(self):
        r, out = self._run('/chat')
        self.assertEqual(r, 'handled')
        self.assertEqual(self.agent.chat_mode, 'chat')
        self.assertIn('日常', out)

        r, out = self._run('/work')
        self.assertEqual(r, 'handled')
        self.assertEqual(self.agent.chat_mode, 'work')

        r, out = self._run('/mode auto')
        self.assertEqual(r, 'handled')
        self.assertEqual(self.agent.chat_mode, 'auto')

        r, out = self._run('/network off')
        self.assertEqual(r, 'handled')
        self.assertEqual(self.agent.network, 'off')

        self.agent.contexts = [{'type': 'paste', 'title': 't', 'url': 'u', 'warnings': []}]
        r, out = self._run('/clear')
        self.assertEqual(r, 'handled')
        self.assertEqual(self.agent.contexts, [])

        r, out = self._run('/help')
        self.assertEqual(r, 'handled')
        self.assertIn('/model', out)

        r, out = self._run('/exit')
        self.assertEqual(r, 'exit')

        r, out = self._run('exit')
        self.assertEqual(r, 'exit')

    def test_context_sources_discard_apply(self):
        r, out = self._run('/context')
        self.assertEqual(r, 'handled')
        self.assertIn('没有获取到', out)

        r, out = self._run('/sources')
        self.assertEqual(r, 'handled')

        r, out = self._run('/discard')
        self.assertEqual(r, 'handled')

        with patch.object(self.agent, 'apply_pending_fix', return_value='applied') as apply_m, \
                patch('ascend_cli._print_agent_reply'):
            r, out = self._run('/apply')
        self.assertEqual(r, 'handled')
        apply_m.assert_called_once()

    def test_unknown_slash_not_sent_to_model(self):
        r, out = self._run('/notacommand')
        self.assertEqual(r, 'handled')
        self.assertIn('未知命令', out)

    def test_plain_text_passes(self):
        r, out = self._run('你好')
        self.assertEqual(r, 'pass')

    def test_status_history_export_retry(self):
        self.agent.history = [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'hi there'},
        ]
        self.agent.last_user_text = 'hello'
        with patch('ascend_cli.read_config', return_value={'provider': 'x', 'model': 'm'}), \
                patch('ascend_cli.load_config_from_env', return_value={}), \
                patch('ascend_cli.merge_config', side_effect=lambda a, b: {**a, **b}), \
                patch('ascend_cli.config_path', return_value='C:/tmp/ai_config.json'):
            r, out = self._run('/status')
        self.assertEqual(r, 'handled')
        self.assertIn('会话状态', out)

        r, out = self._run('/history')
        self.assertEqual(r, 'handled')
        self.assertIn('[你]', out)

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            target = str(Path(td) / 'out.md')
            r, out = self._run(f'/export {target}')
            self.assertEqual(r, 'handled')
            self.assertTrue(Path(target).is_file())
            body = Path(target).read_text(encoding='utf-8')
            self.assertIn('hello', body)

        with patch.object(self.agent, 'answer', return_value='retried') as ans, \
                patch('ascend_cli.begin_think'), patch('ascend_cli.end_think'), \
                patch('ascend_cli._print_agent_reply'):
            r, out = self._run('/retry')
        self.assertEqual(r, 'handled')
        ans.assert_called_once_with('hello')

    def test_ci_and_checklist_and_review_commands(self):
        self.agent.last_user_text = 'ERROR: Codecheck failed\nHCCL 507049 boom\n' + ('x' * 40)
        with patch('ascend_cli._print_agent_reply') as printer:
            r, out = self._run('/ci')
        self.assertEqual(r, 'handled')
        printer.assert_called()
        self.assertIn('CI', printer.call_args[0][0])

        with patch('ascend_cli._print_agent_reply') as printer:
            r, out = self._run('/checklist demo')
        self.assertEqual(r, 'handled')
        self.assertIn('验收清单', printer.call_args[0][0])

        with patch('ascend_cli.begin_think'), patch('ascend_cli.end_think'), \
                patch('ascend_cli.run_local_review', return_value=('## ok', {})), \
                patch('ascend_cli._print_agent_reply') as printer, \
                patch('ascend_cli.config_path', return_value='C:/tmp/x.json'):
            r, out = self._run('/review staged')
        self.assertEqual(r, 'handled')
        printer.assert_called_once()


if __name__ == '__main__':
    unittest.main()
