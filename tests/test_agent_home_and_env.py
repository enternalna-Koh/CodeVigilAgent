"""Tests for REVIEWAGENT_HOME and cc-switch-compatible env loading."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ai_adapter import load_config_from_env, merge_config, load_config_from_file
from scripts import agent_home


class EnvConfigTests(unittest.TestCase):
    def test_openai_env_maps_to_openai_provider(self):
        env = {
            'OPENAI_API_KEY': 'sk-test',
            'OPENAI_BASE_URL': 'https://gateway.example/v1',
            'OPENAI_MODEL': 'gpt-4o-mini',
        }
        with patch.dict(os.environ, env, clear=False):
            for k in ('AI_PROVIDER', 'AI_API_KEY', 'AI_MODEL', 'AI_BASE_URL',
                      'ANTHROPIC_API_KEY'):
                os.environ.pop(k, None)
            cfg = load_config_from_env()
        self.assertEqual(cfg['provider'], 'openai')
        self.assertEqual(cfg['api_key'], 'sk-test')
        self.assertEqual(cfg['base_url'], 'https://gateway.example/v1')
        self.assertEqual(cfg['model'], 'gpt-4o-mini')

    def test_env_overrides_file(self):
        merged = merge_config(
            {'provider': 'deepseek', 'api_key': 'file-key', 'model': 'deepseek-chat'},
            {'provider': 'openai', 'api_key': 'env-key', 'model': 'gpt-4o'},
        )
        self.assertEqual(merged['provider'], 'openai')
        self.assertEqual(merged['api_key'], 'env-key')

    def test_template_placeholder_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ai_config.json'
            path.write_text('{"provider":"deepseek","api_key":"YOUR_API_KEY_HERE","model":"deepseek-chat"}',
                            encoding='utf-8')
            data = load_config_from_file(str(path))
        self.assertEqual(data.get('api_key'), '')


class HomeTests(unittest.TestCase):
    def test_ensure_home_creates_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'REVIEWAGENT_HOME': tmp}):
                root = agent_home.ensure_home()
                self.assertEqual(Path(root), Path(tmp))
                self.assertTrue((Path(tmp) / 'ai_config.json').exists())


if __name__ == '__main__':
    unittest.main()
