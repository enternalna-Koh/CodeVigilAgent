"""当前桌面真实方法回归；Tk 始终隐藏，配置与进程使用隔离替身。"""
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
try:
    import tkinter as tk
except ModuleNotFoundError:
    tk = None
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop_py"))
sys.path.insert(0, str(ROOT))
if tk is not None:
    import app as desktop
    import settings_dialog as settings
    import cli_runtime


@unittest.skipIf(tk is None, '当前 Python 未安装 tkinter')
class HiddenDesktopTests(unittest.TestCase):
    def setUp(self):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError as exc:
            self.skipTest(f'当前环境没有可用图形显示：{exc}')
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"REVIEWAGENT_HOME": self.tmp.name})
        self.env.start()
        with patch.object(desktop.App, "load_sessions"), \
                patch.object(desktop.App, "show_welcome"):
            self.app = desktop.App()
            self.app.withdraw()
        # 不运行启动时的真实 CLI。
        for job in self.app.tk.call("after", "info"):
            self.app.after_cancel(job)
        self.jobs = []

    def tearDown(self):
        try:
            for job in self.app.tk.call("after", "info"):
                self.app.after_cancel(job)
            self.app.destroy()
        except tk.TclError:
            pass
        self.env.stop()
        self.tmp.cleanup()

    def defer(self):
        def enqueue(work, done, label, cancellable=False):
            self.jobs.append((work, done, cancellable))
            if cancellable:
                self.app._running = True
        self.app.run_async = enqueue

    @staticmethod
    def result(name, repo=""):
        return (0, json.dumps({"ok": True, "session": {
            "name": name, "repository": repo, "messages": [
                {"role": "assistant", "content": name}]}}), "")

    def test_settings_scope_standard_and_degraded(self):
        cfg = {"provider": "deepseek", "model": "deepseek-chat",
               "base_url": "https://one.example/v1", "api_key": "fake-original"}
        for degraded in (False, True):
            with self.subTest(degraded=degraded), \
                    patch.object(settings, "load_ai_config", return_value=(cfg, Path(self.tmp.name) / "config.json")), \
                    patch.object(settings.SettingsDialog, "_center", lambda obj: obj.withdraw()), \
                    patch.object(settings, "save_ai_config") as save:
                loader = settings.load_model_choices
                if degraded:
                    loader = lambda *args: ({"options": [], "custom": cfg["model"]}, "测试降级")
                with patch.object(settings, "load_model_choices", side_effect=loader):
                    dialog = settings.SettingsDialog(self.app)
                try:
                    dialog.key_entry.delete(0, "end")
                    dialog.key_entry.insert(0, "fake-edited")
                    dialog.base_var.set(cfg["base_url"] + "/")
                    self.assertEqual(dialog.key_entry.get(), "fake-edited")
                    dialog.base_var.set("https://two.example/v1")
                    self.assertEqual(dialog.key_entry.get(), "")
                    dialog.save()
                    save.assert_not_called()
                    self.assertTrue(dialog.winfo_exists())
                    dialog.base_var.set(cfg["base_url"])
                    self.assertEqual(dialog.key_entry.get(), "fake-original")
                    dialog.save()
                    self.assertEqual(save.call_args.args[0]["api_key"], "fake-original")
                finally:
                    if dialog.winfo_exists():
                        dialog.destroy()

    def test_settings_new_key_save_standard_and_degraded(self):
        cfg = {"provider": "deepseek", "model": "deepseek-chat", "base_url": "",
               "api_key": "fake-original", "unrelated": "preserve"}
        for degraded in (False, True):
            with self.subTest(degraded=degraded), \
                    patch.object(settings, "load_ai_config", return_value=(cfg, Path(self.tmp.name) / "config.json")), \
                    patch.object(settings.SettingsDialog, "_center", lambda obj: obj.withdraw()), \
                    patch.object(settings, "save_ai_config") as save:
                loader = settings.load_model_choices
                if degraded:
                    loader = lambda *args: ({"options": [], "custom": cfg["model"]}, "测试降级")
                with patch.object(settings, "load_model_choices", side_effect=loader):
                    dialog = settings.SettingsDialog(self.app)
                dialog.base_var.set("https://new.example/v1")
                self.assertEqual(dialog.key_entry.get(), "")
                dialog.key_entry.insert(0, "fake-new")
                dialog._sync_key()
                self.assertEqual(dialog.key_entry.get(), "fake-new")
                dialog.save()
                data = save.call_args.args[0]
                self.assertEqual(data["api_key"], "fake-new")
                self.assertEqual(data["base_url"], "https://new.example/v1")
                self.assertEqual(data["provider"], "deepseek")
                self.assertEqual(data["unrelated"], "preserve")

    def test_settings_native_provider_switch_with_empty_endpoint(self):
        from scripts.model_choices import build_choices
        cfg = {"provider": "deepseek", "model": "one", "api_key": "fake-original"}
        catalog = [{"label": name, "file_provider": name, "base_url": "",
                    "models": [model], "default_model": model}
                   for name, model in (("deepseek", "one"), ("glm", "two"))]
        choices = build_choices(catalog, "deepseek", "one")
        with patch.object(settings, "load_ai_config", return_value=(cfg, Path(self.tmp.name) / "config.json")), \
                patch.object(settings, "load_model_choices", return_value=(choices, "")), \
                patch.object(settings.SettingsDialog, "_center", lambda obj: obj.withdraw()), \
                patch.object(settings, "save_ai_config") as save:
            dialog = settings.SettingsDialog(self.app)
            dialog.provider_cb.current(1)
            dialog._on_provider()
            self.assertEqual(dialog.key_entry.get(), "")
            dialog.save()
            save.assert_not_called()
            dialog.provider_cb.current(0)
            dialog._on_provider()
            self.assertEqual(dialog.key_entry.get(), "fake-original")
            dialog.destroy()

    def test_review_snapshots_selected_repository_online_and_offline(self):
        self.defer()
        for offline in (False, True):
            self.app._running = False
            selected = str(Path(self.tmp.name).resolve())
            self.app.repo_var.set(selected)
            self.app._review(offline)
            work, done, _ = self.jobs[-1]
            self.app.repo_var.set(str(ROOT))
            with patch.object(self.app, "run_cli", return_value=(0, "report", "")) as cli:
                done(work())
            self.assertEqual(cli.call_args.kwargs.get("cwd"), selected)
            self.assertEqual("--offline" in cli.call_args.args, offline)
            self.assertIn(selected, self.app.messages[-1]["content"])

    def test_history_out_of_order_cache_miss_and_hit(self):
        for cached in (False, True):
            with self.subTest(cached=cached):
                self.defer()
                self.app._session_cache.clear()
                self.app.show_session("old")
                stale = self.jobs[-1][1]
                if cached:
                    self.app._remember_session("new", {"messages": [
                        {"role": "assistant", "content": "new"}]}, {"ok": True}, "")
                self.app.show_session("new")
                if not cached:
                    self.jobs[-1][1](self.result("new"))
                stale(self.result("old"))
                self.assertEqual(self.app.session_name, "new")
                self.assertEqual(self.app.messages[-1]["content"], "new")

    def test_send_during_uncached_history_read_preserves_input(self):
        self.defer()
        self.app.session_name = "previous"
        self.app.show_session("target")
        self.app.input.insert("1.0", "follow up")
        count = len(self.jobs)
        self.app.send()
        self.assertEqual(len(self.jobs), count)
        self.assertEqual(self.app.input.get("1.0", "end").strip(), "follow up")
        self.jobs[-1][1](self.result("target"))
        self.app.send()
        with patch.object(self.app, "run_cli", return_value=(0, "{}", "")) as cli:
            self.jobs[-1][0]()
        args = cli.call_args.args
        self.assertEqual(args[args.index("--session") + 1], "target")

    def test_running_blocks_all_context_switches_and_second_review(self):
        self.defer()
        self.app.session_name = "active"
        self.app._running = True
        epoch = self.app._conversation_epoch
        original = self.app.repo_var.get()
        with patch.object(desktop.filedialog, "askdirectory", return_value=self.tmp.name) as picker:
            self.app.choose_repo()
            picker.assert_not_called()
        self.app.show_session("other")
        self.app.new_conversation()
        self.app.delete_session("active")
        self.app._review(False)
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.app.session_name, "active")
        self.assertEqual(self.app.repo_var.get(), original)
        self.assertEqual(self.app._conversation_epoch, epoch)

    def test_new_conversation_and_repository_invalidate_pending_history(self):
        self.defer()
        for action in (self.app.new_conversation, self.app.choose_repo):
            self.app.show_session("stale")
            stale = self.jobs[-1][1]
            with patch.object(desktop.filedialog, "askdirectory", return_value=self.tmp.name):
                action()
            stale(self.result("stale"))
            self.assertIsNone(self.app.session_name)
            self.assertIsNone(self.app._pending_session)
            self.assertFalse(any(m["content"] == "stale" for m in self.app.messages))

    def test_delete_invalidates_pending_read_before_delete_returns(self):
        self.defer()
        self.app.show_session("deleted")
        stale = self.jobs[-1][1]
        self.app.delete_session("deleted")
        stale(self.result("deleted"))
        self.assertNotEqual(self.app.session_name, "deleted")
        self.assertIsNone(self.app._pending_session)

    def test_cancel_before_process_publication_is_not_lost(self):
        self.app._running = True
        self.app.cancel()
        self.assertTrue(self.app.cancel_flag)
        process = Mock(returncode=-1)
        process.communicate.return_value = ("", "")
        with patch.object(desktop.subprocess, "Popen", return_value=process):
            self.app.run_cli("review")
        process.terminate.assert_called()
        self.assertIsNone(self.app.proc)

    def test_timeout_escalates_and_reaps_process(self):
        process = Mock(returncode=-9)
        process.communicate.side_effect = [subprocess.TimeoutExpired("cli", 1),
                                           subprocess.TimeoutExpired("cli", 1), ("", "")]
        with patch.object(desktop.subprocess, "Popen", return_value=process):
            code, out, err = self.app.run_cli("review", timeout=1)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertIn("超时", err)
        self.assertIsNone(self.app.proc)

    def test_send_terminal_paths_stop_timer_and_keep_session_identity(self):
        for result, cancelled, expected in (
                ((0, '{"ok": true, "reply": "answer"}', ""), False, "completed"),
                ((1, '{"ok": false, "error": "failure"}', ""), False, "failed"),
                (("error", "start failed"), False, "failed"),
                ((-1, "", ""), True, "interrupted")):
            with self.subTest(expected=expected, result=result):
                self.app._running = False
                self.app.new_conversation()
                self.defer()
                self.app.input.insert("1.0", "question")
                self.app.send()
                session = self.app.session_name
                self.app.cancel_flag = cancelled
                self.jobs[-1][1](result)
                self.assertFalse(self.app._chat_active)
                self.assertIsNone(self.app._chat_timer)
                self.assertEqual(self.app.session_name, session)
                user = next(m for m in self.app.messages if m["role"] == "user")
                self.assertEqual(user["status"], expected)
                if expected == "completed":
                    self.assertEqual(self.app.messages[-1]["content"], "answer")

    def test_failed_history_read_cannot_send_to_previous_session(self):
        self.defer()
        self.app.session_name = "previous"
        self.app.show_session("missing")
        self.jobs[-1][1]((1, '{"ok": false}', "missing"))
        self.assertIsNone(self.app.session_name)
        self.app.input.insert("1.0", "new question")
        self.app.send()
        with patch.object(self.app, "run_cli", return_value=(0, "{}", "")) as cli:
            self.jobs[-1][0]()
        self.assertNotIn("previous", cli.call_args.args)

    def test_stale_history_cannot_clear_newer_pending_selection(self):
        self.defer()
        self.app.show_session("old")
        stale = self.jobs[-1][1]
        self.app.new_conversation()
        self.app.show_session("new")
        stale(self.result("old"))
        self.assertEqual(self.app._pending_session, "new")
        self.jobs[-1][1](self.result("new"))
        self.assertEqual(self.app.session_name, "new")

    def test_short_completion_does_not_unlock_active_task(self):
        gate = threading.Event()
        long_done, short_done = Mock(), Mock()
        try:
            self.app.run_async(lambda: gate.wait(5), long_done, "长任务", cancellable=True)
            self.app.run_async(lambda: "short", short_done, "短任务")
            event = self.app._done_queue.get(timeout=3)
            self.app._done_queue.put(event)
            self.app._pump_done()
            short_done.assert_called_once_with("short")
            self.assertTrue(self.app._running)
            self.assertEqual(self.app._task_label, "长任务")
        finally:
            gate.set()
            event = self.app._done_queue.get(timeout=3)
            self.app._done_queue.put(event)
            self.app._pump_done()
        self.assertFalse(self.app._running)
        long_done.assert_called_once()

    def test_real_process_cwd_and_timeout(self):
        spawn = subprocess.Popen
        processes = []
        code = "import os; print(os.getcwd(), flush=True)"
        def launch(args, **kwargs):
            process = spawn([sys.executable, "-c", code], **kwargs)
            processes.append(process)
            return process
        with patch.object(cli_runtime.subprocess, "Popen", side_effect=launch):
            status, out, err = self.app.run_cli("review", cwd=self.tmp.name)
        self.assertEqual(status, 0)
        self.assertEqual(Path(out.strip()).resolve(), Path(self.tmp.name).resolve())
        code = "import threading; threading.Event().wait(30)"
        with patch.object(cli_runtime.subprocess, "Popen", side_effect=launch):
            status, out, err = self.app.run_cli("review", timeout=0.1)
        self.assertNotEqual(status, 0)
        self.assertIn("超时", err)
        self.assertIsNotNone(processes[-1].poll())
        self.assertIsNone(self.app.proc)

    def test_real_cancel_during_popen_and_close_during_publication(self):
        # 前面窗口留下的循环引用必须在 Tk 主线程回收；否则后台启动进程时触发
        # Tk 对象析构会等待未运行的主循环，掩盖本测试真正要检查的发布竞态。
        gc.collect()
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            spawn = subprocess.Popen
            for closing in (False, True):
                if closing:
                    # 关窗用最后一次循环，后续不再访问 Tk 控件。
                    self.app.cancel_flag = False
                self.app._running = True
                created, release = threading.Event(), threading.Event()
                processes, results = [], []
                def launch(args, **kwargs):
                    process = spawn([sys.executable, "-c",
                                     "import threading; threading.Event().wait(30)"], **kwargs)
                    processes.append(process)
                    created.set()
                    if not release.wait(5):
                        process.kill()
                        process.wait(timeout=3)
                        raise AssertionError("发布进程等待超时")
                    return process
                with patch.object(cli_runtime.subprocess, "Popen", side_effect=launch):
                    thread = threading.Thread(target=lambda: results.append(self.app.run_cli("review", timeout=3)))
                    thread.start()
                    try:
                        self.assertTrue(created.wait(3))
                        if closing:
                            self.app._on_close()
                        else:
                            self.app.cancel()
                    finally:
                        release.set()
                        thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(results), 1)
                self.assertIsNotNone(processes[-1].poll())
                self.assertIsNone(self.app.proc)
        finally:
            if was_enabled:
                gc.enable()

    def test_real_close_reaps_active_process(self):
        process = subprocess.Popen([sys.executable, "-c",
                                    "import threading; threading.Event().wait(30)"],
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self.app._processes.add(process)
            self.app.proc = process
            self.app.begin_chat_timing()
            self.app._on_close()
            self.assertIsNotNone(process.poll())
            self.assertIsNone(self.app._chat_timer)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)

    def test_shared_gateway_key_import_is_compatible(self):
        sys.path.insert(0, str(ROOT / "desktop-app" / "win"))
        from cvapp.features.settings import GatewayKey as LegacyKey
        from scripts.gateway_key import GatewayKey
        self.assertIs(LegacyKey, GatewayKey)
        binding = GatewayKey("deepseek", "", "fake-original")
        self.assertEqual(binding.update("glm", "", "fake-original"), "")
        self.assertEqual(binding.update("glm", "", "fake-new"), "fake-new")
        self.assertEqual(binding.update("deepseek", "", "fake-new"), "fake-original")

    def test_close_reaps_process_and_stops_timers(self):
        self.app.begin_chat_timing()
        process = Mock(returncode=-1)
        process.wait.return_value = -1
        self.app.proc = process
        self.app._running = True
        self.app._on_close()
        process.terminate.assert_called_once()
        process.wait.assert_called()
        self.assertFalse(self.app._chat_active)
        self.assertIsNone(self.app._chat_timer)
        self.assertIsNone(self.app.proc)


if __name__ == "__main__":
    unittest.main()
