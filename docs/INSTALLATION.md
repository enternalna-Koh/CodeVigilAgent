# ReviewAgent 安装和使用指南

让 ReviewAgent 像 `claude` 一样全局可用

---

## 🚀 快速安装

### Windows

#### 方式 1: 添加到 PATH（推荐）

1. 复制路径：
   ```
   D:\Agent-ReviewAgent\bin
   ```

2. 添加到系统 PATH：
   - 按 `Win + X`，选择 "系统"
   - 点击 "高级系统设置"
   - 点击 "环境变量"
   - 在 "系统变量" 中找到 `Path`，点击 "编辑"
   - 点击 "新建"，粘贴路径
   - 一路点击 "确定"

3. 重启 PowerShell 或 CMD

4. 测试：
   ```cmd
   review
   ```

#### 方式 2: 创建别名（临时）

在 PowerShell 中：
```powershell
Set-Alias review "D:\Agent-ReviewAgent\bin\review.bat"
```

每次启动都需要运行，或添加到 PowerShell 配置文件。

---

### Linux/Mac

1. 创建符号链接：
   ```bash
   sudo ln -s /path/to/Agent-ReviewAgent/review.py /usr/local/bin/review
   chmod +x /path/to/Agent-ReviewAgent/review.py
   ```

2. 测试：
   ```bash
   review
   ```

---

## 🎯 使用方式

### 进入对话模式

```bash
review
```

显示 Logo 后进入交互式对话：

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

直接审查文件，不进入对话模式。

### 配置 AI

```bash
review --config
```

运行配置向导。

### 查看统计

```bash
review --stats
```

显示数据统计。

### 查看帮助

```bash
review --help
```

---

## 📖 完整命令

```
review                    进入对话模式（默认）
review <file>             快速审查文件
review --config           配置 AI 服务
review --stats            显示统计信息
review --version          显示版本
review --help             显示帮助
```

---

## 🎨 对话模式内命令

进入对话模式后：

```
/help     显示帮助
/clear    清除历史
/config   重新配置
/stats    显示统计
/exit     退出
```

---

## 🌟 使用示例

### 示例 1: 首次使用

```bash
# 1. 运行
review

# 2. 自动进入配置向导
? 请选择 AI 服务 (1-4): 1
? 请输入 API Key: sk-xxxxx

# 3. 配置完成，进入对话
You> 帮我审查这段代码...
```

### 示例 2: 快速审查

```bash
review my_code.py
```

立即审查，显示报告后退出。

### 示例 3: 技术咨询

```bash
review

You> 昇腾 NPU 怎么优化性能？
ReviewAgent: [详细建议]

You> 给个代码示例
ReviewAgent: [代码示例]
```

---

## 🔧 故障排除

### 问题 1: 命令未找到

**Windows**:
```cmd
# 检查 PATH
echo %PATH%

# 手动运行
D:\Agent-ReviewAgent\bin\review.bat
```

**Linux/Mac**:
```bash
# 检查符号链接
ls -la /usr/local/bin/review

# 手动运行
python /path/to/Agent-ReviewAgent/review.py
```

### 问题 2: 权限问题（Linux/Mac）

```bash
sudo chmod +x /path/to/Agent-ReviewAgent/review.py
```

### 问题 3: Python 未找到

确保 Python 在 PATH 中：
```bash
python --version
```

---

## 💡 与 Claude Code 对比

| 特性 | Claude Code | ReviewAgent |
|------|-------------|-------------|
| 命令 | `claude` | `review` |
| Logo | ✓ | ✓ |
| 对话模式 | ✓ | ✓ |
| 快速命令 | ✓ | ✓ |
| 专业领域 | 通用 | 昇腾 NPU |
| 数据支持 | - | 733 issues + 745 PRs |

---

## 🎊 开始使用

```bash
# 1. 添加到 PATH（首次）
# 2. 运行命令
review

# 就这么简单！
```

---

**现在你有了自己的 `review` 命令！** 🚀
