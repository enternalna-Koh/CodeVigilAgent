"""桌面上下文边界：真实解释器进程及隐藏 Tk 窗口回归。"""
import gc
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'desktop-app' / 'win'))
sys.path.insert(0, str(ROOT / 'desktop_py'))
try:
    import tkinter as tk
except ModuleNotFoundError:
    tk = None
if tk is not None:
    import app as desktop
    import cli_runtime
    from session_controller import canonical_repo
    from cvapp.shell import Shell
    from cvapp.history_panel import HistoryPanel
    from cvapp.features import chat as legacy_chat


@unittest.skipIf(tk is None, '当前 Python 未安装 tkinter')
class DirectInterpreterTests(unittest.TestCase):
    def test_real_launch_timeout_cancel_and_close_without_launcher(self):
        # 不替换 Popen、cli_prefix 或 sys.executable，走实际 run_cli 启动路径。
        gc.collect()
        enabled = gc.isenabled()
        gc.disable()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'ascend_cli.py').write_text(
                    'import json, os, sys, threading\n'
                    'from pathlib import Path\n'
                    'Path("ready").write_text(str(os.getpid()))\n'
                    'print(json.dumps({"pid": os.getpid(), "exe": sys.executable}), flush=True)\n'
                    'threading.Event().wait(60)\n', encoding='utf-8')
                for mode in ('timeout', 'cancel', 'close'):
                    with self.subTest(mode=mode), patch.object(cli_runtime, 'ROOT', root):
                        ready = root / 'ready'
                        ready.unlink(missing_ok=True)
                        runtime = cli_runtime.CliRuntime()
                        runtime._init_runtime()
                        runtime.proc = None
                        runtime.cancel_flag = False
                        runtime._running = True
                        runtime.set_status = Mock()
                        runtime._conversation_epoch = 0
                        runtime.stop_chat_timing = Mock()
                        runtime._cancel_scroll_job = Mock()
                        runtime.tk = SimpleNamespace(call=lambda *args: ())
                        runtime.destroy = Mock()
                        result = queue.Queue()
                        errors = queue.Queue()

                        def work():
                            try:
                                result.put(runtime.run_cli('review', timeout=2 if mode == 'timeout' else 20))
                            except Exception as exc:
                                errors.put(exc)

                        thread = threading.Thread(target=work)
                        thread.start()
                        proc = None
                        try:
                            deadline = time.monotonic() + 5
                            while time.monotonic() < deadline:
                                with runtime._process_lock:
                                    proc = runtime.proc
                                if proc is not None and ready.exists() and ready.stat().st_size:
                                    break
                                threading.Event().wait(0.01)
                            self.assertIsNotNone(proc, list(errors.queue))
                            self.assertTrue(ready.exists())
                            self.assertEqual(int(ready.read_text()), proc.pid)
                            self.assertEqual(Path(cli_runtime.cli_prefix()[0]), Path(sys.executable))
                            if mode == 'cancel':
                                runtime.cancel()
                            elif mode == 'close':
                                runtime._on_close()
                            thread.join(8)
                            self.assertFalse(thread.is_alive())
                            self.assertTrue(errors.empty(), list(errors.queue))
                            code, out, err = result.get_nowait()
                            self.assertNotEqual(code, 0)
                            self.assertEqual(json.loads(out)['pid'], proc.pid)
                            self.assertEqual(Path(json.loads(out)['exe']), Path(sys.executable))
                            self.assertIsNotNone(proc.poll())
                            self.assertIsNone(runtime.proc)
                            self.assertEqual(runtime._processes, set())
                            if mode == 'timeout':
                                self.assertIn('超时', err)
                        finally:
                            if proc is not None and proc.poll() is None:
                                proc.kill()
                                proc.wait(timeout=3)
                            thread.join(5)
        finally:
            if enabled:
                gc.enable()


@unittest.skipIf(tk is None, '当前 Python 未安装 tkinter')
class RepositoryBindingTests(unittest.TestCase):
    def setUp(self):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'REVIEWAGENT_HOME': self.tmp.name})
        self.env.start()
        with patch.object(desktop.App, 'load_sessions'), patch.object(desktop.App, 'show_welcome'):
            self.app = desktop.App()
            self.app.withdraw()
        for job in self.app.tk.call('after', 'info'):
            self.app.after_cancel(job)
        self.jobs = []
        self.app.run_async = lambda work, done, label, **kw: self.jobs.append((work, done, label))
        self.a = Path(self.tmp.name) / 'a'
        self.b = Path(self.tmp.name) / 'b'
        self.a.mkdir()
        self.b.mkdir()
        self.app.repo_var.set(str(self.a))

    def tearDown(self):
        self.app._on_close()
        self.env.stop()
        self.tmp.cleanup()

    def bind_history(self, cached=False):
        session = {'repository': str(self.a), 'messages': [{'role': 'assistant', 'content': 'A history'}]}
        if cached:
            self.app._remember_session('history-a', session, {'ok': True}, '')
        self.app.show_session('history-a')
        if not cached:
            self.jobs[-1][1]((0, json.dumps({'session': session}), ''))
        self.assertEqual(self.app._session_repository, canonical_repo(str(self.a)))

    def assert_blocked(self):
        self.app.input.insert('1.0', '保留问题')
        before = len(self.jobs)
        messages = list(self.app.messages)
        self.app.send()
        self.app.review_online()
        self.app.review_offline()
        self.assertEqual(len(self.jobs), before)
        self.assertEqual(self.app.input.get('1.0', 'end').strip(), '保留问题')
        self.assertEqual(self.app.messages, messages)
        self.assertIn('仓库已改变', self.app.status_var.get())

    def test_typed_repo_cannot_reuse_fresh_session(self):
        self.app.input.insert('1.0', 'first')
        self.app.send()
        session = self.app.session_name
        self.app.repo_var.set(str(self.b))
        self.assert_blocked()
        self.assertEqual(self.app.session_name, session)

    def test_history_binding_blocks_typed_repo_for_cached_and_uncached(self):
        for cached in (False, True):
            with self.subTest(cached=cached):
                self.app.new_conversation()
                self.bind_history(cached)
                self.app.repo_var.set(str(self.b))
                self.assert_blocked()
                self.assertEqual(self.app.session_name, 'history-a')

    def test_equivalent_path_and_restoring_repo_keep_session(self):
        self.bind_history()
        self.app.repo_var.set(str(self.a / '..' / 'a'))
        self.app.input.insert('1.0', 'follow up')
        self.app.send()
        with patch.object(self.app, 'run_cli', return_value=(0, '{}', '')) as cli:
            self.jobs[-1][0]()
        args = cli.call_args.args
        self.assertEqual(args[args.index('--session') + 1], 'history-a')
        self.assertEqual(args[args.index('--repository') + 1], canonical_repo(str(self.a)))

    @unittest.skipUnless(os.name == 'nt', 'Windows 路径大小写规则')
    def test_windows_case_alias_keeps_bound_repository(self):
        self.bind_history()
        self.app.repo_var.set(str(self.a).swapcase())
        self.app.input.insert('1.0', 'follow up')
        before = len(self.jobs)
        self.app.send()
        self.assertEqual(len(self.jobs), before + 1)
        self.assertEqual(self.app.session_name, 'history-a')

    def test_deleting_active_session_releases_binding(self):
        self.bind_history()
        self.app.delete_session('history-a')
        self.assertIsNone(self.app.session_name)
        self.assertIsNone(self.app._session_repository)

    def test_choose_repo_and_explicit_new_session_release_binding(self):
        self.bind_history()
        with patch('session_controller.filedialog.askdirectory', return_value=str(self.b)):
            self.app.choose_repo()
        self.assertIsNone(self.app.session_name)
        self.assertIsNone(self.app._session_repository)
        self.app.input.insert('1.0', 'B question')
        self.app.send()
        self.assertNotEqual(self.app.session_name, 'history-a')
        self.assertEqual(self.app._session_repository, canonical_repo(str(self.b)))
        self.app.new_conversation()
        self.assertIsNone(self.app._session_repository)


@unittest.skipIf(tk is None, '当前 Python 未安装 tkinter')
class LegacyPendingHistoryTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.tmp = tempfile.TemporaryDirectory()
        with patch('cvapp.shell.config.load_last_repo', return_value=self.tmp.name), \
                patch.object(Shell, '_welcome'):
            self.app = Shell(self.root, legacy_chat.FEATURES)
        with patch.object(HistoryPanel, 'refresh'):
            self.panel = HistoryPanel(self.root, self.app)
        self.app.panel_host.panels['history.panel'] = self.panel
        self.jobs = []
        self.panel._async = lambda work, done: self.jobs.append((work, done))
        self.app.run_cli = Mock()
        self.app.chat_session = 'old-session'
        self.app.chat_repository = os.path.realpath(self.tmp.name)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def restored(self, name):
        return {'name': name, 'repository': self.tmp.name, 'messages': [
            {'role': 'assistant', 'content': name}]}

    def test_real_submit_during_restore_preserves_input_and_then_targets_history(self):
        self.panel._open('target')
        token = self.app._pending_history
        self.app.entry.insert(0, 'follow up')
        self.app.submit()
        self.app.run_cli.assert_not_called()
        self.assertEqual(self.app.entry.get(), 'follow up')
        self.assertIs(self.app._pending_history, token)
        with patch('cvapp.history_panel.config.save_last_repo'):
            self.jobs[-1][1](self.restored('target'), '')
        self.assertIsNone(self.app._pending_history)
        self.app.submit()
        args = self.app.run_cli.call_args.args[0]
        self.assertEqual(args[args.index('--session') + 1], 'target')
        self.assertEqual(self.app.entry.get(), '')

    def test_failure_releases_pending_and_preserves_previous_identity(self):
        self.panel._open('missing')
        with patch('cvapp.history_panel.messagebox.showerror'):
            self.jobs[-1][1](None, '读取失败')
        self.assertIsNone(self.app._pending_history)
        self.assertEqual(self.app.chat_session, 'old-session')
        self.app.entry.insert(0, 'question')
        self.app.submit()
        self.app.run_cli.assert_called_once()

    def test_stale_completion_cannot_release_new_pending_after_reset(self):
        self.panel._open('old')
        stale = self.jobs[-1][1]
        self.app.reset_session()
        self.assertIsNone(self.app._pending_history)
        self.panel._open('new')
        token = self.app._pending_history
        stale(self.restored('old'), '')
        self.assertIs(self.app._pending_history, token)
        with patch('cvapp.history_panel.config.save_last_repo'):
            self.jobs[-1][1](self.restored('new'), '')
        self.assertEqual(self.app.chat_session, 'new')
        self.assertIsNone(self.app._pending_history)

    def test_overlapping_open_failure_cannot_clear_new_pending(self):
        self.panel._open('old')
        stale = self.jobs[-1][1]
        self.panel._open('new')
        token = self.app._pending_history
        stale(None, '旧请求失败')
        self.assertIs(self.app._pending_history, token)
        self.assertEqual(self.panel.selected, 'new')
        with patch('cvapp.history_panel.config.save_last_repo'):
            self.jobs[-1][1](self.restored('new'), '')
        self.assertIsNone(self.app._pending_history)
        self.assertEqual(self.app.chat_session, 'new')

    def test_cancel_selection_and_close_release_pending(self):
        self.panel._open('cancelled')
        stale = self.jobs[-1][1]
        self.panel.reset_selection()
        self.assertIsNone(self.app._pending_history)
        stale(self.restored('cancelled'), '')
        self.assertEqual(self.app.chat_session, 'old-session')
        self.panel._open('closing')
        self.panel.close()
        self.assertIsNone(self.app._pending_history)


if __name__ == '__main__':
    unittest.main()
