import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_work


@unittest.skipUnless(shutil.which('git'), '需要 Git')
class GitMonitorSafetyTests(unittest.TestCase):
    def setUp(self):
        # 保留临时仓库样本，不注册清理操作。
        self.root = Path(tempfile.mkdtemp(prefix='cv-git-monitor-'))
        self.marker = 'CV_FSMONITOR_STDERR_SENTINEL'
        self.environment = {
            'GIT_CONFIG_COUNT': '2',
            'GIT_CONFIG_KEY_0': 'core.fsmonitor',
            'GIT_CONFIG_VALUE_0': f'printf {self.marker} >&2',
            'GIT_CONFIG_KEY_1': 'core.fsmonitorHookVersion',
            'GIT_CONFIG_VALUE_1': '2',
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull,
        }
        self.git('init')
        self.file = self.root / 'sample.txt'
        self.file.write_text('staged sample\n', encoding='utf-8')
        self.git('-c', 'core.fsmonitor=false', 'add', 'sample.txt')
        self.file.write_text('working sample\n', encoding='utf-8')
        self.nested = self.root / 'nested'
        self.nested.mkdir()

    def git(self, *args, env=None):
        return subprocess.run(['git', *args], cwd=self.root,
                              env=dict(os.environ, **(env or {})), check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8')

    def test_control_diff_really_invokes_stderr_only_monitor(self):
        result = self.git('diff', '--no-ext-diff', '--no-textconv', env=self.environment)
        self.assertIn(self.marker, result.stderr)
        self.assertNotIn(self.marker, result.stdout)
        self.assertIn('working sample', result.stdout)

    def test_diff_reports_disable_monitor_for_working_and_staged_reads(self):
        with patch.dict(os.environ, self.environment):
            for staged in (False, True):
                with self.subTest(staged=staged):
                    result = git_work.diff_report(cwd=str(self.root), staged=staged)
                    self.assertNotIn(self.marker, result)
                    self.assertIn('staged sample' if staged else 'working sample', result)

    def test_common_runner_disables_monitor_from_subdirectory(self):
        with patch.dict(os.environ, self.environment):
            for args in (['status', '--porcelain'], ['diff', '--no-ext-diff', '--no-textconv']):
                with self.subTest(args=args):
                    result = git_work.run_git(args, cwd=str(self.nested))
                    self.assertTrue(result['ok'], result)
                    self.assertNotIn(self.marker, result['out'])

    def test_diff_report_keeps_existing_run_git_mock_contract(self):
        def fake(args, cwd=None, timeout=120):
            if args == ['rev-parse', '--is-inside-work-tree']:
                return {'ok': True, 'out': 'true'}
            self.assertEqual(args[:3], ['diff', '--no-ext-diff', '--no-textconv'])
            return {'ok': True, 'out': 'sample diff'}

        with patch.object(git_work, 'run_git', side_effect=fake):
            self.assertIn('sample diff', git_work.diff_report(cwd=str(self.root)))


if __name__ == '__main__':
    unittest.main()
