"""v1.8.0 integration regressions, without live credentials or remote calls."""
import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ascend_cli
from scripts.conversation_agent import ConversationAgent, ContextFetcher
from scripts.session_store import apply_to_agent, load_session, save_session, serialize_agent
from scripts.skill_runtime import SkillLoad


def agent():
    return ConversationAgent(MagicMock(), MagicMock(), MagicMock(), network='off')


class IntegrationTests(unittest.TestCase):
    def test_opengauss_slash_review_and_fix_keep_explicit_scenario(self):
        current = agent()
        with patch('ascend_cli.run_local_review', return_value=('ok', {})) as review, \
                patch('ascend_cli.begin_think'), patch('ascend_cli.end_think'), \
                patch('ascend_cli._print_agent_reply'):
            ascend_cli.handle_chat_slash('/review opengauss', current)
        self.assertEqual(review.call_args.kwargs['scenario'], 'opengauss')
        with patch.object(current, 'propose_fix', return_value='none') as fix, \
                patch('ascend_cli.begin_think'), patch('ascend_cli.end_think'), \
                patch('ascend_cli._print_agent_reply'):
            ascend_cli.handle_chat_slash('/fix opengauss', current)
        fix.assert_called_once_with(explicit_scenario='opengauss')

    def test_ship_stops_after_failed_commit_despite_success_word_in_hook(self):
        current = agent()
        with patch('ascend_cli.git_work.status_report', return_value='status'), \
                patch('ascend_cli.git_work.commit_changes', return_value='提交失败:\n已提交 hook error'), \
                patch('ascend_cli.git_work.push_branch') as push, \
                patch('ascend_cli.git_work.create_pull_request') as pr, \
                patch('ascend_cli._print_agent_reply'), patch('builtins.input', return_value='y'), \
                redirect_stdout(io.StringIO()):
            ascend_cli._handle_ship('test', current)
        push.assert_not_called()
        pr.assert_not_called()

    def test_ship_stops_after_failed_push_despite_success_word_in_remote_error(self):
        with patch('ascend_cli.git_work.status_report', return_value='status'), \
                patch('ascend_cli.git_work.commit_changes', return_value='已提交: abc'), \
                patch('ascend_cli.git_work.push_branch', return_value='推送失败:\n已推送 rejected'), \
                patch('ascend_cli.git_work.create_pull_request') as pr, \
                patch('ascend_cli._print_agent_reply'), patch('builtins.input', return_value='y'), \
                redirect_stdout(io.StringIO()):
            ascend_cli._handle_ship('test', agent())
        pr.assert_not_called()

    def test_pr_confirmation_previews_the_actual_body(self):
        current = agent()
        current.last_reply = 'private conversation excerpt'
        output = io.StringIO()
        def confirm(_):
            self.assertIn(current.last_reply, output.getvalue())
            return 'n'
        with patch('builtins.input', side_effect=confirm), \
                patch('ascend_cli.git_work.create_pull_request') as pr, redirect_stdout(output):
            ascend_cli.handle_chat_slash('/pr draft title', current)
        pr.assert_not_called()

    def test_git_add_supports_quoted_spaces_and_windows_paths(self):
        with patch('ascend_cli.git_work.stage_paths', return_value={'ok': True}) as stage, \
                redirect_stdout(io.StringIO()):
            ascend_cli.handle_chat_slash('/git add "folder with space/file.txt" dir\\file.py', agent())
        self.assertEqual(stage.call_args.args[0], ['folder with space/file.txt', 'dir/file.py'])

    def test_git_add_invalid_quotes_does_not_stage_anything(self):
        with patch('ascend_cli.git_work.stage_paths') as stage, redirect_stdout(io.StringIO()) as out:
            ascend_cli.handle_chat_slash('/git add "unfinished', agent())
        stage.assert_not_called()
        self.assertIn('路径格式错误', out.getvalue())

    def test_collect_invalid_config_is_a_failed_cli_result(self):
        with patch('scripts.collect_gitcode_community.collect_community', side_effect=ValueError('bad id')), \
                redirect_stdout(io.StringIO()) as out:
            code = ascend_cli.collect_cmd(argparse.Namespace(community='../bad', pages=2, dialog_limit=2))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue()), {'ok': False, 'error': 'bad id'})


class SessionSkillTests(unittest.TestCase):
    def test_complete_skill_tail_is_sent_without_silent_truncation(self):
        current = agent()
        body = 'x' * 13000 + 'CRITICAL_RULE_AT_END'
        with patch('scripts.skill_runtime.load_skill', return_value=SkillLoad(
                'large', 'ready', text=body, chars=len(body))):
            current.attach_skill('large')
        current.client.chat_with_history.return_value = 'ok'
        current.answer('hello')
        self.assertIn('CRITICAL_RULE_AT_END', current.client.chat_with_history.call_args.args[0][0]['content'])

    def test_incomplete_and_aggregate_budget_keep_previous_skills(self):
        current = agent()
        first = SkillLoad('one', 'ready', text='a' * 10000)
        with patch('scripts.skill_runtime.load_skill', return_value=first):
            current.attach_skill('one')
        original = list(current.active_skills)
        for loaded in (SkillLoad('two', 'incomplete', text='partial'),
                       SkillLoad('two', 'ready', text='b' * 10000),
                       SkillLoad('two', 'ready', text='中' * 8000)):
            with self.subTest(status=loaded.status, length=len(loaded.text)):
                with patch('scripts.skill_runtime.load_skill', return_value=loaded):
                    message = current.attach_skill('two')
                self.assertNotIn('已加载 skill', message)
                self.assertEqual(current.active_skills, original)

    def test_saved_sessions_clear_other_session_skills_and_tool_results(self):
        current, other = agent(), agent()
        current.active_skills = [{'name': 'one', 'text': 'rules'}]
        other.active_skills = [{'name': 'unrelated', 'text': 'wrong rules'}]
        other.last_tools = [{'tool': 'unrelated-source'}]
        data = serialize_agent(current)
        apply_to_agent(other, data)
        self.assertEqual(data['skill_names'], ['one'])
        self.assertEqual(other.active_skills, [])
        self.assertEqual(other.last_tools, [])

    def test_names_with_spaces_resume_and_reserved_names_cannot_overwrite_aliases(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'REVIEWAGENT_HOME': tmp}):
            path = save_session(agent(), 'my project')
            self.assertEqual(Path(load_session('my project')['_path']), path)
            previous = path.read_bytes()
            for name in ('123', 'previous', 'latest', 'back'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    save_session(agent(), name)
            self.assertEqual(path.read_bytes(), previous)

    def test_new_chat_clears_skill_only_session(self):
        current = agent()
        current.active_skills = [{'name': 'one', 'text': 'rules'}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'REVIEWAGENT_HOME': tmp}), \
                redirect_stdout(io.StringIO()):
            ascend_cli.handle_chat_slash('/new', current)
        self.assertEqual(current.active_skills, [])


class McpPolicyTests(unittest.TestCase):
    def test_automatic_mcp_only_calls_declared_read_only_tools(self):
        for annotations, expected in (({}, False), ({'readOnlyHint': True}, True),
                                      ({'readOnlyHint': True, 'destructiveHint': True}, False),
                                      ({'readOnlyHint': 'true'}, False)):
            with self.subTest(annotations=annotations):
                current = agent()
                current.network = 'auto'
                current.client.chat.side_effect = [
                    json.dumps({'tool': 'mcp_call', 'server': 'test', 'name': 'do', 'arguments': {}}),
                    '{"tool":"finish"}']
                registry = MagicMock()
                registry.list_servers.return_value = [{'name': 'test'}]
                registry.get_session.return_value = SimpleNamespace(
                    tools=[{'name': 'do', 'annotations': annotations}])
                current._mcp = registry
                current.investigate('check', {'historical_references': []})
                self.assertEqual(registry.call.called, expected)

    def test_explicit_mcp_call_rejects_array_instead_of_silently_changing_arguments(self):
        current = agent()
        current._mcp = MagicMock()
        with patch('ascend_cli.ensure_default_user_mcp', create=True), \
                patch('scripts.mcp_client.ensure_default_user_mcp'), redirect_stdout(io.StringIO()) as out:
            ascend_cli.handle_chat_slash('/mcp call test do []', current)
        current._mcp.call.assert_not_called()
        self.assertIn('JSON 对象', out.getvalue())

    def test_autosave_closes_mcp_even_on_save_error(self):
        current = agent()
        current._mcp = MagicMock()
        with patch('ascend_cli.save_session', side_effect=OSError('disk full')), redirect_stdout(io.StringIO()):
            ascend_cli._autosave_session(current)
        current._mcp.close.assert_called_once()


class TokenBoundaryTests(unittest.TestCase):
    def test_github_token_never_used_for_gitcode(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'fake-github', 'GITCODE_TOKEN': ''}):
            fetcher = ContextFetcher()
        with patch.object(fetcher, '_http_get_json', return_value={}) as get:
            fetcher.fetch_gitcode_api('/repos/o/r/issues')
        url, headers, _ = get.call_args.args
        self.assertNotIn('fake-github', url)
        self.assertNotIn('Authorization', headers)
        self.assertEqual(fetcher.token, 'fake-github')

    def test_gitcode_token_is_in_headers_only(self):
        fetcher = ContextFetcher(token='fake-github', gitcode_token='fake-gitcode')
        with patch.object(fetcher, '_http_get_json', return_value={}) as get:
            fetcher.fetch_gitcode_api('/repos/o/r/issues?state=all')
        url, headers, _ = get.call_args.args
        self.assertNotIn('fake-gitcode', url)
        self.assertEqual(headers['Authorization'], 'Bearer fake-gitcode')


if __name__ == '__main__':
    unittest.main()
