import unittest

from scripts.conversation_agent import ConversationAgent, ContextFetcher, bound_context
from unittest.mock import patch


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def fetch_url(self, url):
        self.calls.append(url)
        return {
            'type': 'pr', 'title': 'Fix HCCL 507049', 'body': 'Move initialization order',
            'url': url, 'state': 'open', 'comments': [], 'files': [
                {'file': 'src/model.py', 'patch': '-old\n+new'}], 'reviews': [],
            'inline_comments': [], 'warnings': []
        }


class FakeKnowledge:
    warnings = []
    def search(self, query, limit=3):
        return [{'title': 'historical 507049', 'url': 'https://example.test/issue/1',
                 'excerpt': 'SDMA', 'score': 1, 'matched_terms': ['507049']}]


class FakeClient:
    def __init__(self):
        self.messages = []
    def chat_with_history(self, messages, **kwargs):
        self.messages.append(messages)
        return '需要检查初始化顺序。'


class ConversationTests(unittest.TestCase):
    def test_client_exception_preserves_context(self):
        class BrokenClient:
            def chat_with_history(self, *args, **kwargs):
                raise RuntimeError('transport failure')
        agent = ConversationAgent(BrokenClient(), FakeKnowledge(), FakeFetcher())
        self.assertIn('已保留', agent.answer('https://github.com/a/b/pull/1'))
        self.assertEqual(len(agent.contexts), 1)
        self.assertEqual(agent.history, [])

    def test_non_dict_fetch_failure_is_reported(self):
        class BrokenFetcher:
            def fetch_url(self, url):
                return ['unexpected']
        agent = ConversationAgent(FakeClient(), FakeKnowledge(), BrokenFetcher())
        self.assertIn('响应格式异常', agent.answer('https://github.com/a/b/issues/1'))

    def test_default_fetcher_constructs_and_validates_host(self):
        agent = ConversationAgent(FakeClient(), FakeKnowledge())
        self.assertIsInstance(agent.fetcher, ContextFetcher)
        self.assertIsNone(agent.fetcher.parse_url('https://github.com.evil.test/a/b/pull/1'))
        self.assertEqual(agent.fetcher.parse_url('https://github.com/a/b/issues/12#comment')['number'], 12)

    def test_pr_fetches_patches_reviews_and_warns_partial_comments(self):
        fetcher = ContextFetcher()
        def api(endpoint):
            if '?' not in endpoint:
                return {'title': 'PR', 'body': 'body', 'html_url': 'https://github.com/a/b/pull/1'}
            if '/files?' in endpoint:
                return [{'filename': 'model.py', 'patch': '+foo()'}]
            if '/reviews?' in endpoint:
                return [{'body': 'needs fix'}]
            return {'error': 'rate limited'}
        with patch.object(fetcher, 'fetch_api', side_effect=api):
            result = fetcher.fetch_url('https://github.com/a/b/pull/1')
        self.assertEqual(result['files'][0]['patch'], '+foo()')
        self.assertEqual(result['reviews'][0]['body'], 'needs fix')
        self.assertTrue(result['warnings'])

    def test_context_budget_marks_truncation(self):
        context = bound_context({'body': 'a' * 100, 'files': [{'patch': 'b' * 100}], 'warnings': []}, budget=120)
        self.assertEqual(len(context['files'][0]['patch']), 20)
        self.assertTrue(context['warnings'])

    def test_url_fetch_and_followup_reuses_context(self):
        client, fetcher = FakeClient(), FakeFetcher()
        agent = ConversationAgent(client, FakeKnowledge(), fetcher)
        first = agent.answer('请分析 https://github.com/a/b/pull/1')
        second = agent.answer('这个问题的根因是什么？')
        self.assertIn('初始化顺序', first)
        self.assertIn('初始化顺序', second)
        self.assertEqual(fetcher.calls, ['https://github.com/a/b/pull/1'])
        self.assertIn('historical 507049', str(client.messages[0]))
        self.assertIn('Fix HCCL 507049', str(client.messages[1]))

    def test_failed_url_does_not_replace_previous_context(self):
        class F(FakeFetcher):
            def fetch_url(self, url):
                return {'error': 'rate limited'}
        agent = ConversationAgent(FakeClient(), FakeKnowledge(), F())
        self.assertIn('无法分析', agent.answer('分析 https://github.com/a/b/pull/1'))
        self.assertEqual(agent.contexts, [])


if __name__ == '__main__':
    unittest.main()
