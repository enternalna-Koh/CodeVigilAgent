# ReviewAgent CLI 使用指南

快速、简单、强大的命令行界面

---

## 🚀 快速开始

### 安装（可选，添加到 PATH）

**Windows**:
```cmd
# 方式 1: 添加项目目录到 PATH
setx PATH "%PATH%;D:\Agent-ReviewAgent"

# 方式 2: 创建别名（每次都需要）
doskey review=python D:\Agent-ReviewAgent\review_cli.py $*
```

**Linux/Mac**:
```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
alias review='python /path/to/Agent-ReviewAgent/review_cli.py'
```

---

## 📖 基本用法

### 1. 审查代码文件

```bash
# 切换到项目目录
cd D:\Agent-ReviewAgent

# 审查单个文件
python review_cli.py test.py

# 或使用 .bat（Windows）
review.bat test.py
```

### 2. 审查文本内容

```bash
python review_cli.py --text "def foo(): return 1/0"
```

### 3. 从标准输入

```bash
# Windows (PowerShell)
Get-Content code.py | python review_cli.py

# Linux/Mac
cat code.py | python review_cli.py
```

### 4. 保存报告

```bash
python review_cli.py code.py --output report.json
```

---

## 🛠️ 命令详解

### 审查命令（默认）

```bash
python review_cli.py [FILE] [选项]

选项:
  FILE              要审查的文件
  --text, -t TEXT   直接提供文本内容
  --output, -o FILE 保存报告到 JSON 文件
  --quiet, -q       静默模式，不打印报告
  --config, -c FILE AI 配置文件路径
```

**示例**:
```bash
# 审查并保存
python review_cli.py code.py -o report.json

# 审查文本
python review_cli.py -t "print('hello')"

# 静默模式（仅保存报告）
python review_cli.py code.py -o report.json -q
```

---

### 测试命令

```bash
python review_cli.py test
```

运行 3 个内置测试用例：
1. NPU 性能优化 PR
2. 运行时错误 Issue
3. 通用代码审查

---

### 配置命令

```bash
python review_cli.py config [选项]

选项:
  --init      初始化配置文件
  --show      显示当前配置
  --set K=V   设置配置项
  --force     强制覆盖
```

**示例**:
```bash
# 初始化配置
python review_cli.py config --init

# 查看配置
python review_cli.py config --show

# 设置 API Key
python review_cli.py config --set api_key=sk-xxx

# 切换 AI
python review_cli.py config --set provider=openai
python review_cli.py config --set model=gpt-4
```

---

### 统计命令

```bash
python review_cli.py stats
```

显示数据统计：
- 数据文件数量和大小
- Issues/PRs 统计
- 训练数据状态

---

## 💡 使用场景

### 场景 1: 提交前自查

```bash
# 审查你的改动
git diff HEAD > changes.diff
python review_cli.py changes.diff

# 或直接审查文件
python review_cli.py src/model.py
```

### 场景 2: CI/CD 集成

```bash
# .github/workflows/review.yml
- name: Code Review
  run: |
    python review_cli.py src/ --output review_report.json
```

### 场景 3: 批量审查

```bash
# Windows PowerShell
Get-ChildItem *.py | ForEach-Object {
    python review_cli.py $_.Name -o "reports/$($_.BaseName).json"
}

# Linux/Mac
for file in *.py; do
    python review_cli.py "$file" -o "reports/${file%.py}.json"
done
```

---

## 🎯 实际例子

### 例子 1: 审查 NPU 代码

创建测试文件 `npu_test.py`:
```python
import torch

def allocate_memory(size):
    # Wrong: using .cuda() instead of .npu()
    tensor = torch.zeros(size).cuda()
    return tensor
```

审查:
```bash
python review_cli.py npu_test.py
```

输出会指出：
- [!!] HIGH: NPU API 使用错误
- 建议：使用 .npu() 替代 .cuda()

---

### 例子 2: 审查 PR

复制 GitHub PR 内容到文件 `pr.txt`:
```
Pull Request: Fix memory leak

Changes:
- Add proper cleanup
- Fix tensor allocation

Code:
def process():
    data = load_data()
    # Missing cleanup
    return result
```

审查:
```bash
python review_cli.py pr.txt
```

---

### 例子 3: 快速检查代码片段

```bash
python review_cli.py --text "
def calculate(a, b):
    return a / b  # Missing zero check
"
```

---

## ⚙️ 高级用法

### 使用不同配置

```bash
# 使用自定义配置
python review_cli.py code.py --config my_ai.json
```

### 调试模式

```bash
python review_cli.py code.py --debug
```

### 管道处理

```bash
# 审查 Git diff
git diff | python review_cli.py > review.txt

# 审查最近提交
git show HEAD | python review_cli.py
```

---

## 📊 输出格式

### 控制台输出

```
[INFO] 启动智能审查...
[INPUT] 读取文件: test.py

[STEP 1] 识别任务类型...
   类型: code_audit
   子类型: npu, performance
   置信度: 85%

[STEP 2] 匹配审查标准...
   标准: code_audit_npu+performance
   检查项: 10 项

[STEP 3] 执行深度审查...
   使用 AI 引擎...

================================================================================
[REPORT] 智能审查报告
================================================================================

[TYPE] 任务类型: code_audit
   子类型: npu, performance

[STANDARD] 应用标准: code_audit_npu+performance

[ISSUES] 发现问题: 2 个

[!!] HIGH 级别问题 (1 个):
  [1] NPU API 使用错误
      问题: 使用了 .cuda() 而不是 .npu()
      位置: line 5
      建议: 替换为 .npu()
      重要性: 会导致代码在 NPU 上无法运行

[!] MEDIUM 级别问题 (1 个):
  [2] 缺少错误处理
      ...
```

### JSON 输出 (--output)

```json
{
  "task_identification": {
    "type": "code_audit",
    "subtypes": ["npu", "performance"],
    "confidence": 0.85
  },
  "review_result": {
    "issues": [...],
    "overall_assessment": "...",
    "recommendation": "request_changes"
  }
}
```

---

## 🔧 故障排除

### 问题 1: 找不到模块

```
[ERROR] 导入失败: No module named 'scripts.smart_reviewer'
```

**解决**:
```bash
# 确保在项目根目录
cd D:\Agent-ReviewAgent
python review_cli.py test
```

### 问题 2: API Key 未配置

```
[ERROR] API key not configured
```

**解决**:
```bash
python review_cli.py config --init
# 编辑 config/ai_config.json 填入 API Key
```

### 问题 3: 编码错误（Windows）

已自动处理 UTF-8 编码，如果仍有问题：
```cmd
chcp 65001
python review_cli.py code.py
```

---

## 📚 更多资源

- **完整文档**: `README.md`
- **架构文档**: `docs/AI_ARCHITECTURE.md`
- **API 文档**: `docs/API.md`
- **示例**: `examples/`

---

## 🎉 快速参考

```bash
# 最常用的命令

# 1. 审查文件
python review_cli.py file.py

# 2. 运行测试
python review_cli.py test

# 3. 配置 AI
python review_cli.py config --init

# 4. 查看帮助
python review_cli.py --help

# 5. 查看版本
python review_cli.py --version
```

---

**享受智能代码审查！** 🚀
