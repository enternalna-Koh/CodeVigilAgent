import json
import unittest
from unittest.mock import patch

from scripts.conversation_agent import ConversationAgent
from scripts.web_search import SearchResultsParser, WebSearcher
from test_conversation_agent import FakeClient, FakeKnowledge, FakeFetcher


class Planner(FakeClient):
    def __init__(self, actions):
        super().__init__()
        self.actions = iter(actions)
        self.plans = []

    def chat(self, prompt, **kwargs):
        self.plans.append(json.loads(prompt))
        return json.dumps(next(self.actions))


class Searcher:
    def __init__(self):
        self.queries = []

    def search(self, query, num_results=3):
        self.queries.append(query)
        return [{'title': 'official example', 'url': 'https://www.hiascend.com/document',
                 'snippet': 'Version requirements', 'evidence_status': 'search_snippet_only'}]


class InvestigationTests(unittest.TestCase):
    def test_model_searches_then_fetches_link_then_finishes(self):
        client = Planner([{'tool': 'web_search', 'query': '507049 CANN'},
                          {'tool': 'fetch_pr_issue', 'url': 'https://github.com/a/b/issues/2'},
                          {'tool': 'finish'}])
        searcher, fetcher = Searcher(), FakeFetcher()
        agent = ConversationAgent(client, FakeKnowledge(), fetcher, searcher=searcher)
        agent.answer('507049 怎么排查？')
        self.assertEqual(searcher.queries, ['507049 CANN'])
        self.assertEqual(fetcher.calls, ['https://github.com/a/b/issues/2'])
        self.assertEqual(len(agent.last_tools), 2)
        self.assertIn('official example', str(client.messages[-1]))
        self.assertIn('Version requirements', str(client.plans[1]))

    def test_auto_can_skip_search(self):
        client, searcher = Planner([{'tool': 'finish'}]), Searcher()
        agent = ConversationAgent(client, FakeKnowledge(), FakeFetcher(), searcher=searcher)
        agent.answer('你好')
        self.assertEqual(searcher.queries, [])

    def test_off_does_not_fetch_or_search(self):
        client, fetcher, searcher = FakeClient(), FakeFetcher(), Searcher()
        agent = ConversationAgent(client, FakeKnowledge(), fetcher, network='off', searcher=searcher)
        self.assertIn('联网已关闭', agent.answer('https://github.com/a/b/pull/1'))
        agent.answer('解释这段代码')
        self.assertEqual(fetcher.calls, [])
        self.assertEqual(searcher.queries, [])
        self.assertTrue(client.messages)

    def test_always_search_and_failed_search_reaches_answer(self):
        client, searcher = Planner([{'tool': 'finish'}]), Searcher()
        with patch.object(searcher, 'search', return_value=[{'error': 'service unavailable'}]):
            agent = ConversationAgent(client, FakeKnowledge(), FakeFetcher(), network='on', searcher=searcher)
            agent.answer('最新 CANN 版本')
        self.assertIn('service unavailable', str(client.messages[-1]))

    def test_budget_limits_and_duplicate_tool_is_not_repeated(self):
        actions = [{'tool': 'web_search', 'query': f'query{i}'} for i in range(5)]
        searcher = Searcher()
        agent = ConversationAgent(Planner(actions), FakeKnowledge(), FakeFetcher(), searcher=searcher)
        agent.set_chat_mode('work')
        agent.answer('查版本')
        self.assertEqual(len(searcher.queries), 3)
        self.assertEqual(agent.last_tools[-1]['tool'], 'budget')
        searcher = Searcher()
        action = {'tool': 'web_search', 'query': 'same'}
        agent = ConversationAgent(Planner([action, action]), FakeKnowledge(), FakeFetcher(), searcher=searcher)
        agent.set_chat_mode('work')
        agent.answer('查版本')
        self.assertEqual(len(searcher.queries), 1)

    def test_html_parser_nested_tags_redirects_and_snippets(self):
        parser = SearchResultsParser()
        parser.feed('''<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.hiascend.com%2Fdoc" class="result__a">CANN <b>API</b></a>
<a class="result__snippet">Use <b>NPU</b> &amp; CANN</a>
<a class="result__a" href="javascript:alert(1)">invalid</a>''')
        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0]['title'], 'CANN API')
        self.assertEqual(parser.results[0]['snippet'], 'Use NPU & CANN')
        self.assertEqual(parser.results[0]['url'], 'https://www.hiascend.com/doc')

    def test_captcha_or_empty_search_reports_error(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b'<html>captcha</html>'
        with patch('scripts.web_search.urllib.request.urlopen', return_value=Response()):
            result = WebSearcher().search('CANN')
        self.assertIn('error', result[0])


if __name__ == '__main__':
    unittest.main()
