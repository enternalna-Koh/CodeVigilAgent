"""在回收组长前终止进程组，避免保存的组号在回收后被复用。"""
import os
import subprocess
import threading
import time


def protect_reaping(proc, release):
    original_wait = proc._wait
    original_poll = proc._internal_poll
    pause = threading.Event()

    def exited():
        try:
            return os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is not None
        except ChildProcessError:
            # 外部代码若自行waitpid，身份已失效，不再向保存的组号发信号。
            with proc._tree_lock:
                proc._tree_released = True
                vars(proc).pop("_tree_group", None)
            return True

    def wait(timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with proc._tree_lock:
                if proc.returncode is not None:
                    return proc.returncode
                if exited():
                    release(proc)  # WNOWAIT尚未回收组长，其PID不能被复用。
                    return original_wait(timeout=0)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(proc.args, timeout)
                pause.wait(min(0.01, remaining))
            else:
                pause.wait(0.01)

    def poll(*args, **kwargs):
        with proc._tree_lock:
            if proc.returncode is not None:
                return proc.returncode
            if not exited():
                return None
            release(proc)
            return original_poll(*args, **kwargs)

    proc._wait = wait
    proc._internal_poll = poll
