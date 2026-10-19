import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.ci_log_analyzer import analyze_ci_log, format_ci_report
from scripts.conversation_agent import ConversationAgent
from scripts.session_store import (
    apply_to_agent,
    clean_sessions,
    list_sessions,
    load_session,
    save_session,
    serialize_agent,
    start_new_conversation,
)
from scripts.context_compare import compare_contexts, format_compare_report


class CiLogTests(unittest.TestCase):
    def test_detects_hccl_and_codecheck(self):
        log = """
[INFO] start
ERROR: Codecheck failed on kernel.cpp:12
HCCL error 507049 allreduce failed
AssertionError: precision mismatch rtol
"""
        result = analyze_ci_log(log)
        kinds = set(result['kinds'])
        self.assertIn('codecheck', kinds)
        self.assertIn('hccl', kinds)
        self.assertIn('precision', kinds)
        md = format_ci_report(result)
        self.assertIn('CI 日志快析', md)
        self.assertIn('codecheck', md)


class SessionStoreTests(unittest.TestCase):
    def test_save_load_roundtrip(self):
        agent = ConversationAgent(MagicMock(), MagicMock(), MagicMock())
        agent.chat_mode = 'work'
        agent.session_lane = 'work'
        agent.history = [
            {'role': 'user', 'content': 'q1'},
            {'role': 'assistant', 'content': 'a1'},
        ]
        agent.contexts = [{'type': 'paste', 'title': 't', 'url': 'u', 'warnings': []}]
        agent.last_user_text = 'q1'

        with tempfile.TemporaryDirectory() as td:
            with patch('scripts.session_store.home_dir', return_value=Path(td)), \
                    patch('scripts.session_store.ensure_home', return_value=Path(td)):
                path = save_session(agent, 'demo')
                self.assertTrue(path.is_file())
                data = load_session('demo')
                other = ConversationAgent(MagicMock(), MagicMock(), MagicMock())
                apply_to_agent(other, data)
                self.assertEqual(other.chat_mode, 'work')
                self.assertEqual(other.session_lane, 'work')
                self.assertEqual(len(other.history), 2)
                self.assertEqual(other.last_user_text, 'q1')
                rows = list_sessions()
                self.assertTrue(any(r['name'] == 'demo' for r in rows))
                blob = serialize_agent(agent)
                self.assertEqual(blob['version'], 1)
                json.dumps(blob)  # must be serializable


class ChecklistSlashSmoke(unittest.TestCase):
    def test_checklist_helper(self):
        from ascend_cli import _acceptance_checklist
        md = _acceptance_checklist('SpMV')
        self.assertIn('验收清单', md)
        self.assertIn('SpMV', md)
        self.assertIn('Codecheck', md)


class CompareAndCleanTests(unittest.TestCase):
    def test_compare_two_contexts(self):
        ctxs = [
            {
                'type': 'pr', 'title': 'fix hccl hang', 'url': 'https://x/1',
                'state': 'open', 'body': 'HCCL 507049 on NPU allreduce',
                'files': [{'file': 'hccl_ops.cpp'}, {'file': 'common.h'}],
                'comments': [{'body': 'a'}], 'reviews': [], 'warnings': [],
            },
            {
                'type': 'issue', 'title': 'codecheck fail', 'url': 'https://x/2',
                'state': 'open', 'body': 'ERROR Codecheck on kernel',
                'files': [{'file': 'common.h'}, {'file': 'kernel.cpp'}],
                'comments': [], 'reviews': [], 'warnings': [],
            },
        ]
        result = compare_contexts(ctxs)
        self.assertTrue(result['ok'])
        self.assertEqual(result['count'], 2)
        self.assertIn('common.h', result['shared_files'])
        md = format_compare_report(result)
        self.assertIn('多链接对比', md)
        self.assertIn('共同改动文件', md)

    def test_compare_needs_two(self):
        result = compare_contexts([{'type': 'pr', 'title': 'only'}])
        self.assertFalse(result['ok'])

    def test_clean_sessions_keeps_newest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch('scripts.session_store.home_dir', return_value=root), \
                    patch('scripts.session_store.ensure_home', return_value=root):
                sdir = root / 'sessions'
                sdir.mkdir()
                for i in range(4):
                    p = sdir / f'session-{i}.json'
                    p.write_text('{"history":[],"saved_at":"%d"}' % i, encoding='utf-8')
                    # ensure mtime order
                    import time
                    time.sleep(0.02)
                result = clean_sessions(keep=2)
                self.assertEqual(len(result['kept']), 2)
                self.assertEqual(len(result['deleted']), 2)
                self.assertEqual(len(list(sdir.glob('session-*.json'))), 2)

    def test_new_then_back(self):
        with tempfile.TemporaryDirectory() as td:
            with patch('scripts.session_store.home_dir', return_value=Path(td)), \
                    patch('scripts.session_store.ensure_home', return_value=Path(td)):
                a = ConversationAgent(MagicMock(), MagicMock(), MagicMock())
                a.history = [
                    {'role': 'user', 'content': 'old-q'},
                    {'role': 'assistant', 'content': 'old-a'},
                ]
                path = start_new_conversation(a, 'topic-a')
                self.assertTrue(path.is_file())
                self.assertEqual(a.history, [])
                data = load_session('previous')
                other = ConversationAgent(MagicMock(), MagicMock(), MagicMock())
                apply_to_agent(other, data)
                self.assertEqual(other.history[0]['content'], 'old-q')
                rows = list_sessions()
                self.assertTrue(any(r['name'] == 'topic-a' for r in rows))
                by_idx = load_session('1')
                self.assertIn('history', by_idx)


if __name__ == '__main__':
    unittest.main()
