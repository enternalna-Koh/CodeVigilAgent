"""仅在隔离目录内执行无害标记命令与目录替换回归。"""
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_work, patch_fix, patch_paths
from scripts.patch_fix import FileEdit, ProposedFix


class AuditFileSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'repo'
        self.root.mkdir()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith('GIT_')}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        context = patch.dict(os.environ, env, clear=True)
        context.start()
        self.addCleanup(context.stop)

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding='utf-8').stdout

    def link_directory(self, link, destination):
        if os.name == 'nt':
            subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(link), str(destination)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            link.symlink_to(destination, target_is_directory=True)

    def test_diff_does_not_execute_external_diff_or_textconv(self):
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')
        data = self.root / 'data.txt'
        data.write_text('old\n', encoding='utf-8')
        self.git('add', 'data.txt')
        tree = self.git('write-tree').strip()
        commit = self.git('-c', 'user.name=Audit', '-c', 'user.email=audit@example.invalid',
                          'commit-tree', tree, '-m', 'baseline').strip()
        self.git('update-ref', 'HEAD', commit)
        script = self.base / 'marker.py'
        marker = self.base / 'executed'
        script.write_text('from pathlib import Path\nimport sys\n'
                          'Path(sys.argv[1]).write_text("executed")\nprint("converted")\n',
                          encoding='utf-8')
        command = ' '.join(shlex.quote(str(p).replace('\\', '/'))
                           for p in (sys.executable, script, marker))
        for driver in ('external', 'environment', 'textconv'):
            if driver == 'environment':
                self.git('config', '--remove-section', 'diff.audit')
                os.environ['GIT_EXTERNAL_DIFF'] = command
            else:
                os.environ.pop('GIT_EXTERNAL_DIFF', None)
                self.git('config', 'diff.audit.' + ('command' if driver == 'external' else 'textconv'), command)
            (self.root / '.gitattributes').write_text('data.txt diff=audit\n', encoding='utf-8')
            for staged in (False, True):
                with self.subTest(driver=driver, staged=staged):
                    data.write_text('new\n', encoding='utf-8')
                    if staged:
                        self.git('add', 'data.txt')
                    # 对照证据：同一配置在未设防的 Git diff 下确实会执行标记。
                    self.git('diff', *(['--cached'] if staged else []))
                    self.assertTrue(marker.exists(), '标记命令未生效，不能证明防护')
                    marker.unlink()
                    result = git_work.diff_report(cwd=str(self.root), staged=staged)
                    self.assertFalse(marker.exists(), result)
                    self.assertIn('-old', result)
                    self.assertIn('+new', result)
                    if staged:
                        self.git('read-tree', 'HEAD')

    def test_parent_swap_after_validation_cannot_write_outside(self):
        for action in ('replace', 'create'):
            with self.subTest(action=action):
                parent = self.root / action
                parent.mkdir()
                outside = self.base / ('outside-' + action)
                outside.mkdir()
                (outside / 'data.txt').write_bytes(b'old')
                if action == 'replace':
                    (parent / 'data.txt').write_bytes(b'old')
                original = patch_fix._stage_bytes
                attempted, swapped = [], []
                parked = self.root / (action + '-parked')

                def swap_then_stage(*args, **kwargs):
                    if not attempted:
                        attempted.append(True)
                        try:
                            parent.rename(parked)
                        except PermissionError:
                            pass  # Windows 的目录锁必须阻止重命名。
                        else:
                            self.link_directory(parent, outside)
                            swapped.append(True)
                    return original(*args, **kwargs)

                try:
                    with patch.object(patch_fix, '_stage_bytes', side_effect=swap_then_stage):
                        result = patch_fix.apply_fix(ProposedFix(files=[
                            FileEdit(action + '/data.txt', action, 'old', 'new')]), root=self.root)
                    self.assertTrue(attempted, result)
                    self.assertEqual((outside / 'data.txt').read_bytes(), b'old', result)
                    self.assertEqual(sorted(p.name for p in outside.iterdir()), ['data.txt'])
                    if swapped:
                        self.assertTrue(result['ok'], result)
                        self.assertEqual((parked / 'data.txt').read_bytes(), b'new')
                    else:
                        self.assertTrue(result['ok'], result)
                finally:
                    if swapped:
                        if os.name == 'nt':
                            parent.rmdir()
                        else:
                            parent.unlink()

    def apply(self, *edits, **kwargs):
        return patch_fix.apply_fix(ProposedFix(files=list(edits)), root=self.root, **kwargs)

    def test_existing_junction_or_symlink_parent_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'data').write_bytes(b'old')
        alias = self.root / 'alias'
        self.link_directory(alias, outside)
        try:
            result = self.apply(FileEdit('alias/data', 'replace', 'old', 'new'))
            self.assertFalse(result['ok'], result)
            self.assertEqual((outside / 'data').read_bytes(), b'old')
        finally:
            alias.rmdir() if os.name == 'nt' else alias.unlink()

    @unittest.skipUnless(os.name == 'nt', '仅 Windows 支持目录联接重解析点')
    def test_in_place_reparse_change_cannot_redirect_relative_handles(self):
        import ctypes
        import struct
        from ctypes import wintypes

        parent = self.root / 'parent'
        parent.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'data').write_bytes(b'outside')
        original = patch_fix._stage_bytes
        attempted, changed = [], []

        def inject(target, *args):
            if not attempted:
                attempted.append(True)
                handle = patch_paths._kernel.CreateFileW(str(parent), 0x40000000, 7,
                                                         None, 3, 0x02200000, None)
                self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
                try:
                    substitute = ('\\??\\' + str(outside)).encode('utf-16-le')
                    printable = str(outside).encode('utf-16-le')
                    names = substitute + b'\x00\x00' + printable + b'\x00\x00'
                    payload = struct.pack('<HHHH', 0, len(substitute), len(substitute) + 2,
                                          len(printable)) + names
                    raw = struct.pack('<IHH', 0xA0000003, len(payload), 0) + payload
                    buffer = ctypes.create_string_buffer(raw)
                    count = wintypes.DWORD()
                    control = patch_paths._kernel.DeviceIoControl
                    control.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID,
                                        wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
                    control.restype = wintypes.BOOL
                    if not control(handle, 0x900A4, buffer, len(raw), None, 0,
                                   ctypes.byref(count), None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    changed.append(True)
                finally:
                    patch_paths._kernel.CloseHandle(handle)
            return original(target, *args)

        try:
            with patch.object(patch_fix, '_stage_bytes', side_effect=inject):
                result = self.apply(FileEdit('parent/data', 'create', replace='new'))
            self.assertTrue(attempted, result)
            self.assertTrue(changed, '必须实际安装重解析点，不能以静态检查代替')
            self.assertEqual((outside / 'data').read_bytes(), b'outside', result)
            self.assertEqual(sorted(p.name for p in outside.iterdir()), ['data'])
        finally:
            if changed:
                parent.rmdir()

    def test_new_parent_replaced_before_creation_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        original = patch_fix._stage_bytes

        def inject(target, *args):
            self.link_directory(self.root / 'new', outside)
            return original(target, *args)

        try:
            with patch.object(patch_fix, '_stage_bytes', side_effect=inject):
                result = self.apply(FileEdit('new/deep/data', 'create', replace='new'))
            self.assertFalse(result['ok'], result)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            alias = self.root / 'new'
            alias.rmdir() if os.name == 'nt' else alias.unlink()

    def test_rollback_interrupt_cleanup_and_recovery(self):
        original = patch_paths.AnchoredFile.replace_from
        for failure in ('permission', 'interrupt', 'rollback'):
            for create in (False, True):
                with self.subTest(failure=failure, create=create):
                    first = 'new/deep/data' if create else 'first'
                    (self.root / 'first').write_bytes(b'old\r\n')
                    (self.root / 'second').write_bytes(b'old')
                    calls = []

                    def fail(target, staged):
                        calls.append(target.path.name)
                        if target.path.name == 'second' or (failure == 'rollback' and len(calls) > 1):
                            if failure == 'interrupt':
                                raise KeyboardInterrupt()
                            raise PermissionError('模拟提交或回滚失败')
                        return original(target, staged)

                    with patch.object(patch_paths.AnchoredFile, 'replace_from', new=fail):
                        result = self.apply(FileEdit(first, 'create' if create else 'replace', 'old', 'new'),
                                            FileEdit('second', 'replace', 'old', 'new'))
                    self.assertFalse(result['ok'], result)
                    self.assertEqual((self.root / 'second').read_bytes(), b'old')
                    if failure == 'rollback' and not create:
                        self.assertEqual(result['applied'], 1)
                        recovery = Path(result['results'][0]['recovery_file'])
                        self.assertEqual(recovery.read_bytes(), b'old\r\n')
                        self.assertIn(str(recovery), patch_fix.format_apply_result(result))
                        recovery.unlink()
                    else:
                        self.assertEqual(result['applied'], 0, result)
                        self.assertEqual(result['results'][0]['status'], 'rolled_back')
                        self.assertEqual((self.root / 'first').read_bytes(), b'old\r\n')
                        self.assertFalse((self.root / 'new').exists())
                    self.assertFalse(list(self.root.rglob('.reviewagent-*')))

    def test_dry_run_new_directories_crlf_and_actual_platform_mode(self):
        target = self.root / 'first'
        target.write_bytes(b'old\r\nsecond\r\n')
        target.chmod(0o751)
        mode = target.stat().st_mode & 0o777
        edits = [FileEdit('first', 'replace', 'old\nsecond', 'new\nsecond'),
                 FileEdit('new/deep/data', 'create', replace='new\n')]
        result = self.apply(*edits, dry_run=True)
        self.assertTrue(result['ok'], result)
        self.assertFalse((self.root / 'new').exists())
        self.assertEqual(target.read_bytes(), b'old\r\nsecond\r\n')
        result = self.apply(*edits)
        self.assertTrue(result['ok'], result)
        self.assertEqual(target.read_bytes(), b'new\r\nsecond\r\n')
        self.assertEqual(target.stat().st_mode & 0o777, mode)
        self.assertEqual((self.root / 'new/deep/data').read_bytes(), b'new\n')

    def test_parent_swap_during_commit_and_rollback_stays_anchored(self):
        parent = self.root / 'parent'
        parent.mkdir()
        (parent / 'first').write_bytes(b'old')
        (self.root / 'second').write_bytes(b'old')
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'first').write_bytes(b'outside')
        parked = self.root / 'parked'
        original = patch_paths.AnchoredFile.replace_from
        attempted, swapped = [], []

        def fail_second(target, staged):
            if target.path.name == 'second':
                attempted.append(True)
                try:
                    parent.rename(parked)
                except PermissionError:
                    pass
                else:
                    self.link_directory(parent, outside)
                    swapped.append(True)
                raise PermissionError('模拟后续提交失败')
            return original(target, staged)

        try:
            with patch.object(patch_paths.AnchoredFile, 'replace_from', new=fail_second):
                result = self.apply(FileEdit('parent/first', 'replace', 'old', 'new'),
                                    FileEdit('second', 'replace', 'old', 'new'))
            self.assertTrue(attempted, result)
            self.assertFalse(result['ok'], result)
            self.assertEqual(result['results'][0]['status'], 'rolled_back')
            self.assertEqual(((parked if swapped else parent) / 'first').read_bytes(), b'old')
            self.assertEqual((outside / 'first').read_bytes(), b'outside')
            self.assertEqual(sorted(p.name for p in outside.iterdir()), ['first'])
            self.assertFalse(list((parked if swapped else parent).glob('.reviewagent-*')))
        finally:
            if swapped:
                parent.rmdir() if os.name == 'nt' else parent.unlink()

    def test_root_ancestor_replacement_cannot_redirect_writes(self):
        target = self.root / 'first'
        target.write_bytes(b'old')
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'first').write_bytes(b'outside')
        parked = self.base / 'parked'
        original = patch_fix._stage_bytes
        attempted, swapped = [], []

        def swap(target, *args):
            if not attempted:
                attempted.append(True)
                try:
                    self.root.rename(parked)
                except PermissionError:
                    pass
                else:
                    self.link_directory(self.root, outside)
                    swapped.append(True)
            return original(target, *args)

        try:
            with patch.object(patch_fix, '_stage_bytes', side_effect=swap):
                result = self.apply(FileEdit('first', 'replace', 'old', 'new'))
            self.assertTrue(result['ok'], result)
            self.assertTrue(attempted)
            self.assertEqual((outside / 'first').read_bytes(), b'outside')
            self.assertEqual(((parked if swapped else self.root) / 'first').read_bytes(), b'new')
        finally:
            if swapped:
                self.root.rmdir() if os.name == 'nt' else self.root.unlink()

    def test_validation_read_failure_has_no_writes(self):
        target = self.root / 'first'
        target.write_bytes(b'old')
        with patch.object(patch_paths.AnchoredFile, 'snapshot', side_effect=PermissionError('拒绝读取')):
            result = self.apply(FileEdit('first', 'replace', 'old', 'new'))
        self.assertFalse(result['ok'], result)
        self.assertEqual(target.read_bytes(), b'old')

    @unittest.skipUnless(os.name == 'nt', 'Windows 只读属性语义')
    def test_readonly_target_rejects_entire_patch_without_staging(self):
        target = self.root / 'readonly.txt'
        target.write_bytes(b'old')
        target.chmod(0o444)
        try:
            result = self.apply(FileEdit('new.txt', 'create', replace='new'),
                                FileEdit('readonly.txt', 'replace', 'old', 'new'))
            self.assertFalse(result['ok'], result)
            self.assertEqual(target.read_bytes(), b'old')
            self.assertFalse((self.root / 'new.txt').exists())
            self.assertFalse(list(self.root.glob('.reviewagent-*')))
        finally:
            target.chmod(0o666)

    def test_repository_root_alias_is_canonicalized(self):
        alias = self.base / 'root-alias'
        (self.root / 'data').write_bytes(b'old')
        self.link_directory(alias, self.root)
        try:
            result = patch_fix.apply_fix(ProposedFix(files=[
                FileEdit('data', 'replace', 'old', 'new')]), root=alias)
            self.assertTrue(result['ok'], result)
            self.assertEqual(Path(result['root']), self.root.resolve())
            self.assertEqual((self.root / 'data').read_bytes(), b'new')
        finally:
            alias.rmdir() if os.name == 'nt' else alias.unlink()

    def test_unsupported_platform_fails_closed(self):
        with patch.object(patch_paths, '_handles_supported', return_value=False):
            result = self.apply(FileEdit('data', 'create', replace='new'))
        self.assertFalse(result['ok'], result)
        self.assertIn('安全固定目录句柄', result['error'])
        self.assertFalse((self.root / 'data').exists())


if __name__ == '__main__':
    unittest.main()
