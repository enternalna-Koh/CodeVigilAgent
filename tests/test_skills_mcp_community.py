"""Skills runtime, MCP client, openGauss community collect & scenario."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ascend_cli import handle_chat_slash
from scripts.collect_gitcode_community import collect_community, load_community
from scripts.conversation_agent import ConversationAgent, ContextFetcher
from scripts.mcp_client import BUILTIN_SERVERS, McpSession, McpServerConfig, load_mcp_config
from scripts.skill_runtime import format_skill_list, list_skills, load_skill
from scripts.specialist_context import detect_scenario, load_specialist_context


class CommunityRegistryTests(unittest.TestCase):
    def test_opengauss_registry(self):
        cfg = load_community('opengauss')
        self.assertEqual(cfg['id'], 'opengauss')
        repos = {(r['owner'], r['repo']) for r in cfg['repos']}
        self.assertIn(('opengauss', 'Plugin'), repos)
        self.assertIn(('opengauss', 'docs'), repos)

    def test_collect_without_token_writes_error_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('scripts.collect_gitcode_community.PROJECT_ROOT', root), \
                    patch('scripts.collect_gitcode_community.RAW_DIR', root / 'data' / 'raw'), \
                    patch('scripts.collect_gitcode_community.CI_DIR', root / 'data' / 'ci_runs'), \
                    patch('scripts.collect_gitcode_community.DIALOG_DIR', root / 'data' / 'review_dialogs'), \
                    patch('scripts.collect_gitcode_community.COMMUNITIES_DIR',
                          PROJECT_ROOT / 'data' / 'communities'), \
                    patch.dict(os.environ, {'GITCODE_TOKEN': '', 'GITHUB_TOKEN': ''}, clear=False):
                # Ensure empty tokens
                os.environ.pop('GITCODE_TOKEN', None)
                os.environ.pop('GITHUB_TOKEN', None)
                result = collect_community('opengauss')
        self.assertFalse(result['ok'])
        self.assertIn('GITCODE_TOKEN', result['error'])


class SkillRuntimeTests(unittest.TestCase):
    def test_list_includes_project_skills(self):
        names = {s.name for s in list_skills()}
        self.assertIn('opengauss-community', names)
        self.assertIn('api-consistency-community', names)

    def test_load_opengauss_skill(self):
        loaded = load_skill('opengauss-community')
        self.assertEqual(loaded.status, 'ready')
        self.assertIn('openGauss', loaded.text)
        self.assertTrue(format_skill_list())


class SpecialistOpenGaussTests(unittest.TestCase):
    def test_detect_opengauss(self):
        hit = detect_scenario('fix Plugin on openGauss', paths=['opengauss/Plugin/x.cpp'])
        self.assertEqual((hit.scenario, hit.status), ('opengauss', 'ready'))

    def test_detect_api_consistency_as_inference(self):
        hit = detect_scenario('参加 API 一致性对齐任务', paths=['readme.md'])
        self.assertEqual(hit.scenario, 'inference')

    def test_load_opengauss_context(self):
        loaded = load_specialist_context('opengauss')
        self.assertIn(loaded.status, ('ready', 'incomplete'))
        self.assertIn('openGauss', loaded.text)
        self.assertTrue(any('opengauss-community' in (f.get('path') or '') for f in loaded.files))

    def test_explicit_opengauss(self):
        hit = detect_scenario('hello', explicit='opengauss')
        self.assertEqual(hit.scenario, 'opengauss')


class McpClientTests(unittest.TestCase):
    def test_builtin_ascend_doc(self):
        self.assertIn('ascend-doc', BUILTIN_SERVERS)
        cfg = load_mcp_config()
        self.assertIn('ascend-doc', cfg)
        self.assertEqual(cfg['ascend-doc'].args[-1], 'ascend-doc-mcp@latest')

    def test_fake_stdio_session(self):
        # Minimal MCP-ish server: Content-Length JSON-RPC
        server = r'''
import sys, json
def read_msg():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line or line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            k, v = line.decode().split(":", 1)
            headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length", "0"))
    body = sys.stdin.buffer.read(n)
    return json.loads(body.decode())
def write_msg(obj):
    raw = json.dumps(obj).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    sys.stdout.buffer.flush()
while True:
    msg = read_msg()
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        write_msg({"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"fake"}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        write_msg({"jsonrpc":"2.0","id":mid,"result":{"tools":[{"name":"echo","description":"echo"}]}})
    elif method == "tools/call":
        write_msg({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"ok"}]}})
    else:
        write_msg({"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"unknown"}})
'''
        cfg = McpServerConfig(name='fake', command=sys.executable, args=['-c', server])
        sess = McpSession(cfg)
        self.assertTrue(sess.start(timeout=15), sess.last_error)
        try:
            self.assertEqual(sess.tools[0]['name'], 'echo')
            out = sess.call_tool('echo', {'x': 1})
            self.assertTrue(out.get('ok'))
        finally:
            sess.close()


class SlashSkillMcpTests(unittest.TestCase):
    def _run(self, text):
        agent = ConversationAgent(client=MagicMock())
        buf = io.StringIO()
        with patch('sys.stdout', buf):
            result = handle_chat_slash(text, agent)
        return result, buf.getvalue()

    def test_skill_list(self):
        result, out = self._run('/skill list')
        self.assertEqual(result, 'handled')
        self.assertIn('opengauss-community', out)

    def test_skill_load(self):
        agent = ConversationAgent(client=MagicMock())
        buf = io.StringIO()
        with patch('sys.stdout', buf):
            handle_chat_slash('/skill load opengauss-community', agent)
        self.assertEqual(agent.active_skills[0]['name'], 'opengauss-community')

    def test_mcp_list(self):
        result, out = self._run('/mcp')
        self.assertEqual(result, 'handled')
        self.assertIn('ascend-doc', out)


class GitCodeCiFetchTests(unittest.TestCase):
    def test_fetch_gitcode_attaches_ci(self):
        fetcher = ContextFetcher()
        calls = []

        def fake_api(endpoint):
            calls.append(endpoint)
            if endpoint.endswith('/pulls/1'):
                return {
                    'title': 't', 'body': 'b', 'html_url': 'https://gitcode.com/o/r/pulls/1',
                    'state': 'open', 'head': {'sha': 'abc'},
                }
            if '/issues/1/comments' in endpoint:
                return []
            if '/files' in endpoint:
                return []
            if '/comments' in endpoint:
                return []
            if 'check-runs' in endpoint:
                return {'check_runs': [
                    {'name': 'ci', 'status': 'completed', 'conclusion': 'success',
                     'details_url': 'https://example.com/ci'}
                ]}
            return {'error': 'unexpected ' + endpoint}

        fetcher.fetch_gitcode_api = fake_api
        fetcher._list = lambda *a, **k: []
        ctx = fetcher._fetch_gitcode(
            {'owner': 'o', 'repo': 'r', 'type': 'pr', 'number': 1},
            'https://gitcode.com/o/r/pulls/1',
        )
        self.assertEqual(ctx['ci']['check_runs'][0]['conclusion'], 'success')
        self.assertTrue(any('check-runs' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
