# 与 cc-switch / Claude Code 式模型切换配合

ReviewAgent 走 **OpenAI / Anthropic 环境变量优先** 的配置模型，因此可以像 Hermes / Claude Code 一样被 [cc-switch](https://github.com/SaladDay/cc-switch-cli) 或任意 provider 切换工具注入。

## 推荐用法

### 1. 安装并唤醒

```bash
npm install -g reviewagent
reviewagent doctor
reviewagent config --init
reviewagent                 # 唤醒 AI Infra Agent（对话）
```

短命令：`ra`、`review`（兼容旧名）。

### 2. 用环境变量切模型（cc-switch 友好）

ReviewAgent 读取（**环境变量覆盖** `~/.reviewagent/ai_config.json`）：

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | OpenAI 兼容密钥 |
| `OPENAI_BASE_URL` | 网关，如中转 / 本地代理 |
| `OPENAI_MODEL` | 模型名 |
| `ANTHROPIC_API_KEY` | Claude |
| `ANTHROPIC_MODEL` | Claude 模型 |
| `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` / `AI_BASE_URL` | 通用覆盖 |
| `REVIEWAGENT_HOME` | 配置目录（默认 `~/.reviewagent`） |
| `REVIEWAGENT_CONFIG` | 指定配置文件路径 |

示例（PowerShell）：

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_BASE_URL = "https://your-gateway/v1"
$env:OPENAI_MODEL = "gpt-4o"
reviewagent
```

### 3. 与 cc-switch 协作

cc-switch 目前内置 app：`claude` / `codex` / `gemini` / `hermes` / …  
对 ReviewAgent：

1. 在 cc-switch 里选好 OpenAI 兼容 provider（或 Claude）。
2. 用「启动时注入环境变量」的方式打开终端，再运行 `reviewagent`；  
   或把同一组 `OPENAI_*` 导出到当前 shell。
3. 若 cc-switch 后续增加 `--app reviewagent`，可把配置目标指到：

```text
%USERPROFILE%\.reviewagent\ai_config.json
# macOS/Linux: ~/.reviewagent/ai_config.json
```

字段：

```json
{
  "provider": "openai",
  "api_key": "sk-...",
  "model": "gpt-4o",
  "base_url": "https://api.openai.com/v1"
}
```

也可用内置命令写入：

```bash
reviewagent model --provider openai --name gpt-4o --base-url https://your-gateway/v1
reviewagent config --set api_key=sk-xxx
```

### 4. 与 Hermes / Claude Code 的对照

| 能力 | Hermes | ReviewAgent |
|------|--------|-------------|
| 全局安装 | `npm i -g hermes-agent` | `npm i -g reviewagent` |
| 唤醒 | `hermes` | `reviewagent` / `ra` |
| 配置家目录 | `$HERMES_HOME` | `$REVIEWAGENT_HOME` |
| 模型切换 | cc-switch `--app hermes` | `OPENAI_*` / `reviewagent model` |
| 领域 | 通用 Agent | **昇腾 AI Infra**（算子 / 推理 / CANN） |

## 专业场景

```bash
reviewagent review --scenario operator   # AscendC / 社区任务
reviewagent review --scenario inference  # torch-npu / vLLM / 部署
reviewagent search "507049 HCCL"         # 本地案例库
```
