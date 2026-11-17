"""Patch boundaries and recovery use only isolated local files and Git repos."""
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.patch_fix import FileEdit, ProposedFix, apply_fix, format_apply_result, parse_fix_json, preview_fix
from scripts.patch_paths import AnchoredFile


class PatchSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': os.devnull,
                                          'GIT_CONFIG_NOSYSTEM': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR'):
            old = os.environ.pop(key, None)
            if old is not None:
                self.addCleanup(os.environ.__setitem__, key, old)

    def git(self, *args, cwd=None):
        return subprocess.run(['git', *args], cwd=cwd or self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def apply(self, *edits, **kwargs):
        return apply_fix(ProposedFix(files=list(edits)), root=self.root, **kwargs)

    def assert_not_applied(self, result):
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['applied'], 0, result)

    def test_parser_rejects_whole_patch_with_invalid_path_or_action(self):
        good = {'path': 'good.py', 'search': 'old', 'replace': 'new'}
        for path, action in (('.git/config', 'replace'), ('nested/.GIT/config', 'replace'),
                             ('../outside', 'replace'), ('good.py', 'delete')):
            with self.subTest(path=path, action=action), self.assertRaises(ValueError):
                parse_fix_json(json.dumps({'files': [good, {'path': path, 'action': action,
                                                          'replace': 'marker'}]}))

    def test_preview_displays_complete_edit_content(self):
        search, replacement = 'old' * 200, 'new' * 200 + 'END_OF_EDIT'
        preview = preview_fix(ProposedFix(files=[FileEdit('first.py', 'replace', search, replacement),
                                                  FileEdit('new.py', 'create', replace=replacement)]), self.root)
        self.assertIn(search, preview)
        self.assertEqual(preview.count(replacement), 2)

    def test_git_directory_and_symlink_alias_are_rejected(self):
        self.git('init', '-q')
        original = (self.root / '.git/config').read_bytes()
        paths = ['.git/config', 'nested/.git/config']
        try:
            (self.root / 'alias').symlink_to(self.root / '.git', target_is_directory=True)
            paths.append('alias/config')
        except OSError:
            pass
        for path in paths:
            with self.subTest(path=path):
                result = self.apply(FileEdit(path, 'replace', '[core]', '[marker]'))
                self.assert_not_applied(result)
                self.assertEqual((self.root / '.git/config').read_bytes(), original)

    def test_separate_git_directory_is_protected_without_dot_git_in_path(self):
        metadata = self.root / 'git-state'
        self.git('init', '-q', '--separate-git-dir', str(metadata))
        original = (metadata / 'config').read_bytes()
        result = self.apply(FileEdit('git-state/config', 'replace', '[core]', '[marker]'))
        self.assert_not_applied(result)
        self.assertEqual((metadata / 'config').read_bytes(), original)

    def test_common_git_directory_and_its_alias_are_protected(self):
        common = self.root / 'common-state'
        common.mkdir()
        (common / 'config').write_text('old\n')
        git_dir = self.root / 'worktree-state'
        git_dir.mkdir()
        response = subprocess.CompletedProcess([], 0, f'{git_dir}\n{common}\n', '')
        with patch('scripts.patch_fix.subprocess.run', return_value=response):
            result = self.apply(FileEdit('common-state/config', 'replace', 'old', 'new'))
        self.assert_not_applied(result)
        self.assertEqual((common / 'config').read_text(), 'old\n')

    def test_actual_linked_worktree_rejects_common_dir_alias(self):
        main = self.root / 'main'
        self.git('init', '-q', str(main))
        self.git('-c', 'user.name=Audit', '-c', 'user.email=audit@example.invalid',
                 '-c', 'core.hooksPath=' + str(self.root / 'no-hooks'),
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'init', '--allow-empty', cwd=main)
        linked = self.root / 'linked'
        self.git('worktree', 'add', '--detach', str(linked), cwd=main)
        original = (main / '.git/config').read_bytes()
        try:
            (linked / 'metadata-alias').symlink_to(main / '.git', target_is_directory=True)
        except OSError:
            self.skipTest('Symbolic links unavailable')
        result = apply_fix(ProposedFix(files=[FileEdit('metadata-alias/config', 'replace',
                                                       '[core]', '[marker]')]), root=linked)
        self.assert_not_applied(result)
        self.assertEqual((main / '.git/config').read_bytes(), original)

    def test_bad_later_file_prevents_all_writes_and_directory_creation(self):
        first = self.root / 'first.py'
        first.write_bytes(b'old\r\n')
        second = self.root / 'second.py'
        for bad_bytes, search in ((b'\xffold', 'old'), (b'old old', 'old'), (b'other', 'old')):
            second.write_bytes(bad_bytes)
            with self.subTest(content=bad_bytes):
                result = self.apply(FileEdit('first.py', 'replace', 'old', 'new'),
                                    FileEdit('new/created.py', 'create', replace='new'),
                                    FileEdit('second.py', 'replace', search, 'new'))
                self.assert_not_applied(result)
                self.assertEqual(first.read_bytes(), b'old\r\n')
                self.assertEqual(second.read_bytes(), bad_bytes)
                self.assertFalse((self.root / 'new').exists())

    def test_failed_apply_keeps_pending_fix_and_reports_failure(self):
        from scripts.conversation_agent import ConversationAgent

        target = self.root / 'first.py'
        target.write_bytes(b'old')
        agent = ConversationAgent(MagicMock(), MagicMock(), MagicMock(), network='off')
        agent.work_root = self.root
        fix = ProposedFix(files=[FileEdit('first.py', 'replace', 'missing', 'new')])
        agent.pending_fix = fix
        reply = agent.apply_pending_fix(confirm=True)
        self.assertFalse(agent.last_ok)
        self.assertIs(agent.pending_fix, fix)
        self.assertIn('未写入任何文件', reply)
        self.assertEqual(target.read_bytes(), b'old')

    def test_validation_io_error_and_unavailable_git_fail_closed(self):
        target = self.root / 'first.py'
        target.write_bytes(b'old')
        for operation in ('read', 'git'):
            with self.subTest(operation=operation):
                mocked = ('scripts.patch_paths.AnchoredFile.snapshot' if operation == 'read'
                          else 'scripts.patch_fix.subprocess.run')
                with patch(mocked, side_effect=PermissionError('denied')):
                    result = self.apply(FileEdit('first.py', 'replace', 'old', 'new'))
                self.assert_not_applied(result)
                self.assertEqual(target.read_bytes(), b'old')

    def test_duplicate_resolved_target_is_rejected_before_writing(self):
        target = self.root / 'first.py'
        target.write_bytes(b'old')
        result = self.apply(FileEdit('first.py', 'replace', 'old', 'new'),
                            FileEdit('./first.py', 'replace', 'old', 'other'))
        self.assert_not_applied(result)
        self.assertEqual(target.read_bytes(), b'old')

    def test_later_write_failure_restores_originals_and_modes(self):
        first, second = self.root / 'first.py', self.root / 'second.py'
        first.write_bytes(b'old\r\n')
        first.chmod(0o751)
        original_mode = stat.S_IMODE(first.stat().st_mode)
        if os.name == 'posix':
            self.assertEqual(original_mode, 0o751)
        second.write_bytes(b'old\n')
        replace = AnchoredFile.replace_from

        def fail_second(target, staged):
            if target.path == second:
                raise PermissionError('second write denied')
            replace(target, staged)

        with patch.object(AnchoredFile, 'replace_from', autospec=True, side_effect=fail_second):
            result = self.apply(FileEdit('first.py', 'replace', 'old', 'new'),
                                FileEdit('second.py', 'replace', 'old', 'new'))
        self.assert_not_applied(result)
        self.assertEqual(first.read_bytes(), b'old\r\n')
        self.assertEqual(second.read_bytes(), b'old\n')
        self.assertEqual(stat.S_IMODE(first.stat().st_mode), original_mode)
        self.assertEqual(result['results'][0]['status'], 'rolled_back')
        self.assertFalse(list(self.root.rglob('.reviewagent-*')))

    def test_later_write_failure_removes_new_files_and_directories(self):
        second = self.root / 'second.py'
        second.write_bytes(b'old')
        replace = AnchoredFile.replace_from

        def fail_second(target, staged):
            if target.path == second:
                raise PermissionError('second write denied')
            replace(target, staged)

        with patch.object(AnchoredFile, 'replace_from', autospec=True, side_effect=fail_second):
            result = self.apply(FileEdit('new/a.py', 'create', replace='new'),
                                FileEdit('second.py', 'replace', 'old', 'new'))
        self.assert_not_applied(result)
        self.assertFalse((self.root / 'new').exists())
        self.assertEqual(second.read_bytes(), b'old')

    def test_keyboard_interrupt_during_write_restores_applied_file(self):
        first, second = self.root / 'first.py', self.root / 'second.py'
        first.write_bytes(b'old')
        second.write_bytes(b'old')
        replace = AnchoredFile.replace_from

        def interrupt_second(target, staged):
            if target.path == second:
                raise KeyboardInterrupt()
            replace(target, staged)

        with patch.object(AnchoredFile, 'replace_from', autospec=True, side_effect=interrupt_second):
            result = self.apply(FileEdit('first.py', 'replace', 'old', 'new'),
                                FileEdit('second.py', 'replace', 'old', 'new'))
        self.assert_not_applied(result)
        self.assertEqual(first.read_bytes(), b'old')
        self.assertEqual(second.read_bytes(), b'old')
        self.assertFalse(list(self.root.rglob('.reviewagent-*')))

    def test_rollback_failure_keeps_recovery_copy_and_reports_it(self):
        for name in ('first.py', 'second.py'):
            (self.root / name).write_bytes(b'old')
        replace = AnchoredFile.replace_from
        calls = 0

        def fail_write_and_rollback(target, staged):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise PermissionError('filesystem unavailable')
            replace(target, staged)

        with patch.object(AnchoredFile, 'replace_from', autospec=True,
                          side_effect=fail_write_and_rollback):
            result = self.apply(FileEdit('first.py', 'replace', 'old', 'new'),
                                FileEdit('second.py', 'replace', 'old', 'new'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['rollback_errors'], ['first.py'])
        recovery = Path(result['results'][0]['recovery_file'])
        self.assertEqual(recovery.read_bytes(), b'old')
        self.assertIn(str(recovery), format_apply_result(result))

    def test_success_and_dry_run_preserve_bytes_and_permissions(self):
        target = self.root / 'first.py'
        target.write_bytes(b'old\r\nsecond\r\n')
        target.chmod(0o751)
        original_mode = stat.S_IMODE(target.stat().st_mode)
        if os.name == 'posix':
            self.assertEqual(original_mode, 0o751)
        edit = FileEdit('first.py', 'replace', 'old\nsecond', 'new\nsecond')
        result = self.apply(edit, dry_run=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(target.read_bytes(), b'old\r\nsecond\r\n')
        result = self.apply(edit, FileEdit('new/a.py', 'create', replace='new\n'))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['applied'], 2)
        self.assertEqual(target.read_bytes(), b'new\r\nsecond\r\n')
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), original_mode)
        self.assertEqual((self.root / 'new/a.py').read_bytes(), b'new\n')
        self.assertFalse(list(self.root.rglob('.reviewagent-*')))


if __name__ == '__main__':
    unittest.main()
