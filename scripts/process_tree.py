"""受控子进程树；只终止本模块创建的作业/进程组，不枚举或按名称杀进程。"""
from __future__ import annotations

import os
import signal
import subprocess
import threading


def popen(args, **kwargs):
    """用户代码运行前确立归属；归属失败则拒绝启动。"""
    job = None
    if os.name == "nt":
        from scripts._win_process_job import Job
        job = Job()
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x00000004
    else:
        kwargs["start_new_session"] = True
    proc = None
    try:
        proc = subprocess.Popen(args, **kwargs)
        # 内存测试替身没有真实PID；不对它调用系统API。
        if type(getattr(proc, "pid", None)) is int:
            proc._tree_lock = threading.RLock()
            proc._tree_released = False
            if job is not None:
                job.assign_and_resume(proc)
                proc._tree_job = job
                job = None
            else:
                proc._tree_group = proc.pid
                from scripts._posix_process_group import protect_reaping
                protect_reaping(proc, release)
        return proc
    except BaseException:
        if proc is not None:
            proc.kill()
            proc.wait(timeout=3)
            for stream in (getattr(proc, "stdin", None), getattr(proc, "stdout", None),
                           getattr(proc, "stderr", None)):
                if stream is not None:
                    stream.close()
        raise
    finally:
        if job is not None:
            job.close()


def _signal_tree(proc, sig):
    lock = vars(proc).get("_tree_lock")
    if lock is not None:
        with lock:
            if not proc._tree_released:
                _signal_owned(proc, sig)
    else:
        _signal_owned(proc, sig)


def _signal_owned(proc, sig):
    job = vars(proc).get("_tree_job")
    group = vars(proc).get("_tree_group")
    if job is not None:
        job.terminate()
    elif group is not None:
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            pass
    elif sig == signal.SIGTERM:
        proc.terminate()
    else:
        proc.kill()


def terminate(proc, *, wait=False):
    """即使直接进程已退出，也终止其仍存活的受控后代。"""
    try:
        _signal_tree(proc, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if wait:
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            kill(proc)
            proc.wait(timeout=2)
        finally:
            # POSIX后代可能忽略TERM，即使父进程已经退出也必须补KILL。
            if vars(proc).get("_tree_group") is not None:
                _signal_tree(proc, signal.SIGKILL)


def kill(proc):
    # Windows没有SIGKILL；作业对象分支并不使用信号值。
    _signal_tree(proc, getattr(signal, "SIGKILL", signal.SIGTERM + 1))


def release(proc):
    """正常结束/异常退出均释放整棵树的所有权；与迟到的取消互斥。"""
    lock = vars(proc).get("_tree_lock")
    if lock is None:
        return  # 外部进程/测试替身不归本模块释放。
    with lock:
        if proc._tree_released:
            return
        try:
            kill(proc)
        finally:
            proc._tree_released = True
            job = vars(proc).pop("_tree_job", None)
            if job is not None:
                job.close()
            vars(proc).pop("_tree_group", None)


def watch_exit(proc):
    """直接进程退出即释放后代，不能等待后代关闭继承的输出管道。"""
    try:
        proc.wait()
    except OSError:
        return  # 句柄已被其他线程回收；释放由对应路径负责。
    release(proc)


class ProcessOwner:
    """查询所属面板的可关闭进程集合；覆盖创建与登记之间的关闭竞态。"""
    def __init__(self):
        self._lock = threading.Lock()
        self._closed = False
        self._processes = set()

    def run(self, args, *, timeout=None, capture_output=False, **kwargs):
        with self._lock:
            if self._closed:
                raise RuntimeError("查询所属窗口已关闭")
        if capture_output:
            kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
        proc = popen(args, **kwargs)
        with self._lock:
            closed = self._closed
            if not closed:
                self._processes.add(proc)
        threading.Thread(target=watch_exit, args=(proc,), daemon=True).start()
        try:
            if closed:
                terminate(proc, wait=True)
                raise RuntimeError("查询所属窗口已关闭")
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                terminate(proc, wait=True)
                proc.communicate(timeout=3)
                raise
            return subprocess.CompletedProcess(args, proc.returncode, out, err)
        finally:
            try:
                release(proc)
            finally:
                with self._lock:
                    self._processes.discard(proc)
                for stream in (getattr(proc, "stdin", None), getattr(proc, "stdout", None),
                           getattr(proc, "stderr", None)):
                    if stream is not None:
                        stream.close()

    def close(self):
        with self._lock:
            self._closed = True
            processes = tuple(self._processes)
        errors = []
        for proc in processes:
            try:
                terminate(proc, wait=True)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(exc)
        if errors:
            raise errors[0]
