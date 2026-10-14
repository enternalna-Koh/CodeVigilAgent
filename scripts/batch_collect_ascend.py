#!/usr/bin/env python3
"""
批量收集 Ascend 社区仓库数据
"""
import json
import urllib.request
import time
import os

# 目标仓库列表
REPOS = [
    # 已收集
    "Ascend/pytorch",
    "vllm-project/vllm-ascend",
    "Ascend/sglang",

    # 新增：核心框架
    "Ascend/mindspore",
    "Ascend/ModelZoo-PyTorch",
    "Ascend/AscendSpeed",

    # 新增：示例和工具
    "Ascend/samples",
    "Ascend/tools",

    # 新增：算子相关
    "Ascend/ascend-pytorch-crowdsource-op",
]

def fetch_github(url, max_retries=3):
    """获取 GitHub API 数据，带重试"""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'ReviewAgent-DataCollector/2.0')
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            print(f"Error fetching {url}: {e}")
            return []

def collect_repo_data(repo):
    """收集单个仓库的 issues 和 PRs"""
    owner, name = repo.split('/')
    print(f"\n{'='*80}")
    print(f"收集 {repo}")
    print('='*80)

    # 收集 Issues
    issues_url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100"
    issues = fetch_github(issues_url)

    if issues:
        # 分离真实 issues（去除 PRs）
        real_issues = [i for i in issues if 'pull_request' not in i]
        print(f"✓ Issues: {len(real_issues)}")

        # 保存
        output_file = f"data/raw/{owner}_{name}_issues.json"
        os.makedirs('data/raw', exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)

    time.sleep(1)  # 避免 rate limit

    # 收集 PRs
    prs_url = f"https://api.github.com/repos/{repo}/pulls?state=all&per_page=100"
    prs = fetch_github(prs_url)

    if prs:
        print(f"✓ PRs: {len(prs)}")

        # 保存
        output_file = f"data/raw/{owner}_{name}_prs.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(prs, f, indent=2, ensure_ascii=False)

    return len(real_issues) if issues else 0, len(prs) if prs else 0

def main():
    print("="*80)
    print("Ascend 社区数据批量收集工具")
    print("="*80)

    total_issues = 0
    total_prs = 0
    collected = []

    for repo in REPOS:
        try:
            issues_count, prs_count = collect_repo_data(repo)
            total_issues += issues_count
            total_prs += prs_count
            collected.append({
                'repo': repo,
                'issues': issues_count,
                'prs': prs_count
            })
            time.sleep(2)  # 控制请求频率
        except Exception as e:
            print(f"✗ Failed to collect {repo}: {e}")

    # 生成总结
    print("\n" + "="*80)
    print("收集完成")
    print("="*80)
    print(f"\n总仓库数: {len(collected)}")
    print(f"总 Issues: {total_issues}")
    print(f"总 PRs: {total_prs}")

    print("\n详细统计:")
    for item in collected:
        print(f"  {item['repo']}: {item['issues']} issues, {item['prs']} PRs")

    # 保存统计
    with open('data/reports/batch_collection_summary.json', 'w', encoding='utf-8') as f:
        json.dump({
            'total_repos': len(collected),
            'total_issues': total_issues,
            'total_prs': total_prs,
            'repositories': collected
        }, f, indent=2, ensure_ascii=False)

if __name__ == '__main__':
    main()
