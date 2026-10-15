"""
通用 AI API 适配器
支持多种 AI 服务：DeepSeek, OpenAI, Claude, GLM, 等
"""
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import urllib.request
import urllib.parse


def _format_http_error(exc) -> str:
    """Surface provider error body (400 reason) instead of bare HTTP Error 400."""
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        body = ''
        try:
            raw = exc.read()
            body = raw.decode('utf-8', errors='replace')[:800] if raw else ''
        except Exception:
            body = ''
        hint = ''
        lower = (body + str(exc.reason)).lower()
        model_hint = ''
        if 'vl' in lower or 'vision' in lower or 'image' in lower:
            model_hint = '（当前模型可能是视觉/多模态，对话请改用文本模型，如 MiniMax-Text-01 / MiniMax-M1）'
        if exc.code == 400:
            hint = model_hint or '（常见原因：模型 ID 不支持 chat、参数不兼容、或 base_url 不对）'
        detail = f' — {body}' if body else ''
        return f'Error: HTTP {exc.code} {exc.reason}{detail}{hint}'
    return f'Error: {exc}'


def _post_json(url: str, headers: Dict, data: Dict, timeout: int = 60) -> Dict:
    import urllib.error
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
    except Exception as exc:
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

    def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 2000) -> str:
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
            result = _post_json(self.get_api_url(), headers, data)
            return result['choices'][0]['message']['content']
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class OpenAIProvider(AIProvider):
    """OpenAI / Azure OpenAI / OpenAI-compatible gateways"""

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, model)
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip('/')

    def get_api_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 2000) -> str:
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
            result = _post_json(self.get_api_url(), headers, data)
            return result['choices'][0]['message']['content']
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class ClaudeProvider(AIProvider):
    """Anthropic Claude"""

    def get_api_url(self) -> str:
        return "https://api.anthropic.com/v1/messages"

    def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 2000) -> str:
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

        req = urllib.request.Request(
            self.get_api_url(),
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        try:
            result = _post_json(self.get_api_url(), headers, data)
            return result['content'][0]['text']
        except Exception as e:
            return str(e) if str(e).startswith('Error:') else f'Error: {e}'


class GLMProvider(AIProvider):
    """智谱 GLM"""

    def get_api_url(self) -> str:
        return "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 2000) -> str:
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
            result = _post_json(self.get_api_url(), headers, data)
            return result['choices'][0]['message']['content']
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

        return self.provider.chat(messages, **kwargs)

    def chat_with_history(self, messages: List[Dict], **kwargs) -> str:
        """
        带历史记录的对话

        Args:
            messages: 消息历史 [{"role": "user/assistant", "content": "..."}]
            **kwargs: temperature, max_tokens 等

        Returns:
            AI 响应文本
        """
        return self.provider.chat(messages, **kwargs)


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


def get_ai_client(config_file: Optional[str] = None) -> AIClient:
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
