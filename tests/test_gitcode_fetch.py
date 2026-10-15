import unittest
from unittest.mock import patch

from scripts.conversation_agent import ContextFetcher, is_infra_query


class GitCodeFetchTests(unittest.TestCase):
    def test_parse_gitcode_issue_and_pr(self):
        f = ContextFetcher()
        issue = f.parse_url('https://gitcode.com/Ascend/pytorch/issues/3135')
        self.assertEqual(issue['host'], 'gitcode')
        self.assertEqual(issue['type'], 'issue')
        self.assertEqual(issue['number'], 3135)
        pr = f.parse_url('https://gitcode.com/Ascend/pytorch/pulls/12')
        self.assertEqual(pr['type'], 'pr')
        self.assertEqual(pr['number'], 12)

    def test_parse_still_rejects_evil_host(self):
        f = ContextFetcher()
        self.assertIsNone(f.parse_url('https://gitcode.com.evil/a/b/issues/1'))

    def test_community_task_is_infra(self):
        self.assertTrue(is_infra_query('7月社区任务第三期-28'))

    def test_fetch_gitcode_issue_mocked(self):
        f = ContextFetcher()

        def api(endpoint):
            if endpoint.endswith('/issues/3135'):
                return {
                    'title': '社区任务', 'body': '任务概览', 'html_url': 'https://gitcode.com/x',
                    'state': 'open', 'updated_at': 't',
                }
            if '/comments' in endpoint:
                return [{'body': '老师回复', 'user': {'login': 'mentor'}}]
            return []

        with patch.object(f, 'fetch_gitcode_api', side_effect=api):
            ctx = f.fetch_url('https://gitcode.com/Ascend/pytorch/issues/3135')
        self.assertEqual(ctx['title'], '社区任务')
        self.assertEqual(ctx['host'], 'gitcode')
        self.assertEqual(ctx['comments'][0]['author'], 'mentor')

    def test_patch_dict_normalized(self):
        self.assertIn('@@', ContextFetcher._patch_text({'diff': '@@ -1 +1 @@\n+x'}))


if __name__ == '__main__':
    unittest.main()
