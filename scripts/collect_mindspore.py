#!/usr/bin/env python3
"""
扩展数据收集 - MindSpore 生态
收集 MindSpore GitHub 和 Gitee 仓库的 issues 和 PRs
"""
import urllib.request
import json
import time
import os

MINDSPORE_REPOS_GITHUB = [
    'mindspore-ai/mindspore',
    'mindspore-ai/models',
    'mindspore-ai/docs',
    'mindspore-ai/graphengine'
]

MINDSPORE_REPOS_GITEE = [
    'mindspore/mindspore',
    'mindspore/models',
    'mindspore/hub',
    'mindspore/community'
]

def fetch_github(url):
    """从 GitHub 获取数据"""
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"  错误: {e}")
        return None

def fetch_gitee(url, access_token=None):
    """从 Gitee 获取数据"""
    if access_token:
        url += f"?access_token={access_token}"

    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"  错误: {e}")
        return None

def collect_github_mindspore():
    """收集 MindSpore GitHub 数据"""
    print("="*80)
    print("收集 MindSpore GitHub 数据")
    print("="*80)

    os.makedirs('data/raw', exist_ok=True)

    for repo in MINDSPORE_REPOS_GITHUB:
        print(f"\n处理 {repo}...")

        owner, name = repo.split('/')

        # 收集 issues (增加到 100 个)
        print("  收集 issues...")
        issues_url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100"
        issues = fetch_github(issues_url)

        if issues:
            output_file = f"data/raw/{owner}_{name}_issues.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(issues, f, indent=2, ensure_ascii=False)
            print(f"    OK: {len(issues)} issues 已保存")
        else:
            print(f"    失败: 无法获取 issues")

        time.sleep(2)

        # 收集 PRs (增加到 100 个)
        print("  收集 PRs...")
        prs_url = f"https://api.github.com/repos/{repo}/pulls?state=all&per_page=100"
        prs = fetch_github(prs_url)

        if prs:
            output_file = f"data/raw/{owner}_{name}_prs.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(prs, f, indent=2, ensure_ascii=False)
            print(f"    OK: {len(prs)} PRs 已保存")
        else:
            print(f"    失败: 无法获取 PRs")

        time.sleep(2)

    print("\n" + "="*80)
    print("MindSpore GitHub 收集完成")
    print("="*80)

def collect_gitee_mindspore():
    """收集 MindSpore Gitee 数据"""
    print("\n" + "="*80)
    print("收集 MindSpore Gitee 数据")
    print("="*80)

    print("\n注意: Gitee API 需要 access_token")
    print("可以在 https://gitee.com/profile/personal_access_tokens 生成")
    print("当前使用公开 API，可能有限流")

    os.makedirs('data/raw', exist_ok=True)

    for repo in MINDSPORE_REPOS_GITEE:
        print(f"\n处理 {repo}...")

        owner, name = repo.split('/')

        # 收集 issues
        print("  收集 issues...")
        issues_url = f"https://gitee.com/api/v5/repos/{repo}/issues?state=all&per_page=100"
        issues = fetch_gitee(issues_url)

        if issues:
            output_file = f"data/raw/gitee_{owner}_{name}_issues.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(issues, f, indent=2, ensure_ascii=False)
            print(f"    OK: {len(issues)} issues 已保存")
        else:
            print(f"    失败: 无法获取 issues (可能需要 token)")

        time.sleep(2)

        # 收集 PRs
        print("  收集 PRs...")
        prs_url = f"https://gitee.com/api/v5/repos/{repo}/pulls?state=all&per_page=100"
        prs = fetch_gitee(prs_url)

        if prs:
            output_file = f"data/raw/gitee_{owner}_{name}_prs.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(prs, f, indent=2, ensure_ascii=False)
            print(f"    OK: {len(prs)} PRs 已保存")
        else:
            print(f"    失败: 无法获取 PRs (可能需要 token)")

        time.sleep(2)

    print("\n" + "="*80)
    print("MindSpore Gitee 收集完成")
    print("="*80)

def main():
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*20 + "MindSpore 生态数据收集" + " "*36 + "║")
    print("╚" + "="*78 + "╝")

    # GitHub
    collect_github_mindspore()

    # Gitee
    collect_gitee_mindspore()

    # 统计
    print("\n" + "="*80)
    print("收集完成统计")
    print("="*80)

    import glob
    mindspore_files = glob.glob('data/raw/*mindspore*')

    total_size = sum(os.path.getsize(f) for f in mindspore_files)

    print(f"\nMindSpore 相关文件: {len(mindspore_files)} 个")
    print(f"总大小: {total_size / 1024 / 1024:.2f} MB")

    for f in sorted(mindspore_files):
        size = os.path.getsize(f) / 1024
        print(f"  {os.path.basename(f):50s} {size:8.1f} KB")

if __name__ == '__main__':
    main()
