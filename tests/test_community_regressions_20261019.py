"""Offline regressions for collection and skill installation trust boundaries."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import collect_gitcode_community as collector
from scripts import skill_runtime as skills


class CollectionRegressionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for key, relative in (
            ('PROJECT_ROOT', ''), ('RAW_DIR', 'data/raw'), ('CI_DIR', 'data/ci_runs'),
            ('DIALOG_DIR', 'data/review_dialogs'), ('COMMUNITIES_DIR', 'data/communities'),
        ):
            self.stack.enter_context(patch.object(collector, key, self.root / relative))
        self.stack.enter_context(patch.object(collector.time, 'sleep'))
        self.stack.enter_context(patch.dict(os.environ, {'GITCODE_TOKEN': '', 'GITHUB_TOKEN': 'github-secret'}))
        collector.COMMUNITIES_DIR.mkdir(parents=True)
        (collector.COMMUNITIES_DIR / 'sample.json').write_text(json.dumps({
            'name': 'sample', 'repos': [{'owner': 'team', 'repo': 'project', 'collect': ['issues']}],
        }), encoding='utf-8')

    def test_github_token_is_not_sent_to_gitcode(self):
        with patch.object(collector, 'ContextFetcher') as fetcher:
            result = collector.collect_community('sample')
        self.assertFalse(result['ok'])
        fetcher.assert_not_called()

    def test_failed_request_preserves_existing_data(self):
        path = collector.RAW_DIR / 'gitcode_sample_team_project_issues.json'
        collector.write_json(path, [{'number': 99}])
        fetcher = MagicMock()
        fetcher.fetch_gitcode_api.return_value = {'error': 'token invalid'}
        with patch.object(collector, 'ContextFetcher', return_value=fetcher):
            result = collector.collect_community('sample', token='gitcode-secret')
        self.assertFalse(result['ok'])
        self.assertIn('token invalid', result['repos'][0]['error'])
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), [{'number': 99}])

    def test_failed_later_page_does_not_return_partial_success(self):
        fetcher = MagicMock()
        fetcher.fetch_gitcode_api.side_effect = [[{'number': i} for i in range(100)], {'error': '429'}]
        with self.assertRaisesRegex(RuntimeError, '429'):
            collector.fetch_list(fetcher, '/repos/team/project/issues')

    def test_bad_list_entry_is_reported(self):
        fetcher = MagicMock()
        fetcher.fetch_gitcode_api.return_value = [None]
        with self.assertRaisesRegex(RuntimeError, '响应格式'):
            collector.fetch_list(fetcher, '/repos/team/project/issues')

    def test_failed_repo_does_not_stop_other_repositories(self):
        cfg = {'repos': [
            {'owner': 'team', 'repo': 'bad', 'collect': ['issues']},
            {'owner': 'team', 'repo': 'good', 'collect': ['issues']},
        ]}
        fetcher = MagicMock()
        fetcher.fetch_gitcode_api.side_effect = [{'error': 'offline'}, []]
        with patch.object(collector, 'load_community', return_value=cfg), \
                patch.object(collector, 'ContextFetcher', return_value=fetcher):
            result = collector.collect_community('sample', token='gitcode-secret')
        self.assertFalse(result['ok'])
        self.assertEqual([row['ok'] for row in result['repos']], [False, True])

    def test_community_path_traversal_and_invalid_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            collector.load_community('../outside')
        with self.assertRaises(ValueError):
            collector.collect_community('sample', pages=0)
        with self.assertRaises(ValueError):
            collector.collect_community('sample', dialog_limit=-1)

    def test_ci_only_collection_fetches_prs(self):
        fetcher = MagicMock()
        fetcher.fetch_gitcode_api.side_effect = [
            [{'number': 1, 'head': {'sha': 'abc'}}], {'check_runs': []},
        ]
        result = collector.collect_repo(fetcher, 'sample',
                                        {'owner': 'team', 'repo': 'project', 'collect': ['ci']}, 1, 1)
        self.assertTrue(result['ok'])
        self.assertEqual(result['ci'], 1)
        self.assertIn('ci', result['files'])

    def test_dialog_request_error_is_not_an_empty_success(self):
        fetcher = MagicMock()
        fetcher.fetch_gitcode_api.return_value = {'error': 'permission denied'}
        rows = collector.collect_dialogs(fetcher, 'team', 'project', 'issue', [{'number': 1}])
        self.assertIn('permission denied', rows[0]['warnings'])


class SkillInstallationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(skills, 'home_dir', return_value=self.root))
        self.stack.enter_context(patch.object(skills, 'ensure_home', return_value=self.root))
        self.stack.enter_context(patch.dict(os.environ, {'GITCODE_TOKEN': '', 'GITHUB_TOKEN': 'github-secret'}))

    def test_install_does_not_fallback_to_github_token(self):
        with patch.object(skills, '_download_blob_text', return_value='# rules') as download, \
                patch.object(skills, '_list_dir', return_value=[]):
            result = skills.install_skill('test-skill')
        self.assertTrue(result['ok'])
        self.assertFalse(download.call_args.kwargs['token'])

    def test_token_is_a_header_and_not_part_of_request_url(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch.object(skills.urllib.request, 'urlopen', return_value=response) as open_url:
            skills._http_get_json('https://api.gitcode.com/api/v5/repos/team/project', token='gitcode-secret')
        request = open_url.call_args.args[0]
        self.assertNotIn('gitcode-secret', request.full_url)
        self.assertEqual(request.get_header('Authorization'), 'Bearer gitcode-secret')

    def test_reference_traversal_is_rejected_before_any_write(self):
        outside = self.root / 'outside.md'
        outside.write_text('keep', encoding='utf-8')
        with patch.object(skills, '_download_blob_text', return_value='# rules'), \
                patch.object(skills, '_list_dir', return_value=[
                    {'type': 'file', 'name': '../../outside.md', 'size': 12},
                ]):
            result = skills.install_skill('test-skill')
        self.assertFalse(result['ok'])
        self.assertEqual(outside.read_text(encoding='utf-8'), 'keep')
        self.assertFalse((self.root / 'skills/test-skill/SKILL.md').exists())

    def test_failed_reference_fetch_preserves_existing_skill(self):
        dest = self.root / 'skills/test-skill'
        dest.mkdir(parents=True)
        (dest / 'SKILL.md').write_text('old rules', encoding='utf-8')
        with patch.object(skills, '_download_blob_text', side_effect=['# new rules', OSError('offline')]), \
                patch.object(skills, '_list_dir', return_value=[
                    {'type': 'file', 'name': 'guide.md', 'size': 12},
                ]):
            result = skills.install_skill('test-skill')
        self.assertFalse(result['ok'])
        self.assertEqual((dest / 'SKILL.md').read_text(encoding='utf-8'), 'old rules')

    def test_malformed_json_and_utf8_return_install_errors(self):
        for error in (json.JSONDecodeError('bad', 'x', 0), UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'bad')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(skills, '_download_blob_text', side_effect=error):
                self.assertFalse(skills.install_skill('test-skill')['ok'])

    def test_malformed_blob_and_reference_size_return_errors(self):
        with patch.object(skills, '_http_get_json', side_effect=[{'sha': 'abc'}, []]):
            with self.assertRaisesRegex(RuntimeError, 'blob'):
                skills._download_blob_text('team/project', 'SKILL.md')
        with patch.object(skills, '_download_blob_text', return_value='# rules'), \
                patch.object(skills, '_list_dir', return_value=[
                    {'type': 'file', 'name': 'guide.md', 'size': []},
                ]):
            # An empty value means unknown size; the downloaded byte limit still applies.
            self.assertTrue(skills.install_skill('test-skill')['ok'])
        with patch.object(skills, '_download_blob_text', return_value='# rules'), \
                patch.object(skills, '_list_dir', return_value=[
                    {'type': 'file', 'name': 'guide.md', 'size': [1]},
                ]):
            self.assertFalse(skills.install_skill('test-skill')['ok'])

    def test_user_home_write_error_is_reported(self):
        with patch.object(skills, 'ensure_home', side_effect=PermissionError('read only')):
            result = skills.install_skill('test-skill')
        self.assertFalse(result['ok'])
        self.assertIn('read only', result['error'])

    def test_folded_frontmatter_description_is_text(self):
        text = '---\nname: test\ndescription: >\n  first line\n  second line\n---\n# Test'
        self.assertEqual(skills._frontmatter_desc(text), 'first line second line')

    def test_non_gitcode_download_url_is_rejected(self):
        with patch.object(skills, '_http_get_json', return_value={'download_url': 'file:///etc/passwd'}), \
                patch.object(skills.urllib.request, 'urlopen') as open_url:
            with self.assertRaisesRegex(RuntimeError, 'HTTPS'):
                skills._download_blob_text('team/project', 'SKILL.md')
        open_url.assert_not_called()

    def test_absent_optional_reference_directory_is_allowed(self):
        error = urllib.error.HTTPError('https://api.gitcode.com/', 404, 'missing', None, io.BytesIO())
        with patch.object(skills, '_download_blob_text', return_value='# rules'), \
                patch.object(skills, '_list_dir', side_effect=error):
            result = skills.install_skill('test-skill')
        self.assertTrue(result['ok'])

    def test_missing_large_reference_marks_loaded_skill_incomplete(self):
        with patch.object(skills, '_download_blob_text', return_value='# rules'), \
                patch.object(skills, '_list_dir', return_value=[
                    {'type': 'file', 'name': 'guide.md', 'size': 200001},
                ]):
            result = skills.install_skill('test-skill')
        self.assertTrue(result['ok'])
        info = skills.SkillInfo('test-skill', self.root / 'skills/test-skill/SKILL.md', 'test')
        with patch.object(skills, 'find_skill', return_value=info):
            loaded = skills.load_skill('test-skill')
        self.assertEqual(loaded.status, 'incomplete')
        self.assertIn('guide.md', loaded.omitted[0])

    def test_utf8_budget_includes_truncation_marker(self):
        path = self.root / 'SKILL.md'
        path.write_text('规则' * 200, encoding='utf-8')
        info = skills.SkillInfo('test-skill', path, 'test')
        with patch.object(skills, 'find_skill', return_value=info):
            loaded = skills.load_skill('test-skill', max_chars=20, max_bytes=23)
        self.assertEqual(loaded.status, 'incomplete')
        self.assertLessEqual(len(loaded.text), 20)
        self.assertLessEqual(len(loaded.text.encode('utf-8')), 23)


if __name__ == '__main__':
    unittest.main()
