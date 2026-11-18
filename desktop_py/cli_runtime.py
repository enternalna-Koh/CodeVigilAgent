"""桌面 CLI 运行、取消与关窗回收；后台线程只向主线程队列投递。"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading

from ui_kit import IS_WIN, ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import process_tree


def cli_prefix():
    return [sys.executable or ("python" if IS_WIN else "python3")]


def cli_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def terminate_process(proc, *, wait=False):
    process_tree.terminate(proc, wait=wait)


class CliRuntime:
    def _init_runtime(self):
        self._process_lock = threading.Lock()
        self._processes = set()
        self._closing = False
        self._pump_job = None
        self._task_serial = 0
        self._active_task = None
        self._worker_context = threading.local()

    def run_cli(self, *args, timeout=120, track=True, extra_env=None, cwd=None):
        env = cli_env()
        if extra_env:
            env.update({str(k): str(v) for k, v in extra_env.items()})
        frozen = getattr(sys, "frozen", False)
        if frozen:
            # 打包后：同一个 exe 用 --cli 参数跑 CLI 逻辑，不再依赖机器上的 Python。
            argv = ["--cli"] + [str(a) for a in args]
            launch = [sys.executable] + argv
        else:
            argv = [str(ROOT / "ascend_cli.py")] + [str(a) for a in args]
            launch = cli_prefix() + argv
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
        task = getattr(self._worker_context, "task", None)
        with self._process_lock:
            if self._closing:
                return -1, "", "[窗口已关闭]"
        try:
            proc = process_tree.popen(launch, cwd=str(cwd or ROOT), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
        except FileNotFoundError:
            if frozen:
                raise
            proc = process_tree.popen([sys.executable] + argv, cwd=str(cwd or ROOT), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
        with self._process_lock:
            self._processes.add(proc)
            if track:
                self.proc = proc
            abort = self._closing or (track and (self.cancel_flag or
                    (task is not None and task != self._active_task)))
        if type(getattr(proc, "pid", None)) is int:
            threading.Thread(target=process_tree.watch_exit, args=(proc,), daemon=True).start()
        try:
            if abort:
                terminate_process(proc, wait=True)
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                terminate_process(proc)
                try:
                    out, err = proc.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    process_tree.kill(proc)
                    out, err = proc.communicate(timeout=2)
                err = (err or "") + f"\n[超时 {timeout}s]"
            return proc.returncode, out or "", err or ""
        finally:
            try:
                process_tree.release(proc)
            finally:
                with self._process_lock:
                    self._processes.discard(proc)
                    if track and self.proc is proc:
                        self.proc = None
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()

    def run_async(self, work, done, label, cancellable=False):
        if self._closing:
            return False
        if cancellable and self._running:
            self.set_status("上一个任务还没结束，请先取消或等它结束")
            return False
        task = None
        if cancellable:
            self._task_serial += 1
            task = self._task_serial
            self._active_task = task
            self._task_label = label
            self.cancel_flag = False
            self._running = True
            self.new_button.set_enabled(False)
            self.cancel_button.set_enabled(True)
        if cancellable or not self._running:
            self.set_status(f"{label} 运行中…")

        def runner():
            self._worker_context.task = task
            try:
                result = work()
            except Exception as exc:
                result = ("error", str(exc))
            if not self._closing:
                self._done_queue.put((done, result, cancellable, task))

        threading.Thread(target=runner, daemon=True).start()
        return True

    def _pump_done(self):
        self._pump_job = None
        if self._closing:
            return
        try:
            while True:
                done, result, cancellable, task = self._done_queue.get_nowait()
                if cancellable:
                    if task != self._active_task:
                        continue
                    self._running = False
                    self._active_task = None
                    self._task_label = ""
                    self.cancel_button.set_enabled(False)
                    self.new_button.set_enabled(True)
                try:
                    done(result)
                except Exception as exc:
                    self.set_status(f"回调失败：{exc}")
        except queue.Empty:
            pass
        self._pump_job = self.after(50, self._pump_done)

    def cancel(self):
        if not self._running:
            return
        with self._process_lock:
            self.cancel_flag = True
            proc = self.proc
        self.set_status("正在取消…")
        # 独立回收线程不阻塞 Tk，也不会误杀下一轮任务的句柄。
        if proc is not None:
            threading.Thread(target=terminate_process, args=(proc,),
                             kwargs={"wait": True}, daemon=True).start()

    def _on_close(self):
        with self._process_lock:
            self._closing = True
            self.cancel_flag = True
            processes = set(self._processes)
            self._processes.clear()
            if self.proc is not None:
                processes.add(self.proc)
            self.proc = None
        self._conversation_epoch += 1
        self._pending_session = None
        self.stop_chat_timing()
        self._cancel_scroll_job()
        # 覆盖启动回调、重排、轮询和控件自己的定时器。
        for job in self.tk.call("after", "info"):
            self.after_cancel(job)
        self._pump_job = self._resize_job = None
        for proc in processes:
            try:
                terminate_process(proc, wait=True)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.destroy()
