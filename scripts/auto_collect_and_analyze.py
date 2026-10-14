#!/usr/bin/env python3
"""
自动收集 GitHub 社区数据并分析

使用方法：
    python auto_collect_and_analyze.py

输出目录：
    data/
    ├── raw/              # 原始 JSON 数据
    ├── analyzed/         # 分析后的结构化数据
    └── reports/          # 人类可读的报告
"""

import json
import urllib.request
import time
import os
from datetime import datetime
from collections import Counter

# 配置
REPOS = [
    "vllm-project/vllm-ascend",
    "Ascend/pytorch",
]

OUTPUT_DIR = "data"
RAW_DIR = os.path.join(OUTPUT_DIR, "raw")
ANALYZED_DIR = os.path.join(OUTPUT_DIR, "analyzed")
REPORTS_DIR = os.path.join(OUTPUT_DIR, "reports")

# GitHub Token (可选)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

def ensure_dirs():
    """创建输出目录"""
    for d in [RAW_DIR, ANALYZED_DIR, REPORTS_DIR]:
        os.makedirs(d, exist_ok=True)

def fetch_github(url, retries=3):
    """获取 GitHub API 数据，带重试"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'ReviewAgent-DataCollector/1.0')
            if GITHUB_TOKEN:
                req.add_header('Authorization', f'token {GITHUB_TOKEN}')

            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())

        except urllib.error.HTTPError as e:
            if e.code == 403:  # Rate limit
                print(f"  [WARN] Rate limit hit, waiting 60s...")
                time.sleep(60)
                continue
            elif e.code == 404:
                print(f"  [ERROR] Not found: {url}")
                return []
            else:
                print(f"  [ERROR] HTTP Error {e.code}: {e}")
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return []

        except Exception as e:
            print(f"  [ERROR] Error (attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(5)
                continue
            return []

    return []

def collect_issues(repo):
    """收集 Issues"""
    print(f"\n[*] 收集 {repo} Issues...")

    issues_data = {
        'open': [],
        'closed': []
    }

    for state in ['open', 'closed']:
        url = f"https://api.github.com/repos/{repo}/issues?state={state}&per_page=50&sort=updated"
        issues = fetch_github(url)

        # 过滤掉 PR（GitHub API 中 PR 也算 Issue）
        issues_only = [i for i in issues if 'pull_request' not in i]
        issues_data[state] = issues_only

        print(f"  [OK] {state}: {len(issues_only)} issues")
        time.sleep(1)  # 避免 rate limit

    return issues_data

def collect_prs(repo):
    """收集 PRs"""
    print(f"\n[*] 收集 {repo} PRs...")

    url = f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=50&sort=updated"
    prs = fetch_github(url)

    merged_prs = [p for p in prs if p.get('merged_at')]

    print(f"  [OK] Total: {len(prs)} PRs ({len(merged_prs)} merged)")
    time.sleep(1)

    return prs

def analyze_error_patterns(issues):
    """分析错误模式"""
    error_keywords = {
        'OOM': ['oom', 'out of memory', 'memory error'],
        'Timeout': ['timeout', 'timed out', 'hanging', 'freeze', 'stuck'],
        'Compatibility': ['compatibility', 'not supported', 'unsupported'],
        'CANN': ['cann', 'ascend', 'npu'],
        'Performance': ['slow', 'performance', 'latency', 'throughput'],
        'Accuracy': ['accuracy', 'precision', 'nan', 'inf', 'numerical'],
    }

    patterns = {k: [] for k in error_keywords.keys()}

    for issue in issues:
        body = (issue.get('body') or '').lower()
        title = issue.get('title', '').lower()
        text = body + ' ' + title

        for category, keywords in error_keywords.items():
            if any(kw in text for kw in keywords):
                patterns[category].append({
                    'number': issue['number'],
                    'title': issue['title'],
                    'state': issue['state'],
                    'url': issue['html_url']
                })

    return patterns

def analyze_pr_patterns(prs):
    """分析 PR 模式"""
    pr_types = Counter()
    review_stats = {
        'total_merged': 0,
        'avg_comments': 0,
        'common_labels': Counter()
    }

    total_comments = 0

    for pr in prs:
        # PR 类型（从标题推断）
        title = pr['title'].lower()
        if 'fix' in title or 'bug' in title:
            pr_types['bugfix'] += 1
        elif 'feat' in title or 'add' in title:
            pr_types['feature'] += 1
        elif 'refactor' in title:
            pr_types['refactor'] += 1
        elif 'doc' in title:
            pr_types['documentation'] += 1
        else:
            pr_types['other'] += 1

        # 统计
        if pr.get('merged_at'):
            review_stats['total_merged'] += 1

        total_comments += pr.get('comments', 0)

        for label in pr.get('labels', []):
            review_stats['common_labels'][label['name']] += 1

    if len(prs) > 0:
        review_stats['avg_comments'] = total_comments / len(prs)

    return {
        'types': dict(pr_types),
        'stats': review_stats
    }

def generate_report(repo, issues_data, prs_data, error_patterns, pr_patterns):
    """生成人类可读报告"""
    repo_name = repo.replace('/', '_')
    report_file = os.path.join(REPORTS_DIR, f"{repo_name}_report.md")

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# {repo} 数据分析报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Issues 统计
        f.write("## Issues 统计\n\n")
        f.write(f"- Open: {len(issues_data['open'])}\n")
        f.write(f"- Closed: {len(issues_data['closed'])}\n")
        f.write(f"- Total: {len(issues_data['open']) + len(issues_data['closed'])}\n\n")

        # 错误模式
        f.write("## 常见问题模式\n\n")
        for category, issues in error_patterns.items():
            if issues:
                f.write(f"### {category} ({len(issues)} issues)\n\n")
                for issue in issues[:5]:
                    f.write(f"- [#{issue['number']}]({issue['url']}): {issue['title']}\n")
                f.write("\n")

        # PR 统计
        f.write("## PR 统计\n\n")
        f.write(f"- Total PRs: {len(prs_data)}\n")
        f.write(f"- Merged: {pr_patterns['stats']['total_merged']}\n")
        f.write(f"- Avg Comments: {pr_patterns['stats']['avg_comments']:.1f}\n\n")

        f.write("### PR 类型分布\n\n")
        for pr_type, count in pr_patterns['types'].items():
            f.write(f"- {pr_type}: {count}\n")

        f.write("\n### 常见标签\n\n")
        for label, count in pr_patterns['stats']['common_labels'].most_common(10):
            f.write(f"- {label}: {count}\n")

    print(f"  [OK] 报告已保存: {report_file}")

def main():
    print("="*80)
    print("GitHub 数据自动收集与分析")
    print("="*80)

    ensure_dirs()

    for repo in REPOS:
        print(f"\n{'='*80}")
        print(f"处理仓库: {repo}")
        print(f"{'='*80}")

        try:
            # 收集数据
            issues_data = collect_issues(repo)
            prs_data = collect_prs(repo)

            # 保存原始数据
            repo_name = repo.replace('/', '_')
            with open(os.path.join(RAW_DIR, f"{repo_name}_issues.json"), 'w', encoding='utf-8') as f:
                json.dump(issues_data, f, indent=2, ensure_ascii=False)

            with open(os.path.join(RAW_DIR, f"{repo_name}_prs.json"), 'w', encoding='utf-8') as f:
                json.dump(prs_data, f, indent=2, ensure_ascii=False)

            # 分析
            print(f"\n[*] 分析数据...")
            all_issues = issues_data['open'] + issues_data['closed']
            error_patterns = analyze_error_patterns(all_issues)
            pr_patterns = analyze_pr_patterns(prs_data)

            # 保存分析结果
            analysis = {
                'error_patterns': error_patterns,
                'pr_patterns': pr_patterns,
                'summary': {
                    'total_issues': len(all_issues),
                    'open_issues': len(issues_data['open']),
                    'total_prs': len(prs_data),
                    'merged_prs': pr_patterns['stats']['total_merged']
                }
            }

            with open(os.path.join(ANALYZED_DIR, f"{repo_name}_analysis.json"), 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)

            # 生成报告
            print(f"\n[*] 生成报告...")
            generate_report(repo, issues_data, prs_data, error_patterns, pr_patterns)

            print(f"\n[OK] {repo} 处理完成")

        except Exception as e:
            print(f"\n[ERROR] 处理 {repo} 时出错: {e}")
            continue

        time.sleep(2)  # 仓库之间的间隔

    print("\n" + "="*80)
    print("[SUCCESS] 所有数据收集完成！")
    print("="*80)
    print(f"\n数据保存在:")
    print(f"  - 原始数据: {RAW_DIR}/")
    print(f"  - 分析结果: {ANALYZED_DIR}/")
    print(f"  - 报告: {REPORTS_DIR}/")
    print("\n请查看报告文件，然后将发现的问题模式发给 Claude 以优化智能体。")

if __name__ == '__main__':
    main()
