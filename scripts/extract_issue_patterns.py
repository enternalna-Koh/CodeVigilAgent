#!/usr/bin/env python3
"""
Issue 问题模式提取器
从 210 issues 中提取 Q&A 对和诊断模式
"""
import json
import os
import re
from collections import defaultdict

ERROR_CODE_PATTERN = re.compile(r'\b[45]\d{5}\b')  # 匹配 5-6 位错误码

def extract_error_codes(text):
    """从文本中提取错误码"""
    if not text:
        return []
    return list(set(ERROR_CODE_PATTERN.findall(text)))

def classify_issue_type(issue):
    """分类 issue 类型"""
    title = issue.get('title', '').lower()
    body = issue.get('body', '').lower() if issue.get('body') else ''

    text = title + ' ' + body

    # 版本兼容性
    if any(word in text for word in ['version', 'compatibility', 'upgrade', 'downgrade']):
        return 'version_compatibility'

    # 性能问题
    if any(word in text for word in ['performance', 'slow', 'speed', 'optimize', 'memory', 'oom']):
        return 'performance'

    # 精度问题
    if any(word in text for word in ['accuracy', 'precision', 'nan', 'inf', 'gradient']):
        return 'accuracy'

    # 编译/构建问题
    if any(word in text for word in ['compile', 'build', 'cmake', 'link']):
        return 'build'

    # 运行时错误
    if any(word in text for word in ['error', 'fail', 'crash', 'exception', 'timeout']):
        return 'runtime_error'

    # API 使用
    if any(word in text for word in ['api', 'usage', 'how to', 'example']):
        return 'api_usage'

    return 'other'

def extract_solution(issue):
    """提取解决方案（从 comments 中）"""
    comments = issue.get('comments', 0)

    # 简单启发式：如果 issue 已关闭且有 comments，假设有解决方案
    if issue.get('state') == 'closed' and comments > 0:
        return {
            'has_solution': True,
            'source': 'community_discussion',
            'status': 'resolved'
        }
    elif issue.get('state') == 'open':
        return {
            'has_solution': False,
            'status': 'open',
            'note': 'Issue still open, no confirmed solution'
        }
    else:
        return {
            'has_solution': False,
            'status': 'unknown'
        }

def extract_qa_pairs(issues_data):
    """提取问题-答案对"""
    qa_pairs = []

    for issue in issues_data:
        if 'pull_request' in issue:
            continue  # 跳过 PRs

        issue_type = classify_issue_type(issue)
        error_codes = extract_error_codes(
            issue.get('title', '') + ' ' + (issue.get('body', '') or '')
        )
        solution = extract_solution(issue)

        qa_pair = {
            'id': f"issue_{issue['number']}",
            'type': 'issue_qa',
            'repo': 'ascend',  # 需要从 issue URL 提取
            'issue_number': issue['number'],
            'question': {
                'title': issue.get('title', ''),
                'body': issue.get('body', '')[:500] if issue.get('body') else '',  # 截断
                'category': issue_type,
                'error_codes': error_codes
            },
            'answer': solution,
            'metadata': {
                'state': issue.get('state', 'unknown'),
                'comments_count': issue.get('comments', 0),
                'created_at': issue.get('created_at', ''),
                'url': issue.get('html_url', '')
            }
        }

        qa_pairs.append(qa_pair)

    return qa_pairs

def analyze_error_patterns(qa_pairs):
    """分析错误模式"""
    patterns = {
        'by_category': defaultdict(int),
        'by_error_code': defaultdict(int),
        'by_status': defaultdict(int),
        'common_errors': []
    }

    for qa in qa_pairs:
        patterns['by_category'][qa['question']['category']] += 1
        patterns['by_status'][qa['metadata']['state']] += 1

        for code in qa['question']['error_codes']:
            patterns['by_error_code'][code] += 1

    # 找出高频错误码
    patterns['common_errors'] = [
        {'code': code, 'count': count}
        for code, count in sorted(
            patterns['by_error_code'].items(),
            key=lambda x: -x[1]
        )[:10]
    ]

    return patterns

def generate_issue_knowledge_base():
    """生成 Issue 诊断知识库"""

    print("="*80)
    print("Issue 诊断知识库生成")
    print("="*80)

    # 读取多个仓库的 issues
    repos = [
        ('Ascend_pytorch', 'Ascend/pytorch'),
        ('vllm-project_vllm-ascend', 'vllm-ascend'),
        ('Ascend_sglang', 'Ascend/sglang'),
        ('gitcode_pytorch-ecosystem', 'pytorch-ecosystem')
    ]

    all_qa_pairs = []

    for file_prefix, repo_name in repos:
        issues_file = f'data/raw/{file_prefix}_issues.json'

        if not os.path.exists(issues_file):
            continue

        with open(issues_file, 'r', encoding='utf-8') as f:
            try:
                issues_data = json.load(f)
                if not isinstance(issues_data, list):
                    continue
            except:
                continue

        print(f"\n处理 {repo_name}: {len(issues_data)} issues")

        qa_pairs = extract_qa_pairs(issues_data)

        # 添加 repo 信息
        for qa in qa_pairs:
            qa['repo'] = repo_name

        all_qa_pairs.extend(qa_pairs)

    print(f"\n总 Q&A 对: {len(all_qa_pairs)}")

    # 分析错误模式
    patterns = analyze_error_patterns(all_qa_pairs)

    # 保存结果
    os.makedirs('data/training/issues', exist_ok=True)

    output_file = 'data/training/issues/qa_knowledge_base.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'qa_pairs': all_qa_pairs,
            'patterns': {
                'by_category': dict(patterns['by_category']),
                'by_error_code': dict(patterns['by_error_code']),
                'by_status': dict(patterns['by_status']),
                'common_errors': patterns['common_errors']
            },
            'metadata': {
                'total_qa_pairs': len(all_qa_pairs),
                'repositories': [r[1] for r in repos]
            }
        }, f, indent=2, ensure_ascii=False)

    print(f"\n输出文件: {output_file}")

    # 显示统计
    print("\n按类别统计:")
    for cat, count in sorted(patterns['by_category'].items(), key=lambda x: -x[1])[:5]:
        print(f"  {cat:25s}: {count:3d}")

    print("\n按状态统计:")
    for status, count in patterns['by_status'].items():
        print(f"  {status:10s}: {count:3d}")

    print("\n高频错误码:")
    for err in patterns['common_errors'][:5]:
        print(f"  {err['code']}: {err['count']} 次")

    return all_qa_pairs

if __name__ == '__main__':
    generate_issue_knowledge_base()
