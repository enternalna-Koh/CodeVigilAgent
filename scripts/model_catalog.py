"""Known providers / models for /model switching (mirrors bin/onboard.js catalogs)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


# file_provider: value stored in ai_config.json (native adapter or openai+base_url)
# label: logical vendor name shown to user
CATALOG: List[Dict] = [
    {
        'label': 'deepseek',
        'file_provider': 'deepseek',
        'base_url': '',
        'models': [
            'deepseek-chat', 'deepseek-reasoner', 'deepseek-coder',
            'deepseek-v3', 'deepseek-v3.1', 'deepseek-r1', 'deepseek-r1-0528',
        ],
        'default_model': 'deepseek-chat',
        'aliases': ('deepseek',),
    },
    {
        'label': 'openai',
        'file_provider': 'openai',
        'base_url': 'https://api.openai.com/v1',
        'models': [
            'gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini',
            'o1', 'o3-mini', 'o4-mini', 'gpt-3.5-turbo',
        ],
        'default_model': 'gpt-4o',
        'aliases': ('openai', 'gpt'),
    },
    {
        'label': 'claude',
        'file_provider': 'claude',
        'base_url': '',
        'models': [
            'claude-opus-4-20250514', 'claude-sonnet-4-20250514',
            'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022',
        ],
        'default_model': 'claude-3-5-sonnet-20241022',
        'aliases': ('claude', 'anthropic'),
    },
    {
        'label': 'glm',
        'file_provider': 'glm',
        'base_url': '',
        'models': [
            'glm-4', 'glm-4-plus', 'glm-4-air', 'glm-4-flash', 'glm-4-long',
            'glm-4v', 'glm-z1-air', 'glm-3-turbo',
        ],
        'default_model': 'glm-4-flash',
        'aliases': ('glm', 'zhipu', '智谱'),
    },
    {
        'label': 'minimax',
        'file_provider': 'openai',
        'base_url': 'https://api.minimax.chat/v1',
        'models': [
            'MiniMax-M1', 'MiniMax-Text-01',
            'abab6.5s-chat', 'abab6.5-chat', 'abab5.5-chat',
        ],
        'default_model': 'MiniMax-Text-01',
        'aliases': ('minimax',),
    },
    {
        'label': 'gemini',
        'file_provider': 'openai',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
        'models': [
            'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro',
        ],
        'default_model': 'gemini-2.5-flash',
        'aliases': ('gemini', 'google'),
    },
    {
        'label': 'xai',
        'file_provider': 'openai',
        'base_url': 'https://api.x.ai/v1',
        'models': ['grok-4', 'grok-4-latest', 'grok-3', 'grok-3-mini', 'grok-2'],
        'default_model': 'grok-3',
        'aliases': ('xai', 'grok'),
    },
    {
        'label': 'qwen',
        'file_provider': 'openai',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models': [
            'qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen-long',
            'qwen2.5-72b-instruct', 'qwq-32b', 'qwen3-32b',
        ],
        'default_model': 'qwen-plus',
        'aliases': ('qwen', '通义', 'dashscope'),
    },
    {
        'label': 'doubao',
        'file_provider': 'openai',
        'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'models': [
            'doubao-seed-1.6', 'doubao-1.5-pro-32k', 'doubao-pro-32k', 'doubao-lite-32k',
        ],
        'default_model': 'doubao-1.5-pro-32k',
        'aliases': ('doubao', '豆包', 'volc'),
    },
    {
        'label': 'hunyuan',
        'file_provider': 'openai',
        'base_url': 'https://api.hunyuan.cloud.tencent.com/v1',
        'models': [
            'hunyuan-lite', 'hunyuan-standard', 'hunyuan-pro', 'hunyuan-turbo',
        ],
        'default_model': 'hunyuan-turbo',
        'aliases': ('hunyuan', '混元'),
    },
    {
        'label': 'kimi',
        'file_provider': 'openai',
        'base_url': 'https://api.moonshot.cn/v1',
        'models': [
            'moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k',
            'kimi-latest', 'kimi-k2-0711-preview',
        ],
        'default_model': 'kimi-latest',
        'aliases': ('kimi', 'moonshot'),
    },
    {
        'label': 'siliconflow',
        'file_provider': 'openai',
        'base_url': 'https://api.siliconflow.cn/v1',
        'models': [
            'deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1',
            'Qwen/Qwen2.5-72B-Instruct', 'THUDM/GLM-4-9B-0414',
        ],
        'default_model': 'deepseek-ai/DeepSeek-V3',
        'aliases': ('siliconflow', '硅基'),
    },
]


def _norm(s: str) -> str:
    return (s or '').strip().lower()


def _base_key(provider: str, base_url: str) -> Tuple[str, str]:
    return (_norm(provider), _norm(base_url).rstrip('/'))


def find_entry_by_alias(token: str) -> Optional[Dict]:
    t = _norm(token)
    for entry in CATALOG:
        if t == _norm(entry['label']) or t in {_norm(a) for a in entry.get('aliases', ())}:
            return entry
        for m in entry['models']:
            if t == _norm(m):
                return entry
    # prefix / contains for glm-4-xxx etc.
    for entry in CATALOG:
        for m in entry['models']:
            if _norm(m).startswith(t) or t.startswith(_norm(entry['label'])):
                if t.startswith(_norm(entry['label'])) or any(
                        _norm(m2).startswith(t) for m2 in entry['models']):
                    return entry
    return None


def resolve_model_request(raw: str) -> Dict:
    """Parse user input like 'glm' / 'glm-4-flash' / 'MiniMax-M1'.

    Returns dict:
      ok, label, file_provider, model, base_url, matched_exact, message
    """
    text = (raw or '').strip()
    if not text:
        return {'ok': False, 'message': '用法: /model <厂商或模型ID>  例: /model glm  或  /model glm-4-flash'}

    parts = text.split()
    token = parts[0]
    explicit_model = parts[1] if len(parts) > 1 else ''

    # Exact model id match first
    for entry in CATALOG:
        for m in entry['models']:
            if _norm(token) == _norm(m):
                return {
                    'ok': True,
                    'label': entry['label'],
                    'file_provider': entry['file_provider'],
                    'model': m,
                    'base_url': entry.get('base_url') or '',
                    'matched_exact': True,
                    'message': f"识别为 {entry['label']} / {m}",
                }

    entry = find_entry_by_alias(token)
    if not entry:
        # Unknown: keep as bare model id on current gateway — caller decides
        return {
            'ok': True,
            'label': 'custom',
            'file_provider': None,
            'model': text,
            'base_url': None,
            'matched_exact': False,
            'message': f'未识别厂商，将只改 model={text}（仍用当前 API/base_url）',
        }

    model = explicit_model or entry['default_model']
    if explicit_model:
        # allow custom id under known vendor
        model = explicit_model
    else:
        # if token looks like a model under this vendor
        for m in entry['models']:
            if _norm(token) == _norm(m) or _norm(m).startswith(_norm(token)):
                if _norm(token) != _norm(entry['label']) and token.lower() not in {
                        a.lower() for a in entry.get('aliases', ())}:
                    model = m
                    break

    # Vendor-only token (glm / minimax) → default model
    if _norm(token) in {_norm(entry['label']), *{_norm(a) for a in entry.get('aliases', ())}}:
        model = explicit_model or entry['default_model']

    return {
        'ok': True,
        'label': entry['label'],
        'file_provider': entry['file_provider'],
        'model': model,
        'base_url': entry.get('base_url') or '',
        'matched_exact': True,
        'message': f"识别为 {entry['label']} / {model}",
    }


def gateway_changed(current: Dict, target: Dict) -> bool:
    """True if provider/base_url family changes (needs a new API key)."""
    if not target.get('file_provider'):
        return False
    cur_p = _norm(current.get('provider') or '')
    cur_b = _norm(current.get('base_url') or '').rstrip('/')
    # Treat openai+minimax base as minimax lane
    tgt_p = _norm(target['file_provider'])
    tgt_b = _norm(target.get('base_url') or '').rstrip('/')
    return _base_key(cur_p, cur_b) != _base_key(tgt_p, tgt_b)


def apply_target_to_config(data: Dict, target: Dict, api_key: Optional[str] = None) -> Dict:
    """Return updated config dict."""
    out = dict(data or {})
    out['model'] = target['model']
    if target.get('file_provider'):
        out['provider'] = target['file_provider']
        base = target.get('base_url') or ''
        if base:
            out['base_url'] = base
        else:
            # native adapters should not keep a foreign base_url
            out['base_url'] = ''
        out['label'] = target.get('label') or out.get('label')
    if api_key is not None:
        out['api_key'] = api_key
    return out


def format_catalog_help() -> str:
    lines = ['可用厂商（/model <名> 会切厂商并要求对应 API Key）:']
    for entry in CATALOG:
        sample = entry['default_model']
        lines.append(f"  {entry['label']:12} 例: /model {entry['label']}  → {sample}")
    lines.append('也可直接: /model glm-4-flash  /model MiniMax-M1')
    return '\n'.join(lines)
