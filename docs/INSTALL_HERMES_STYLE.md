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

常用子命令：

```bash
reviewagent review                 # 审查当前 git diff
reviewagent review --scenario operator
reviewagent search "HCCL 507049"
reviewagent config --init
reviewagent doctor
reviewagent model --provider openai --name gpt-4o
reviewagent --help
```

## 配置位置

- 用户配置：`~/.reviewagent/ai_config.json`（可用 `REVIEWAGENT_HOME` 改目录）
- 模型热切换：环境变量优先（见 [CC_SWITCH.md](CC_SWITCH.md)）

## 卸载

```bash
npm uninstall -g reviewagent
# 可选：删除 ~/.reviewagent
```
