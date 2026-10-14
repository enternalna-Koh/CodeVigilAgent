#!/usr/bin/env python3
"""
收集 PR Review 对话数据
从 merged PRs 中提取审核意见和讨论
"""
import json
import urllib.request
import time
import os

# 高价值仓库 - 有活跃的 PR review
REPOS = [
    "Ascend/pytorch",
    "vllm-project/vllm-ascend",
    "Ascend/sglang",
]

def fetch_github(url, max_retries=3):
    """获取 GitHub API 数据"""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'ReviewAgent-ReviewCollector/1.0')
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"Error: {e}")
            return None

def collect_pr_reviews(repo, pr_number):
    """收集单个 PR 的所有 review comments"""
    # Review comments
    reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    reviews = fetch_github(reviews_url)

    # Review comments (inline)
    comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"
    comments = fetch_github(comments_url)

    # Issue comments (general)
    issue_comments_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    issue_comments = fetch_github(issue_comments_url)

    return {
        'reviews': reviews if reviews else [],
        'review_comments': comments if comments else [],
        'issue_comments': issue_comments if issue_comments else []
    }

def main():
    print("="*80)
    print("收集 PR Review 对话数据")
    print("="*80)

    os.makedirs('data/pr_reviews', exist_ok=True)

    for repo in REPOS:
        owner, name = repo.split('/')
        print(f"\n处理 {repo}...")

        # 读取已收集的 PRs
        prs_file = f"data/raw/{owner}_{name}_prs.json"
        if not os.path.exists(prs_file):
            print(f"  跳过: PRs 数据不存在")
            continue

        with open(prs_file, 'r', encoding='utf-8') as f:
            prs = json.load(f)

        # 只收集 merged PRs 的前 20 个
        merged_prs = [pr for pr in prs if pr.get('merged_at')][:20]

        print(f"  找到 {len(merged_prs)} 个 merged PRs，收集前 20 个的 review...")

        pr_reviews_data = []

        for i, pr in enumerate(merged_prs):
            pr_number = pr['number']
            print(f"    [{i+1}/{len(merged_prs)}] PR #{pr_number}: {pr['title'][:50]}...")

            reviews = collect_pr_reviews(repo, pr_number)

            if reviews['reviews'] or reviews['review_comments']:
                pr_reviews_data.append({
                    'pr_number': pr_number,
                    'pr_title': pr['title'],
                    'pr_url': pr['html_url'],
                    'merged_at': pr['merged_at'],
                    'reviews': reviews['reviews'],
                    'review_comments': reviews['review_comments'],
                    'issue_comments': reviews['issue_comments']
                })

                review_count = len(reviews['reviews'])
                comment_count = len(reviews['review_comments'])
                print(f"      -> {review_count} reviews, {comment_count} inline comments")

            time.sleep(2)  # 避免 rate limit

        # 保存
        output_file = f"data/pr_reviews/{owner}_{name}_reviews.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(pr_reviews_data, f, indent=2, ensure_ascii=False)

        print(f"  ✓ 已保存 {len(pr_reviews_data)} 个 PR reviews 到 {output_file}")

if __name__ == '__main__':
    main()
