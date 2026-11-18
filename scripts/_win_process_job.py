"""Windows作业对象：挂起创建的子进程必须先归属作业，再恢复首线程。"""
import ctypes
from ctypes import wintypes as w
import threading

kernel = ctypes.WinDLL("kernel32", use_last_error=True)


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", w.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", w.DWORD), ("Affinity", ctypes.c_size_t),
                ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ThreadID", w.DWORD),
                ("th32OwnerProcessID", w.DWORD), ("tpBasePri", w.LONG),
                ("tpDeltaPri", w.LONG), ("dwFlags", w.DWORD)]


def _api(name, args, result):
    fn = getattr(kernel, name)
    fn.argtypes, fn.restype = args, result
    return fn


CreateJobObject = _api("CreateJobObjectW", [w.LPVOID, w.LPCWSTR], w.HANDLE)
SetInformationJobObject = _api("SetInformationJobObject", [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL)
AssignProcessToJobObject = _api("AssignProcessToJobObject", [w.HANDLE, w.HANDLE], w.BOOL)
TerminateJobObject = _api("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL)
CloseHandle = _api("CloseHandle", [w.HANDLE], w.BOOL)
CreateSnapshot = _api("CreateToolhelp32Snapshot", [w.DWORD, w.DWORD], w.HANDLE)
ThreadFirst = _api("Thread32First", [w.HANDLE, ctypes.POINTER(THREADENTRY32)], w.BOOL)
ThreadNext = _api("Thread32Next", [w.HANDLE, ctypes.POINTER(THREADENTRY32)], w.BOOL)
OpenThread = _api("OpenThread", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE)
ResumeThread = _api("ResumeThread", [w.HANDLE], w.DWORD)


def _check(ok):
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def resume_primary_thread(pid):
    # CREATE_SUSPENDED时尚未执行用户代码，进程只有系统创建的首线程。
    snapshot = CreateSnapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        more = ThreadFirst(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                thread = OpenThread(0x0002, False, entry.th32ThreadID)
                _check(thread)
                try:
                    if ResumeThread(thread) == 0xFFFFFFFF:
                        raise ctypes.WinError(ctypes.get_last_error())
                    return
                finally:
                    CloseHandle(thread)
            more = ThreadNext(snapshot, ctypes.byref(entry))
        raise OSError("找不到挂起进程的首线程")
    finally:
        CloseHandle(snapshot)


class Job:
    def __init__(self):
        self._lock = threading.Lock()
        self.handle = CreateJobObject(None, None)
        _check(self.handle)
        try:
            limits = EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
            _check(SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    def assign_and_resume(self, proc):
        _check(AssignProcessToJobObject(self.handle, int(proc._handle)))
        resume_primary_thread(proc.pid)

    def terminate(self):
        with self._lock:
            if self.handle:
                _check(TerminateJobObject(self.handle, 1))

    def close(self):
        with self._lock:
            if self.handle:
                CloseHandle(self.handle)
                self.handle = None
