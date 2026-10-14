# ReviewAgent - 本地测试完整指南

无需发布到 npm，本地完整测试

---

## 🚀 快速测试（3 步）

### 1. 安装 Node.js 依赖

```bash
cd D:\Agent-ReviewAgent
npm install
```

### 2. 链接到全局

```bash
npm link
```

### 3. 测试命令

```bash
review
```

**就这么简单！** 🎉

---

## 📖 详细步骤

### Step 1: 检查环境

```bash
# 检查 Node.js
node --version  # 应该 >= 14.0.0

# 检查 npm
npm --version   # 应该 >= 6.0.0

# 检查 Python
python --version  # 应该 >= 3.7
```

### Step 2: 进入项目目录

```bash
cd D:\Agent-ReviewAgent
```

### Step 3: 安装依赖

```bash
npm install
```

会安装:
- chalk - 终端颜色
- inquirer - 交互提示
- ora - 进度指示
- boxen - 边框盒子

### Step 4: 链接到全局

```bash
npm link
```

这会创建全局符号链接，让 `review` 命令可用。

### Step 5: 测试

```bash
# 进入对话模式
review

# 快速审查
review test.py

# 配置
review --config

# 帮助
review --help
```

---

## 🎯 完整测试流程

```bash
# 1. 测试基本命令
review --version

# 2. 测试配置向导
review --config

# 3. 测试对话模式
review

You> 帮我审查代码

# 4. 测试文件审查
echo "def foo(): return 1/0" > test.py
review test.py

# 5. 测试统计
review --stats
```

---

## 🔧 故障排除

### 问题 1: npm install 失败

```bash
# 清除缓存
npm cache clean --force

# 重试
npm install
```

### 问题 2: npm link 失败

Windows 可能需要管理员权限：

```powershell
# 以管理员运行 PowerShell
npm link
```

### 问题 3: review 命令未找到

```bash
# 检查全局链接
npm ls -g --depth=0

# 重新链接
npm unlink -g @reviewagent/cli
npm link
```

### 问题 4: Python 未找到

确保 Python 在 PATH 中：

```bash
python --version
```

如果没有，安装 Python: https://www.python.org/downloads/

---

## 🎨 查看效果

运行 `review` 后会看到：

```
    ____            _                ___                    __
   / __ \___ _   __(_)__ _      __  /   | ____ ____  ____  / /_
  / /_/ / _ \ | / / / _ \ | /| / / / /| |/ __ `/ _ \/ __ \/ __/
 / _, _/  __/ |/ / /  __/ |/ |/ / / ___ / /_/ /  __/ / / / /_
/_/ |_|\___/|___/_/\___/|__/|__/ /_/  |_\__, /\___/_/ /_/\__/
                                        /____/

智能代码审查助手 - 专为昇腾 NPU 打造
======================================================================

[✓] 初始化 ReviewAgent...
[ℹ] 首次使用，需要配置 AI 服务

┌─────────────────────────────────────────────────────────────┐
│                      AI 配置向导                             │
├─────────────────────────────────────────────────────────────┤
│ 欢迎使用 ReviewAgent！                                       │
│                                                             │
│ ReviewAgent 需要连接 AI 服务来提供智能审查。                │
│ 请选择你要使用的 AI 服务商。                                 │
└─────────────────────────────────────────────────────────────┘

可用的 AI 服务:
  • 1. DeepSeek - 性价比最高，代码能力强
  • 2. OpenAI - 最强大的通用 AI
  • 3. Claude - 长文本理解优秀
  • 4. GLM - 中文支持好

? 请选择 (1-4):
```

---

## ✅ 测试清单

- [ ] `review` 命令可用
- [ ] 显示 Logo
- [ ] 配置向导正常
- [ ] 对话模式工作
- [ ] 文件审查功能
- [ ] 命令行参数正确
- [ ] 颜色显示正常
- [ ] 错误处理正确

---

## 🎊 完成测试

如果一切正常，你现在拥有：

✅ **全局 `review` 命令**  
✅ **专业 Logo 和 UI**  
✅ **完整的对话功能**  
✅ **智能代码审查**  
✅ **像 Claude Code 一样的体验**

---

## 📝 下一步

### 选项 A: 继续本地使用

保持 `npm link` 状态，随时使用 `review` 命令

### 选项 B: 发布到 npm

参考 `docs/NPM_PUBLISH.md` 发布为公开包

### 选项 C: 分享给团队

将项目打包分享，其他人也可以 `npm link` 使用

---

## 🔄 取消链接

不想用时：

```bash
npm unlink -g @reviewagent/cli
```

重新链接：

```bash
npm link
```

---

**开始测试吧！** 🚀

```bash
npm install
npm link
review
```
