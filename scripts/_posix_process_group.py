"""在回收组长前终止其进程组；仅平台确认支持时启用，其余退回普通等待。

为什么需要：POSIX 下组号等于组长 PID。组长被回收后，该编号可能被系统复用，
再向保存的组号发信号就可能命中无关进程。Linux 的 waitid 支持 WNOWAIT，
可以“只观察不回收”，从而在编号失效前先终止整组。
macOS 的 waitid 不支持该组合（实测抛 PermissionError），因此不启用，
退回普通 wait；残余的“回收后到终止前”窗口在模块文档和架构文档中标注。
"""
import os
import subprocess
import sys
import threading
import time

# 运行期读取，便于测试在不支持的平台上强制走该分支。
ENABLED = sys.platform.startswith("linux") and hasattr(os, "waitid")


def protect_reaping(proc, release):
    """若平台支持，则包装 Popen 的等待：观察退出→先释放整组→再回收。"""
    if not ENABLED:
        return
    original_wait = proc._wait
    original_poll = proc._internal_poll
    state = {"enabled": True}
    pause = threading.Event()

    def exit_seen():
        """返回 (是否已退出, 是否仍可用 WNOWAIT)；平台限制时自动降级。"""
        try:
            return os.waitid(os.P_PID, proc.pid,
                             os.WEXITED | os.WNOWAIT | os.WNOHANG) is not None, True
        except ChildProcessError:
            # 其他代码已自行 waitpid：编号已失效，立刻放弃组所有权。
            with proc._tree_lock:
                proc._tree_released = True
                vars(proc).pop("_tree_group", None)
            return True, True
        except OSError:
            return False, False

    def wait(timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with proc._tree_lock:
                if proc.returncode is not None:
                    return proc.returncode
                seen, usable = exit_seen()
                if not usable:
                    state["enabled"] = False
                elif seen:
                    release(proc)  # 组长尚未回收，编号不会失效。
                    return original_wait(timeout=0)
            if not state["enabled"]:
                return original_wait(timeout=timeout)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(proc.args, timeout)
                pause.wait(min(0.01, remaining))
            else:
                pause.wait(0.01)

    def poll(*args, **kwargs):
        with proc._tree_lock:
            if proc.returncode is not None or not state["enabled"]:
                return original_poll(*args, **kwargs)
            seen, usable = exit_seen()
            if not usable:
                state["enabled"] = False
                return original_poll(*args, **kwargs)
            if not seen:
                return None
            release(proc)
            return original_poll(*args, **kwargs)

    proc._wait = wait
    proc._internal_poll = poll
