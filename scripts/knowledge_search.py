"""Local source-linked retrieval over collected community records (no network)."""

import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STOP_WORDS = set('the a an and or to of in is it for on with from this that def class return import self error issue pr git diff review npu ascend torch python'.split())


def tokenize(text):
    text = text.lower()
    words = re.findall(r'[a-z0-9]+(?:[._-][a-z0-9]+)*', text)
    parts = [part for word in words for part in re.split(r'[._-]', word)]
    chinese = []
    for run in re.findall(r'[\u4e00-\u9fff]+', text):
        chinese.extend(run[i:i+2] for i in range(len(run)-1))
    return [word for word in words + parts + chinese if len(word) > 1 and word not in STOP_WORDS]


def records(payload):
    if isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, dict))
    elif isinstance(payload, dict):
        if isinstance(payload.get('title'), str):
            yield payload
        else:
            for key in ('open', 'closed'):
                if isinstance(payload.get(key), list):
                    yield from records(payload[key])


class KnowledgeSearch:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir is not None else PROJECT_ROOT / 'data' / 'raw'
        self.documents = []
        self.warnings = []
        self._counts = []
        self._df = Counter()
        seen = set()
        if not self.data_dir.is_dir():
            self.warnings.append(f'数据目录不存在: {self.data_dir}')
        for path in sorted(self.data_dir.glob('*.json')):
            if not path.stem.endswith(('_issues', '_prs')):
                continue
            try:
                payload = json.loads(path.read_text(encoding='utf-8-sig'))
            except (OSError, ValueError) as exc:
                self.warnings.append(f'{path.name}: {exc}')
                continue
            items = list(records(payload))
            if isinstance(payload, dict) and 'message' in payload and not items:
                self.warnings.append(f'{path.name}: 采集失败响应，未纳入检索')
            for item in items:
                title = item.get('title')
                url = item.get('html_url') or item.get('web_url') or ''
                if not isinstance(title, str) or not isinstance(url, str):
                    continue
                parsed = urlparse(url)
                if parsed.scheme not in ('http', 'https') or not parsed.netloc or url in seen:
                    continue
                seen.add(url)
                body = item.get('body') or ''
                if not isinstance(body, str):
                    body = ''
                doc = {
                    'title': title, 'url': url, 'body': body[:30000],
                    'kind': 'pr' if path.stem.endswith('_prs') or 'pull_request' in item else 'issue',
                    'state': item.get('state'), 'updated_at': item.get('updated_at'),
                    'source_file': path.name,
                }
                counts = Counter(tokenize(title + ' ' + title + ' ' + doc['body']))
                self.documents.append(doc)
                self._counts.append(counts)
                self._df.update(counts.keys())
        self._average = sum(sum(c.values()) for c in self._counts) / max(len(self.documents), 1)

    def search(self, query, limit=5, kind=None):
        if not 1 <= limit <= 20:
            raise ValueError('limit 必须在 1 到 20 之间')
        terms = set(tokenize(query))
        ranked = []
        total = len(self.documents)
        for doc, counts in zip(self.documents, self._counts):
            if kind and doc['kind'] != kind:
                continue
            matched = sorted(terms.intersection(counts))
            if not matched:
                continue
            score = 0.0
            for term in matched:
                frequency = counts[term]
                idf = math.log(1 + (total - self._df[term] + 0.5) / (self._df[term] + 0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * sum(counts.values()) / max(self._average, 1)))
            body = doc['body']
            positions = [body.lower().find(term) for term in matched if term in body.lower()]
            start = max(0, min(positions) - 150) if positions else 0
            ranked.append({
                **{key: value for key, value in doc.items() if key != 'body'},
                'excerpt': body[start:start+1200],
                'score': round(score, 4), 'matched_terms': matched,
                'evidence_status': 'historical_record_unverified',
            })
        ranked.sort(key=lambda doc: (-doc['score'], doc['url']))
        return ranked[:limit]
