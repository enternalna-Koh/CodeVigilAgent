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
        self._sink = on_line          # 本轮输出的去处：默认写输出区，聊天时写气泡缓冲区
        self._tick()

    # ------------------------------------------------------------ 状态
    @property
    def busy(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------ 控制
    def start(self, args: list, cwd: str, label: str, columns: int | None = None,
              sink=None) -> bool:
        if self.busy:
            return False
        self._sink = sink or self._on_line

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
            self._on_line(f'启动失败：{exc}\n')
            return False

        threading.Thread(target=self._reader, args=(self._proc,), daemon=True).start()
        self._on_start(label)
        return True

    def cancel(self) -> None:
        if self.busy and self._proc is not None:
            self._proc.terminate()
            self._on_line('\n[已请求取消]\n')

    def python(self) -> str:
        """用当前解释器 —— 启动器保证它带 tkinter，子进程也用它。"""
        return sys.executable

    # ------------------------------------------------------------ 内部
    def _reader(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:                    # type: ignore[union-attr]
                self._queue.put(('out', line))
        except Exception as exc:                       # noqa: BLE001
            self._queue.put(('out', f'\n读取输出出错：{exc}\n'))
        finally:
            self._queue.put(('done', proc.wait()))

    def _tick(self) -> None:
        """每 40ms 把后台线程收到的输出搬到界面线程（tkinter 不是线程安全的）。"""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == 'out':
                    self._sink(payload)
                else:
                    self._sink = self._on_line
                    self._on_done(int(payload))
        except queue.Empty:
            pass
        try:
            self._root.after(40, self._tick)
        except tk.TclError:                             # 窗口已关闭
            pass
