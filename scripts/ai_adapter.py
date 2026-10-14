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

        req = urllib.request.Request(
            self.get_api_url(),
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except Exception as e:
            return f"Error: {str(e)}"


class OpenAIProvider(AIProvider):
    """OpenAI / Azure OpenAI"""

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, model)
        self.base_url = base_url

    def get_api_url(self) -> str:
        return f"{self.base_url}/chat/completions"

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

        req = urllib.request.Request(
            self.get_api_url(),
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except Exception as e:
            return f"Error: {str(e)}"


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
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['content'][0]['text']
        except Exception as e:
            return f"Error: {str(e)}"


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

        req = urllib.request.Request(
            self.get_api_url(),
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except Exception as e:
            return f"Error: {str(e)}"


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
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")

        provider_class = self.PROVIDERS[provider]
        self.provider = provider_class(api_key, model, **kwargs)

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
    """从环境变量加载配置"""
    return {
        'provider': os.getenv('AI_PROVIDER', 'deepseek'),
        'api_key': os.getenv('AI_API_KEY', ''),
        'model': os.getenv('AI_MODEL', 'deepseek-chat'),
        'base_url': os.getenv('AI_BASE_URL', '')  # For OpenAI-compatible APIs
    }


def load_config_from_file(config_file: str = 'config/ai_config.json') -> Dict:
    """从配置文件加载"""
    if not os.path.exists(config_file):
        return {}

    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_ai_client(config_file: Optional[str] = None) -> AIClient:
    """
    获取配置好的 AI 客户端

    优先级: 配置文件 > 环境变量
    """
    # 先尝试从配置文件加载
    config = {}
    if config_file:
        config = load_config_from_file(config_file)

    # 如果没有配置文件，从环境变量加载
    if not config:
        config = load_config_from_env()

    if not config.get('api_key'):
        raise ValueError("API key not configured. Set AI_API_KEY env var or create config file.")

    # 提取 base_url (for OpenAI-compatible)
    kwargs = {}
    if config.get('base_url'):
        kwargs['base_url'] = config['base_url']

    return AIClient(
        provider=config['provider'],
        api_key=config['api_key'],
        model=config['model'],
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
