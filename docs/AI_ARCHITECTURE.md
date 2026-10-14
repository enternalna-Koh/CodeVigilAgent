# 通用 AI 集成架构

完成时间: 2026-10-14

---

## 🎯 设计目标

创建一个**与 AI 服务解耦**的架构，支持：
- ✅ 多种 AI 服务（DeepSeek, OpenAI, Claude, GLM, 等）
- ✅ 统一的调用接口
- ✅ 灵活的配置管理
- ✅ 易于扩展新的 AI 服务

---

## 🏗️ 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────┐
│           ReviewAgent 应用层                      │
│  (代码审查、Issue 分析、训练数据生成)               │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│            AIClient (统一接口)                    │
│    - chat(prompt)                                │
│    - chat_with_history(messages)                 │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│           Provider 抽象层                         │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │DeepSeek  │  │ OpenAI   │  │ Claude   │      │
│  │Provider  │  │ Provider │  │ Provider │      │
│  └──────────┘  └──────────┘  └──────────┘      │
│                                                   │
│  ┌──────────┐  ┌──────────┐                     │
│  │   GLM    │  │  Custom  │                     │
│  │ Provider │  │ Provider │                     │
│  └──────────┘  └──────────┘                     │
└─────────────────────────────────────────────────┘
```

### 关键特性

1. **Provider 抽象**
   - 每个 AI 服务一个 Provider 类
   - 实现统一的 `chat()` 接口
   - 处理各自的 API 差异

2. **统一的 AIClient**
   - 应用层只需要调用 `AIClient`
   - 自动路由到正确的 Provider
   - 透明的服务切换

3. **配置驱动**
   - JSON 配置文件或环境变量
   - 不修改代码即可切换 AI 服务

---

## 📦 文件结构

```
ReviewAgent/
├── config/
│   └── ai_config.json.template     # 配置模板
│
├── scripts/
│   ├── ai_adapter.py               # 核心适配器
│   └── ai_code_review.py           # AI 审查应用
│
└── .env (或环境变量)
    AI_PROVIDER=deepseek
    AI_API_KEY=your-key-here
    AI_MODEL=deepseek-chat
```

---

## 🚀 使用方式

### 方式 1: 配置文件

创建 `config/ai_config.json`:

```json
{
  "provider": "deepseek",
  "api_key": "sk-xxx",
  "model": "deepseek-chat"
}
```

代码中使用:

```python
from scripts.ai_adapter import get_ai_client

client = get_ai_client('config/ai_config.json')
response = client.chat("审查这段代码...")
```

### 方式 2: 环境变量

```bash
export AI_PROVIDER=deepseek
export AI_API_KEY=sk-xxx
export AI_MODEL=deepseek-chat
```

代码中使用:

```python
from scripts.ai_adapter import get_ai_client

client = get_ai_client()  # 自动从环境变量加载
response = client.chat("审查这段代码...")
```

### 方式 3: 直接初始化

```python
from scripts.ai_adapter import AIClient

client = AIClient(
    provider='deepseek',
    api_key='sk-xxx',
    model='deepseek-chat'
)
response = client.chat("审查这段代码...")
```

---

## 🔌 支持的 AI 服务

### 1. DeepSeek

```json
{
  "provider": "deepseek",
  "api_key": "sk-xxx",
  "model": "deepseek-chat"
}
```

**模型选择**:
- `deepseek-chat` - 通用对话
- `deepseek-coder` - 代码专用

### 2. OpenAI

```json
{
  "provider": "openai",
  "api_key": "sk-xxx",
  "model": "gpt-4-turbo"
}
```

**模型选择**:
- `gpt-4-turbo` - 最强大
- `gpt-4` - GPT-4
- `gpt-3.5-turbo` - 快速经济

### 3. Claude (Anthropic)

```json
{
  "provider": "claude",
  "api_key": "sk-ant-xxx",
  "model": "claude-3-opus-20240229"
}
```

**模型选择**:
- `claude-3-opus-20240229` - 最强大
- `claude-3-sonnet-20240229` - 平衡
- `claude-3-haiku-20240307` - 快速

### 4. GLM (智谱)

```json
{
  "provider": "glm",
  "api_key": "xxx.xxx",
  "model": "glm-4"
}
```

### 5. 自定义 / OpenAI 兼容 API

任何兼容 OpenAI API 格式的服务：

```json
{
  "provider": "openai",
  "api_key": "xxx",
  "model": "your-model",
  "base_url": "https://your-api-endpoint.com/v1"
}
```

---

## 💡 应用示例

### 1. 代码审查

```python
from scripts.ai_code_review import review_code_with_ai

code = """
def calculate(a, b):
    return a / b
"""

result = review_code_with_ai(code)
print(result)
```

输出:
```json
{
  "issues": [
    {
      "type": "error_handling",
      "severity": "high",
      "description": "除零错误未处理",
      "suggestion": "添加 b != 0 检查"
    }
  ],
  "summary": "代码缺少错误处理"
}
```

### 2. Issue 分析

```python
from scripts.ai_code_review import analyze_issue_with_ai

result = analyze_issue_with_ai(
    issue_title="torch-npu 2.10 compatibility issue",
    issue_body="Error 507049 when running on NPU..."
)
print(result)
```

### 3. 批量分析 Reviews

```bash
python scripts/ai_code_review.py \
    --mode batch \
    --file data/pr_reviews/vllm-project_vllm-ascend_reviews.json \
    --config config/ai_config.json
```

---

## 🔧 扩展新的 AI 服务

### 添加新 Provider

1. 在 `ai_adapter.py` 中创建新类:

```python
class NewAIProvider(AIProvider):
    """Your New AI Service"""
    
    def get_api_url(self) -> str:
        return "https://api.newai.com/v1/chat"
    
    def chat(self, messages: List[Dict], **kwargs) -> str:
        # 实现 API 调用逻辑
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages
        }
        
        # ... HTTP 请求 ...
        
        return response_text
```

2. 注册到 `AIClient.PROVIDERS`:

```python
class AIClient:
    PROVIDERS = {
        'deepseek': DeepSeekProvider,
        'openai': OpenAIProvider,
        'claude': ClaudeProvider,
        'glm': GLMProvider,
        'newai': NewAIProvider  # 添加这行
    }
```

3. 使用:

```json
{
  "provider": "newai",
  "api_key": "your-key",
  "model": "newai-model"
}
```

---

## 🔒 安全注意事项

### 1. API Key 管理

**不要**将 API Key 提交到 Git:

```bash
# .gitignore
config/ai_config.json
.env
```

**推荐**使用环境变量:

```bash
export AI_API_KEY=your-key-here
```

### 2. 配置模板

提供 `ai_config.json.template`，用户复制并填入自己的密钥:

```bash
cp config/ai_config.json.template config/ai_config.json
# 然后编辑 ai_config.json 填入 API Key
```

### 3. 密钥轮换

定期更换 API Key，使用密钥管理服务。

---

## 📊 成本优化

### 选择合适的模型

| 任务 | 推荐模型 | 原因 |
|------|----------|------|
| 代码审查 | DeepSeek-Coder | 专为代码优化，成本低 |
| Issue 分析 | GPT-3.5-Turbo | 快速且经济 |
| 复杂推理 | GPT-4 / Claude Opus | 准确度高 |
| 批量处理 | Claude Haiku | 快速且便宜 |

### 控制 Token 使用

```python
client.chat(
    prompt=prompt[:1000],  # 限制输入长度
    max_tokens=500,         # 限制输出长度
    temperature=0.3         # 更确定的输出
)
```

---

## 🎯 与 ReviewAgent 集成

### 替代 Stage 3 脚本

原来的 `analyze_reviews.py` 使用规则分类，现在可以用 AI:

```python
# 原来: 基于关键词
def classify_review_type(text):
    if 'design' in text.lower():
        return 'design'
    # ...

# 现在: 使用 AI
def classify_review_type(text):
    client = get_ai_client()
    response = client.chat(
        f"将这条 review 分类: {text}",
        system_prompt="分类为: design/quality/performance/test/bug"
    )
    return response.strip()
```

### 增强训练数据生成

使用 AI 生成更丰富的训练样本:

```python
# 基于真实 review，生成变体
original_review = "does self.module only used here?"

client = get_ai_client()
variants = client.chat(
    f"基于这条 review，生成 3 个类似的审查意见: {original_review}",
    system_prompt="保持风格和严重程度一致"
)
```

---

## 📈 性能对比

| Provider | 速度 | 成本 | 代码能力 | 中文支持 |
|----------|------|------|----------|----------|
| DeepSeek | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| GPT-3.5 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| GPT-4 | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Claude 3 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| GLM-4 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**推荐**: DeepSeek (性价比最高，代码能力强)

---

## 🚀 快速开始

```bash
# 1. 配置 AI
cp config/ai_config.json.template config/ai_config.json
# 编辑 ai_config.json，填入你的 API Key

# 2. 测试连接
python scripts/ai_adapter.py

# 3. 代码审查
python scripts/ai_code_review.py --mode review

# 4. 批量分析
python scripts/ai_code_review.py --mode batch
```

---

## 🎊 总结

**通用 AI 架构的优势**:

✅ **灵活切换** - 配置文件即可换 AI 服务  
✅ **成本优化** - 选择最适合的模型  
✅ **易于扩展** - 新增 AI 服务只需实现一个类  
✅ **统一接口** - 应用层代码无需修改  
✅ **独立于 Claude Code** - 不依赖特定环境  

**现在 ReviewAgent 可以使用任何 AI 服务了！** 🎉
