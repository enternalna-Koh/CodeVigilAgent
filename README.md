# CodeVigil Agent - 智能代码审查助手

专为昇腾 NPU / AI Infra 打造的智能体（Hermes 风格 CLI + Cursor Subagent）。

仓库：[`enternalna-Koh/ReviewAgent`](https://github.com/enternalna-Koh/ReviewAgent)。

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### Cursor 智能体

| Agent | 场景 |
|-------|------|
| [cann-op-checker](.cursor/agents/cann-op-checker.md) | AscendC 社区任务算子检查 / design.md / IT 五件套 |
| [cann-inference-advisor](.cursor/agents/cann-inference-advisor.md) | 模型迁移、推理优化、服务部署、vLLM-Ascend、API 一致性 |
| [opengauss-community-advisor](.cursor/agents/opengauss-community-advisor.md) | openGauss Plugin / docs / 师生审核与 CI |

路由说明见 [CodeVigil AGENTS.md](CodeVigil AGENTS.md)。Skills 在 `.cursor/skills/`（镜像 `.agents/skills/`）。对话内 `/skill`、内置昇腾文档 MCP `/mcp`；社区采集 `reviewagent collect --community opengauss`。

### Skills、MCP 与社区采集的使用边界

对话中可用 `/review opengauss`、`/fix opengauss` 明确选择 openGauss 场景；一次性审查使用 `reviewagent review --scenario opengauss`。

`/skill load <name>` 只接受完整材料，已加载技能的组合正文上限为 16,000 字符、32 KiB UTF-8；超限会保留原有技能并提示失败。恢复会话时只提示原技能名，需要重新加载。安装器当前仅下载 `SKILL.md` 和小于等于 200 KB 的 Markdown references；遗漏材料会显示为不完整。references 保存在本地，`/skill load` 当前只把 `SKILL.md` 正文加入会话。

`/mcp tools <server>` 启动配置的本地 MCP 进程并读取工具。自动调查只执行服务端声明 `readOnlyHint: true` 且未声明破坏性的工具；该声明由服务端提供，配置自定义服务时仍需确认来源。`/mcp call <server> <tool> {}` 可显式调用其他工具，参数须为 JSON 对象。退出对话、重载或超时会清理连接。内置服务仍需实际安装包及对应 Node 环境，本仓离线回归使用本地假服务端。

GitCode 在线上下文、技能安装和社区采集只读取 `GITCODE_TOKEN`，不会借用 `GITHUB_TOKEN`。采集失败会返回非零退出码，保留失败资源的旧数据；成功资源仍可更新。新采集文件名包含社区、owner 和仓库名，原有旧命名文件保留。

---

## 🚀 30 秒快速开始（Hermes 风格）

```bash
npm install -g reviewagent   # 或在本仓: npm install && npm link

reviewagent                  # 唤醒 Agent（对话）
reviewagent review           # 审查当前 git diff
reviewagent doctor           # 环境自检
reviewagent config --init    # 写入 ~/.reviewagent/ai_config.json
```

模型可用 **cc-switch** 注入的 `OPENAI_*` / `ANTHROPIC_*`（环境变量优先）。详见 [docs/CC_SWITCH.md](docs/CC_SWITCH.md)、[docs/INSTALL_HERMES_STYLE.md](docs/INSTALL_HERMES_STYLE.md)。

短命令：`ra` · 旧命令：`review`。

### 仓库级 Agent CLI

当前工作区的审查入口是 `ascend_cli.py`。它会读取 Git 分支、状态和已跟踪文件的 diff，再交给审查器分析。未跟踪文件不在审查范围内：

```bash
# 审查工作区变更
python ascend_cli.py review

# 只审查暂存区
python ascend_cli.py review --staged

# 输出机器可读 JSON
python ascend_cli.py review --json --output report.json
```

Windows 下也可以直接运行：

```bat
ascend.bat review
```

### 本地昇腾案例检索

```powershell
# 无需 API Key，搜索采集的 Issue/PR 原文
python ascend_cli.py search "507049 HCCL"
python ascend_cli.py search "显存分配" --kind issue --limit 3 --json

# 本地规则审查 + 历史案例检索，不调用外部 AI
python ascend_cli.py review --offline --json
```

审查报告的 `knowledge_retrieval` 字段包含相关案例、原文摘录、来源文件和链接。
配置 AI 时，这些案例也会进入模型上下文。知识库默认从工具所在目录的
`data/raw` 读取，因此可以在其他 Git 仓库中使用此 CLI。

当前采用本地关键词 BM25 排序，支持错误码、API 名称和中文词片段；无需向量数据库。
历史记录仅作为参考：Issue 关闭或 PR 合并均不等于解决方案已验证，检索匹配也不证明
当前代码存在问题。缺失数据、无效 JSON 和 API 错误响应会产生知识库提示。

离线回归检查：`python -m unittest discover -s tests -v`。

### 自然语言 PR/Issue 对话

默认启用 `auto` 自动联网调查：模型根据问题和证据决定是否搜索，最多执行三次只读调查。
可调用网页搜索、本地案例检索、关联 GitHub PR/Issue 获取；所有入口共用同一对话核心和搜索后端。

```powershell
review chat --network auto --multiline
# 或
python ascend_cli.py chat --network auto --multiline
```

对话中 `/network auto` 按需查证，`/network on` 每轮先搜索，`/network off` 关闭外部资料获取
（仍调用配置的 AI 服务，不代表完全离线）。`/sources` 查看最近调查的工具结果和来源。
网页结果目前是 DuckDuckGo 搜索摘要，不是网页全文；搜索服务限流或验证页会被标记为失败。

正式全局入口 `review` 与 `python ascend_cli.py` 使用相同运行时。
旧 `chat.py` / `chat_v2.py` 保留供对比；协同修改前请阅读
[开发交接](docs/DEVELOPMENT_HANDOFF.md)，避免把功能加到未被正式入口使用的版本中。

启动连续对话：

```powershell
python ascend_cli.py chat
```

输入多行描述或代码时，先输入 `/paste`，再粘贴内容（保留空行和缩进），
最后单独输入 `/send` 发送；`/cancel` 或 Ctrl+C 取消本次输入。
也可以运行 `python ascend_cli.py chat --multiline`，让每条消息都使用多行模式。

然后直接输入：

```text
请分析 https://github.com/Ascend/pytorch/issues/166，重点看 507049 的根因
```

Agent 会依次获取正文、评论、PR 文件补丁和人工 Review（GitHub 链接），检索本地昇腾案例，
再生成带证据范围的分析。之后可以继续问：

```text
这个判断的证据是什么？
应该怎么修改？
还缺哪些环境信息？
```

上下文会保留在当前会话中；`/clear` 清除上下文，`/exit` 退出。也可以单次执行：

```powershell
python ascend_cli.py chat -m "帮我分析 https://github.com/Ascend/pytorch/pull/123"
```

在线获取器支持 GitHub、GitCode 的 PR/Issue URL；认证分别使用 `GITHUB_TOKEN`、`GITCODE_TOKEN`，网络或权限失败会明确报告原因。Gitee 等其他来源可以直接粘贴正文，避免把网页不完整内容误判为已审查。

这条入口是后续 Agent 能力的基础：文件搜索、测试执行、Issue/PR 检索和自动修复都可以沿着同一套仓库上下文继续接入。

**就这么简单！** ✨

---

## ✨ 核心特性

### 🧠 自动识别任务类型
- PR Review - 代码审查
- Issue Diagnosis - 问题诊断  
- Code Audit - 代码审计

**无需手动指定**，智能体自动理解！

### 📐 自动匹配审查标准
- NPU 特定标准（算子、内存、精度）
- 性能标准（算法、内存分配）
- 安全标准（注入、权限）
- 通用代码规范

### 🎯 主动找问题
- 不只是说"看起来不错"
- 识别潜在问题
- 评估严重程度（critical/high/medium/low）
- 提供具体建议

### 🔌 支持多种 AI
- DeepSeek（默认，性价比最高）
- OpenAI（GPT-4, GPT-3.5）
- Claude（Anthropic）
- GLM（智谱）

---

## 📖 使用方式

### CLI 命令行（推荐）

```bash
# 审查文件
python review_cli.py code.py

# 审查文本
python review_cli.py --text "def foo(): pass"

# 保存报告
python review_cli.py code.py --output report.json

# 运行测试
python review_cli.py test

# 配置管理
python review_cli.py config --show
```

详细文档：[CLI 使用指南](docs/CLI_GUIDE.md)

### Python API

```python
from scripts.smart_reviewer import SmartReviewer

reviewer = SmartReviewer()
report = reviewer.review("你的代码...")
reviewer.print_report(report)
```

---

## 📊 项目数据

基于业界最完整的昇腾 AI 数据库：

| 指标 | 数量 |
|------|------|
| 仓库 | 18 个 |
| Issues | 733 个 |
| PRs | 745 个 |
| Reviews | 78 条 |
| CI Workflows | 175 个 |
| 总数据 | 25 MB |

双框架覆盖：
- PyTorch 生态（pytorch, vllm-ascend, sglang）
- MindSpore 生态（mindspore, models, hub）

---

## 🎯 使用场景

### 场景 1: 提交前自查
```bash
python review_cli.py my_changes.py
```

### 场景 2: PR Review
```bash
# 复制 PR 内容到文件
python review_cli.py pr_content.txt
```

### 场景 3: Issue 诊断
```bash
# 粘贴 Issue 内容
python review_cli.py --text "Error: ..."
```

### 场景 4: 批量审查
```bash
# PowerShell
Get-ChildItem *.py | ForEach-Object {
    python review_cli.py $_.Name
}
```

---

## 📁 项目结构

```
ReviewAgent/
├── review_cli.py              # CLI 入口
├── ascend_cli.py              # 仓库级昇腾 Agent CLI
├── review.bat                 # Windows 快捷方式
├── scripts/
│   ├── smart_reviewer.py      # 核心：智能审查器
│   ├── ai_adapter.py          # AI 适配器
│   ├── repo_context.py         # Git 仓库上下文采集
│   └── agent_tools.py          # 测试/命令工具
│   └── ai_code_review.py      # AI 审查工具
├── config/
│   └── ai_config.json         # AI 配置
├── data/                      # 数据资产（25 MB）
└── docs/                      # 完整文档
```

---

## 🔧 配置

### 初始化配置

```bash
python review_cli.py config --init
```

### 编辑配置

编辑 `config/ai_config.json`:

```json
{
  "provider": "deepseek",
  "api_key": "你的API密钥",
  "model": "deepseek-chat"
}
```

### 切换 AI

```bash
# 使用 OpenAI
python review_cli.py config --set provider=openai
python review_cli.py config --set model=gpt-4

# 使用 Claude
python review_cli.py config --set provider=claude
python review_cli.py config --set model=claude-3-opus-20240229
```

---

## 📚 文档

- [CLI 使用指南](docs/CLI_GUIDE.md) - 命令行详细教程
- [AI 架构文档](docs/AI_ARCHITECTURE.md) - 技术架构
- [完整总结](FINAL_SUMMARY.md) - 项目全貌
- [手动执行指南](MANUAL_EXECUTION_GUIDE.md) - 故障排除

---

## 🎓 工作原理

```
输入（代码/PR/Issue）
    ↓
[自动识别] 任务类型和子类型
    ↓
[自动匹配] 对应的审查标准
    ↓
[AI 分析] 深度代码分析
    ↓
[生成报告] 结构化输出
```

---

## 🔍 审查报告示例

```
[TYPE] 任务类型: pr_review
   子类型: npu, performance

[ISSUES] 发现问题: 3 个

[!!] HIGH 级别问题 (1 个):
  [1] NPU API 使用错误
      问题: 使用了 .cuda() 而不是 .npu()
      建议: 替换为 .npu()
      重要性: 会导致代码在 NPU 上无法运行

[!] MEDIUM 级别问题 (2 个):
  [2] 性能问题 - 可以向量化
  [3] 缺少错误处理

[RESULT] 审查结论: REQUEST_CHANGES
```

---

## 🤝 贡献

欢迎贡献！

- 报告 Bug
- 提交 PR
- 添加新的审查规则
- 支持新的 AI Provider

---

## 📝 许可

本项目代码采用 [MIT License](LICENSE)。第三方依赖及收集的上游资料遵循各自许可证。

---

## 🙏 致谢

- 基于 18 个开源仓库的真实数据
- 感谢昇腾社区的支持
- 感谢所有贡献者

---

## 🎯 下一步

- [ ] Web UI
- [ ] GitHub Action
- [ ] VS Code 插件
- [ ] 更多 AI 模型

---

## 💬 联系

有问题或建议？欢迎：
- 提 Issue
- 查看文档
- 运行 `python review_cli.py --help`

---

**让 AI 帮你写出更好的代码！** 🚀

---

## 快速链接

- [开始使用](#🚀-30-秒快速开始)
- [CLI 指南](docs/CLI_GUIDE.md)
- [示例代码](#📖-使用方式)
- [配置说明](#🔧-配置)
- [完整文档](docs/)
