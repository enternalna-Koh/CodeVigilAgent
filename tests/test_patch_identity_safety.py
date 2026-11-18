"""身份与回滚回归：真实工作区只预演，事务故障使用内存对象。"""
import os
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.patch_fix import FileEdit, ProposedFix, apply_fix, _apply_anchored
from scripts.patch_paths import PatchPaths

ROOT = Path(__file__).resolve().parents[1]


class MemoryFile:
    def __init__(self, paths, path, data=None, identity=None):
        self.paths, self.path = paths, path
        self.data, self.identity = data, identity

    def __str__(self):
        return str(self.path)

    def exists(self):
        return self.data is not None

    def snapshot(self):
        if self.data is None:
            raise FileNotFoundError(str(self.path))
        return self.data, 0o666

    def read_bytes(self):
        return self.snapshot()[0]

    def stage(self, data, mode):
        self.paths.counter += 1
        staged = MemoryFile(self.paths, self.path.with_name(f'.backup-{self.paths.counter}'),
                            data, (1, self.paths.counter + 100))
        self.paths.staged.append(staged)
        return staged

    def replace_from(self, staged):
        if self.path.name == 'second':
            self.paths.before_failure()
            raise PermissionError('模拟第二文件写入失败')
        self.data, self.identity = staged.data, staged.identity
        staged.data = None

    def unlink(self):
        self.data = None


class MemoryPaths:
    def __init__(self, first=b'old', aliases=False):
        self.root = ROOT
        self.counter, self.staged = 0, []
        self.first = MemoryFile(self, ROOT / 'first', first, (1, 1))
        self.second = MemoryFile(self, ROOT / 'second', b'old', (1, 1 if aliases else 2))
        self.before_failure = lambda: None

    def target(self, relative):
        return self.first if relative.name == 'first' else self.second


def transaction(paths, create=False, dry_run=False):
    fix = ProposedFix(files=[FileEdit('first', 'create' if create else 'replace', 'old', 'new'),
                             FileEdit('second', 'replace', 'old', 'new')])
    result = dict(root=str(ROOT), ok=False, applied=0, total=2, dry_run=dry_run, results=[])
    with patch('scripts.patch_fix._git_metadata_paths', return_value=[]):
        return _apply_anchored(fix, paths, dry_run, result)


class RollbackIdentityTests(unittest.TestCase):
    def test_concurrent_save_is_not_overwritten_and_backup_is_retained(self):
        for create in (False, True):
            for same_bytes in (False, True):
                with self.subTest(create=create, same_bytes=same_bytes):
                    paths = MemoryPaths(first=None if create else b'old')

                    def save():
                        paths.first.data = b'new' if same_bytes else b'user-save'
                        paths.first.identity = (1, 999)

                    paths.before_failure = save
                    result = transaction(paths, create=create)
                    row = result['results'][0]
                    self.assertFalse(result['ok'], result)
                    self.assertEqual(row['status'], 'rollback_failed')
                    self.assertIn('回滚冲突', row['error'])
                    self.assertEqual(result['rollback_errors'], ['first'])
                    self.assertEqual(paths.first.data, b'new' if same_bytes else b'user-save')
                    if not create:
                        backup = next(s for s in paths.staged if str(s) == row['recovery_file'])
                        self.assertEqual(backup.data, b'old')

    def test_in_place_save_with_same_identity_is_not_overwritten(self):
        paths = MemoryPaths()
        paths.before_failure = lambda: setattr(paths.first, 'data', b'user-save')
        result = transaction(paths)
        self.assertEqual(result['results'][0]['status'], 'rollback_failed')
        self.assertEqual(paths.first.data, b'user-save')
        self.assertEqual([s.data for s in paths.staged if s.data is not None], [b'old'])

    def test_unchanged_transaction_output_is_restored(self):
        for create in (False, True):
            with self.subTest(create=create):
                paths = MemoryPaths(first=None if create else b'old')
                result = transaction(paths, create=create)
                self.assertEqual(result['results'][0]['status'], 'rolled_back')
                self.assertEqual(paths.first.data, None if create else b'old')
                self.assertTrue(all(s.data is None for s in paths.staged))

    def test_deleted_target_is_not_recreated_and_backup_is_retained(self):
        paths = MemoryPaths()
        paths.before_failure = lambda: setattr(paths.first, 'data', None)
        result = transaction(paths)
        row = result['results'][0]
        self.assertEqual(row['status'], 'rollback_failed')
        self.assertIsNone(paths.first.data)
        self.assertEqual([s.data for s in paths.staged if s.data is not None], [b'old'])
        self.assertIn('recovery_file', row)

    def test_duplicate_identity_rejected_even_with_different_names(self):
        paths = MemoryPaths(aliases=True)
        result = transaction(paths, dry_run=True)
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['applied'], 0)
        self.assertIn('同一文件身份', result['results'][1]['error'])
        self.assertEqual(paths.staged, [])

    def test_identity_change_with_same_bytes_before_commit_is_rejected(self):
        paths = MemoryPaths()
        original = paths.first.stage

        def swap(data, mode):
            paths.first.identity = (1, 999)
            return original(data, mode)

        paths.first.stage = swap
        result = transaction(paths)
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['applied'], 0)
        self.assertEqual(paths.first.data, b'old')
        self.assertEqual(paths.first.identity, (1, 999))


class RealIdentityTests(unittest.TestCase):
    def apply(self, *edits):
        return apply_fix(ProposedFix(files=list(edits)), root=ROOT, dry_run=True)

    def test_regular_file_dry_run_stays_legal(self):
        target = ROOT / 'scripts/patch_fix.py'
        before = target.read_bytes()
        result = self.apply(FileEdit('scripts/patch_fix.py', 'replace', 'def work_root(', 'def work_root('))
        self.assertTrue(result['ok'], result)
        self.assertEqual(target.read_bytes(), before)

    def test_hardlink_identity_is_rejected_from_open_file_stat(self):
        # 不创建或清理链接；由真实句柄读取，仅注入 fstat 的链接计数。
        real_stat = os.fstat

        def linked(fd):
            info = real_stat(fd)
            return SimpleNamespace(st_mode=info.st_mode, st_dev=info.st_dev,
                                   st_ino=info.st_ino, st_nlink=2)

        with closing(PatchPaths(ROOT)) as paths, patch('scripts.patch_paths.os.fstat', side_effect=linked):
            target = paths.target(Path('scripts/patch_fix.py'))
            with self.assertRaisesRegex(ValueError, '硬链接'):
                target.snapshot()

    @unittest.skipUnless(os.name == 'nt', 'NTFS 大小写别名')
    def test_case_alias_duplicate_is_rejected(self):
        result = self.apply(FileEdit('scripts/patch_fix.py', 'replace', 'def work_root(', 'one'),
                            FileEdit('SCRIPTS/PATCH_FIX.PY', 'replace', 'def work_root(', 'two'))
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['applied'], 0)

    @unittest.skipUnless(os.name == 'nt', 'NTFS 8.3 别名')
    def test_short_parent_and_leaf_aliases_are_rejected(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        short_path = kernel.GetShortPathNameW
        short_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        short_path.restype = wintypes.DWORD
        exercised = set()
        for relative, search in (('.git', 'gitdir:'),
                                 ('scripts/specialist_context.py', 'from __future__ import annotations'),
                                 ('scripts/cli_commands/__init__.py', 'from __future__ import annotations')):
            target = ROOT / relative
            if not target.is_file():
                continue
            buffer = ctypes.create_unicode_buffer(32768)
            length = short_path(str(target), buffer, len(buffer))
            self.assertGreater(length, 0)
            self.assertLess(length, len(buffer))
            full_short = Path(buffer.value)
            # 根路径允许规范化；只把目标路径内真实短名交给验证器。
            count = len(Path(relative).parts)
            alias = Path(*full_short.parts[-count:])
            if alias == Path(relative):
                continue
            before = target.read_bytes()
            self.assertIn(search.encode(), before)
            result = self.apply(FileEdit(str(alias), 'replace', search, 'audit:'))
            self.assertFalse(result['ok'], result)
            self.assertEqual(result['applied'], 0)
            self.assertEqual(target.read_bytes(), before)
            exercised.add(relative)
        if not exercised:
            self.skipTest('卷没有为这些文件生成 8.3 短名')


if __name__ == '__main__':
    unittest.main()
