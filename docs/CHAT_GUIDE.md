# ReviewAgent 对话式智能体使用指南

自然语言交互，智能理解需求

---

## 🚀 快速开始

### 启动对话

```bash
reviewagent              # 推荐：Logo + 首次 API 引导 + 对话
# 或
npm install -g reviewagent && reviewagent
```

### 首次使用

直接运行 `reviewagent`。若未配置 API，会像 Claude Code 一样自动进入引导：

1. 选择 Provider（DeepSeek / OpenAI 兼容 / Claude / GLM）
2. **从列表选择模型**（勿手写错误 ID，如误写成 `deepseek v4 flash`）
3. 隐藏输入 API Key（也可改用 cc-switch 注入 `OPENAI_API_KEY`）
4. 保存到 `~/.reviewagent/ai_config.json` 后进入对话

重配：`reviewagent config --wizard`

---

## 💬 对话示例

### 示例 1: 审查代码

```
[YOU] > 帮我审查这段代码:
def allocate_tensor(size):
    tensor = torch.zeros(size).cuda()
    return tensor

[INTENT] 检测到意图: review_code (置信度: 85%)
[ACTION] 执行代码审查...

[REPORT] 智能审查报告
========================================
发现问题: 1 个

[!!] HIGH 级别问题:
  NPU API 使用错误
  - 使用了 .cuda() 而不是 .npu()
  - 建议: 替换为 .npu()
```

### 示例 2: 审查 GitHub PR

```
[YOU] > https://github.com/vllm-project/vllm-ascend/pull/123

[INTENT] 检测到意图: fetch_and_review (置信度: 90%)
[ACTION] 获取并审查 URL 内容...
[FETCH] https://github.com/...
[OK] 内容已获取

[ANALYSIS]
这是一个 Pull Request，主要修改了...

[REPORT] 智能审查报告
...
```

### 示例 3: 技术咨询

```
[YOU] > 昇腾 NPU 和 CUDA 有什么区别？

[INTENT] 检测到意图: chat (置信度: 50%)

[AGENT] 昇腾 NPU 和 CUDA 的主要区别:

1. 硬件架构
   - CUDA: NVIDIA GPU
   - NPU: 华为昇腾处理器

2. API 差异
   - CUDA: torch.cuda.device()
   - NPU: torch.npu.device()

3. 编程模型
   - CUDA: CUDA C++/Python
   - NPU: CANN (异构计算架构)

建议使用 torch_npu 进行迁移...
```

### 示例 4: 自然对话

```
[YOU] > 我的代码在 NPU 上运行很慢，怎么优化？

[AGENT] NPU 性能优化建议:

1. 算子融合
   - 使用 torch_npu.npu_fusion_attention
   - 减少算子调用次数

2. 内存优化
   - 避免频繁的 CPU-NPU 数据传输
   - 使用 pin_memory

3. 并行优化
   - 多卡并行训练
   - 使用 DataParallel

需要看具体代码才能给更精准的建议。
```

---

## 🎯 支持的操作

### 1. 代码审查

**触发词**: 审查、review、检查、分析

**方式**:
- 直接粘贴代码
- 使用代码块 \`\`\`python ... \`\`\`
- 发送文件路径

**示例**:
```
> 审查这段代码: def foo(): pass
> 帮我看看这个函数有没有问题
> 检查一下这个算子实现
```

### 2. PR/Issue 审查

**触发词**: PR、issue、链接、URL

**方式**:
- 发送 GitHub/Gitee URL
- 粘贴 PR/Issue 内容

**示例**:
```
> https://github.com/user/repo/pull/123
> 这个 issue 怎么解决？[粘贴 issue 内容]
> 帮我分析这个 PR
```

### 3. 技术咨询

**自动识别**: 问题类对话

**示例**:
```
> torch_npu 怎么使用？
> 如何把 CUDA 代码迁移到 NPU？
> 昇腾 910 和 310P 有什么区别？
> 模型精度对不齐怎么办？
```

### 4. 命令

- `help` - 显示帮助
- `config` - 重新配置 AI
- `clear` - 清除对话历史
- `exit` / `quit` - 退出

---

## 🧠 智能特性

### 1. 自动意图识别

系统会自动理解你的意图：

- 包含代码 → 代码审查
- 包含 URL → 获取并审查
- 包含问号 → 技术咨询
- 其他 → 自然对话

**不需要特殊命令**，像和人聊天一样！

### 2. 上下文记忆

会记住对话历史（最近 5 轮）：

```
[YOU] > 昇腾 NPU 支持哪些模型？

[AGENT] 支持 ResNet、BERT、GPT、LLaMA 等...

[YOU] > 怎么部署 LLaMA？

[AGENT] LLaMA 部署步骤...（记住了你在问 LLaMA）
```

### 3. 多模态输入

支持多种输入方式：

- 纯文本
- 代码块
- URL 链接
- 混合内容

### 4. 智能提取

自动提取关键信息：

- 从消息中提取代码
- 从 URL 获取内容
- 识别错误码
- 检测技术关键词

---

## 📊 工作流程

```
用户输入
    ↓
[意图识别] 这是要做什么？
    ↓
[实体提取] 提取代码/URL/关键词
    ↓
[选择工具]
    ├─ 代码审查 → SmartReviewer
    ├─ URL 获取 → 网络请求
    ├─ 技术咨询 → AI 对话
    └─ 其他 → 自然聊天
    ↓
[执行并返回结果]
```

---

## 🎨 使用技巧

### 技巧 1: 直接粘贴

不需要说"请审查"，直接粘贴：

```
> def foo():
>     return 1/0
```

系统会自动识别这是代码并审查。

### 技巧 2: 自然语言

用自然语言描述需求：

```
> 我有个代码在 NPU 上跑不通，帮我看看
> 这个 PR 有什么问题吗？
> 帮我优化一下这段代码的性能
```

### 技巧 3: 连续对话

可以连续提问，系统会记住上下文：

```
> 审查这段代码: [代码]
> 那第 3 行的问题怎么修？
> 修改后的代码是这样的: [新代码]
> 现在还有问题吗？
```

### 技巧 4: 混合输入

可以在一个消息里包含多种内容：

```
> 帮我审查这个 PR: https://github.com/.../pull/123
  顺便看看这段代码: [代码]
```

---

## 🔧 高级功能

### 自定义 AI 模型

```
[YOU] > config

[选择新的 AI 服务]
```

### 清除历史

```
[YOU] > clear

[INFO] 对话历史已清除
```

### 查看帮助

```
[YOU] > help

[显示完整使用指南]
```

---

## 🎯 实际场景

### 场景 1: 代码开发

```
[开发中]
> 帮我写个 NPU 版本的矩阵乘法

[AI 生成代码]

> 审查一下这个实现

[显示审查报告]

> 那性能问题怎么优化？

[给出优化建议]
```

### 场景 2: PR Review

```
[收到 PR]
> https://github.com/.../pull/456

[自动获取并审查]

> 第 15 行的问题严重吗？

[详细解释]

> 帮我写个 review comment

[生成 comment]
```

### 场景 3: 问题排查

```
[遇到错误]
> 我的代码报错: EZ9999 Memory allocation failed

[分析问题]

> 怎么解决？

[提供解决方案]

> 还是不行，这是我的代码: [代码]

[深入分析代码]
```

---

## 💡 对比：CLI vs 对话式

| 特性 | CLI | 对话式 |
|------|-----|--------|
| 使用方式 | 命令行 | 自然语言 |
| 学习成本 | 需要记命令 | 直接对话 |
| 灵活性 | 固定命令 | 自由表达 |
| 上下文 | 单次执行 | 连续对话 |
| 适合场景 | 自动化脚本 | 交互探索 |

**推荐**: 两者结合使用
- 日常交互 → 对话式
- 批量处理 → CLI

---

## 🎉 快速命令

```bash
# 启动对话
python chat.py

# 或使用批处理
chat.bat
```

**然后直接对话，就像和人聊天一样！** 💬

---

## 📚 更多资源

- **CLI 指南**: `docs/CLI_GUIDE.md`
- **API 文档**: `docs/AI_ARCHITECTURE.md`
- **完整总结**: `FINAL_SUMMARY.md`

---

**享受智能对话式代码审查！** 🚀
