#!/usr/bin/env python3
"""
Review 意见分析和标注工具
从收集的 PR reviews 中提取和分类审核意见
"""
import json
import os
import re
from collections import defaultdict

# Review 意见分类
REVIEW_CATEGORIES = {
    'design': ['design', 'architecture', 'api', 'interface', 'pattern'],
    'quality': ['readable', 'clean', 'naming', 'comment', 'doc', 'style'],
    'performance': ['performance', 'optimize', 'efficient', 'memory', 'speed'],
    'test': ['test', 'coverage', 'assert', 'mock', 'unittest'],
    'dependency': ['dependency', 'import', 'package', 'version', 'requirement'],
    'bug': ['bug', 'fix', 'error', 'issue', 'problem', 'fail'],
    'other': []
}

# 严重程度关键词
SEVERITY_KEYWORDS = {
    'high': ['must', 'critical', 'blocking', 'required', 'necessary'],
    'medium': ['should', 'recommend', 'suggest', 'consider', 'better'],
    'low': ['could', 'minor', 'nit', 'optional', 'maybe']
}

def classify_review_type(text):
    """根据文本内容分类 review 类型"""
    text_lower = text.lower()

    for category, keywords in REVIEW_CATEGORIES.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category

    return 'other'

def detect_severity(text):
    """检测严重程度"""
    text_lower = text.lower()

    # 检查关键词
    for severity, keywords in SEVERITY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return severity

    # 默认 medium
    return 'medium'

def extract_code_context(comment, file_path, line_number):
    """提取代码上下文信息"""
    return {
        'file': file_path,
        'line': line_number,
        'type': 'inline_comment'
    }

def analyze_review(review):
    """分析单个 review"""
    if not review.get('body'):
        return None

    body = review['body']

    return {
        'reviewer': review.get('user', {}).get('login', 'unknown'),
        'state': review.get('state', 'COMMENTED'),
        'body': body,
        'category': classify_review_type(body),
        'severity': detect_severity(body),
        'timestamp': review.get('submitted_at', '')
    }

def analyze_comment(comment):
    """分析单个 inline comment"""
    if not comment.get('body'):
        return None

    body = comment['body']

    return {
        'author': comment.get('user', {}).get('login', 'unknown'),
        'body': body,
        'category': classify_review_type(body),
        'severity': detect_severity(body),
        'context': extract_code_context(
            comment,
            comment.get('path', ''),
            comment.get('line', 0)
        ),
        'timestamp': comment.get('created_at', '')
    }

def analyze_pr_reviews(pr_data):
    """分析 PR 的所有 reviews"""
    pr_number = pr_data['pr_number']
    reviews = pr_data.get('reviews', [])
    comments = pr_data.get('comments', [])

    analyzed = {
        'pr_number': pr_number,
        'reviews': [],
        'inline_comments': [],
        'summary': {
            'total_reviews': len(reviews),
            'total_comments': len(comments),
            'categories': defaultdict(int),
            'severity': defaultdict(int),
            'decisions': defaultdict(int)
        }
    }

    # 分析 reviews
    for review in reviews:
        analyzed_review = analyze_review(review)
        if analyzed_review:
            analyzed['reviews'].append(analyzed_review)
            analyzed['summary']['categories'][analyzed_review['category']] += 1
            analyzed['summary']['severity'][analyzed_review['severity']] += 1
            analyzed['summary']['decisions'][analyzed_review['state']] += 1

    # 分析 comments
    for comment in comments:
        analyzed_comment = analyze_comment(comment)
        if analyzed_comment:
            analyzed['inline_comments'].append(analyzed_comment)
            analyzed['summary']['categories'][analyzed_comment['category']] += 1
            analyzed['summary']['severity'][analyzed_comment['severity']] += 1

    return analyzed

def main():
    print("="*80)
    print("Review 意见分析和标注")
    print("="*80)

    review_file = 'data/pr_reviews/vllm-project_vllm-ascend_reviews.json'

    if not os.path.exists(review_file):
        print(f"错误: 文件不存在 {review_file}")
        return

    with open(review_file, 'r', encoding='utf-8') as f:
        prs_data = json.load(f)

    print(f"\n加载 {len(prs_data)} 个 PRs 的 review 数据...")

    # 分析所有 PRs
    all_analyzed = []
    global_summary = {
        'total_prs': len(prs_data),
        'total_reviews': 0,
        'total_comments': 0,
        'categories': defaultdict(int),
        'severity': defaultdict(int),
        'decisions': defaultdict(int)
    }

    for pr_data in prs_data:
        analyzed = analyze_pr_reviews(pr_data)
        all_analyzed.append(analyzed)

        # 更新全局统计
        global_summary['total_reviews'] += analyzed['summary']['total_reviews']
        global_summary['total_comments'] += analyzed['summary']['total_comments']

        for cat, count in analyzed['summary']['categories'].items():
            global_summary['categories'][cat] += count

        for sev, count in analyzed['summary']['severity'].items():
            global_summary['severity'][sev] += count

        for dec, count in analyzed['summary']['decisions'].items():
            global_summary['decisions'][dec] += count

    # 显示统计
    print("\n" + "="*80)
    print("全局统计")
    print("="*80)
    print(f"总 PRs: {global_summary['total_prs']}")
    print(f"总 Reviews: {global_summary['total_reviews']}")
    print(f"总 Comments: {global_summary['total_comments']}")

    print("\n按类别:")
    for cat, count in sorted(global_summary['categories'].items(), key=lambda x: -x[1]):
        print(f"  {cat:15s}: {count:3d}")

    print("\n按严重程度:")
    for sev, count in sorted(global_summary['severity'].items()):
        print(f"  {sev:15s}: {count:3d}")

    print("\n按决策:")
    for dec, count in sorted(global_summary['decisions'].items(), key=lambda x: -x[1]):
        print(f"  {dec:20s}: {count:3d}")

    # 保存分析结果
    os.makedirs('data/training/reviews', exist_ok=True)

    output_file = 'data/training/reviews/analyzed_reviews.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'prs': all_analyzed,
            'summary': {
                'total_prs': global_summary['total_prs'],
                'total_reviews': global_summary['total_reviews'],
                'total_comments': global_summary['total_comments'],
                'categories': dict(global_summary['categories']),
                'severity': dict(global_summary['severity']),
                'decisions': dict(global_summary['decisions'])
            }
        }, f, indent=2, ensure_ascii=False)

    print(f"\nOK: 分析结果已保存到 {output_file}")

    # 生成样例展示
    print("\n" + "="*80)
    print("Review 样例 (前 3 个)")
    print("="*80)

    for i, pr in enumerate(all_analyzed[:3]):
        if pr['reviews']:
            print(f"\nPR #{pr['pr_number']}:")
            for j, review in enumerate(pr['reviews'][:2]):
                print(f"  Review {j+1}:")
                print(f"    Category: {review['category']}")
                print(f"    Severity: {review['severity']}")
                print(f"    State: {review['state']}")
                print(f"    Body: {review['body'][:100]}...")

if __name__ == '__main__':
    main()
