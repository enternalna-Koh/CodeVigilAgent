import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from scripts.patch_fix import (
    apply_fix,
    parse_fix_json,
    preview_fix,
    ProposedFix,
    FileEdit,
)
from scripts.conversation_agent import ConversationAgent


class PatchFixUnitTests(unittest.TestCase):
    def test_parse_and_reject_traversal(self):
        raw = json.dumps({
            'scenario': 'operator',
            'summary': 'fix tiling',
            'files': [
                {'path': 'ops/a.cpp', 'action': 'replace', 'search': 'old', 'replace': 'new'},
                {'path': '../evil', 'action': 'replace', 'search': 'a', 'replace': 'b'},
            ],
        })
        fix = parse_fix_json(raw)
        self.assertEqual(len(fix.files), 1)
        self.assertEqual(fix.files[0].path, 'ops/a.cpp')

    def test_apply_replace_unique_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / 'src' / 'x.py'
            f.parent.mkdir(parents=True)
            f.write_text('hello WORLD hello\n', encoding='utf-8')
            fix = ProposedFix(files=[
                FileEdit(path='src/x.py', action='replace', search='WORLD', replace='ASCEND'),
            ])
            result = apply_fix(fix, root=root)
            self.assertEqual(result['applied'], 1)
            self.assertEqual(f.read_text(encoding='utf-8'), 'hello ASCEND hello\n')

            # ambiguous
            f.write_text('aa aa\n', encoding='utf-8')
            fix2 = ProposedFix(files=[
                FileEdit(path='src/x.py', action='replace', search='aa', replace='bb'),
            ])
            result2 = apply_fix(fix2, root=root)
            self.assertEqual(result2['applied'], 0)
            self.assertEqual(f.read_text(encoding='utf-8'), 'aa aa\n')

    def test_preview_mentions_apply(self):
        text = preview_fix(ProposedFix(summary='s', files=[
            FileEdit(path='a.py', action='create', replace='print(1)\n'),
        ]))
        self.assertIn('/apply', text)


class FakeKnowledge:
    warnings = []

    def search(self, query, limit=3):
        return []


class FixClient:
    def chat(self, prompt, **kwargs):
        return json.dumps({
            'scenario': 'general',
            'summary': 'rename flag',
            'files': [{
                'path': 'demo.txt',
                'action': 'replace',
                'search': 'OLD',
                'replace': 'NEW',
            }],
        })

    def chat_with_history(self, messages, **kwargs):
        return 'analysis ok'


class ProposeFixAgentTests(unittest.TestCase):
    def test_propose_then_apply_with_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'demo.txt').write_text('value=OLD\n', encoding='utf-8')
            agent = ConversationAgent(FixClient(), FakeKnowledge(), MagicMock())
            agent.work_root = root
            agent.contexts = [{
                'type': 'pr', 'title': 't', 'body': 'b', 'url': 'https://github.com/a/b/pull/1',
                'files': [{'file': 'demo.txt', 'patch': '-OLD\n+OLD'}],
                'comments': [], 'reviews': [], 'inline_comments': [], 'warnings': [],
            }]
            preview = agent.propose_fix()
            self.assertIn('/apply', preview)
            self.assertIsNotNone(agent.pending_fix)
            denied = agent.apply_pending_fix(confirm=False)
            self.assertIn('/apply', denied)
            self.assertEqual((root / 'demo.txt').read_text(encoding='utf-8'), 'value=OLD\n')
            applied = agent.apply_pending_fix(confirm=True)
            self.assertIn('replaced', applied)
            self.assertEqual((root / 'demo.txt').read_text(encoding='utf-8'), 'value=NEW\n')
            self.assertIsNone(agent.pending_fix)

    def test_discard(self):
        agent = ConversationAgent(FixClient(), FakeKnowledge(), MagicMock())
        agent.contexts = [{'type': 'pr', 'title': 't', 'body': '', 'url': 'u',
                           'files': [], 'comments': [], 'reviews': [],
                           'inline_comments': [], 'warnings': []}]
        agent.propose_fix()
        self.assertIsNotNone(agent.pending_fix)
        self.assertIn('丢弃', agent.discard_fix())
        self.assertIsNone(agent.pending_fix)


if __name__ == '__main__':
    unittest.main()
