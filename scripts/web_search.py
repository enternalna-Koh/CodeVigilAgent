"""Shared web search backend for all CLI frontends; snippets are not page text."""

import html
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse


class SearchResultsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.capture = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if self.capture:
            self.depth += 1
        elif tag == 'a' and 'result__a' in classes:
            url = urljoin('https://duckduckgo.com', html.unescape(attrs.get('href', '')))
            parsed = urlparse(url)
            if parsed.hostname in ('duckduckgo.com', 'www.duckduckgo.com'):
                url = parse_qs(parsed.query).get('uddg', [''])[0]
            parsed = urlparse(url)
            self.current = None
            if parsed.scheme in ('https', 'http') and parsed.hostname:
                self.current = {'title': '', 'url': url, 'snippet': '',
                                'evidence_status': 'search_snippet_only'}
                self.results.append(self.current)
            self.capture, self.depth = 'title', 1
        elif 'result__snippet' in classes:
            self.capture, self.depth = 'snippet', 1

    def handle_endtag(self, tag):
        if self.capture:
            self.depth -= 1
            if self.depth <= 0:
                self.capture = None

    def handle_data(self, data):
        if self.capture and self.current is not None:
            self.current[self.capture] += data


class WebSearcher:
    def search(self, query, num_results=3):
        query = str(query).strip()[:300]
        if not query:
            return [{'error': '搜索关键词为空'}]
        request = urllib.request.Request(
            'https://html.duckduckgo.com/html/?' + urlencode({'q': query}),
            headers={'User-Agent': 'Mozilla/5.0 (compatible; ReviewAgent/1.1)'})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    return [{'error': '搜索响应超过 2 MB 限制'}]
                parser = SearchResultsParser()
                parser.feed(raw.decode('utf-8', errors='replace'))
            results, seen = [], set()
            for item in parser.results:
                if item['url'] in seen:
                    continue
                seen.add(item['url'])
                item['title'] = ' '.join(item['title'].split())[:300]
                item['snippet'] = ' '.join(item['snippet'].split())[:1200]
                results.append(item)
            if not results:
                return [{'error': '没有解析到搜索结果；可能无匹配结果或搜索服务要求验证。'}]
            return results[:max(1, min(num_results, 5))]
        except (OSError, ValueError) as exc:
            return [{'error': f'联网搜索失败: {exc}'}]

    def search_ascend_docs(self, query):
        return self.search(f'site:hiascend.com {query}', num_results=3)
