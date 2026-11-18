"""旧版桌面生命周期回归：真实方法配内存控件，不创建 Tk 窗口。"""
from __future__ import annotations

import io
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop-app' / 'win'))

try:
    from cvapp.chat_section import ChatSection
    from cvapp.features.history import new_session
    from cvapp.features.output import _clear
    from cvapp.history_panel import HistoryPanel
    from cvapp.runner import Runner
    from cvapp.shell import Shell
    HAS_TK = True
except ModuleNotFoundError as exc:
    if exc.name != 'tkinter':
        raise
    HAS_TK = False


class MemoryRoot:
    def __init__(self):
        self.jobs = {}
        self.serial = 0
        self.protocols = {}
        self.destroyed = False
        self.tk = SimpleNamespace(call=lambda *_: tuple(self.jobs))

    def after(self, delay, callback):
        self.serial += 1
        self.jobs[str(self.serial)] = callback
        return str(self.serial)

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run(self, callback):
        for job, work in tuple(self.jobs.items()):
            if work == callback:
                self.jobs.pop(job)
        callback()

    def protocol(self, name, callback):
        self.protocols[name] = callback

    def destroy(self):
        self.destroyed = True


class MemoryOutput:
    def __init__(self):
        self.lines = []
        self.text = SimpleNamespace(yview_moveto=lambda *_: None)

    def append(self, text, tag=None):
        self.lines.append((text, tag))

    def clear(self):
        self.lines.clear()


class MemoryPane:
    def __init__(self):
        self.messages = []

    def add_user(self, text):
        self.messages.append(('user', text))

    def add_agent(self, text):
        self.messages.append(('agent', text))

    def finish_user(self, *args):
        pass

    def set_header(self, *args):
        pass

    def clear(self):
        self.messages.clear()


def make_shell(busy=False):
    app = Shell.__new__(Shell)
    app.root = MemoryRoot()
    app.runner = SimpleNamespace(busy=busy, close=Mock())
    app._session_generation = 0
    app.current_session = 'old'
    app.session_title = '旧会话'
    app.chat_session = 'old'
    app.chat_repository = 'old-repo'
    app.output = MemoryOutput()
    app.status_var = SimpleNamespace(set=Mock())
    app.repo_var = SimpleNamespace(set=Mock(), get=lambda: '')
    app.features = []
    app.buttons = {}
    app.panel_host = SimpleNamespace(panels={}, refresh_visible=Mock())
    section = ChatSection.__new__(ChatSection)
    section.shell = app
    section.pane = MemoryPane()
    section._buffer = None
    section._cancelled = False
    app.chat_section = section
    app.chat = section.pane
    return app


def make_panel(app):
    panel = HistoryPanel.__new__(HistoryPanel)
    panel.app = app
    panel.rows = []
    panel.cards = {}
    panel.selected = 'old'
    panel._generation = 0
    panel._open_generation = 0
    panel._open_token = None
    panel._closed = False
    panel._pending = 0
    panel._pump = None
    panel._search_job = None
    panel._queue = queue.Queue()
    panel.count_var = SimpleNamespace(set=Mock())
    panel.after = app.root.after
    panel.after_cancel = app.root.after_cancel
    pending = []
    panel._async = lambda work, done: pending.append((work, done))
    app.panels['history.panel'] = panel
    return panel, pending


def session(name):
    return {'name': name, 'title': name, 'messages': [{'role': 'user', 'content': name}]}


@unittest.skipUnless(HAS_TK, '当前 Python 未安装 tkinter')
class RunnerIsolationTests(unittest.TestCase):
    def make_runner(self, done=None):
        root = MemoryRoot()
        output, finished = [], []
        runner = Runner(root, output.append, lambda *_: None,
                        done or finished.append)
        self.addCleanup(runner.close)
        return runner, root, output, finished

    def finish_worker(self, runner):
        runner._proc.wait(timeout=10)
        # join 真实 reader，精确制造「已退出但界面尚未消费」窗口。
        for thread in threading.enumerate():
            if getattr(thread, '_target', None) == runner._reader:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())

    def test_exited_process_stays_busy_until_output_and_done_are_consumed(self):
        runner, root, output, finished = self.make_runner()
        old, new = [], []
        self.assertTrue(runner.start([sys.executable, '-c', "print('old')"], str(ROOT), '旧任务', sink=old.append))
        self.finish_worker(runner)
        self.assertTrue(runner.busy)
        self.assertFalse(runner.start([sys.executable, '-c', "print('new')"], str(ROOT), '新任务', sink=new.append))
        runner._root.run(runner._tick)
        self.assertFalse(runner.busy)
        self.assertEqual(old, ['old\n'])
        self.assertEqual(new, [])
        self.assertEqual(finished, [0])
        self.assertTrue(runner.start([sys.executable, '-c', "print('new')"], str(ROOT), '新任务', sink=new.append))
        self.finish_worker(runner)
        runner._root.run(runner._tick)
        self.assertEqual(new, ['new\n'])
        self.assertEqual(finished, [0, 0])
        runner.close()
        self.assertEqual(root.jobs, {})

    def test_done_callback_cannot_reenter_or_finish_another_chat_buffer(self):
        app = make_shell()
        attempted = []

        def done(code):
            attempted.append(app.runner.busy)
            attempted.append(app.reset_session(clear_output=True))
            attempted.append(app.runner.start([sys.executable, '-c', 'pass'], str(ROOT), '重入'))
            app._on_done(code)

        runner, _, _, _ = self.make_runner(done)
        app.runner = runner
        buffer = app.chat_section.begin('旧问题')
        runner.start([sys.executable, '-c', "print('old reply')"], str(ROOT), '任务', sink=buffer.append)
        self.finish_worker(runner)
        runner._root.run(runner._tick)
        self.assertEqual(attempted, [True, False, False])
        self.assertEqual(app.chat.messages, [('user', '旧问题'), ('agent', 'old reply')])
        self.assertIsNone(app.chat_section._buffer)
        runner.close()

    def test_stale_events_are_dropped_and_reentrant_tick_keeps_task_busy(self):
        observed = []
        runner, root, _, finished = self.make_runner()

        def sink(line):
            observed.append(line)
            runner._tick()
            observed.append(runner.busy)

        runner.start([sys.executable, '-c', "print('owned')"], str(ROOT), '任务', sink=sink)
        self.finish_worker(runner)
        runner._queue.put((runner._active - 1, observed.append, 'out', 'stale'))
        runner._queue.put((runner._active - 1, observed.append, 'done', 99))
        root.run(runner._tick)
        self.assertEqual(observed, ['owned\n', True])
        self.assertEqual(finished, [0])
        self.assertEqual(len(root.jobs), 1)

    def test_running_cancel_is_reaped_before_done_releases_busy(self):
        runner, root, _, finished = self.make_runner()
        ready = threading.Event()
        original_put = runner._queue.put

        def put(event):
            original_put(event)
            if 'ready' in str(event):
                ready.set()

        runner._queue.put = put
        runner.start([sys.executable, '-u', '-c',
                      "import threading; print('ready', flush=True); threading.Event().wait()"],
                     str(ROOT), '任务')
        self.assertTrue(ready.wait(5))
        proc = runner._proc
        runner.cancel()
        self.finish_worker(runner)
        self.assertTrue(runner.busy)
        root.run(runner._tick)
        self.assertFalse(runner.busy)
        self.assertIsNotNone(proc.returncode)
        self.assertEqual(finished, [proc.returncode])

    def test_start_failure_uses_requested_sink_and_leaves_runner_idle(self):
        runner, _, output, _ = self.make_runner()
        sink = []
        with patch('cvapp.runner.subprocess.Popen', side_effect=OSError('fixture')):
            self.assertFalse(runner.start(['fixture'], str(ROOT), '失败', sink=sink.append))
        self.assertFalse(runner.busy)
        self.assertEqual(output, [])
        self.assertIn('fixture', ''.join(sink))
        runner.close()

    def test_cancel_after_process_exit_is_safe_while_done_is_pending(self):
        runner, _, _, finished = self.make_runner()
        runner.start([sys.executable, '-c', 'pass'], str(ROOT), '任务')
        self.finish_worker(runner)
        runner.cancel()
        self.assertTrue(runner.busy)
        runner._root.run(runner._tick)
        self.assertEqual(finished, [0])
        runner.close()


@unittest.skipUnless(HAS_TK, '当前 Python 未安装 tkinter')
class HistoryIsolationTests(unittest.TestCase):
    def test_real_async_queue_drains_latest_result_and_stops_after_close(self):
        app = make_shell()
        panel, _ = make_panel(app)
        panel._async = HistoryPanel._async.__get__(panel)
        enqueued = threading.Event()
        original_put = panel._queue.put

        def put(event):
            original_put(event)
            enqueued.set()

        panel._queue.put = put
        with patch('cvapp.history_panel.sessions.show_session', return_value=session('a')):
            panel._open('a')
            self.assertTrue(enqueued.wait(5))
        app.root.run(panel._drain)
        self.assertEqual(app.current_session, 'a')
        self.assertEqual(panel._pending, 0)
        self.assertEqual(app.root.jobs, {})
        panel._queue.put((Mock(side_effect=AssertionError('关闭后不得回调')), None, ''))
        panel.close()
        panel._drain()
        panel._schedule()
        self.assertEqual(app.root.jobs, {})

    def test_reversed_open_results_and_stale_errors_do_not_override_latest(self):
        app = make_shell()
        panel, pending = make_panel(app)
        panel._open('a')
        panel._open('b')
        pending[1][1](session('b'), '')
        snapshot = list(app.output.lines)
        with patch('cvapp.history_panel.messagebox.showerror') as error:
            pending[0][1](session('a'), '')
            pending[0][1](None, '旧错误')
        error.assert_not_called()
        self.assertEqual(app.current_session, 'b')
        self.assertEqual(app.chat_session, 'b')
        self.assertEqual(panel.selected, 'b')
        self.assertEqual(app.output.lines, snapshot)

    def test_same_name_repeated_open_still_uses_request_generation(self):
        app = make_shell()
        panel, pending = make_panel(app)
        panel._open('a')
        panel._open('a')
        pending[1][1](session('a'), '')
        snapshot = list(app.output.lines)
        pending[0][1](session('stale'), '')
        self.assertEqual(app.current_session, 'a')
        self.assertEqual(app.output.lines, snapshot)

    def test_every_new_session_entry_invalidates_pending_history(self):
        for action in (lambda a, p: a.reset_session(True),
                       lambda a, p: new_session(a),
                       lambda a, p: p.new_session(),
                       lambda a, p: _clear(a)):
            with self.subTest(action=action):
                app = make_shell()
                panel, pending = make_panel(app)
                panel.refresh = Mock()
                panel._open('a')
                action(app, panel)
                pending[0][1](session('a'), '')
                self.assertEqual(app.current_session, '')
                self.assertIsNone(app.chat_session)
                self.assertEqual(panel.selected, '')

    def test_every_new_session_entry_is_rejected_while_busy(self):
        for action in (lambda a, p: a.reset_session(True),
                       lambda a, p: new_session(a),
                       lambda a, p: p.new_session(),
                       lambda a, p: _clear(a)):
            with self.subTest(action=action):
                app = make_shell(busy=True)
                panel, pending = make_panel(app)
                panel.refresh = Mock()
                app.chat.add_user('保留气泡')
                action(app, panel)
                self.assertEqual(app.current_session, 'old')
                self.assertEqual(app.chat_session, 'old')
                self.assertEqual(panel.selected, 'old')
                self.assertEqual(app.chat.messages, [('user', '保留气泡')])
                panel.refresh.assert_not_called()

    def test_history_cannot_open_or_delete_during_task(self):
        app = make_shell(busy=True)
        panel, pending = make_panel(app)
        with patch('cvapp.history_panel.sessions.delete_session') as delete, \
                patch('cvapp.history_panel.messagebox.askyesno', return_value=True):
            panel._open('other')
            panel.delete_selected()
        self.assertEqual(pending, [])
        self.assertEqual(panel.selected, 'old')
        delete.assert_not_called()

    def test_task_start_invalidates_history_even_if_task_already_finished(self):
        app = make_shell()
        panel, pending = make_panel(app)
        panel._open('a')
        app._on_start('任务')
        app._on_done(0)
        pending[0][1](session('a'), '')
        self.assertEqual(app.current_session, 'old')
        self.assertNotEqual(app.chat_session, 'a')

    def test_latest_error_is_reported_but_reset_selection_invalidates_old_error(self):
        app = make_shell()
        panel, pending = make_panel(app)
        panel._open('a')
        with patch('cvapp.history_panel.messagebox.showerror') as error:
            pending[0][1](None, '当前错误')
            self.assertEqual(error.call_count, 1)
            panel._open('b')
            panel.reset_selection()
            pending[1][1](None, '过期错误')
            self.assertEqual(error.call_count, 1)


@unittest.skipUnless(HAS_TK, '当前 Python 未安装 tkinter')
class CloseTests(unittest.TestCase):
    def test_shell_registers_window_close_without_creating_gui(self):
        root = MemoryRoot()
        root.title = root.geometry = root.minsize = root.configure = Mock()
        root.winfo_screenwidth = lambda: 1200
        root.winfo_screenheight = lambda: 900
        with patch('cvapp.shell.tk.StringVar'), \
                patch('cvapp.shell.config.load_last_repo', return_value=''), \
                patch('cvapp.shell.theme.pick_mono_font'), \
                patch.object(Shell, '_build'), patch.object(Shell, '_bind_shortcuts'), \
                patch.object(Shell, '_welcome'):
            app = Shell(root, [])
        app.panel_host = SimpleNamespace(panels={})
        self.assertIn('WM_DELETE_WINDOW', root.protocols)
        root.protocols['WM_DELETE_WINDOW']()
        self.assertTrue(root.destroyed)
        self.assertEqual(root.jobs, {})
        self.assertFalse(app.runner.start([sys.executable, '-c', 'pass'], str(ROOT), '关闭后'))

    def test_close_stops_history_timers_and_ignores_late_results(self):
        app = make_shell()
        panel, pending = make_panel(app)
        panel._open('a')
        panel._pump = app.root.after(60, panel._drain)
        panel._search_job = app.root.after(300, panel.refresh)
        app.root.after(20, lambda: None)
        app.close()
        app.close()
        app.runner.close.assert_called_once()
        pending[0][1](session('a'), '')
        self.assertEqual(app.current_session, 'old')
        self.assertTrue(app.root.destroyed)
        self.assertEqual(app.root.jobs, {})
        self.assertIsNone(panel._pump)
        self.assertIsNone(panel._search_job)

    def test_close_reaps_real_child_in_isolated_python_process(self):
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--close-probe'],
                                cwd=ROOT, capture_output=True, text=True, timeout=30,
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('进程已回收，定时器已停止', result.stdout)

    def test_close_escalates_terminate_timeout_to_kill_and_wait(self):
        root = MemoryRoot()
        proc = SimpleNamespace(stdout=io.StringIO(''), terminate=Mock(), kill=Mock(),
                               poll=lambda: None,
                               wait=Mock(side_effect=[subprocess.TimeoutExpired('fixture', 1), 0]))
        runner = Runner(root, Mock(), Mock(), Mock())
        with patch('cvapp.runner.subprocess.Popen', return_value=proc), \
                patch('cvapp.runner.threading.Thread'):
            runner.start(['fixture'], str(ROOT), '任务')
        runner.close()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_count, 2)
        self.assertEqual(root.jobs, {})


def close_probe():
    app = make_shell()
    root = app.root
    done = Mock()
    app.runner = Runner(root, Mock(), Mock(), done)
    ready = threading.Event()
    original_put = app.runner._queue.put

    def put(event):
        original_put(event)
        if 'ready' in str(event):
            ready.set()

    app.runner._queue.put = put
    try:
        app.runner.start([sys.executable, '-u', '-c',
                          "import threading; print('ready', flush=True); threading.Event().wait()"],
                         str(ROOT), '子进程')
        proc = app.runner._proc
        assert ready.wait(5)
        assert proc.poll() is None
        app.close()
        assert proc.poll() is not None
        assert not app.runner._thread.is_alive()
        assert not root.jobs
        assert root.destroyed
        assert not app.runner.busy
        done.assert_not_called()
        print('进程已回收，定时器已停止')
    finally:
        proc = app.runner._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == '__main__':
    if '--close-probe' in sys.argv:
        close_probe()
    else:
        unittest.main()
