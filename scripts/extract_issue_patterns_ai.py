#!/usr/bin/env python3
"""
AI 增强版 - Issue 模式提取器
使用 AI 进行更智能的问题分类和解决方案提取
"""
import json
import os
import re
from collections import defaultdict
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from scripts.ai_adapter import get_ai_client
    HAS_AI = True
except:
    HAS_AI = False

ERROR_CODE_PATTERN = re.compile(r'\b[45]\d{5}\b')


def extract_error_codes(text):
    """从文本中提取错误码"""
    if not text:
        return []
    return list(set(ERROR_CODE_PATTERN.findall(text)))


def classify_issue_with_ai(issue, ai_client):
    """使用 AI 分类 issue"""
    title = issue.get('title', '')
    body = issue.get('body', '')[:500] if issue.get('body') else ''

    prompt = f"""分析这个 GitHub Issue 并分类:

标题: {title}
内容: {body}

请返回 JSON:
{{
  "category": "version_compatibility|performance|accuracy|build|runtime_error|api_usage|other",
  "confidence": 0.0-1.0,
  "has_solution": true/false,
  "priority": "high|medium|low"
}}
"""

    try:
        response = ai_client.chat(prompt, temperature=0.3, max_tokens=200)

        # 提取 JSON
        if '```json' in response:
            json_str = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            json_str = response.split('```')[1].split('```')[0]
        else:
            json_str = response

        result = json.loads(json_str.strip())
        return result
    except:
        return None


def extract_solution_with_ai(issue, ai_client):
    """使用 AI 提取解决方案"""
    title = issue.get('title', '')
    body = issue.get('body', '')[:1000] if issue.get('body') else ''

    # 检查是否已关闭
    if issue.get('state') != 'closed':
        return {'has_solution': False, 'reason': 'issue still open'}

    prompt = f"""从这个已关闭的 Issue 中提取解决方案:

标题: {title}
内容: {body}

请返回 JSON:
{{
  "solution_found": true/false,
  "solution_type": "version_change|code_fix|workaround|config_change|wont_fix",
  "solution": "简短的解决方案描述",
  "confidence": 0.0-1.0
}}
"""

    try:
        response = ai_client.chat(prompt, temperature=0.3, max_tokens=300)

        if '```json' in response:
            json_str = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            json_str = response.split('```')[1].split('```')[0]
        else:
            json_str = response

        result = json.loads(json_str.strip())
        return result
    except:
        return None


def generate_issue_knowledge_base_with_ai(use_ai=True):
    """生成 Issue 诊断知识库（AI 增强版）"""

    print("="*80)
    print("AI 增强版 - Issue 诊断知识库生成")
    print("="*80)

    # 初始化 AI
    ai_client = None
    if use_ai and HAS_AI:
        try:
            ai_client = get_ai_client('config/ai_config.json')
            print("\n✓ AI 引擎已启用 (更智能的分类和解决方案提取)")
        except:
            print("\n⚠ AI 未配置，使用规则引擎")
            ai_client = None
    else:
        print("\n使用规则引擎")

    # 读取多个仓库的 issues
    repos = [
        ('Ascend_pytorch', 'Ascend/pytorch'),
        ('vllm-project_vllm-ascend', 'vllm-ascend'),
        ('Ascend_sglang', 'Ascend/sglang'),
        ('gitcode_pytorch-ecosystem', 'pytorch-ecosystem'),
        # MindSpore repos
        ('mindspore-ai_mindspore', 'mindspore-ai/mindspore'),
        ('mindspore-ai_models', 'mindspore-ai/models'),
        ('gitee_mindspore_mindspore', 'gitee/mindspore/mindspore'),
        ('gitee_mindspore_models', 'gitee/mindspore/models'),
    ]

    all_qa_pairs = []
    ai_enhanced = 0

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

        for issue in issues_data:
            if 'pull_request' in issue:
                continue

            # AI 分类
            if ai_client:
                ai_category = classify_issue_with_ai(issue, ai_client)
                if ai_category:
                    category = ai_category['category']
                    ai_enhanced += 1
                else:
                    category = classify_issue_rule_based(issue)
            else:
                category = classify_issue_rule_based(issue)

            error_codes = extract_error_codes(
                issue.get('title', '') + ' ' + (issue.get('body', '') or '')
            )

            # AI 提取解决方案
            if ai_client and issue.get('state') == 'closed':
                ai_solution = extract_solution_with_ai(issue, ai_client)
                if ai_solution and ai_solution.get('solution_found'):
                    solution = {
                        'has_solution': True,
                        'type': ai_solution.get('solution_type', 'unknown'),
                        'description': ai_solution.get('solution', ''),
                        'confidence': ai_solution.get('confidence', 0.5),
                        'source': 'ai_extracted'
                    }
                else:
                    solution = extract_solution_rule_based(issue)
            else:
                solution = extract_solution_rule_based(issue)

            qa_pair = {
                'id': f"issue_{issue['number']}",
                'type': 'issue_qa',
                'repo': repo_name,
                'issue_number': issue['number'],
                'question': {
                    'title': issue.get('title', ''),
                    'body': issue.get('body', '')[:500] if issue.get('body') else '',
                    'category': category,
                    'error_codes': error_codes
                },
                'answer': solution,
                'metadata': {
                    'state': issue.get('state', 'unknown'),
                    'comments_count': issue.get('comments', 0),
                    'created_at': issue.get('created_at', ''),
                    'url': issue.get('html_url', ''),
                    'ai_enhanced': ai_client is not None
                }
            }

            all_qa_pairs.append(qa_pair)

    print(f"\n总 Q&A 对: {len(all_qa_pairs)}")
    if ai_client:
        print(f"AI 增强: {ai_enhanced} 个")

    # 分析错误模式
    patterns = analyze_error_patterns(all_qa_pairs)

    # 保存结果
    os.makedirs('data/training/issues', exist_ok=True)

    output_file = 'data/training/issues/qa_knowledge_base.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'qa_pairs': all_qa_pairs,
            'patterns': patterns,
            'metadata': {
                'total_qa_pairs': len(all_qa_pairs),
                'repositories': [r[1] for r in repos],
                'ai_enhanced': ai_client is not None,
                'ai_enhanced_count': ai_enhanced
            }
        }, f, indent=2, ensure_ascii=False)

    print(f"\n输出文件: {output_file}")

    # 显示统计
    print("\n按类别统计:")
    for cat, count in sorted(patterns['by_category'].items(), key=lambda x: -x[1])[:10]:
        print(f"  {cat:25s}: {count:3d}")

    print("\n按状态统计:")
    for status, count in patterns['by_status'].items():
        print(f"  {status:10s}: {count:3d}")

    print("\n高频错误码:")
    for err in patterns['common_errors'][:10]:
        print(f"  {err['code']}: {err['count']} 次")

    return all_qa_pairs


def classify_issue_rule_based(issue):
    """规则引擎分类"""
    title = issue.get('title', '').lower()
    body = issue.get('body', '').lower() if issue.get('body') else ''
    text = title + ' ' + body

    if any(word in text for word in ['version', 'compatibility', 'upgrade', 'downgrade']):
        return 'version_compatibility'
    if any(word in text for word in ['performance', 'slow', 'speed', 'optimize', 'memory', 'oom']):
        return 'performance'
    if any(word in text for word in ['accuracy', 'precision', 'nan', 'inf', 'gradient']):
        return 'accuracy'
    if any(word in text for word in ['compile', 'build', 'cmake', 'link']):
        return 'build'
    if any(word in text for word in ['error', 'fail', 'crash', 'exception', 'timeout']):
        return 'runtime_error'
    if any(word in text for word in ['api', 'usage', 'how to', 'example']):
        return 'api_usage'

    return 'other'


def extract_solution_rule_based(issue):
    """规则引擎提取解决方案"""
    if issue.get('state') == 'closed' and issue.get('comments', 0) > 0:
        return {
            'has_solution': True,
            'source': 'community_discussion',
            'status': 'resolved'
        }
    elif issue.get('state') == 'open':
        return {
            'has_solution': False,
            'status': 'open',
            'note': 'Issue still open'
        }
    else:
        return {
            'has_solution': False,
            'status': 'unknown'
        }


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

    patterns['common_errors'] = [
        {'code': code, 'count': count}
        for code, count in sorted(
            patterns['by_error_code'].items(),
            key=lambda x: -x[1]
        )[:20]
    ]

    return {
        'by_category': dict(patterns['by_category']),
        'by_error_code': dict(patterns['by_error_code']),
        'by_status': dict(patterns['by_status']),
        'common_errors': patterns['common_errors']
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--no-ai', action='store_true', help='不使用 AI，仅使用规则')
    args = parser.parse_args()

    generate_issue_knowledge_base_with_ai(use_ai=not args.no_ai)
