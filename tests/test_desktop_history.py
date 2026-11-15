# -*- coding: utf-8 -*-
"""Windows 桌面版历史会话（cvapp.sessions）的纯逻辑测试。

只测数据层与格式化：它不 import tkinter，所以无头环境也能跑。
CLI 调用用桩替换，测试不依赖真实会话目录。
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
WIN = ROOT / 'desktop-app' / 'win'
if str(WIN) not in sys.path:
    sys.path.insert(0, str(WIN))

from cvapp import sessions  # noqa: E402


def row(**kw):
    base = {
        'name': 'x', 'title': '标题', 'saved_at': '2026-11-13T10:00:00+08:00',
        'turns': '1', 'summary': '最后一句', 'repository': '', 'status': 'completed',
    }
    base.update(kw)
    return base


class FakeProc:
    def __init__(self, stdout='', stderr='', code=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = code


class FormatTests(unittest.TestCase):
    def test_clip_truncates_with_ellipsis(self):
        self.assertEqual(sessions.clip('一' * 30, 24), '一' * 24 + '…')
        self.assertEqual(sessions.clip('短标题', 24), '短标题')

    def test_clip_flattens_whitespace(self):
        self.assertEqual(sessions.clip('a\n  b\tc', 24), 'a b c')

    def test_title_falls_back_to_name(self):
        self.assertEqual(sessions.format_title(row(title='', name='desktop-1')), 'desktop-1')
        self.assertEqual(sessions.format_title(row(title='', name='')), '（未命名会话）')

    def test_meta_is_time_plus_turns(self):
        self.assertEqual(sessions.format_meta(row()), '2026-11-13 10:00 · 1 轮')

    def test_meta_marks_failed_session(self):
        self.assertIn('回复失败', sessions.format_meta(row(status='failed', turns='2')))

    def test_meta_without_time(self):
        self.assertEqual(sessions.format_meta(row(saved_at='', turns='0')), '时间未知')

    def test_preview_uses_summary(self):
        self.assertEqual(sessions.format_preview(row(summary='已完成')), '已完成')
        self.assertEqual(sessions.format_preview(row(summary='')), '（空对话）')

    def test_turns_of_tolerates_garbage(self):
        self.assertEqual(sessions.turns_of({'turns': '3'}), 3)
        self.assertEqual(sessions.turns_of({'turns': 'x'}), 0)
        self.assertEqual(sessions.turns_of({}), 0)

    def test_keep_row_drops_empty_and_corrupt(self):
        self.assertTrue(sessions.keep_row(row()))
        self.assertFalse(sessions.keep_row(row(turns='0', summary='')))
        self.assertFalse(sessions.keep_row(
            row(turns='0', summary='', saved_at='', status='failed')))

    def test_sort_rows_by_saved_at_desc(self):
        rows = [
            row(name='old', saved_at='2026-11-12T10:00:00+08:00'),
            row(name='bad', saved_at=''),
            row(name='new', saved_at='2026-11-13T09:00:00+08:00'),
        ]
        self.assertEqual([r['name'] for r in sessions.sort_rows(rows)], ['new', 'old', 'bad'])

    def test_sort_rows_handles_mixed_timezone(self):
        rows = [
            row(name='utc', saved_at='2026-11-13T01:00:00+00:00'),
            row(name='local', saved_at='2026-11-13T10:00:00+08:00'),
        ]
        # 01:00Z = 09:00+08:00，所以 local 更新
        self.assertEqual([r['name'] for r in sessions.sort_rows(rows)], ['local', 'utc'])


class RenderTests(unittest.TestCase):
    def test_render_header_roles_and_status(self):
        session = {
            'name': 'desktop-1', 'title': '修复 401', 'repository': r'D:\repo',
            'saved_at': '2026-11-13T10:00:00+08:00',
            'messages': [
                {'role': 'user', 'content': '问一句', 'status': 'completed'},
                {'role': 'assistant', 'content': '答一句', 'status': 'completed'},
                {'role': 'assistant', 'content': '', 'status': 'failed'},
            ],
        }
        chunks = sessions.render_chunks(session, '2026-11-13 16:00')
        text = ''.join(piece for piece, _tag in chunks)
        tags = [tag for _piece, tag in chunks]
        self.assertIn('历史会话：修复 401', text)
        self.assertIn(r'仓库 D:\repo', text)
        self.assertIn('恢复于 2026-11-13 16:00', text)
        self.assertIn('● 你', text)
        self.assertEqual(text.count('● Agent'), 2)
        self.assertIn('（回复失败）', text)
        self.assertIn('user', tags)
        self.assertIn('agent', tags)
        self.assertIn('err', tags)

    def test_render_running_marker(self):
        session = {'name': 'n', 'messages': [
            {'role': 'user', 'content': 'q', 'status': 'running'}]}
        text = ''.join(piece for piece, _ in sessions.render_chunks(session))
        self.assertIn('（进行中…）', text)

    def test_render_empty_session(self):
        text = ''.join(piece for piece, _ in sessions.render_chunks({'messages': []}))
        self.assertIn('没有保存任何消息', text)

    def test_render_skips_unknown_roles(self):
        session = {'name': 'n', 'messages': [
            {'role': 'system', 'content': '不该出现'}]}
        text = ''.join(piece for piece, _ in sessions.render_chunks(session))
        self.assertNotIn('不该出现', text)


class CliBoundaryTests(unittest.TestCase):
    def test_list_filters_empty_rows(self):
        payload = {'ok': True, 'sessions': [
            row(name='keep'), row(name='empty', turns='0', summary='')]}
        with patch.object(sessions.subprocess, 'run',
                          return_value=FakeProc(json.dumps(payload))):
            names = [r['name'] for r in sessions.list_sessions()]
        self.assertEqual(names, ['keep'])

    def test_list_passes_query(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured['cmd'] = cmd
            return FakeProc(json.dumps({'ok': True, 'sessions': []}))

        with patch.object(sessions.subprocess, 'run', side_effect=fake_run):
            sessions.list_sessions('根因')
        self.assertIn('--query', captured['cmd'])
        self.assertIn('根因', captured['cmd'])

    def test_show_unwraps_session(self):
        payload = {'ok': True, 'session': {
            'name': 'a', 'title': 't', 'messages': [{'role': 'user', 'content': 'q'}]}}
        with patch.object(sessions.subprocess, 'run',
                          return_value=FakeProc(json.dumps(payload))):
            session = sessions.show_session('a')
        self.assertEqual(session['name'], 'a')
        self.assertEqual(len(session['messages']), 1)

    def test_error_payload_becomes_session_error(self):
        payload = {'ok': False, 'error': '未找到会话: nope'}
        with patch.object(sessions.subprocess, 'run',
                          return_value=FakeProc(json.dumps(payload))):
            with self.assertRaises(sessions.SessionError) as ctx:
                sessions.show_session('nope')
        self.assertIn('未找到会话', str(ctx.exception))

    def test_non_json_output_mentions_stderr(self):
        with patch.object(sessions.subprocess, 'run',
                          return_value=FakeProc('Traceback...', 'ModuleNotFoundError: x', 1)):
            with self.assertRaises(sessions.SessionError) as ctx:
                sessions.delete_session('x')
        self.assertIn('ModuleNotFoundError', str(ctx.exception))

    def test_empty_output_falls_back_to_exit_code(self):
        with patch.object(sessions.subprocess, 'run',
                          return_value=FakeProc('', '', 3)):
            with self.assertRaises(sessions.SessionError) as ctx:
                sessions.list_sessions()
        self.assertIn('3', str(ctx.exception))

    def test_timeout_becomes_session_error(self):
        import subprocess
        with patch.object(sessions.subprocess, 'run',
                          side_effect=subprocess.TimeoutExpired('cmd', 60)):
            with self.assertRaises(sessions.SessionError) as ctx:
                sessions.list_sessions()
        self.assertIn('超时', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
