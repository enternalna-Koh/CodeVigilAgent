import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import git_work


class GitRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.hooksPath', str(self.root / 'no-hooks'))
        self.data = self.root / 'data.txt'
        self.data.write_bytes(b'original\n')
        self.git('add', 'data.txt')
        self.git('commit', '-m', 'init')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=str(self.root), check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8').stdout.strip()

    def test_branch_options_cannot_discard_uncommitted_work(self):
        self.data.write_bytes(b'uncommitted important data\r\n')
        for name in ('-f', '--force', '--detach', '--orphan'):
            with self.subTest(name=name):
                result = git_work.create_branch(name, cwd=str(self.root))
                self.assertIn('不合法', result)
                self.assertEqual(self.data.read_bytes(), b'uncommitted important data\r\n')
                self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_existing_local_branch_can_be_switched(self):
        self.git('branch', 'feature/one')
        self.data.write_bytes(b'uncommitted data\n')
        result = git_work.create_branch('feature/one', cwd=str(self.root))
        self.assertIn('已切换', result)
        self.assertEqual(self.git('branch', '--show-current'), 'feature/one')
        self.assertEqual(self.data.read_bytes(), b'uncommitted data\n')

    def test_failed_creation_does_not_checkout_matching_file(self):
        self.data.write_bytes(b'uncommitted important data\n')
        run_git = git_work.run_git

        def fail_creation(args, **kwargs):
            if args[:2] == ['checkout', '-b']:
                return {'ok': False, 'code': 128, 'out': 'cannot lock ref'}
            return run_git(args, **kwargs)

        with patch.object(git_work, 'run_git', side_effect=fail_creation):
            result = git_work.create_branch('data.txt', cwd=str(self.root))
        self.assertIn('失败', result)
        self.assertEqual(self.data.read_bytes(), b'uncommitted important data\n')
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_new_branch_is_created(self):
        result = git_work.create_branch('feature/new', cwd=str(self.root))
        self.assertIn('已创建', result)
        self.assertEqual(self.git('branch', '--show-current'), 'feature/new')

    def test_github_remote_conversion_preserves_dots(self):
        for url in ('https://github.com/org/repo.name.git',
                    'https://github.com/org/repo.name/',
                    'https://github.com/org/repo.name'):
            with self.subTest(url=url):
                self.assertEqual(git_work.https_to_ssh(url),
                                 'git@github.com:org/repo.name.git')
        self.assertIsNone(git_work.https_to_ssh('https://github.com.evil/org/repo.name'))
        self.assertIsNone(git_work.https_to_ssh('https://github.com/org/repo?token=secret'))

    def test_suggest_commit_message_uses_agent_work_root(self):
        agent = SimpleNamespace(work_root=self.root, pending_fix=None, last_user_text=None)
        with patch.object(git_work, 'run_git', return_value={'out': 'correct project title'}) as run:
            self.assertEqual(git_work.suggest_commit_message(agent), 'correct project title')
        run.assert_called_once_with(['log', '-1', '--pretty=%s'], cwd=self.root)


if __name__ == '__main__':
    unittest.main()
