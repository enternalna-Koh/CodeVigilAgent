# Hermes 风格安装与唤醒

把 ReviewAgent 用成和 `hermes` / Claude Code 一样的「装完敲命令就进 Agent」体验，但默认能力偏向 **昇腾 AI Infra**。

## 安装

```bash
# 发布后
npm install -g reviewagent

# 或本地开发
cd ReviewAgent
npm install
npm link
```

## 唤醒

```bash
reviewagent              # 进入 AI Infra 对话（默认 chat）
ra                       # 短命令
review                   # 旧别名，仍可用
```

**首次启动（类似 Claude Code）**：若本机没有可用 API Key（文件或 `OPENAI_API_KEY` / `AI_API_KEY` 等），会自动弹出彩色引导：选 Provider → 从列表选模型 → 隐藏输入 API Key → 写入 `~/.reviewagent/ai_config.json` 后进入对话。也可随时 `reviewagent config --wizard` 重配。

**Buddy 宠物（对齐 CC `/buddy`）**：启动时会破壳/展示 ASCII 精灵（稀有度、帽子、眼睛、属性条、气泡、抚摸飘心）。随时 `reviewagent buddy`；换种子设 `REVIEWAGENT_BUDDY_SEED`；跳过动画 `REVIEWAGENT_NO_PET=1`。

常用子命令：

```bash
reviewagent review                 # 审查当前 git diff
reviewagent review --scenario operator
reviewagent search "HCCL 507049"
reviewagent config --wizard        # 重新配置 API（Node TUI）
reviewagent config --init
reviewagent doctor
reviewagent model --provider openai --name gpt-4o
reviewagent --help
```

## 配置位置

- 用户配置：`~/.reviewagent/ai_config.json`（可用 `REVIEWAGENT_HOME` 改目录）
- 模型热切换：环境变量优先（见 [CC_SWITCH.md](CC_SWITCH.md)）
- CLI UI：`bin/ui.js`（Logo / 动画）+ `bin/onboard.js`（首次引导）

## 卸载

```bash
npm uninstall -g reviewagent
# 可选：删除 ~/.reviewagent
```
