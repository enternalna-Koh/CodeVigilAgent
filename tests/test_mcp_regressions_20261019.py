"""MCP transport regressions using local Python processes, never remote servers."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.mcp_client import McpRegistry, McpServerConfig, McpSession, load_mcp_config


SERVER = r'''
import json, sys, time
mode = sys.argv[1]
def send(message):
    raw = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    if mode == "fragmented":
        for pos in range(0, len(raw), 7):
            sys.stdout.buffer.write(raw[pos:pos + 7])
            sys.stdout.buffer.flush()
    else:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
for line in sys.stdin.buffer:
    message = json.loads(line)
    method, mid = message.get("method"), message.get("id")
    if method == "notifications/initialized":
        continue
    if method == "initialize":
        if mode == "silent":
            time.sleep(10)
        if mode == "bad-json":
            print("[]", flush=True)
            continue
        if mode == "fragmented":
            sys.stderr.buffer.write(b"log " * 131072)
            sys.stderr.buffer.flush()
        if mode == "slow-start":
            time.sleep(0.2)
        if mode == "ping":
            send({"jsonrpc": "2.0", "id": mid, "method": "ping"})
            reply = json.loads(sys.stdin.buffer.readline())
            assert reply["id"] == mid and reply["result"] == {}
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    elif method == "tools/list":
        if mode == "slow-start":
            time.sleep(0.2)
        result = {"tools": [{"name": "echo", "description": "local echo"}]}
    elif method == "tools/call":
        if mode == "slow-tool":
            time.sleep(10)
        result = {"content": [{"type": "text", "text": "昇腾文档"}]}
        if mode == "tool-error":
            result["isError"] = True
    else:
        continue
    send({"jsonrpc": "2.0", "id": mid, "result": result})
'''


class McpTransportRegressions(unittest.TestCase):
    def session(self, mode):
        session = McpSession(McpServerConfig('local', sys.executable, ['-u', '-c', SERVER, mode]))
        self.addCleanup(session.close)
        return session

    def test_standard_json_lines_handles_fragmented_unicode_and_stderr_backpressure(self):
        session = self.session('fragmented')
        self.assertTrue(session.start(timeout=5), session.last_error)
        result = session.call_tool('echo', {'query': '昇腾'})
        self.assertTrue(result.get('ok'), result)
        self.assertEqual(result['result']['content'][0]['text'], '昇腾文档')
        self.assertLessEqual(len(session._stderr_tail), 500)

    def test_same_session_can_restart_without_stale_reader(self):
        session = self.session('fragmented')
        self.assertTrue(session.start(timeout=5), session.last_error)
        previous = session.proc
        self.assertTrue(session.start(timeout=5), session.last_error)
        self.assertIsNotNone(previous.poll())
        self.assertTrue(session.call_tool('echo').get('ok'))

    def test_failed_initialize_closes_process_and_readers(self):
        session = self.session('silent')
        start = time.monotonic()
        self.assertFalse(session.start(timeout=0.2))
        self.assertIn('超时', session.last_error)
        self.assertIsNone(session.proc)
        self.assertEqual(session._reader_threads, [])
        self.assertLess(time.monotonic() - start, 2)

    def test_start_timeout_is_shared_by_initialize_and_tools_list(self):
        session = self.session('slow-start')
        self.assertFalse(session.start(timeout=0.3))
        self.assertIn('超时', session.last_error)
        self.assertIsNone(session.proc)

    def test_tool_timeout_closes_process_before_reuse(self):
        session = self.session('slow-tool')
        self.assertTrue(session.start(timeout=5), session.last_error)
        result = session.call_tool('echo', timeout=0.2)
        self.assertIn('超时', result.get('error', ''))
        self.assertIsNone(session.proc)

    def test_non_object_message_is_rejected_and_process_closed(self):
        session = self.session('bad-json')
        self.assertFalse(session.start(timeout=5))
        self.assertIn('JSON 对象', session.last_error)
        self.assertIsNone(session.proc)

    def test_server_ping_cannot_masquerade_as_initialize_response(self):
        session = self.session('ping')
        self.assertTrue(session.start(timeout=5), session.last_error)
        self.assertEqual(session.tools[0]['name'], 'echo')

    def test_tool_is_error_is_reported_as_failure(self):
        session = self.session('tool-error')
        self.assertTrue(session.start(timeout=5), session.last_error)
        result = session.call_tool('echo')
        self.assertIn('error', result)
        self.assertNotIn('ok', result)

    def test_command_uses_resolved_windows_cmd_path(self):
        session = McpSession(McpServerConfig('local', 'npx', ['--version']))
        with patch('scripts.mcp_client.shutil.which', return_value='C:/Node/npx.cmd'), \
                patch('scripts.mcp_client.subprocess.Popen', side_effect=OSError('fake launch')) as spawn:
            self.assertFalse(session.start())
        self.assertEqual(spawn.call_args.args[0], ['C:/Node/npx.cmd', '--version'])

    def test_invalid_process_environment_is_reported_without_crashing(self):
        session = McpSession(McpServerConfig('local', sys.executable, env={'INVALID=KEY': 'fake'}))
        self.assertFalse(session.start())
        self.assertIn('启动失败', session.last_error)
        self.assertIsNone(session.proc)


class McpConfigRegressions(unittest.TestCase):
    def test_malformed_server_wrapper_and_non_utf8_config_do_not_crash(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'mcp.json'
            for content in (b'{"mcpServers": ["bad"]}', b'\xff'):
                config.write_bytes(content)
                with patch('scripts.mcp_client.config_paths', return_value=[config]):
                    self.assertIn('ascend-doc', load_mcp_config())

    def test_command_list_preserves_scalar_argument_as_one_value(self):
        extra = {'mcpServers': {'local': {'command': ['python', '-u'], 'args': 'server.py'}}}
        with patch('scripts.mcp_client.config_paths', return_value=[]):
            config = load_mcp_config(extra)['local']
        self.assertEqual(config.command, 'python')
        self.assertEqual(config.args, ['-u', 'server.py'])

    def test_registry_close_releases_sessions_without_reloading_configuration(self):
        with patch('scripts.mcp_client.load_mcp_config', return_value={}):
            registry = McpRegistry()
        session = MagicMock()
        registry._sessions['local'] = session
        registry.close()
        session.close.assert_called_once_with()
        self.assertEqual(registry._sessions, {})


if __name__ == '__main__':
    unittest.main()
