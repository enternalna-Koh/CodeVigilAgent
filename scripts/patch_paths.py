"""补丁事务的目录锚点；没有安全句柄能力时拒绝写入。"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path


if os.name == 'nt':
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    _kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HANDLE]
    _kernel.CreateFileW.restype = wintypes.HANDLE
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.CloseHandle.restype = wintypes.BOOL
    _kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                    wintypes.LPVOID, wintypes.DWORD]
    _kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                                wintypes.DWORD, wintypes.DWORD]
    _kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD

    class _AttributeTag(ctypes.Structure):
        _fields_ = [('attributes', wintypes.DWORD), ('tag', wintypes.DWORD)]

    _ntdll = ctypes.WinDLL('ntdll')

    class _IoStatus(ctypes.Structure):
        _fields_ = [('status', ctypes.c_void_p), ('information', ctypes.c_size_t)]

    class _UnicodeString(ctypes.Structure):
        _fields_ = [('length', wintypes.USHORT), ('maximum', wintypes.USHORT),
                    ('buffer', wintypes.LPWSTR)]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [('length', wintypes.ULONG), ('root', wintypes.HANDLE),
                    ('name', ctypes.POINTER(_UnicodeString)), ('attributes', wintypes.ULONG),
                    ('security', wintypes.LPVOID), ('quality', wintypes.LPVOID)]

    _ntdll.NtCreateFile.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
        ctypes.POINTER(_ObjectAttributes), ctypes.POINTER(_IoStatus), wintypes.LPVOID,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
        wintypes.LPVOID, wintypes.ULONG]
    _ntdll.NtCreateFile.restype = wintypes.LONG
    _ntdll.NtSetInformationFile.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IoStatus),
                                          wintypes.LPVOID, wintypes.ULONG, ctypes.c_int]
    _ntdll.NtSetInformationFile.restype = wintypes.LONG
    _ntdll.RtlNtStatusToDosError.argtypes = [wintypes.LONG]
    _ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG

    def _check_status(status):
        if status < 0:
            raise ctypes.WinError(_ntdll.RtlNtStatusToDosError(status))

    def _win_relative(parent, name, access, disposition=1, directory=False):
        buffer = ctypes.create_unicode_buffer(name)
        length = len(name.encode('utf-16-le'))
        string = _UnicodeString(length, length + 2, ctypes.cast(buffer, wintypes.LPWSTR))
        attrs = _ObjectAttributes(ctypes.sizeof(_ObjectAttributes), parent,
                                  ctypes.pointer(string), 0x40, None, None)
        handle, status = wintypes.HANDLE(), _IoStatus()
        _check_status(_ntdll.NtCreateFile(ctypes.byref(handle), access | 0x100000,
            ctypes.byref(attrs), ctypes.byref(status), None, 0x80, 3, disposition,
            0x00200000 | 0x20 | (1 if directory else 0x40), None, 0))
        return handle.value

    def _win_set(handle, info, kind):
        _check_status(_ntdll.NtSetInformationFile(handle, ctypes.byref(_IoStatus()),
                                                 ctypes.byref(info), ctypes.sizeof(info), kind))

    def _win_open(path, directory=False, parent=None):
        # 不共享 DELETE 固定祖先；相对句柄操作也不跟随锚点上新设的重解析点。
        handle = (_win_relative(parent, path.name, 0x80000000, directory=directory)
                  if parent is not None else _kernel.CreateFileW(str(path), 0x80000000,
                                     3, None, 3, 0x00200000 | 0x02000000, None))
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info = _AttributeTag()
            if not _kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info),
                                                       ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory:
                raise ValueError(f'拒绝链接、重解析点或非预期文件类型: {path}')
            # 查询已打开对象的规范名，拒绝 8.3 父目录/叶子别名而非字符串 resolve。
            buffer = ctypes.create_unicode_buffer(32768)
            length = _kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
            if not length or length >= len(buffer):
                raise ValueError(f'无法确认句柄规范名: {path}')
            canonical = Path(buffer.value)
            if path.parent != path and canonical.name.casefold() != path.name.casefold():
                raise ValueError(f'拒绝非规范文件别名（可能为 Git 元数据）: {path}')
            return handle
        except BaseException:
            _kernel.CloseHandle(handle)
            raise


def _posix_supported():
    return (os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and
            hasattr(os, 'O_DIRECTORY') and all(fn in os.supports_dir_fd for fn in
                (os.open, os.mkdir, os.stat, os.unlink, os.rmdir, os.rename)))


def _handles_supported():
    return os.name == 'nt' or _posix_supported()


class PatchPaths:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.directories = {}
        self.created = []
        if not _handles_supported():
            raise ValueError('当前平台缺少安全固定目录句柄能力，拒绝应用补丁')
        try:
            self.pin(self.root)
        except BaseException:
            self.close()
            raise

    def pin(self, path, create=False):
        path = Path(path)
        if path in self.directories:
            return self.directories[path]
        if path.parent == path:
            handle = (_win_open(path, True) if os.name == 'nt' else
                      os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        else:
            parent = self.pin(path.parent, create)
            try:
                handle = self._open_directory(path, parent)
            except FileNotFoundError:
                if not create:
                    raise
                if os.name == 'nt':
                    handle = _win_relative(parent, path.name, 0x80000000, 2, True)
                else:
                    os.mkdir(path.name, dir_fd=parent)
                    handle = self._open_directory(path, parent)
                self.created.append(path)
        self.directories[path] = handle
        return handle

    def _open_directory(self, path, parent):
        if os.name == 'nt':
            return _win_open(path, True, parent)
        return os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                       dir_fd=parent)

    def target(self, relative):
        path = self.root / relative
        # 预先固定全部已存在的父目录；缺失部分只能在整批验证通过后创建。
        current = self.root
        for part in relative.parts[:-1]:
            current = current / part
            try:
                self.pin(current)
            except FileNotFoundError:
                break
        return AnchoredFile(self, path)

    def close(self, remove_created=False):
        for path, handle in reversed(list(self.directories.items())):
            if os.name == 'nt':
                _kernel.CloseHandle(handle)
            else:
                os.close(handle)
            if remove_created and path in self.created:
                try:
                    if os.name == 'nt':
                        parent = self.directories[path.parent]
                        child = _win_relative(parent, path.name, 0x10000, directory=True)
                        try:
                            _win_set(child, wintypes.BOOLEAN(True), 13)
                        finally:
                            _kernel.CloseHandle(child)
                    else:
                        os.rmdir(path.name, dir_fd=self.directories[path.parent])
                except OSError:
                    pass
        self.directories.clear()


class AnchoredFile:
    def __init__(self, paths, path):
        self.paths, self.path = paths, path
        self.identity = None

    def __str__(self):
        return str(self.path)

    @property
    def parent_fd(self):
        return self.paths.pin(self.path.parent)

    def snapshot(self):
        parent = self.parent_fd
        if os.name == 'nt':
            handle = _win_open(self.path, parent=parent)
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            except BaseException:
                _kernel.CloseHandle(handle)
                raise
        else:
            fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self.parent_fd)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f'拒绝非普通文件: {self.path}')
            # 硬链接可能指向任意位置的 Git 元数据，无法仅由当前名称判定安全。
            if info.st_nlink != 1 or not info.st_ino:
                raise ValueError(f'拒绝硬链接或无法确认文件身份: {self.path}')
            self.identity = (info.st_dev, info.st_ino)
            return stream.read(), stat.S_IMODE(info.st_mode)

    def exists(self):
        try:
            if os.name == 'nt':
                handle = _win_relative(self.parent_fd, self.path.name, 0x80)
                _kernel.CloseHandle(handle)
            else:
                os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def read_bytes(self):
        return self.snapshot()[0]

    def stage(self, data, mode):
        parent = self.paths.pin(self.path.parent, create=True)
        name = '.reviewagent-' + secrets.token_hex(16)
        staged = AnchoredFile(self.paths, self.path.with_name(name))
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
        if os.name == 'nt':
            handle = _win_relative(parent, name, 0x40000000 | 0x100, 2)
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
            except BaseException:
                _kernel.CloseHandle(handle)
                raise
        else:
            fd = os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                if mode is not None:
                    if os.name == 'nt':
                        class BasicInfo(ctypes.Structure):
                            _fields_ = [('times', ctypes.c_longlong * 4),
                                        ('attributes', wintypes.ULONG)]
                        info = BasicInfo()
                        info.attributes = 0x80 if mode & stat.S_IWRITE else 1
                        _win_set(msvcrt.get_osfhandle(stream.fileno()), info, 4)
                    else:
                        os.fchmod(stream.fileno(), mode)
            return staged
        except BaseException:
            staged.unlink()
            raise

    def replace_from(self, staged):
        if os.name == 'nt':
            name = self.path.name.encode('utf-16-le')

            class RenameInfo(ctypes.Structure):
                _fields_ = [('replace', wintypes.BOOLEAN), ('root', wintypes.HANDLE),
                            ('length', wintypes.ULONG), ('name', ctypes.c_byte * len(name))]

            info = RenameInfo()
            info.replace, info.root, info.length = True, self.parent_fd, len(name)
            ctypes.memmove(ctypes.addressof(info) + RenameInfo.name.offset, name, len(name))
            handle = _win_relative(staged.parent_fd, staged.path.name, 0x10000)
            try:
                _win_set(handle, info, 10)
            finally:
                _kernel.CloseHandle(handle)
        else:
            os.replace(staged.path.name, self.path.name,
                       src_dir_fd=staged.parent_fd, dst_dir_fd=self.parent_fd)

    def unlink(self):
        if os.name == 'nt':
            handle = _win_relative(self.parent_fd, self.path.name, 0x10000)
            try:
                _win_set(handle, wintypes.BOOLEAN(True), 13)
            finally:
                _kernel.CloseHandle(handle)
        else:
            os.unlink(self.path.name, dir_fd=self.parent_fd)
