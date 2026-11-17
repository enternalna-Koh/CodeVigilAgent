"""Desktop credential ownership and Windows conversation isolation, without a UI."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ascend_cli

WIN = Path(__file__).resolve().parents[1] / 'desktop-app' / 'win'
sys.path.insert(0, str(WIN))
try:
    from cvapp import config
    from cvapp.features.chat import send
    from cvapp.features.output import _clear
    from cvapp.features.settings import GatewayKey
except ModuleNotFoundError as exc:
    if exc.name != 'tkinter':
        raise
    GatewayKey = None


@unittest.skipIf(GatewayKey is None, 'Python was built without tkinter')
class GatewayKeyTests(unittest.TestCase):
    def test_native_providers_with_empty_endpoints_do_not_share_keys(self):
        binding = GatewayKey('deepseek', '', 'fake-deepseek')
        self.assertEqual(binding.update('glm', '', 'fake-deepseek'), '')
        self.assertTrue(binding.changed)
        self.assertEqual(binding.update('glm', '', 'fake-glm'), 'fake-glm')
        self.assertEqual(binding.update('claude', '', 'fake-glm'), '')

    def test_return_to_original_restores_its_key(self):
        binding = GatewayKey('deepseek', '', 'fake-original')
        self.assertEqual(binding.update('openai', 'https://other.example/v1', 'fake-original'), '')
        self.assertEqual(binding.update('deepseek', '', 'fake-other'), 'fake-original')
        self.assertFalse(binding.changed)

    def test_manual_endpoint_changes_clear_keys_and_return_restores_them(self):
        binding = GatewayKey('openai', 'https://one.example/v1', 'fake-one')
        self.assertEqual(binding.update('openai', 'https://two.example/v1', 'fake-one'), '')
        self.assertTrue(binding.changed)
        self.assertEqual(binding.update('openai', 'https://two.example/v1', 'fake-two'), 'fake-two')
        self.assertEqual(binding.update('openai', 'https://one.example/v1', 'fake-two'), 'fake-one')

    def test_equivalent_formatting_keeps_key_but_url_path_case_is_distinct(self):
        binding = GatewayKey('OpenAI', 'https://one.example/v1/', 'fake-one')
        self.assertEqual(binding.update(' openai ', ' https://one.example/v1 ', 'edited'), 'edited')
        self.assertFalse(binding.changed)
        self.assertEqual(binding.update('openai', 'https://one.example/V1', 'edited'), '')


class FakeKnowledge:
    warnings = []
    documents = []
    def search(self, *_args, **_kwargs):
        return []


class FakeModel:
    provider = SimpleNamespace(api_key='fake-local-test-key')
    def __init__(self):
        self.calls = []
    def chat_with_history(self, messages, **_kwargs):
        self.calls.append(messages)
        return 'fake reply'


@unittest.skipIf(GatewayKey is None, 'Python was built without tkinter')
class WindowsChatTests(unittest.TestCase):
    def test_selected_repo_and_followup_reach_model_and_new_chat_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'repo'
            repo.mkdir()
            (repo / 'sample.py').write_text('selected_repository_sentinel = 1', encoding='utf-8')
            other = root / 'other'
            other.mkdir()
            model = FakeModel()
            app = SimpleNamespace(
                runner=SimpleNamespace(busy=False, python=lambda: sys.executable),
                current_repo=lambda: str(repo), append=lambda *_args: None,
                output=SimpleNamespace(clear=lambda: None), set_status=lambda *_args: None,
                chat_session=None, chat_repository=None,
                chat=SimpleNamespace(clear=lambda: None),
                chat_section=SimpleNamespace(begin=lambda text: [],
                                             cancel=lambda: None),
            )

            def run_cli(args, cwd, label, sink=None):
                output = io.StringIO()
                with patch.dict(os.environ, {'REVIEWAGENT_HOME': str(root / 'home')}), \
                        patch.object(ascend_cli, 'get_ai_client', return_value=model), \
                        patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()), \
                        patch('sys.argv', ['ascend_cli.py'] + args[2:] + ['--json']), \
                        contextlib.redirect_stdout(output):
                    self.assertEqual(ascend_cli.main(), 0)
                self.assertTrue(json.loads(output.getvalue())['ok'])
                self.assertEqual(Path(cwd), Path(app.current_repo()).resolve())

            app.run_cli = run_cli
            send(app, 'first question @sample.py')
            session = app.chat_session
            self.assertIn('selected_repository_sentinel', json.dumps(model.calls[0]))
            send(app, 'follow up')
            self.assertEqual(app.chat_session, session)
            self.assertTrue(any(m['role'] == 'assistant' for m in model.calls[1]))
            _clear(app)
            self.assertIsNone(app.chat_session)
            send(app, 'new question')
            self.assertNotEqual(app.chat_session, session)
            self.assertFalse(any(m['role'] == 'assistant' for m in model.calls[2]))
            session = app.chat_session
            app.current_repo = lambda: str(other)
            send(app, 'other repository')
            self.assertNotEqual(app.chat_session, session)
            self.assertFalse(any(m['role'] == 'assistant' for m in model.calls[3]))

    def test_running_task_cannot_reset_conversation(self):
        clear = unittest.mock.Mock()
        app = SimpleNamespace(runner=SimpleNamespace(busy=True), chat_session='active',
                              output=SimpleNamespace(clear=clear), append=lambda *_args: None)
        _clear(app)
        self.assertEqual(app.chat_session, 'active')
        clear.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX file permissions')
    def test_settings_use_private_config_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'shared' / 'custom.json'
            target.parent.mkdir(mode=0o755)
            target.write_text('{}', encoding='utf-8')
            target.chmod(0o644)
            with patch.object(config, 'CONFIG_PATH', str(target)), \
                    patch.dict(os.environ, {'REVIEWAGENT_HOME': str(Path(tmp) / 'home')}):
                config.save_config({'api_key': 'fake-only'})
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o755)
            self.assertEqual(json.loads(target.read_text())['api_key'], 'fake-only')


if __name__ == '__main__':
    unittest.main()
