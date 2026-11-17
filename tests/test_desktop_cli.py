import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ascend_cli
from scripts.repo_context import RepoContextError


class FakeKnowledge:
    warnings = []
    documents = []

    def search(self, query, limit=3):
        return []


class FakeModel:
    provider = type('Provider', (), {'api_key': 'fake-secret-value-123456789'})()

    def __init__(self):
        self.calls = []

    def chat_with_history(self, messages, **kwargs):
        self.calls.append(messages)
        return f"fake reply {len(self.calls)}"


class DesktopChatTests(unittest.TestCase):
    def test_repository_is_used_for_file_mentions_without_named_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / 'chosen-repository'
            repository.mkdir()
            (repository / 'selected.py').write_text('SELECTED_REPO_SENTINEL = 1\n', encoding='utf-8')
            model = FakeModel()
            output = io.StringIO()
            argv = ['ascend_cli.py', 'chat', '--message', 'explain @selected.py',
                    '--repository', str(repository), '--network', 'off', '--json']
            with patch.dict(os.environ, {'REVIEWAGENT_HOME': str(Path(tmp) / 'home')}), \
                    patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()), \
                    patch.object(ascend_cli, 'get_ai_client', return_value=model), \
                    patch('sys.argv', argv), contextlib.redirect_stdout(output):
                self.assertEqual(ascend_cli.main(), 0)
            self.assertTrue(json.loads(output.getvalue())['ok'])
            self.assertIn('SELECTED_REPO_SENTINEL', json.dumps(model.calls[0]))

    def test_named_session_keeps_fake_model_history_and_new_session_isolated(self):
        with tempfile.TemporaryDirectory() as home:
            model = FakeModel()
            sessions = Path(home) / 'sessions'
            sessions.mkdir()
            latest = sessions / 'latest.json'
            latest.write_text('preserve existing latest session', encoding='utf-8')

            def send(session, message):
                output = io.StringIO()
                argv = ['ascend_cli.py', 'chat', '--message', message, '--session', session,
                        '--network', 'off', '--json']
                with patch.dict(os.environ, {'REVIEWAGENT_HOME': home}), \
                        patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()), \
                        patch.object(ascend_cli, 'get_ai_client', return_value=model), \
                        patch('sys.argv', argv), contextlib.redirect_stdout(output):
                    status = ascend_cli.main()
                return status, json.loads(output.getvalue())

            self.assertEqual(send('desktop-test', 'first question')[0], 0)
            self.assertEqual(latest.read_text(encoding='utf-8'), 'preserve existing latest session')
            self.assertEqual(send('desktop-test', 'follow up')[0], 0)
            second_messages = model.calls[1]
            self.assertTrue(any(m['role'] == 'user' and 'first question' in m['content']
                                for m in second_messages))
            self.assertTrue(any(m['role'] == 'assistant' and m['content'] == 'fake reply 1'
                                for m in second_messages))

            self.assertEqual(send('desktop-new', 'fresh question')[0], 0)
            fresh_messages = model.calls[2]
            self.assertFalse(any('first question' in m.get('content', '') for m in fresh_messages))

    def test_history_crud_search_export_and_secret_redaction(self):
        from scripts.session_store import delete_session, list_sessions, load_session, rename_session, session_markdown
        from scripts.conversation_agent import ConversationAgent

        with tempfile.TemporaryDirectory() as home:
            model = FakeModel()
            latest = Path(home) / 'sessions' / 'latest.json'
            latest.parent.mkdir(parents=True)
            latest.write_text('legacy alias remains untouched', encoding='utf-8')
            argv = ['ascend_cli.py', 'chat', '--message',
                    'Discuss fake-secret-value-123456789 and history search', '--session', 'desktop-history',
                    '--network', 'off', '--json']
            with patch.dict(os.environ, {'REVIEWAGENT_HOME': home}), \
                    patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()), \
                    patch.object(ascend_cli, 'get_ai_client', return_value=model), \
                    patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ascend_cli.main(), 0)

            path = Path(home) / 'sessions' / 'desktop-history.json'
            with patch.dict(os.environ, {'REVIEWAGENT_HOME': home}):
                stored = path.read_text(encoding='utf-8')
                self.assertNotIn('fake-secret-value-123456789', stored)
                self.assertNotIn('fake-secret-value-123456789', session_markdown('desktop-history'))
                matches = list_sessions(limit=None, query='history search')
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]['summary'], 'fake reply 1')
                renamed = rename_session('desktop-history', 'Renamed history')
                self.assertEqual(renamed['title'], 'Renamed history')
                self.assertEqual(load_session('desktop-history')['desktop_title'], 'Renamed history')
                self.assertEqual(latest.read_text(encoding='utf-8'), 'legacy alias remains untouched')
                self.assertTrue(delete_session('desktop-history'))
                self.assertFalse(path.exists())
                self.assertFalse(list_sessions(limit=None, query='Renamed history'))

            agent = ConversationAgent(model, knowledge=FakeKnowledge(), fetcher=object())
            agent.history = [{'role': 'user', 'content': 'fake-secret-value-123456789'}]
            exported = Path(home) / 'safe-export.md'
            agent.export_session(str(exported))
            self.assertNotIn('fake-secret-value-123456789', exported.read_text(encoding='utf-8'))

    def test_running_message_recovers_as_interrupted(self):
        from scripts.session_store import list_sessions

        with tempfile.TemporaryDirectory() as home:
            session_dir = Path(home) / 'sessions'
            session_dir.mkdir()
            session_path = session_dir / 'desktop-running.json'
            session_path.write_text(json.dumps({
                'version': 1, 'saved_at': '2026-11-09T00:00:00-08:00',
                'history': [], 'contexts': [], 'work_root': home,
                'desktop_title': 'Interrupted request', 'desktop_repository': home,
                'desktop_messages': [{'role': 'user', 'content': 'resume this', 'status': 'running'}],
            }), encoding='utf-8')
            with patch.dict(os.environ, {'REVIEWAGENT_HOME': home}):
                rows = list_sessions(limit=None)
                restored = json.loads(session_path.read_text(encoding='utf-8'))
            self.assertEqual(rows[0]['status'], 'interrupted')
            self.assertEqual(restored['desktop_messages'][0]['status'], 'interrupted')
            self.assertEqual(restored['history'], [{'role': 'user', 'content': 'resume this'}])

    def test_cli_history_commands_and_failed_turn_state(self):
        class FailedModel:
            provider = type('Provider', (), {'api_key': 'secret-test-key-123456'})()

            def chat_with_history(self, messages, **kwargs):
                return 'Error: secret-test-key-123456 rejected'

        with tempfile.TemporaryDirectory() as home:
            def cli(argv, client=None):
                output = io.StringIO()
                with patch.dict(os.environ, {'REVIEWAGENT_HOME': home}), \
                        patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()), \
                        patch.object(ascend_cli, 'get_ai_client', return_value=client or FailedModel()), \
                        patch('sys.argv', ['ascend_cli.py'] + argv), contextlib.redirect_stdout(output):
                    status = ascend_cli.main()
                return status, output.getvalue()

            status, output = cli(['chat', '--message', 'broken request', '--session', 'desktop-failed',
                                  '--network', 'off', '--json'])
            self.assertEqual(status, 1)
            self.assertNotIn('secret-test-key-123456', output)
            session_path = Path(home) / 'sessions' / 'desktop-failed.json'
            session = json.loads(session_path.read_text(encoding='utf-8'))
            self.assertEqual(session['desktop_messages'][-1]['status'], 'failed')
            self.assertFalse(any(row['role'] == 'assistant' for row in session['desktop_messages']))
            self.assertNotIn('secret-test-key-123456', session_path.read_text(encoding='utf-8'))

            status, output = cli(['sessions', 'list', '--query', 'broken request'])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output)['sessions'][0]['status'], 'failed')
            status, output = cli(['sessions', 'show', 'desktop-failed'])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output)['session']['title'], 'broken request')
            self.assertEqual(cli(['sessions', 'rename', 'desktop-failed', 'Changed title'])[0], 0)
            export = Path(home) / 'export.md'
            self.assertEqual(cli(['sessions', 'export', 'desktop-failed', '--output', str(export)])[0], 0)
            self.assertIn('Changed title', export.read_text(encoding='utf-8'))
            self.assertNotIn('secret-test-key-123456', export.read_text(encoding='utf-8'))
            self.assertEqual(cli(['sessions', 'delete', 'desktop-failed'])[0], 0)
            self.assertFalse(session_path.exists())

    def test_json_chat_failure_is_nonzero_and_never_prints_api_key(self):
        class FailedModel:
            provider = type('Provider', (), {'api_key': 'secret-test-key'})()

            def chat_with_history(self, messages, **kwargs):
                return 'Error: secret-test-key rejected'

        with tempfile.TemporaryDirectory() as home:
            output = io.StringIO()
            argv = ['ascend_cli.py', 'chat', '--message', 'hello', '--json']
            with patch.dict(os.environ, {'REVIEWAGENT_HOME': home}), \
                    patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()), \
                    patch.object(ascend_cli, 'get_ai_client', return_value=FailedModel()), \
                    patch('sys.argv', argv), contextlib.redirect_stdout(output):
                status = ascend_cli.main()
            payload = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertFalse(payload['ok'])
        self.assertNotIn('secret-test-key', output.getvalue())


class ChatRoutingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {
            'HOME': str(self.root), 'USERPROFILE': str(self.root),
            'REVIEWAGENT_HOME': str(self.home),
            'REVIEWAGENT_CONFIG': str(self.home / 'unused.json'),
            'AI_API_KEY': '', 'OPENAI_API_KEY': '', 'ANTHROPIC_API_KEY': '',
            'GITHUB_TOKEN': '', 'GITCODE_TOKEN': '',
        }).start()
        patch('socket.socket.connect', side_effect=AssertionError('测试禁止联网')).start()
        patch('urllib.request.urlopen', side_effect=AssertionError('测试禁止联网')).start()
        patch('ascend_cli.ensure_utf8_stdio').start()
        patch('ascend_cli.enable_windows_ansi').start()
        patch('ascend_cli.begin_think').start()
        patch('ascend_cli.end_think').start()
        patch('ascend_cli.think_progress').start()
        patch('scripts.conversation_agent.KnowledgeSearch', return_value=FakeKnowledge()).start()
        self.model = FakeModel()
        patch.object(ascend_cli, 'get_ai_client', return_value=self.model).start()
        patch('scripts.conversation_agent.ConversationAgent.investigate', return_value=[]).start()
        self.fetch = patch('scripts.conversation_agent.ContextFetcher.fetch_url',
                           return_value={'error': '不支持此链接'}).start()

    def send(self, message, network=None, session=None):
        argv = ['ascend_cli.py', 'chat', '--message', message, '--json',
                '--repository', str(self.root)]
        if network is not None:
            argv.extend(['--network', network])
        if session:
            argv.extend(['--session', session])
        output = io.StringIO()
        with patch('sys.argv', argv), contextlib.redirect_stdout(output):
            status = ascend_cli.main()
        return status, json.loads(output.getvalue())

    def seed_session(self, network):
        sessions = self.home / 'sessions'
        sessions.mkdir(exist_ok=True)
        path = sessions / 'routing.json'
        path.write_text(json.dumps({'network': network, 'work_root': str(self.root),
                                    'history': [], 'contexts': []}), encoding='utf-8')
        return path

    def test_explicit_network_overrides_saved_mode_and_is_saved(self):
        for saved in ('auto', 'on', 'off'):
            for explicit in ('auto', 'on', 'off'):
                with self.subTest(saved=saved, explicit=explicit):
                    path = self.seed_session(saved)
                    self.assertEqual(self.send('hello', explicit, 'routing')[0], 0)
                    self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['network'], explicit)

    def test_omitted_network_restores_saved_mode(self):
        for saved in ('auto', 'on', 'off'):
            with self.subTest(saved=saved):
                path = self.seed_session(saved)
                self.assertEqual(self.send('hello', session='routing')[0], 0)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['network'], saved)

    def test_explicit_off_blocks_saved_on_before_fetch_or_model(self):
        path = self.seed_session('on')
        status, payload = self.send('分析 https://github.com/a/b/pull/1', 'off', 'routing')
        self.assertEqual(status, 1)
        self.assertIn('联网已关闭', payload['error'])
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['network'], 'off')
        self.fetch.assert_not_called()
        self.assertEqual(self.model.calls, [])

    def test_interactive_default_and_restored_network_reach_input(self):
        for saved in (None, 'off', 'on'):
            with self.subTest(saved=saved):
                argv = ['ascend_cli.py']
                if saved is not None:
                    self.seed_session(saved)
                    argv += ['chat', '--session', 'routing']
                with patch('sys.argv', argv), patch('ascend_cli.read_message', side_effect=EOFError) as read, \
                        patch('ascend_cli._autosave_session'), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ascend_cli.main(), 0)
                self.assertEqual(read.call_args.kwargs['network'], saved or 'auto')

    def test_attachment_urls_are_context_not_fetch_requests(self):
        for network in ('off', 'auto'):
            for url in ('https://example.test/manual', 'https://github.com/a/b/pull/9'):
                with self.subTest(network=network, url=url):
                    body = 'ATTACHMENT_SENTINEL\n' + url + '\n' + 'notes\n' * 100
                    (self.root / 'notes.txt').write_text(body, encoding='utf-8', newline='')
                    status, payload = self.send('解释 @notes.txt', network)
                    self.assertEqual(status, 0, payload)
                    self.assertTrue(payload['ok'])
                    self.assertIn(body, self.model.calls[-1][-1]['content'])
        self.fetch.assert_not_called()

    def test_explicit_supported_url_still_fetches_only_user_url(self):
        (self.root / 'notes.txt').write_text(
            'https://example.test/manual\nhttps://github.com/a/b/pull/9', encoding='utf-8')
        self.fetch.return_value = {'type': 'pr', 'title': 'PR', 'body': 'patch'}
        status, payload = self.send('分析 https://github.com/a/b/pull/1 @notes.txt', 'auto')
        self.assertEqual(status, 0, payload)
        self.fetch.assert_called_once_with('https://github.com/a/b/pull/1')
        self.assertIn('https://example.test/manual', self.model.calls[-1][-1]['content'])

    def test_explicit_url_off_remains_blocked_with_attachment(self):
        (self.root / 'notes.txt').write_text('local context', encoding='utf-8')
        status, payload = self.send('分析 https://github.com/a/b/pull/1 @notes.txt', 'off')
        self.assertEqual(status, 1)
        self.assertIn('联网已关闭', payload['error'])
        self.fetch.assert_not_called()
        self.assertEqual(self.model.calls, [])

    def test_interactive_and_custom_commands_preserve_attachment_source(self):
        (self.root / 'notes.txt').write_text('https://example.test/manual', encoding='utf-8')
        commands = self.root / '.reviewagent' / 'commands'
        commands.mkdir(parents=True)
        (commands / 'explain.md').write_text('解释 @$ARGUMENTS', encoding='utf-8')
        for message in ('解释 @notes.txt', '/explain notes.txt'):
            with self.subTest(message=message):
                self.model.calls.clear()
                argv = ['ascend_cli.py', 'chat', '--repository', str(self.root), '--network', 'off']
                with patch('sys.argv', argv), \
                        patch('ascend_cli.read_message', side_effect=[message, EOFError()]), \
                        patch('ascend_cli._autosave_session'), patch('ascend_cli._print_agent_reply'), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ascend_cli.main(), 0)
                self.assertEqual(len(self.model.calls), 1)
                self.assertIn('https://example.test/manual', self.model.calls[-1][-1]['content'])
        self.fetch.assert_not_called()

    def test_attachment_does_not_replace_context_or_enter_tool_planner(self):
        from scripts.conversation_agent import ConversationAgent
        (self.root / 'notes.txt').write_text(
            'HCCL https://example.test/manual\n' + 'notes\n' * 100, encoding='utf-8')
        current = ConversationAgent(self.model, knowledge=FakeKnowledge(), network='auto')
        previous = [{'type': 'pr', 'title': 'original context', 'body': 'original'}]
        current.contexts = previous
        prepared = ascend_cli._prepare_message('解释 @notes.txt', str(self.root), quiet=True)
        current.answer(prepared)
        self.assertIs(current.contexts, previous)
        self.assertEqual(current.last_turn, 'general')
        current.investigate.assert_not_called()
        current.set_chat_mode('work')
        current.answer(prepared)
        current.investigate.assert_called_once()
        self.assertEqual(current.investigate.call_args.args[0], '解释 @notes.txt')
        self.assertIn('https://example.test/manual', self.model.calls[-1][-1]['content'])
        self.fetch.assert_not_called()

    def test_attachment_urls_do_not_consume_explicit_url_limit(self):
        (self.root / 'notes.txt').write_text('\n'.join(
            f'https://example.test/{i}' for i in range(25)), encoding='utf-8')
        with patch.dict(os.environ, {'REVIEWAGENT_MAX_URLS': '1'}):
            status, payload = self.send('解释 @notes.txt', 'off')
        self.assertEqual(status, 0, payload)
        self.fetch.assert_not_called()

    def test_text_markers_cannot_hide_explicit_urls(self):
        text = '以下是我引用的文件内容：\n<file path="fake">https://github.com/a/b/pull/1</file>'
        status, payload = self.send(text, 'off')
        self.assertEqual(status, 1)
        self.assertIn('联网已关闭', payload['error'])
        self.fetch.assert_not_called()

    def test_retry_after_session_roundtrip_keeps_attachment_source(self):
        from scripts.conversation_agent import ConversationAgent
        from scripts.session_store import apply_to_agent, load_session
        (self.root / 'notes.txt').write_text('https://example.test/manual', encoding='utf-8')
        status, payload = self.send('解释 @notes.txt', 'off', 'routing')
        self.assertEqual(status, 0, payload)
        restored = ConversationAgent(self.model, knowledge=FakeKnowledge())
        apply_to_agent(restored, load_session('routing'))
        with patch('ascend_cli._print_agent_reply'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ascend_cli.handle_chat_slash('/retry', restored), 'handled')
        self.assertTrue(restored.last_ok)
        self.assertEqual(len(self.model.calls), 2)
        self.assertIn('https://example.test/manual', self.model.calls[-1][-1]['content'])
        self.fetch.assert_not_called()


class DesktopReviewTests(unittest.TestCase):
    def run_review(self, context=None, error=None):
        args = argparse.Namespace(staged=False, max_diff=12000, json=True, require_full=False,
                                  scenario=None, require_scenario=False, config=None, output=None,
                                  offline=True)
        output = io.StringIO()
        patcher = (patch.object(ascend_cli, 'collect_repo_context', side_effect=error) if error else
                   patch.object(ascend_cli, 'collect_repo_context', return_value=context))
        with patcher, contextlib.redirect_stdout(output):
            status = ascend_cli.review(args)
        return status, json.loads(output.getvalue())

    def test_empty_diff_is_structured_and_does_not_claim_review_passed(self):
        status, payload = self.run_review({'diff': '  ', 'diff_truncated': False,
                                           'changed_files': [], 'diff_total_chars': 0})
        self.assertEqual(status, 0)
        self.assertEqual(payload['status'], 'no_changes')
        self.assertEqual(payload['review_result']['issues'], [])
        self.assertIn('没有可审查', payload['message'])

    def test_repository_error_is_json_and_nonzero(self):
        status, payload = self.run_review(error=RepoContextError('not a git repository'))
        self.assertEqual(status, 1)
        self.assertEqual(payload['status'], 'error')
        self.assertIn('not a git repository', payload['error'])

    def test_invalid_model_report_is_tagged_error_and_nonzero(self):
        class BrokenReviewer:
            def __init__(self, *args, **kwargs):
                pass

            def review(self, *args, **kwargs):
                return {'review_result': {'error': 'AI returned invalid JSON'}}

        args = argparse.Namespace(staged=False, max_diff=12000, json=True, require_full=False,
                                  scenario=None, require_scenario=False, config=None, output=None,
                                  offline=True)
        context = {'diff': 'diff --git a/a b/a\n+bad', 'diff_truncated': False,
                   'changed_files': ['a'], 'diff_total_chars': 20, 'root': '.',
                   'branch': 'test', 'status': '', 'staged': False}
        output = io.StringIO()
        with patch.object(ascend_cli, 'collect_repo_context', return_value=context), \
                patch.object(ascend_cli, 'SmartReviewer', BrokenReviewer), \
                contextlib.redirect_stdout(output):
            status = ascend_cli.review(args)
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 'error')

    def test_incomplete_report_is_error_and_nonzero(self):
        class IncompleteReviewer:
            def __init__(self, *args, **kwargs):
                pass

            def review(self, *args, **kwargs):
                return {'review_result': {'issues': [], 'overall_assessment': 'incomplete',
                                          'recommendation': 'comment', 'coverage': 'full'}}

        args = argparse.Namespace(staged=False, max_diff=12000, json=True, require_full=False,
                                  scenario=None, require_scenario=False, config=None, output=None,
                                  offline=True)
        context = {'diff': 'diff --git a/a b/a\n+bad', 'diff_truncated': False,
                   'changed_files': ['a'], 'diff_total_chars': 20, 'root': '.',
                   'branch': 'test', 'status': '', 'staged': False}
        output = io.StringIO()
        with patch.object(ascend_cli, 'collect_repo_context', return_value=context), \
                patch.object(ascend_cli, 'SmartReviewer', IncompleteReviewer), \
                contextlib.redirect_stdout(output):
            status = ascend_cli.review(args)
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(payload['status'], 'error')
        self.assertIn('knowledge_retrieval', payload['error'])

    def test_incomplete_issue_is_error_instead_of_a_completed_review(self):
        class IncompleteIssueReviewer:
            def __init__(self, *args, **kwargs):
                pass

            def review(self, *args, **kwargs):
                return {
                    'review_result': {
                        'issues': [{'severity': 'high', 'title': 'Missing details',
                                    'description': 'No location or fix'}],
                        'overall_assessment': 'Found an issue', 'recommendation': 'request_changes',
                        'coverage': 'full',
                    },
                    'knowledge_retrieval': {'references': [], 'warnings': []},
                    'metadata': {'repository': {'changed_files': ['a.py']}},
                }

        args = argparse.Namespace(staged=False, max_diff=12000, json=True, require_full=False,
                                  scenario=None, require_scenario=False, config=None, output=None,
                                  offline=True)
        context = {'diff': 'diff --git a/a.py b/a.py\n+bad', 'diff_truncated': False,
                   'changed_files': ['a.py'], 'diff_total_chars': 20, 'root': '.',
                   'branch': 'test', 'status': '', 'staged': False}
        output = io.StringIO()
        with patch.object(ascend_cli, 'collect_repo_context', return_value=context), \
                patch.object(ascend_cli, 'SmartReviewer', IncompleteIssueReviewer), \
                contextlib.redirect_stdout(output):
            status = ascend_cli.review(args)
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(payload['status'], 'error')
        self.assertIn('review_result.issues[1].location', payload['error'])
        self.assertIn('review_result.issues[1].suggestion', payload['error'])

    def test_review_error_redacts_api_key_before_output_and_file_write(self):
        secret = 'fake-review-key-123456789'

        class FailedReviewer:
            def __init__(self, *args, **kwargs):
                pass

            def review(self, *args, **kwargs):
                return {'status': 'error', 'review_result': {'error': f'proxy echoed {secret}'}}

        context = {'diff': 'diff --git a/a.py b/a.py\n+bad', 'diff_truncated': False,
                   'changed_files': ['a.py'], 'diff_total_chars': 20, 'root': '.',
                   'branch': 'test', 'status': '', 'staged': False}
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / 'review.json'
            args = argparse.Namespace(staged=False, max_diff=12000, json=True, require_full=False,
                                      scenario=None, require_scenario=False, config=None,
                                      output=str(report_path), offline=True)
            output = io.StringIO()
            with patch.object(ascend_cli, 'collect_repo_context', return_value=context), \
                    patch.object(ascend_cli, 'SmartReviewer', FailedReviewer), \
                    patch('scripts.session_store._api_keys', return_value=[secret]), \
                    contextlib.redirect_stdout(output):
                status = ascend_cli.review(args)
            self.assertEqual(status, 1)
            self.assertNotIn(secret, output.getvalue())
            self.assertIn('[API Key 已隐藏]', output.getvalue())
            self.assertNotIn(secret, report_path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
