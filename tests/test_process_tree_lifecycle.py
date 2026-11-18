"""真实无文件进程回归：直接进程结束后，后代不能继续运行。"""
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "desktop_py"))
sys.path.insert(0, str(ROOT / "desktop-app" / "win"))
from scripts import process_tree

# 子进程持有本地连接；退出才会产生EOF，不靠PID复用或计时猜测存活状态。
CHILD = ("import socket,sys; s=socket.create_connection(('127.0.0.1',int(sys.argv[1]))); "
         "s.sendall(b'ready'); s.recv(1)")
PARENT = ("import subprocess,sys,threading; "
          "p=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]], "
          "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
          "print('started',flush=True); threading.Event().wait(30)")


class ProcessTreeTests(unittest.TestCase):
    def setUp(self):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.server.settimeout(8)
        self.addCleanup(self.server.close)
        self.port = str(self.server.getsockname()[1])

    def command(self):
        return [sys.executable, "-c", PARENT, CHILD, self.port]

    def connected(self):
        conn, _ = self.server.accept()
        self.addCleanup(conn.close)
        conn.settimeout(5)
        self.assertEqual(conn.recv(5), b"ready")
        # 失败清理也只关闭本测试连接，让测试后代自行退出。
        return conn

    def assert_disconnected(self, conn):
        try:
            self.assertEqual(conn.recv(1), b"")
        except ConnectionResetError:
            pass  # Windows强制终止进程时以RST而非EOF关闭连接。

    def test_release_serializes_with_late_signals(self):
        proc = SimpleNamespace(_tree_lock=threading.RLock(), _tree_released=False,
                               _tree_group=123, poll=lambda: 0)
        entered, proceed = threading.Event(), threading.Event()
        calls = []
        def signal_group(group, sig):
            calls.append((group, sig))
            if len(calls) == 1:
                entered.set()
                self.assertTrue(proceed.wait(5))
        with patch.object(process_tree.os, "killpg", side_effect=signal_group, create=True):
            cancel = threading.Thread(target=process_tree.kill, args=(proc,))
            cancel.start()
            self.assertTrue(entered.wait(5))
            releasing = threading.Thread(target=process_tree.release, args=(proc,))
            releasing.start()
            proceed.set()
            cancel.join(5)
            releasing.join(5)
            self.assertTrue(proc._tree_released)
            count = len(calls)
            process_tree.kill(proc)
            self.assertEqual(len(calls), count)

    def test_posix_wait_releases_group_before_reaping(self):
        from scripts._posix_process_group import protect_reaping
        events = []
        proc = SimpleNamespace(pid=123, args=["test"], returncode=None,
                               _tree_lock=threading.RLock(), _tree_released=False)
        def reap(timeout=0):
            events.append("reap")
            proc.returncode = 0
            return 0
        proc._wait = reap
        proc._internal_poll = lambda *a, **kw: reap()
        with patch.object(os, "waitid", return_value=object(), create=True), \
             patch.object(os, "P_PID", 1, create=True), \
             patch.object(os, "WEXITED", 4, create=True), \
             patch.object(os, "WNOWAIT", 16, create=True), \
             patch.object(os, "WNOHANG", 1, create=True):
            protect_reaping(proc, lambda _: events.append("release"))
            self.assertEqual(proc._wait(timeout=1), 0)
        self.assertEqual(events, ["release", "reap"])

    def test_terminate_reaps_descendant_and_is_idempotent(self):
        proc = process_tree.popen(self.command(), stdout=subprocess.PIPE, text=True)
        self.addCleanup(process_tree.release, proc)
        conn = self.connected()
        self.assertEqual(proc.stdout.readline().strip(), "started")
        process_tree.terminate(proc, wait=True)
        self.assertIsNotNone(proc.poll())
        self.assert_disconnected(conn)
        process_tree.terminate(proc, wait=True)
        proc.stdout.close()

    def test_normal_exit_release_reaps_surviving_descendant(self):
        code = PARENT.replace("threading.Event().wait(30)", "sys.stdin.read(1)")
        proc = process_tree.popen([sys.executable, "-c", code, CHILD, self.port],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        self.addCleanup(process_tree.release, proc)
        try:
            conn = self.connected()
        except TimeoutError:
            process_tree.terminate(proc, wait=True)
            out, err = proc.communicate(timeout=3)
            self.fail(f"child did not connect: {out} {err}")
        proc.communicate("x", timeout=5)
        self.assertEqual(proc.returncode, 0)
        process_tree.release(proc)
        self.assert_disconnected(conn)

    def test_current_runtime_timeout_cancel_and_close_reap_descendant(self):
        try:
            import cli_runtime
        except ModuleNotFoundError as exc:
            if exc.name == "tkinter":
                self.skipTest("没有tkinter")
            raise
        for mode in ("timeout", "cancel", "close"):
            with self.subTest(mode=mode):
                runtime = cli_runtime.CliRuntime()
                runtime._init_runtime()
                runtime.proc = None
                runtime.cancel_flag = False
                runtime._running = True
                runtime.set_status = Mock()
                runtime._conversation_epoch = 0
                runtime.stop_chat_timing = Mock()
                runtime._cancel_scroll_job = Mock()
                runtime.tk = SimpleNamespace(call=lambda *_: ())
                runtime.destroy = Mock()
                results, errors = queue.Queue(), queue.Queue()
                def work():
                    try:
                        results.put(runtime.run_cli(timeout=3 if mode == "timeout" else 15))
                    except Exception as exc:
                        errors.put(exc)
                spawn = subprocess.Popen
                def launch(_args, **kwargs):
                    return spawn(self.command(), **kwargs)
                with patch.object(process_tree.subprocess, "Popen", side_effect=launch):
                    thread = threading.Thread(target=work)
                    thread.start()
                    conn = self.connected()
                    if mode == "cancel":
                        runtime.cancel()
                    elif mode == "close":
                        runtime._on_close()
                    thread.join(10)
                self.assertFalse(thread.is_alive())
                self.assertTrue(errors.empty(), list(errors.queue))
                self.assertNotEqual(results.get_nowait()[0], 0)
                self.assert_disconnected(conn)
                self.assertEqual(runtime._processes, set())

    def test_legacy_runner_cancel_and_close_reap_descendant(self):
        from test_legacy_task_isolation import MemoryRoot
        from cvapp.runner import Runner
        for mode in ("cancel", "close"):
            with self.subTest(mode=mode):
                runner = Runner(MemoryRoot(), Mock(), Mock(), Mock())
                self.addCleanup(runner.close)
                self.assertTrue(runner.start(self.command(), str(ROOT), "test"))
                conn = self.connected()
                getattr(runner, mode)()
                runner._thread.join(5)
                self.assertFalse(runner._thread.is_alive())
                self.assert_disconnected(conn)
                runner.close()

    def test_legacy_normal_parent_exit_with_inherited_stdout(self):
        from test_legacy_task_isolation import MemoryRoot
        from cvapp.runner import Runner
        code = PARENT.replace("stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL", "stdin=subprocess.DEVNULL")
        code = code.replace("threading.Event().wait(30)", "sys.stdin.read(1)")
        # 独立父进程先等测试连接建立，再退出；后代仍继承stdout。
        runner = Runner(MemoryRoot(), Mock(), Mock(), Mock())
        self.addCleanup(runner.close)
        started = threading.Event()
        original_put = runner._queue.put
        def put(event):
            original_put(event)
            if event[2] == "out":
                started.set()
        runner._queue.put = put
        # 父进程用本机第二连接等待放行，不依赖睡眠。
        gate = socket.socket()
        self.addCleanup(gate.close)
        gate.bind(("127.0.0.1", 0))
        gate.listen()
        gate.settimeout(8)
        code = code.replace("sys.stdin.read(1)",
            f"__import__('socket').create_connection(('127.0.0.1',{gate.getsockname()[1]})).recv(1)")
        self.assertTrue(runner.start([sys.executable, "-c", code, CHILD, self.port], str(ROOT), "test"))
        conn = self.connected()
        peer, _ = gate.accept()
        self.addCleanup(peer.close)
        self.assertTrue(started.wait(5))
        peer.sendall(b"x")
        runner._thread.join(8)
        self.assertFalse(runner._thread.is_alive(), "继承输出管道不得阻止正常完成")
        self.assert_disconnected(conn)
        runner.close()

    def test_history_panel_close_reaps_real_query(self):
        from test_legacy_task_isolation import make_panel, make_shell
        from cvapp.history_panel import HistoryPanel
        from cvapp import sessions
        panel, _ = make_panel(make_shell())
        panel._async = HistoryPanel._async.__get__(panel)
        spawn = process_tree.popen
        def launch(_args, **kwargs):
            return spawn(self.command(), **kwargs)
        with patch.object(process_tree, "popen", side_effect=launch):
            panel._async(lambda: sessions.list_sessions(), Mock())
            conn = self.connected()
            owner = panel._queries
            panel.close()
            self.assert_disconnected(conn)
        self.assertTrue(panel._closed)
        self.assertTrue(owner._closed)

    def test_owner_close_rejects_late_queries(self):
        owner = process_tree.ProcessOwner()
        owner.close()
        with self.assertRaises(RuntimeError):
            owner.run([sys.executable, "-c", "raise AssertionError('must not launch')"])

    def test_owner_close_reaps_query_and_rejects_publication_race(self):
        for during_launch in (False, True):
            with self.subTest(during_launch=during_launch):
                owner = process_tree.ProcessOwner()
                created, publish = threading.Event(), threading.Event()
                errors = queue.Queue()
                spawn = process_tree.popen
                def launch(*args, **kwargs):
                    proc = spawn(*args, **kwargs)
                    if during_launch:
                        created.set()
                        if not publish.wait(8):
                            process_tree.release(proc)
                            raise AssertionError("publication timeout")
                    return proc
                def work():
                    try:
                        owner.run(self.command(), capture_output=True, text=True, timeout=15)
                    except Exception as exc:
                        errors.put(exc)
                with patch.object(process_tree, "popen", side_effect=launch):
                    thread = threading.Thread(target=work)
                    thread.start()
                    conn = self.connected()
                    if during_launch:
                        self.assertTrue(created.wait(5))
                    owner.close()
                    publish.set()
                    thread.join(8)
                self.assertFalse(thread.is_alive())
                self.assert_disconnected(conn)
                self.assertEqual(owner._processes, set())
                if during_launch:
                    self.assertIsInstance(errors.get_nowait(), RuntimeError)


if __name__ == "__main__":
    unittest.main()
