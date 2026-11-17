"""Review scope and failure status regressions; no model or network calls."""
import argparse
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import review_cli
from scripts.chat_review import run_local_review
from scripts.repo_context import collect_repo_context, format_repo_prompt
from scripts.smart_reviewer import SmartReviewer
from test_reliability import run_cli_review


APPROVAL = json.dumps({'issues': [], 'overall_assessment': 'No issues',
                       'recommendation': 'approve'})


class BinaryCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git('init')
        self.name = '资料 with spaces.dat' if os.name == 'nt' else '资料 with\ttab.dat'
        (self.root / self.name).write_bytes(b'\x00old')
        (self.root / 'a.py').write_text('x = 1\n', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        (self.root / self.name).write_bytes(b'\x00new')
        (self.root / 'a.py').write_text('x = 2\n', encoding='utf-8')

    def git(self, *args):
        return subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=t@example.invalid',
                               *args], cwd=self.root, check=True, capture_output=True)

    def test_binary_paths_survive_tabs_and_staging(self):
        for staged in (False, True):
            if staged:
                self.git('add', '.')
            context = collect_repo_context(str(self.root), staged=staged)
            self.assertEqual(context['unreviewed_files'], [self.name])
            self.assertIn('二进制', format_repo_prompt(context))

    def test_model_approval_is_downgraded_and_chat_shows_omissions(self):
        with patch('scripts.smart_reviewer.get_ai_client') as factory:
            factory.return_value.chat.return_value = APPROVAL
            code, output, _ = run_cli_review(self.root)
            md, chat_report = run_local_review(path=self.root, offline=False)
        self.assertEqual(code, 0)
        for report in (json.loads(output), chat_report):
            result = report['review_result']
            self.assertEqual(result['coverage'], 'partial')
            self.assertEqual(result['recommendation'], 'comment')
            self.assertEqual(result['unreviewed_files'], [self.name])
        self.assertIn('二进制', md)
        self.assertIn('coverage=partial', md)

    def test_require_full_rejects_before_constructing_model(self):
        with patch('scripts.smart_reviewer.get_ai_client') as factory:
            code, _, error = run_cli_review(self.root, require_full=True)
        self.assertEqual(code, 1)
        self.assertIn('二进制', error)
        factory.assert_not_called()


class LegacyFailureTests(unittest.TestCase):
    def run_review(self, response):
        with patch('scripts.smart_reviewer.get_ai_client') as factory:
            factory.return_value.chat.return_value = response
            reviewer = SmartReviewer('unused.json', verbose=False)
            with patch('review_cli.SmartReviewer', return_value=reviewer), redirect_stdout(io.StringIO()):
                return review_cli.cmd_review(argparse.Namespace(config='unused.json',
                    git_diff=False, staged=False, file=None, text='x = 1', output=None, quiet=True))

    def test_invalid_or_failed_model_response_exits_nonzero(self):
        for response in ('{}', 'Error: unavailable', 'not json'):
            with self.subTest(response=response):
                self.assertEqual(self.run_review(response), 1)

    def test_valid_review_still_exits_zero(self):
        self.assertEqual(self.run_review(APPROVAL), 0)
