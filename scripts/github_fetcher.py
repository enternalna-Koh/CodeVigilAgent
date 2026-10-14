#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多平台内容获取器
支持 GitHub、Gitee、GitCode
"""
import re
import json
import urllib.request
import urllib.error
from typing import Dict, Optional


class UniversalFetcher:
    """通用内容获取器 - 支持多个 Git 平台"""

    def __init__(self, github_token: Optional[str] = None, gitee_token: Optional[str] = None):
        """
        初始化

        Args:
            github_token: GitHub Personal Access Token
            gitee_token: Gitee 私人令牌
        """
        self.github_token = github_token
        self.gitee_token = gitee_token

    def parse_url(self, url: str) -> Optional[Dict]:
        """
        解析 Git 平台 URL

        Returns:
            {
                'platform': 'github' | 'gitee' | 'gitcode',
                'type': 'pr' | 'issue',
                'owner': 'user',
                'repo': 'repo',
                'number': 123
            }
        """
        # GitHub PR
        if match := re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', url):
            return {
                'platform': 'github',
                'type': 'pr',
                'owner': match.group(1),
                'repo': match.group(2),
                'number': int(match.group(3))
            }

        # GitHub Issue
        if match := re.match(r'https://github\.com/([^/]+)/([^/]+)/issues/(\d+)', url):
            return {
                'platform': 'github',
                'type': 'issue',
                'owner': match.group(1),
                'repo': match.group(2),
                'number': int(match.group(3))
            }

        # Gitee PR
        if match := re.match(r'https://gitee\.com/([^/]+)/([^/]+)/pulls/(\d+)', url):
            return {
                'platform': 'gitee',
                'type': 'pr',
                'owner': match.group(1),
                'repo': match.group(2),
                'number': int(match.group(3))
            }

        # Gitee Issue
        if match := re.match(r'https://gitee\.com/([^/]+)/([^/]+)/issues/([^/?]+)', url):
            return {
                'platform': 'gitee',
                'type': 'issue',
                'owner': match.group(1),
                'repo': match.group(2),
                'number': match.group(3)  # Gitee 可能用字符串
            }

        # GitCode PR
        if match := re.match(r'https://gitcode\.com/([^/]+)/([^/]+)/-/merge_requests/(\d+)', url):
            return {
                'platform': 'gitcode',
                'type': 'pr',
                'owner': match.group(1),
                'repo': match.group(2),
                'number': int(match.group(3))
            }

        # GitCode Issue
        if match := re.match(r'https://gitcode\.com/([^/]+)/([^/]+)/-/issues/(\d+)', url):
            return {
                'platform': 'gitcode',
                'type': 'issue',
                'owner': match.group(1),
                'repo': match.group(2),
                'number': int(match.group(3))
            }

        return None

    def fetch_github(self, parsed: Dict) -> Optional[Dict]:
        """获取 GitHub 内容"""
        endpoint = f"/repos/{parsed['owner']}/{parsed['repo']}"

        if parsed['type'] == 'pr':
            endpoint += f"/pulls/{parsed['number']}"
        else:
            endpoint += f"/issues/{parsed['number']}"

        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ReviewAgent/1.0'
        }

        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'

        url = f"https://api.github.com{endpoint}"
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                data['platform'] = 'github'
                data['type'] = parsed['type']
                return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {'error': '内容不存在或私有仓库（需要 token）', 'platform': 'github'}
            elif e.code == 403:
                return {'error': 'API 速率限制，请配置 GitHub token', 'platform': 'github'}
            else:
                return {'error': f'HTTP {e.code}', 'platform': 'github'}
        except Exception as e:
            return {'error': str(e), 'platform': 'github'}

    def fetch_gitee(self, parsed: Dict) -> Optional[Dict]:
        """获取 Gitee 内容"""
        endpoint = f"/api/v5/repos/{parsed['owner']}/{parsed['repo']}"

        if parsed['type'] == 'pr':
            endpoint += f"/pulls/{parsed['number']}"
        else:
            endpoint += f"/issues/{parsed['number']}"

        headers = {'User-Agent': 'ReviewAgent/1.0'}

        if self.gitee_token:
            endpoint += f"?access_token={self.gitee_token}"

        url = f"https://gitee.com{endpoint}"
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                data['platform'] = 'gitee'
                data['type'] = parsed['type']
                return data
        except Exception as e:
            return {'error': str(e), 'platform': 'gitee'}

    def fetch_gitcode(self, parsed: Dict) -> Optional[Dict]:
        """
        获取 GitCode 内容
        GitCode 基于 GitLab，使用 GitLab API
        """
        project_id = f"{parsed['owner']}/{parsed['repo']}"

        if parsed['type'] == 'pr':
            endpoint = f"/api/v4/projects/{project_id}/merge_requests/{parsed['number']}"
        else:
            endpoint = f"/api/v4/projects/{project_id}/issues/{parsed['number']}"

        headers = {'User-Agent': 'ReviewAgent/1.0'}

        url = f"https://gitcode.com{endpoint}"
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                data['platform'] = 'gitcode'
                data['type'] = parsed['type']
                return data
        except Exception as e:
            return {'error': str(e), 'platform': 'gitcode'}

    def fetch_url(self, url: str) -> Optional[Dict]:
        """
        根据 URL 自动获取内容

        Args:
            url: GitHub/Gitee/GitCode URL

        Returns:
            内容数据
        """
        parsed = self.parse_url(url)

        if not parsed:
            return {'error': '无效的 URL，支持: GitHub、Gitee、GitCode'}

        if parsed['platform'] == 'github':
            return self.fetch_github(parsed)
        elif parsed['platform'] == 'gitee':
            return self.fetch_gitee(parsed)
        elif parsed['platform'] == 'gitcode':
            return self.fetch_gitcode(parsed)

        return {'error': f"不支持的平台: {parsed['platform']}"}

    def format_for_review(self, data: Dict) -> str:
        """格式化为审查文本"""
        if 'error' in data:
            return f"错误: {data['error']}"

        lines = []
        platform = data.get('platform', '').upper()

        # 标题
        lines.append("=" * 70)
        if data.get('type') == 'pr':
            lines.append(f"[{platform}] Pull Request: {data.get('title', 'N/A')}")
        else:
            lines.append(f"[{platform}] Issue: {data.get('title', 'N/A')}")
        lines.append("=" * 70)

        # 基本信息
        author = data.get('user', {})
        if isinstance(author, dict):
            author = author.get('login') or author.get('name', 'Unknown')

        lines.append(f"作者: {author}")
        lines.append(f"状态: {data.get('state', 'N/A')}")
        lines.append(f"链接: {data.get('html_url', 'N/A')}")
        lines.append("")

        # 描述
        lines.append("描述:")
        body = data.get('body') or data.get('description', '(无描述)')
        lines.append(body[:1000])  # 限制长度
        lines.append("")

        # 标签（如果是 issue）
        if data.get('type') == 'issue' and data.get('labels'):
            labels = data['labels']
            if isinstance(labels, list):
                label_names = [l.get('name') if isinstance(l, dict) else str(l) for l in labels]
                lines.append(f"标签: {', '.join(label_names)}")
                lines.append("")

        return '\n'.join(lines)


# 向后兼容
GitHubFetcher = UniversalFetcher


# ============================================================================
# 网络搜索
# ============================================================================

class WebSearcher:
    """网络搜索功能"""

    def __init__(self):
        """初始化搜索器"""
        pass

    def search(self, query: str, num_results: int = 5) -> list:
        """
        搜索网络

        Args:
            query: 搜索关键词
            num_results: 返回结果数量

        Returns:
            [{'title': '...', 'url': '...', 'snippet': '...'}, ...]
        """
        # 使用 DuckDuckGo HTML 搜索（无需 API key）
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            req = urllib.request.Request(search_url, headers=headers)

            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')

            # 简单解析 HTML（提取结果）
            results = []

            # 提取搜索结果（简化版）
            result_pattern = r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a[^>]+class="result__snippet"[^>]*>([^<]+)</a>'

            matches = re.findall(result_pattern, html)
            snippets = re.findall(snippet_pattern, html)

            for i, (url, title) in enumerate(matches[:num_results]):
                snippet = snippets[i] if i < len(snippets) else ''

                # 清理 URL
                if url.startswith('//duckduckgo.com/l/'):
                    # 提取真实 URL
                    url_match = re.search(r'uddg=([^&]+)', url)
                    if url_match:
                        url = urllib.parse.unquote(url_match.group(1))

                results.append({
                    'title': title.strip(),
                    'url': url,
                    'snippet': snippet.strip()
                })

            return results

        except Exception as e:
            return [{'error': f'搜索失败: {str(e)}'}]

    def search_ascend_docs(self, query: str) -> list:
        """
        搜索昇腾文档

        Args:
            query: 搜索关键词

        Returns:
            搜索结果列表
        """
        # 限定在昇腾官方文档站点
        site_query = f"site:hiascend.com OR site:ascend.huawei.com {query}"
        return self.search(site_query, num_results=3)


# ============================================================================
# 测试
# ============================================================================

# Both the legacy UI and the current Agent use the same search backend.
from scripts.web_search import WebSearcher

if __name__ == '__main__':
    # 测试 GitHub
    fetcher = UniversalFetcher()

    print("测试 GitHub:")
    url = "https://github.com/pytorch/pytorch/issues/1"
    data = fetcher.fetch_url(url)
    print(fetcher.format_for_review(data))
    print()

    # 测试搜索
    print("测试搜索:")
    searcher = WebSearcher()
    results = searcher.search("昇腾 NPU torch_npu")
    for r in results:
        print(f"- {r['title']}")
        print(f"  {r['url']}")
        print()

    def parse_url(self, url: str) -> Optional[Dict]:
        """
        解析 GitHub URL

        Returns:
            {
                'type': 'pr' | 'issue',
                'owner': 'user',
                'repo': 'repo',
                'number': 123
            }
        """
        # PR: https://github.com/owner/repo/pull/123
        pr_match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', url)
        if pr_match:
            return {
                'type': 'pr',
                'owner': pr_match.group(1),
                'repo': pr_match.group(2),
                'number': int(pr_match.group(3))
            }

        # Issue: https://github.com/owner/repo/issues/123
        issue_match = re.match(r'https://github\.com/([^/]+)/([^/]+)/issues/(\d+)', url)
        if issue_match:
            return {
                'type': 'issue',
                'owner': issue_match.group(1),
                'repo': issue_match.group(2),
                'number': int(issue_match.group(3))
            }

        return None

    def fetch_api(self, endpoint: str) -> Optional[Dict]:
        """
        调用 GitHub API

        Args:
            endpoint: API 端点，如 /repos/owner/repo/pulls/123

        Returns:
            JSON 响应数据
        """
        url = self.base_url + endpoint

        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ReviewAgent/1.0'
        }

        if self.token:
            headers['Authorization'] = f'token {self.token}'

        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {'error': 'PR/Issue 不存在或私有仓库（需要 token）'}
            elif e.code == 403:
                return {'error': 'API 速率限制，请配置 GitHub token'}
            else:
                return {'error': f'HTTP {e.code}: {e.reason}'}
        except Exception as e:
            return {'error': str(e)}

    def fetch_pr(self, owner: str, repo: str, number: int) -> Optional[Dict]:
        """
        获取 PR 详情

        Returns:
            {
                'title': '...',
                'body': '...',
                'state': 'open/closed',
                'user': '...',
                'diff_url': '...',
                'files': [...],
                'comments': [...]
            }
        """
        # 获取 PR 基本信息
        pr_data = self.fetch_api(f'/repos/{owner}/{repo}/pulls/{number}')

        if not pr_data or 'error' in pr_data:
            return pr_data

        # 获取文件变更
        files_data = self.fetch_api(f'/repos/{owner}/{repo}/pulls/{number}/files')

        # 获取评论
        comments_data = self.fetch_api(f'/repos/{owner}/{repo}/issues/{number}/comments')

        return {
            'type': 'pr',
            'title': pr_data.get('title', ''),
            'body': pr_data.get('body', ''),
            'state': pr_data.get('state', ''),
            'user': pr_data.get('user', {}).get('login', ''),
            'html_url': pr_data.get('html_url', ''),
            'diff_url': pr_data.get('diff_url', ''),
            'files': files_data if isinstance(files_data, list) else [],
            'comments': comments_data if isinstance(comments_data, list) else [],
            'created_at': pr_data.get('created_at', ''),
            'updated_at': pr_data.get('updated_at', ''),
        }

    def fetch_issue(self, owner: str, repo: str, number: int) -> Optional[Dict]:
        """
        获取 Issue 详情

        Returns:
            {
                'title': '...',
                'body': '...',
                'state': 'open/closed',
                'user': '...',
                'comments': [...]
            }
        """
        # 获取 Issue 基本信息
        issue_data = self.fetch_api(f'/repos/{owner}/{repo}/issues/{number}')

        if not issue_data or 'error' in issue_data:
            return issue_data

        # 获取评论
        comments_data = self.fetch_api(f'/repos/{owner}/{repo}/issues/{number}/comments')

        return {
            'type': 'issue',
            'title': issue_data.get('title', ''),
            'body': issue_data.get('body', ''),
            'state': issue_data.get('state', ''),
            'user': issue_data.get('user', {}).get('login', ''),
            'html_url': issue_data.get('html_url', ''),
            'comments': comments_data if isinstance(comments_data, list) else [],
            'created_at': issue_data.get('created_at', ''),
            'updated_at': issue_data.get('updated_at', ''),
            'labels': [l.get('name') for l in issue_data.get('labels', [])],
        }

    def fetch_url(self, url: str) -> Optional[Dict]:
        """
        根据 URL 自动获取内容

        Args:
            url: GitHub PR 或 Issue URL

        Returns:
            PR 或 Issue 数据
        """
        parsed = self.parse_url(url)

        if not parsed:
            return {'error': '无效的 GitHub URL'}

        if parsed['type'] == 'pr':
            return self.fetch_pr(parsed['owner'], parsed['repo'], parsed['number'])
        else:
            return self.fetch_issue(parsed['owner'], parsed['repo'], parsed['number'])

    def format_for_review(self, data: Dict) -> str:
        """
        格式化为适合审查的文本

        Args:
            data: fetch_url 返回的数据

        Returns:
            格式化的文本
        """
        if 'error' in data:
            return f"错误: {data['error']}"

        lines = []

        if data['type'] == 'pr':
            lines.append("=" * 70)
            lines.append(f"Pull Request: {data['title']}")
            lines.append("=" * 70)
            lines.append(f"作者: {data['user']}")
            lines.append(f"状态: {data['state']}")
            lines.append(f"链接: {data['html_url']}")
            lines.append("")
            lines.append("描述:")
            lines.append(data['body'] or '(无描述)')
            lines.append("")

            if data['files']:
                lines.append(f"变更文件 ({len(data['files'])} 个):")
                for f in data['files'][:10]:  # 最多显示 10 个
                    changes = f.get('changes', 0)
                    additions = f.get('additions', 0)
                    deletions = f.get('deletions', 0)
                    lines.append(f"  - {f['filename']} (+{additions} -{deletions})")

                    # 显示补丁（如果有）
                    if f.get('patch'):
                        lines.append("    ```diff")
                        lines.append(f.get('patch', '')[:500])  # 限制长度
                        lines.append("    ```")

            if data['comments']:
                lines.append("")
                lines.append(f"评论 ({len(data['comments'])} 条):")
                for c in data['comments'][:5]:  # 最多显示 5 条
                    lines.append(f"  - {c['user']['login']}: {c['body'][:100]}")

        else:  # issue
            lines.append("=" * 70)
            lines.append(f"Issue: {data['title']}")
            lines.append("=" * 70)
            lines.append(f"作者: {data['user']}")
            lines.append(f"状态: {data['state']}")
            lines.append(f"标签: {', '.join(data['labels']) if data['labels'] else '(无)'}")
            lines.append(f"链接: {data['html_url']}")
            lines.append("")
            lines.append("描述:")
            lines.append(data['body'] or '(无描述)')
            lines.append("")

            if data['comments']:
                lines.append(f"评论 ({len(data['comments'])} 条):")
                for c in data['comments'][:5]:
                    lines.append(f"  - {c['user']['login']}: {c['body'][:100]}")

        return '\n'.join(lines)


# ============================================================================
# 测试
# ============================================================================

if __name__ == '__main__':
    fetcher = GitHubFetcher()

    # 测试 PR
    print("测试 PR:")
    url = "https://github.com/vllm-project/vllm/pull/1"
    data = fetcher.fetch_url(url)
    print(fetcher.format_for_review(data))
    print()

    # 测试 Issue
    print("测试 Issue:")
    url = "https://github.com/pytorch/pytorch/issues/1"
    data = fetcher.fetch_url(url)
    print(fetcher.format_for_review(data))
