#!/usr/bin/env python3
"""
GitHub 数据收集脚本 - 用于优化 ReviewAgent 智能体

使用方法：
    python collect_github_data.py

输出：
    - github_issues.txt - Issue 列表
    - github_prs.txt - PR 列表
    - github_comments.txt - 重要的审核评论
"""

import json
import urllib.request
import time
import sys
from typing import List, Dict

# GitHub Token (可选，提高 API 速率限制)
GITHUB_TOKEN = ""  # 填入你的 token，或留空使用公开 API

REPOS = [
    "vllm-project/vllm-ascend",
    "Ascend/pytorch",
    "Ascend/samples",
    "Ascend/ModelZoo-PyTorch",
]

def fetch_github(url: str) -> List[Dict]:
    """获取 GitHub API 数据"""
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'ReviewAgent-DataCollector')
    if GITHUB_TOKEN:
        req.add_header('Authorization', f'token {GITHUB_TOKEN}')

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def collect_issues(repo: str, output_file):
    """收集 Issues"""
    print(f"\n{'='*80}")
    print(f"Collecting Issues from {repo}")
    print(f"{'='*80}")

    # 获取 open 和 closed issues
    for state in ['open', 'closed']:
        url = f"https://api.github.com/repos/{repo}/issues?state={state}&per_page=30&sort=updated"
        issues = fetch_github(url)

        output_file.write(f"\n\n## {repo} - {state.upper()} ISSUES\n")
        output_file.write("=" * 80 + "\n")

        for issue in issues[:15]:
            # 跳过 PR（GitHub API 中 PR 也算作 Issue）
            if 'pull_request' in issue:
                continue

            output_file.write(f"\n### Issue #{issue['number']}: {issue['title']}\n")
            output_file.write(f"**State**: {issue['state']} | **Comments**: {issue['comments']}\n")
            output_file.write(f"**Created**: {issue['created_at'][:10]}\n")

            labels = ', '.join([l['name'] for l in issue.get('labels', [])])
            if labels:
                output_file.write(f"**Labels**: {labels}\n")

            body = (issue.get('body') or 'No description')
            output_file.write(f"\n**Description**:\n{body[:600]}...\n")
            output_file.write("-" * 80 + "\n")

            print(f"  - #{issue['number']}: {issue['title'][:60]}")

        time.sleep(1)  # 避免 API 限速

def collect_prs(repo: str, output_file):
    """收集 PRs"""
    print(f"\n{'='*80}")
    print(f"Collecting PRs from {repo}")
    print(f"{'='*80}")

    url = f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=30&sort=updated"
    prs = fetch_github(url)

    output_file.write(f"\n\n## {repo} - CLOSED PRS\n")
    output_file.write("=" * 80 + "\n")

    for pr in prs[:15]:
        output_file.write(f"\n### PR #{pr['number']}: {pr['title']}\n")
        output_file.write(f"**Author**: {pr['user']['login']}\n")
        output_file.write(f"**Merged**: {pr.get('merged_at') is not None}\n")
        output_file.write(f"**Created**: {pr['created_at'][:10]}\n")

        body = (pr.get('body') or 'No description')
        output_file.write(f"\n**Description**:\n{body[:600]}...\n")
        output_file.write("-" * 80 + "\n")

        print(f"  - #{pr['number']}: {pr['title'][:60]}")

    time.sleep(1)

def collect_pr_reviews(repo: str, pr_numbers: List[int], output_file):
    """收集 PR 审核评论（重点）"""
    print(f"\n{'='*80}")
    print(f"Collecting PR Reviews from {repo}")
    print(f"{'='*80}")

    output_file.write(f"\n\n## {repo} - PR REVIEW COMMENTS\n")
    output_file.write("=" * 80 + "\n")

    for pr_num in pr_numbers:
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews"
        reviews = fetch_github(url)

        if not reviews:
            continue

        output_file.write(f"\n### PR #{pr_num} Reviews\n")

        for review in reviews:
            if not review.get('body'):
                continue

            output_file.write(f"\n**Reviewer**: {review['user']['login']}\n")
            output_file.write(f"**State**: {review['state']}\n")
            output_file.write(f"**Comment**:\n{review['body']}\n")
            output_file.write("-" * 40 + "\n")

        print(f"  - PR #{pr_num}: {len(reviews)} reviews")
        time.sleep(0.5)

def main():
    print("=" * 80)
    print("GitHub Data Collector for ReviewAgent")
    print("=" * 80)

    # 输出文件
    with open('github_issues.txt', 'w', encoding='utf-8') as f_issues, \
         open('github_prs.txt', 'w', encoding='utf-8') as f_prs:

        for repo in REPOS:
            try:
                # 收集 Issues
                collect_issues(repo, f_issues)

                # 收集 PRs
                collect_prs(repo, f_prs)

                print(f"\n✓ Completed {repo}")
                time.sleep(2)

            except Exception as e:
                print(f"\n✗ Error processing {repo}: {e}")
                continue

    # 收集重点 PR 的审核评论
    print("\n" + "=" * 80)
    print("Collecting detailed PR reviews...")
    print("=" * 80)

    with open('github_comments.txt', 'w', encoding='utf-8') as f_comments:
        # 示例：收集最近的几个重要 PR
        important_prs = {
            'vllm-project/vllm-ascend': [17344, 14409],  # 从第一次 API 调用看到的
            'Ascend/pytorch': list(range(1, 20)),  # PR #1-20
        }

        for repo, pr_nums in important_prs.items():
            try:
                collect_pr_reviews(repo, pr_nums, f_comments)
            except Exception as e:
                print(f"Error collecting reviews for {repo}: {e}")

    print("\n" + "=" * 80)
    print("✓ Data collection complete!")
    print("=" * 80)
    print("\n生成的文件：")
    print("  - github_issues.txt")
    print("  - github_prs.txt")
    print("  - github_comments.txt")
    print("\n请将这些文件内容发给 Claude，用于优化智能体知识库。")

if __name__ == '__main__':
    main()
