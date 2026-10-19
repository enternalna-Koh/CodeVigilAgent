import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.git_work import (
    commit_changes,
    create_branch,
    https_to_ssh,
    status_report,
    to_ssh_origin,
)


def _git_repo():
    import subprocess
    root = tempfile.mkdtemp()
    subprocess.check_call(['git', 'init'], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(['git', 'config', 'user.email', 't@example.com'], cwd=root)
    subprocess.check_call(['git', 'config', 'user.name', 't'], cwd=root)
    (Path(root) / 'a.txt').write_text('one\n', encoding='utf-8')
    subprocess.check_call(['git', 'add', 'a.txt'], cwd=root)
    subprocess.check_call(['git', 'commit', '-m', 'init'], cwd=root, stdout=subprocess.DEVNULL)
    return root


class GitWorkTests(unittest.TestCase):
    def test_https_to_ssh(self):
        self.assertEqual(
            https_to_ssh('https://github.com/enternalna-Koh/ReviewAgent.git'),
            'git@github.com:enternalna-Koh/ReviewAgent.git',
        )
        self.assertIsNone(https_to_ssh('https://gitlab.com/a/b.git'))

    def test_status_and_commit_branch(self):
        root = _git_repo()
        md = status_report(cwd=root)
        self.assertIn('Git 状态', md)
        (Path(root) / 'a.txt').write_text('two\n', encoding='utf-8')
        out = commit_changes('chore: bump', cwd=root)
        self.assertIn('已提交', out)
        out2 = create_branch('feat/demo', cwd=root)
        self.assertIn('feat/demo', out2)

    def test_to_ssh_origin(self):
        root = _git_repo()
        # no origin yet
        msg = to_ssh_origin(cwd=root)
        self.assertTrue('失败' in msg or 'origin' in msg.lower() or '读取' in msg)


class GitSlashSmoke(unittest.TestCase):
    def test_git_help_via_handler(self):
        from unittest.mock import MagicMock
        from ascend_cli import _handle_git_slash
        from scripts.conversation_agent import ConversationAgent
        agent = ConversationAgent(MagicMock(), MagicMock(), MagicMock())
        with patch('ascend_cli._print_agent_reply') as printer:
            r = _handle_git_slash('help', agent)
        self.assertEqual(r, 'handled')
        printer.assert_called()
        self.assertIn('生产力命令', printer.call_args[0][0])


if __name__ == '__main__':
    unittest.main()
