# ReviewAgent

[![npm version](https://img.shields.io/npm/v/@reviewagent/cli.svg)](https://www.npmjs.com/package/@reviewagent/cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

智能代码审查助手 - 专为昇腾 NPU 生态打造

---

## 🚀 一键安装

### 全局安装（推荐）

```bash
npm install -g @reviewagent/cli
```

或使用 yarn:

```bash
yarn global add @reviewagent/cli
```

### 本地安装

```bash
npm install @reviewagent/cli
npx review
```

---

## ✨ 使用方式

安装后，在任何地方使用 `review` 命令：

### 进入对话模式

```bash
review
```

显示 Logo 和欢迎信息，进入交互式对话：

```
    ____            _                ___                    __
   / __ \___ _   __(_)__ _      __  /   | ____ ____  ____  / /_
  / /_/ / _ \ | / / / _ \ | /| / / / /| |/ __ `/ _ \/ __ \/ __/
 / _, _/  __/ |/ / /  __/ |/ |/ / / ___ / /_/ /  __/ / / / /_
/_/ |_|\___/|___/_/\___/|__/|__/ /_/  |_\__, /\___/_/ /_/\__/
                                        /____/

智能代码审查助手 - 专为昇腾 NPU 打造
======================================================================

启动对话模式...

You>
```

### 快速审查文件

```bash
review code.py
```

### 配置 AI

```bash
review --config
```

### 查看帮助

```bash
review --help
```

---

## 📖 功能特性

### 🧠 智能对话
- 自然语言交互
- 自动识别意图
- 上下文记忆
- 专业领域知识

### 📐 代码审查
- 自动识别任务类型
- 智能匹配审查标准
- NPU 特定检查
- 详细问题报告

### 🎯 昇腾专家
- 基于 733 issues + 745 PRs 的实战经验
- PyTorch + MindSpore 双框架支持
- NPU 性能优化建议
- 常见问题诊断

### 🔌 多 AI 支持
- DeepSeek（推荐）
- OpenAI (GPT-4, GPT-3.5)
- Claude (Anthropic)
- GLM (智谱)

---

## 🎯 使用场景

### 场景 1: 日常开发

```bash
review

You> 审查这段代码:
def allocate(size):
    return torch.zeros(size).cuda()

ReviewAgent: [分析]
发现问题: NPU API 使用错误
应该使用 .npu() 而不是 .cuda()
```

### 场景 2: PR Review

```bash
You> https://github.com/user/repo/pull/123

ReviewAgent: [自动获取并分析]
```

### 场景 3: 技术咨询

```bash
You> 昇腾 NPU 怎么优化性能？

ReviewAgent: [详细建议和代码示例]
```

---

## 📋 依赖要求

- **Node.js** >= 14.0.0
- **Python** >= 3.7
- **npm** >= 6.0.0

安装会自动检查依赖。

---

## 🔧 配置

首次运行会自动进入配置向导：

```bash
review

? 请选择 AI 服务:
  1. DeepSeek (推荐)
  2. OpenAI
  3. Claude
  4. GLM

? 请输入 API Key: sk-xxxxx

✓ 配置完成！
```

配置保存在 `~/.reviewagent/config.json`

---

## 📊 命令完整列表

```bash
review                    进入对话模式（默认）
review <file>             快速审查文件
review --config           配置向导
review --stats            显示统计
review --version          显示版本
review --help             显示帮助
```

### 对话模式内命令

```
/help     显示帮助
/clear    清除历史
/config   重新配置
/stats    显示统计
/exit     退出
```

---

## 🌍 支持平台

- ✓ Windows
- ✓ macOS
- ✓ Linux

---

## 🤝 贡献

欢迎贡献！

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

---

## 📝 许可

MIT License

---

## 🙏 致谢

- 基于 18 个开源仓库的真实数据
- 733 issues + 745 PRs
- 昇腾社区的支持

---

## 📮 联系

- Issues: https://github.com/your-username/ReviewAgent/issues
- Email: support@reviewagent.dev

---

## 🎉 快速开始

```bash
# 1. 安装
npm install -g @reviewagent/cli

# 2. 运行
review

# 3. 开始使用！
```

**就这么简单！** 🚀

---

## 📈 更新日志

### v1.0.0 (2024-10-14)

- 🎉 首次发布
- ✨ 对话式交互
- 🧠 智能意图识别
- 📐 代码审查
- 🎯 昇腾 NPU 专家知识
- 🔌 多 AI 支持

---

**让 AI 帮你写出更好的代码！** 🎊
