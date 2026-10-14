"""Offline regression tests for data normalization and retrieval integration."""
import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.knowledge_search import KnowledgeSearch
from scripts.smart_reviewer import SmartReviewer
from scripts.knowledge_search import PROJECT_ROOT


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.issue = {'title': 'HCCL 507049 SDMA failure', 'body': 'Check HCCL configuration.',
                      'html_url': 'https://github.com/Ascend/pytorch/issues/1', 'state': 'closed'}
        self.write('a_issues.json', {'open': [], 'closed': [self.issue]})
        self.write('b_issues.json', [self.issue, {'title': 'other', 'html_url': 'javascript:alert(1)'}])
        self.write('c_prs.json', [{'title': 'Memory allocator', 'body': 'allocate memory',
                                 'html_url': 'https://github.com/Ascend/pytorch/pull/2'}])
        self.write('failed_issues.json', {'message': 'Not Found'})
        (self.root / 'bad_issues.json').write_text('{', encoding='utf-8')

    def write(self, name, payload):
        (self.root / name).write_text(json.dumps(payload), encoding='utf-8')

    def test_normalize_deduplicate_and_warn(self):
        index = KnowledgeSearch(self.root)
        self.assertEqual(len(index.documents), 2)
        self.assertEqual(len(index.warnings), 2)

    def test_exact_error_code_and_irrelevant_query(self):
        index = KnowledgeSearch(self.root)
        hits = index.search('507049')
        self.assertEqual(hits[0]['url'], self.issue['html_url'])
        self.assertEqual(hits[0]['evidence_status'], 'historical_record_unverified')
        self.assertEqual(index.search('totally_unrelated_symbol'), [])
        self.assertEqual(index.search('507049', kind='pr'), [])

    def test_chinese_search(self):
        self.write('zh_issues.json', [{'title': '显存分配失败', 'body': '检查设备配置',
                                     'html_url': 'https://gitee.com/mindspore/mindspore/issues/1'}])
        self.assertEqual(KnowledgeSearch(self.root).search('显存分配')[0]['title'], '显存分配失败')

    def test_missing_data_directory(self):
        index = KnowledgeSearch(self.root / 'missing')
        self.assertEqual(index.search('507049'), [])
        self.assertTrue(index.warnings)

    def test_references_reach_ai_and_report_without_network(self):
        with patch('scripts.smart_reviewer.get_ai_client') as client:
            client.return_value.chat.return_value = '{"issues": [], "recommendation": "comment"}'
            reviewer = SmartReviewer(verbose=False, knowledge_search=KnowledgeSearch(self.root))
            report = reviewer.review('507049', verbose=False)
            self.assertEqual(report['knowledge_retrieval']['references'][0]['url'], self.issue['html_url'])
            prompt = client.return_value.chat.call_args.kwargs['prompt']
            self.assertIn(self.issue['html_url'], prompt)
            self.assertEqual(report['review_result']['issues'], [])

    def test_cli_review_external_repository_json_and_output(self):
        def git(*args):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        git('init')
        (self.root / 'model.py').write_text('value = 1\n', encoding='utf-8')
        git('add', 'model.py')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'fixture')
        (self.root / 'model.py').write_text('# HCCL 507049\nvalue = 2\n', encoding='utf-8')
        output = self.root / 'report.json'
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'ascend_cli.py'), 'review', '--offline',
             '--json', '--output', str(output)], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report, json.loads(output.read_text(encoding='utf-8')))
        self.assertEqual(report['task_identification']['type'], 'pr_review')
        self.assertEqual(report['review_result']['method'], 'rule_based')
        self.assertEqual(report['metadata']['repository']['changed_files'], ['model.py'])
        self.assertTrue(report['knowledge_retrieval']['references'])
        # The installed Node wrapper must use the same CLI without changing
        # cwd or polluting JSON with banners.
        import shutil
        if shutil.which('node'):
            wrapped = subprocess.run(
                ['node', str(PROJECT_ROOT / 'bin/review.js'), 'review', '--offline', '--json'],
                cwd=self.root, capture_output=True, text=True, encoding='utf-8', check=True)
            wrapped_report = json.loads(wrapped.stdout)
            self.assertEqual(Path(wrapped_report['metadata']['repository']['root']), self.root)
            self.assertEqual(wrapped_report['metadata']['repository']['changed_files'], ['model.py'])


if __name__ == '__main__':
    unittest.main()
