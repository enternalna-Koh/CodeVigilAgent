"""子进程执行器：启动 CLI、逐行读输出、支持取消。

和界面解耦：只通过三个回调跟外界说话 —— on_line（来了一行输出）、
on_start（开始运行）、on_done（结束，带退出码）。
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk

from . import ROOT


class Runner:
    def __init__(self, root: tk.Misc, on_line, on_start, on_done):
        self._root = root
        self._on_line = on_line
        self._on_start = on_start
        self._on_done = on_done
        self._queue: queue.Queue = queue.Queue()
        self._proc: subprocess.Popen | None = None
        self._active: int | None = None
        self._serial = 0
        self._thread: threading.Thread | None = None
        self._closed = False
        self._after = None
        self._draining = False
        self._tick()

    # ------------------------------------------------------------ 状态
    @property
    def busy(self) -> bool:
        return self._active is not None

    # ------------------------------------------------------------ 控制
    def start(self, args: list, cwd: str, label: str, columns: int | None = None,
              sink=None) -> bool:
        if self._closed or self.busy:
            return False
        sink = sink if sink is not None else self._on_line

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
        # Text 组件里没有终端光标，定位序列（\x1b[75C）只会显示成乱码，
        # 所以桌面版强制走「补空格对齐」那条渲染路径。
        env['REVIEWAGENT_RENDER'] = 'pad'
        # 按输出区实际像素宽度告诉 CLI 用多少列，避免边框比面板还宽、
        # 底部常驻一条横向滚动条。
        if columns:
            env['COLUMNS'] = str(int(columns))
        creation = 0x08000000 if os.name == 'nt' else 0   # CREATE_NO_WINDOW

        try:
            self._proc = subprocess.Popen(
                args, cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, creationflags=creation,
            )
        except Exception as exc:                       # noqa: BLE001
            sink(f'启动失败：{exc}\n')
            return False

        self._serial += 1
        self._active = self._serial
        self._thread = threading.Thread(
            target=self._reader, args=(self._proc, self._active, sink), daemon=True)
        self._thread.start()
        self._on_start(label)
        return True

    def cancel(self) -> None:
        proc = self._proc
        if self.busy and proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                return
            self._on_line('\n[已请求取消]\n')

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._after is not None:
            try:
                self._root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        proc = self._proc
        if proc is not None:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._active = None
        self._proc = None
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def python(self) -> str:
        """用当前解释器 —— 启动器保证它带 tkinter，子进程也用它。"""
        return sys.executable

    # ------------------------------------------------------------ 内部
    def _reader(self, proc: subprocess.Popen, task_id: int, sink) -> None:
        try:
            with proc.stdout:
                for line in proc.stdout:
                    self._queue.put((task_id, sink, 'out', line))
        except Exception as exc:                       # noqa: BLE001
            self._queue.put((task_id, sink, 'out', f'\n读取输出出错：{exc}\n'))
        finally:
            self._queue.put((task_id, sink, 'done', proc.wait()))

    def _tick(self) -> None:
        """Tk 线程消费事件；完成回调返回前仍占有本轮任务。"""
        if self._closed or self._draining:
            return
        self._after = None
        self._draining = True
        try:
            while not self._closed:
                task_id, sink, kind, payload = self._queue.get_nowait()
                if task_id != self._active:
                    continue
                if kind == 'out':
                    sink(payload)
                else:
                    try:
                        self._on_done(int(payload))
                    finally:
                        self._active = None
                        self._proc = None
        except queue.Empty:
            pass
        finally:
            self._draining = False
            if not self._closed:
                try:
                    self._after = self._root.after(40, self._tick)
                except tk.TclError:
                    pass
