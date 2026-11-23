"""
通用 AI API 适配器
支持多种 AI 服务：DeepSeek, OpenAI, Claude, GLM, 等
"""
import json
import os
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import urllib.request
import urllib.parse

# "The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek-v3.2."
_SUPPORTED_RE = re.compile(r'supported API model names are\s+(.+?)(?:\s*,\s*but you passed|\s*\.|$)', re.I)
_PASSED_RE = re.compile(r'but you passed\s+(\S+)', re.I)


def _probe_body(body: str) -> Dict[str, str]:
    """从错误响应里抽出 type / message，取不到就返回空串。"""
    try:
        data = json.loads(body)
    except Exception:
        return {}
    err = data.get('error') if isinstance(data, dict) else None
    if isinstance(err, dict):
        return {
            'type': str(err.get('type') or err.get('code') or ''),
            'message': str(err.get('message') or ''),
        }
    if isinstance(data, dict):
        return {'type': '', 'message': str(data.get('message') or '')}
    return {}


def _format_http_error(exc) -> str:
    """Surface provider error body (400 reason) instead of bare HTTP Error 400.

    400 且能解析出"支持模型列表"时，直接给出可操作的修复步骤，
    而不是把整段 JSON 糊在屏幕上（那串 JSON 会撑爆边框）。
    """
    import urllib.error
    if not isinstance(exc, urllib.error.HTTPError):
        return f'Error: {exc}'
    body = ''
    try:
        raw = exc.read()
        body = raw.decode('utf-8', errors='replace')[:800] if raw else ''
    except Exception:
        body = ''

    probed = _probe_body(body)
    message = probed.get('message') or body
    err_type = probed.get('type') or ''

    supported: List[str] = []
    m = _SUPPORTED_RE.search(message)
    if m:
        supported = [s.strip() for s in re.split(r'[,/、]', m.group(1)) if s.strip()]
    passed = ''
    pm = _PASSED_RE.search(message)
    if pm:
        passed = pm.group(1).rstrip('.,;:')

    if supported:
        head = f'Error: HTTP {exc.code}'
        if err_type:
            head += f' {err_type}'
        lines = [head]
        if passed:
            lines.append(f'  服务端不认识模型 ID「{passed}」')
        else:
            lines.append('  服务端不认识当前模型 ID')
        lines.append(f'  现在可用：{" / ".join(supported)}')
        lines.append('  修复：跑 reviewagent config -w 重选模型，'
                     '或把本机配置里的 "model" 改成上面任一名字')
        lines.append(f'  原始响应：{message[:180]}')
        return '\n'.join(lines)

    lower = (body + str(exc.reason)).lower()
    hint = ''
    if 'vl' in lower or 'vision' in lower or 'image' in lower:
        hint = '（当前模型可能是视觉/多模态，对话请改用文本模型，如 MiniMax-Text-01 / MiniMax-M1）'
    if exc.code == 400:
        hint = hint or '（常见原因：模型 ID 不支持 chat、参数不兼容、或 base_url 不对）'
    detail = f' — {body}' if body else ''
    return f'Error: HTTP {exc.code} {exc.reason}{detail}{hint}'


# 最近一次请求的终止原因（finish_reason / reasoning_tokens）。
# provider 层只返回字符串，拿不到这些字段；用模块级变量记一手，
# 让调用方在"回复被截断"时能给出准确原因而不是笼统的解析失败。
_LAST_FINISH: Dict[str, object] = {'reason': None, 'reasoning_tokens': 0}


def _extract_content(result: Dict, model: str = '') -> str:
    """取回复正文。

    推理型模型（deepseek-flash 等）会把 max_tokens 先用在 reasoning 上，
    额度不够时正文直接是空字符串 —— 直接返回 '' 会让界面显示一个空盒子，
    所以这里给出可读的原因。
    """
    try:
        choice = (result.get('choices') or [{}])[0]
    except Exception:
        return ''
    # 记下这次的真实终止原因：正文不空但被截断时，上层（如审查的 JSON 解析）
    # 只能看到"JSON 不完整"，分不清是模型胡说还是额度不够，这里留下一手证据。
    _LAST_FINISH['reason'] = choice.get('finish_reason')
    usage_ = result.get('usage') or {}
    _LAST_FINISH['reasoning_tokens'] = (
        (usage_.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0)
    msg = choice.get('message') or {}
    content = msg.get('content')
    if isinstance(content, list):  # 部分网关把正文分段返回
        parts = []
        for seg in content:
            parts.append(str(seg.get('text', '')) if isinstance(seg, dict) else str(seg))
        content = ''.join(parts)
    content = (content or '').strip()
    if content:
        return content
    usage = result.get('usage') or {}
    reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0
    finish = choice.get('finish_reason')
    if reasoning and finish == 'length':
        return (f'（正文为空：max_tokens 被推理过程用掉了 {reasoning} tokens。'
                f'把 max_tokens 调大，或换非推理模型。）')
    if finish == 'length':
        return '（正文为空：回复被 max_tokens 截断，请调大 max_tokens。）'
    return ''


def non_json_reply(response: str) -> str:
    """回复明显不是 JSON 时，返回一句能看懂的原因；是 JSON 则返回空串。

    这些文本都是本模块自己拼的说明（正文为空、HTTP 错误），
    形状和 JSON 差得远，直接丢给 json.loads 只会得到
    "Expecting value: line 1 column 1 (char 0)"，用户完全看不出发生了什么。
    """
    text = (response or '').strip()
    if not text:
        return 'AI 返回了空内容（请求可能超时，或模型没有输出正文）。'
    if text.startswith('Error:'):
        # HTTP 4xx/5xx、网络错误：原因已经写在第一行
        return f'AI 调用失败：{text.splitlines()[0]}'
    if text.startswith('（') and ('正文为空' in text or '截断' in text):
        return f'AI 没有返回可解析的内容：{text}'
    return ''


def resolve_ai_timeout(explicit: Optional[int] = None) -> int:
    """HTTP read timeout for model calls (seconds).

    Default 180 — PR 诊断带证据包时 60s 很容易 `The read operation timed out`。
    Override: REVIEWAGENT_AI_TIMEOUT or AI_HTTP_TIMEOUT (integer seconds, 30–600).
    """
    if explicit is not None:
        try:
            return max(30, min(600, int(explicit)))
        except (TypeError, ValueError):
            pass
    for key in ('REVIEWAGENT_AI_TIMEOUT', 'AI_HTTP_TIMEOUT'):
        raw = (os.getenv(key) or '').strip()
        if not raw:
            continue
        try:
            return max(30, min(600, int(raw)))
        except ValueError:
            continue
    return 180


def _post_json(url: str, headers: Dict, data: Dict, timeout: Optional[int] = None) -> Dict:
    import urllib.error
    timeout = resolve_ai_timeout(timeout)
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_format_http_error(exc)) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f'Error: The read operation timed out（HTTP {timeout}s）。'
            f'可设 REVIEWAGENT_AI_TIMEOUT=300 后重试，或 /model 换更快模型，或 /retry。'
        ) from exc
    except Exception as exc:
        msg = str(exc)
        if 'timed out' in msg.lower() or 'timeout' in msg.lower():
            raise RuntimeError(
                f'Error: The read operation timed out（HTTP {timeout}s）。'
                f'可设 REVIEWAGENT_AI_TIMEOUT=300 后重试，或 /model 换更快模型，或 /retry。'
            ) from exc
        raise RuntimeError(f'Error: {exc}') from exc


class AIProvider(ABC):
    """AI 服务提供商基类"""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def chat(self, messages: List[Dict], **kwargs) -> str:
        """发送对话请求"""
        pass

    @abstractmethod
    def get_api_url(self) -> str:
        """获取 API 端点"""
        pass


class DeepSeekProvider(AIProvider):
    """DeepSeek AI"""

    def get_api_url(self) -> str:
        return "https://api.deepseek.com/v1/chat/completions"

    def chat(self, messages: List[Dict], temperature: float = 0.7,
             max_tokens: int = 2000, timeout: Optional[int] = None, **_kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            result = _post_json(self.get_api_url(), headers, data, timeout=timeout)
            return _extract_content(result, self.model)
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class OpenAIProvider(AIProvider):
    """OpenAI / Azure OpenAI / OpenAI-compatible gateways"""

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, model)
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip('/')

    def get_api_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def chat(self, messages: List[Dict], temperature: float = 0.7,
             max_tokens: int = 2000, timeout: Optional[int] = None, **_kwargs) -> str:
        # Vision-only model IDs often 400 on text chat
        if any(x in (self.model or '').lower() for x in ('-vl', 'vl-', 'vision')):
            return (
                f'Error: 模型 `{self.model}` 像是视觉/多模态模型，纯文本对话常会 HTTP 400。'
                f'请改用文本模型（MiniMax 可用 MiniMax-Text-01 / MiniMax-M1）：'
                f'`reviewagent model --name MiniMax-Text-01`'
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            result = _post_json(self.get_api_url(), headers, data, timeout=timeout)
            return _extract_content(result, self.model)
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class ClaudeProvider(AIProvider):
    """Anthropic Claude"""

    def get_api_url(self) -> str:
        return "https://api.anthropic.com/v1/messages"

    def chat(self, messages: List[Dict], temperature: float = 0.7,
             max_tokens: int = 2000, timeout: Optional[int] = None, **_kwargs) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        # Claude 需要分离 system 和 messages
        system = ""
        claude_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system = msg['content']
            else:
                claude_messages.append(msg)

        data = {
            "model": self.model,
            "messages": claude_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if system:
            data["system"] = system

        try:
            result = _post_json(self.get_api_url(), headers, data, timeout=timeout)
            return result['content'][0]['text']
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class GLMProvider(AIProvider):
    """智谱 GLM"""

    def get_api_url(self) -> str:
        return "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def chat(self, messages: List[Dict], temperature: float = 0.7,
             max_tokens: int = 2000, timeout: Optional[int] = None, **_kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            result = _post_json(self.get_api_url(), headers, data, timeout=timeout)
            return _extract_content(result, self.model)
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class AIClient:
    """统一的 AI 客户端"""

    PROVIDERS = {
        'deepseek': DeepSeekProvider,
        'openai': OpenAIProvider,
        'claude': ClaudeProvider,
        'glm': GLMProvider
    }

    def __init__(self, provider: str, api_key: str, model: str, **kwargs):
        """
        初始化 AI 客户端

        Args:
            provider: 'deepseek', 'openai', 'claude', 'glm'
            api_key: API 密钥
            model: 模型名称
            **kwargs: 额外参数（如 OpenAI 的 base_url）
        """
        # Unknown labels (gemini/xai/minimax/qwen/doubao/…) → OpenAI-compatible HTTP
        if provider not in self.PROVIDERS:
            if kwargs.get('base_url'):
                provider = 'openai'
            else:
                raise ValueError(
                    f"Unsupported provider: {provider}. "
                    "Use openai + base_url, or deepseek/claude/glm."
                )

        provider_class = self.PROVIDERS[provider]
        self.provider_name = provider
        self.model_name = model
        if provider == 'openai':
            base_url = kwargs.get('base_url') or 'https://api.openai.com/v1'
            self.provider = provider_class(api_key, model, base_url=base_url)
        else:
            self.provider = provider_class(api_key, model)
        # 最近一次回复的终止原因：'length' 表示被 max_tokens 截断
        self.last_finish_reason: Optional[str] = None
        self.last_reasoning_tokens: int = 0

    def _sync_finish_state(self) -> None:
        self.last_finish_reason = _LAST_FINISH.get('reason')  # type: ignore[assignment]
        self.last_reasoning_tokens = int(_LAST_FINISH.get('reasoning_tokens') or 0)

    def truncation_hint(self) -> str:
        """回复被截断时给一句可操作的建议；没截断返回空串。"""
        if self.last_finish_reason != 'length':
            return ''
        if self.last_reasoning_tokens:
            return (f'（回复被 max_tokens 截断，其中 {self.last_reasoning_tokens} tokens '
                    f'被推理过程用掉。请调大 max_tokens，或换非推理模型。）')
        return '（回复被 max_tokens 截断，请调大 max_tokens。）'

    def chat(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """
        发送对话请求

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            **kwargs: temperature, max_tokens 等

        Returns:
            AI 响应文本
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        reply = self.provider.chat(messages, **kwargs)
        self._sync_finish_state()
        return reply

    def chat_with_history(self, messages: List[Dict], **kwargs) -> str:
        """
        带历史记录的对话

        Args:
            messages: 消息历史 [{"role": "user/assistant", "content": "..."}]
            **kwargs: temperature, max_tokens 等

        Returns:
            AI 响应文本
        """
        reply = self.provider.chat(messages, **kwargs)
        self._sync_finish_state()
        return reply


# ============================================================================
# 配置加载
# ============================================================================

def load_config_from_env() -> Dict:
    """从环境变量加载配置（兼容 cc-switch / OpenAI / Anthropic 注入）。

    识别顺序（后者不覆盖已有非空值，由 merge 控制）：
    - AI_PROVIDER / AI_API_KEY / AI_MODEL / AI_BASE_URL
    - OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL  → provider=openai
    - ANTHROPIC_API_KEY / ANTHROPIC_MODEL → provider=claude
    """
    config: Dict = {
        'provider': os.getenv('AI_PROVIDER', '').strip(),
        'api_key': os.getenv('AI_API_KEY', '').strip(),
        'model': os.getenv('AI_MODEL', '').strip(),
        'base_url': os.getenv('AI_BASE_URL', '').strip(),
    }

    openai_key = os.getenv('OPENAI_API_KEY', '').strip()
    if openai_key:
        if not config['api_key']:
            config['api_key'] = openai_key
        if not config['provider']:
            config['provider'] = 'openai'
        if not config['base_url']:
            config['base_url'] = (
                os.getenv('OPENAI_BASE_URL', '').strip() or 'https://api.openai.com/v1'
            )
        if not config['model']:
            config['model'] = os.getenv('OPENAI_MODEL', '').strip() or 'gpt-4o'

    anthropic_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    if anthropic_key and not config.get('api_key'):
        config['api_key'] = anthropic_key
        if not config['provider']:
            config['provider'] = 'claude'
        if not config['model']:
            config['model'] = (
                os.getenv('ANTHROPIC_MODEL', '').strip() or 'claude-3-5-sonnet-20241022'
            )

    if config.get('api_key') and not config.get('provider'):
        config['provider'] = 'openai' if config.get('base_url') else 'deepseek'
    if config.get('api_key') and not config.get('model'):
        config['model'] = 'deepseek-chat' if config['provider'] == 'deepseek' else 'gpt-4o'
    return {k: v for k, v in config.items() if v}


def load_config_from_file(config_file: str = 'config/ai_config.json') -> Dict:
    """从配置文件加载"""
    if not os.path.exists(config_file):
        return {}

    with open(config_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Ignore template placeholder keys that are not credentials
    if data.get('api_key') in ('', 'YOUR_API_KEY_HERE'):
        data = {**data, 'api_key': ''}
    return data


def merge_config(file_cfg: Dict, env_cfg: Dict) -> Dict:
    """环境变量优先（便于 cc-switch 热切换），文件补齐缺省。"""
    merged = dict(file_cfg or {})
    for key, value in (env_cfg or {}).items():
        if value:
            merged[key] = value
    return merged


def get_ai_client(config_file: Optional[str] = None, overrides: Optional[Dict] = None) -> AIClient:
    """
    获取配置好的 AI 客户端

    优先级: 环境变量（含 OPENAI_* / ANTHROPIC_* / AI_*）> 配置文件
    配置文件默认解析顺序见 scripts.agent_home.resolve_config_file
    """
    from scripts.agent_home import resolve_config_file

    path = resolve_config_file(config_file)
    file_cfg = load_config_from_file(path)
    env_cfg = load_config_from_env()
    config = merge_config(file_cfg, env_cfg)
    # Explicit in-chat switches override inherited environment values for this session.
    config.update(overrides or {})

    if not config.get('api_key'):
        raise ValueError(
            "API key not configured. Set OPENAI_API_KEY / AI_API_KEY, "
            "or run `reviewagent config`, or create ~/.reviewagent/ai_config.json."
        )

    provider = (config.get('provider') or 'openai').strip().lower()
    model = config.get('model') or 'gpt-4o'
    kwargs = {}
    if config.get('base_url'):
        kwargs['base_url'] = config['base_url']
    # OpenAI-compatible custom gateways often still use provider=openai
    if provider not in AIClient.PROVIDERS and config.get('base_url'):
        provider = 'openai'

    return AIClient(
        provider=provider,
        api_key=config['api_key'],
        model=model,
        **kwargs
    )


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == '__main__':
    # 方式 1: 直接创建客户端
    client = AIClient(
        provider='deepseek',
        api_key='your-api-key-here',
        model='deepseek-chat'
    )

    # 方式 2: 从环境变量/配置文件加载
    # client = get_ai_client('config/ai_config.json')

    # 简单对话
    response = client.chat(
        prompt="解释一下什么是昇腾 NPU",
        system_prompt="你是一个 AI 硬件专家"
    )
    print(response)

    # 带历史的对话
    messages = [
        {"role": "system", "content": "你是代码审查专家"},
        {"role": "user", "content": "这段代码有什么问题？"},
        {"role": "assistant", "content": "让我分析一下..."},
        {"role": "user", "content": "如何改进？"}
    ]
    response = client.chat_with_history(messages)
    print(response)
