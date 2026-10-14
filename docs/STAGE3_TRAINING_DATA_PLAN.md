# Stage 3: 训练数据构建计划

开始时间: 2026-10-14

---

## 🎯 目标

将三层数据（CI + Review + Dialog）转换为可用于训练 AI 代码审查模型的结构化数据集。

---

## 📊 输入数据清单

### Level 1: CI Pass 标准
- ✅ ci_workflows_analysis.json (73 KB)
- ✅ 175 workflows 已分类
- ✅ 9 种类型标签

### Level 2: Human Review
- ✅ vllm-ascend: 9 PRs, 34 reviews, 44 comments (240 KB)
- ⚠️ pytorch: 数据不足
- ⚠️ sglang: 数据缺失

### Level 3: Community Dialog
- ✅ 10 仓库 issues (6.6 MB)
- ✅ 210 issues 已收集
- ✅ 错误模式已分类

---

## 🏗️ 训练数据结构设计

### 数据集 A: CI 规则学习

**目标**: 学习什么样的代码能通过 CI

**输入**: 代码 diff
**输出**: CI 检查结果

```json
{
  "id": "ci_001",
  "type": "ci_rule",
  "code_diff": "...",
  "ci_checks": {
    "test_coverage": {"status": "pass", "value": 85},
    "lint": {"status": "fail", "errors": ["E501 line too long"]},
    "build": {"status": "pass"}
  },
  "workflow": "test",
  "verdict": "fail",
  "reason": "lint errors"
}
```

### 数据集 B: Human Review 学习

**目标**: 学习审核人的判断标准

**输入**: 代码 diff + CI 结果
**输出**: Review 意见

```json
{
  "id": "review_001",
  "type": "human_review",
  "pr_number": 7,
  "repo": "vllm-ascend",
  "code_diff": "...",
  "ci_status": "pass",
  "reviews": [
    {
      "reviewer": "maintainer_A",
      "state": "CHANGES_REQUESTED",
      "body": "does self.module only used here? If yes...",
      "category": "code_quality",
      "severity": "medium"
    }
  ],
  "inline_comments": [
    {
      "file": "vllm/executor/npu_executor.py",
      "line": 42,
      "body": "is it necessary for dev?",
      "category": "dependency",
      "severity": "low"
    }
  ],
  "final_decision": "approved_with_changes"
}
```

### 数据集 C: 问题诊断学习

**目标**: 学习问题解决方案

**输入**: 错误信息/问题描述
**输出**: 诊断和解决方案

```json
{
  "id": "issue_001",
  "type": "problem_diagnosis",
  "issue_number": 144,
  "repo": "pytorch",
  "problem": {
    "title": "torch-npu 2.10 + CANN 9.0 compatibility issue",
    "description": "...",
    "error_code": "507049",
    "category": "version_compatibility"
  },
  "diagnosis": {
    "root_cause": "HCCL SDMA device error",
    "affected_versions": ["torch-npu 2.10", "CANN 9.0"],
    "workaround": "Downgrade to torch-npu 2.1.0.post6 + CANN 8.0.RC2+"
  },
  "solution": {
    "type": "version_change",
    "recommendation": "Use tested version combination",
    "evidence": "Community confirmed working"
  }
}
```

---

## 🔄 数据处理流程

### Step 1: Review 数据提取和标注

**输入**: vllm-ascend reviews (240 KB)
**处理**: 
1. 提取每个 review 的意见
2. 分类意见类型（设计/质量/性能/测试）
3. 标注严重程度（high/medium/low）
4. 提取 inline comments 的上下文

**输出**: 标注后的 review 数据集

### Step 2: CI 规则提取

**输入**: ci_workflows_analysis.json
**处理**:
1. 提取测试覆盖率要求
2. 提取 lint 规则
3. 提取构建步骤
4. 推断质量门禁标准

**输出**: CI 规则数据库

### Step 3: Issue 模式提取

**输入**: 210 issues 原始数据
**处理**:
1. 提取问题-解决方案对
2. 识别错误模式
3. 提取版本兼容信息
4. 构建 Q&A 对

**输出**: 问题诊断知识库

### Step 4: 数据集合并

**处理**:
1. 关联相同代码的 CI + Review
2. 构建训练样本
3. 划分训练/验证/测试集
4. 生成最终数据集

---

## 📦 输出数据集

### training_dataset_v1.0/

```
├── ci_rules/
│   ├── test_rules.json          (测试规则)
│   ├── lint_rules.json          (Lint 规则)
│   └── build_rules.json         (构建规则)
│
├── reviews/
│   ├── design_reviews.json      (设计审查)
│   ├── quality_reviews.json     (代码质量)
│   ├── performance_reviews.json (性能审查)
│   └── test_reviews.json        (测试审查)
│
├── issues/
│   ├── version_compat.json      (版本兼容)
│   ├── error_diagnosis.json     (错误诊断)
│   ├── performance_opt.json     (性能优化)
│   └── api_usage.json           (API 使用)
│
├── combined/
│   ├── train.jsonl              (训练集)
│   ├── valid.jsonl              (验证集)
│   └── test.jsonl               (测试集)
│
└── metadata.json                (数据集元信息)
```

---

## 🎯 关键任务

### Task 1: Review 意见分类和标注 ⭐⭐⭐

**优先级**: 最高
**输入**: 34 reviews + 44 comments
**输出**: 标注后的 review 数据集

**分类维度**:
- 意见类型: design / quality / performance / test / doc
- 严重程度: high / medium / low
- 决策: approve / request_changes / comment

### Task 2: CI 规则数据库构建 ⭐⭐

**优先级**: 高
**输入**: 175 workflows 分析结果
**输出**: CI 规则数据库

**提取内容**:
- 测试覆盖率标准
- Lint 检查规则
- 构建流程要求
- 质量门禁条件

### Task 3: Issue Q&A 对构建 ⭐⭐

**优先级**: 高
**输入**: 210 issues
**输出**: 问题诊断知识库

**提取内容**:
- 问题描述 → 解决方案
- 错误码 → 诊断步骤
- 版本 → 兼容性信息

### Task 4: 训练样本生成 ⭐

**优先级**: 中
**输入**: 所有处理后的数据
**输出**: 最终训练数据集

**生成格式**:
- JSONL 格式
- 训练/验证/测试 8:1:1
- 包含 prompt 和 completion

---

## 🔧 实现工具

### 1. Review 分析器

```python
class ReviewAnalyzer:
    def extract_reviews(self, pr_data):
        """提取 review 意见"""
        
    def classify_feedback(self, review):
        """分类 review 类型"""
        
    def annotate_severity(self, review):
        """标注严重程度"""
        
    def extract_context(self, comment):
        """提取代码上下文"""
```

### 2. CI 规则提取器

```python
class CIRuleExtractor:
    def extract_test_requirements(self, workflows):
        """提取测试要求"""
        
    def extract_lint_rules(self, workflows):
        """提取 Lint 规则"""
        
    def infer_quality_gates(self, workflows):
        """推断质量门禁"""
```

### 3. Issue 模式提取器

```python
class IssuePatternExtractor:
    def extract_qa_pairs(self, issues):
        """提取 Q&A 对"""
        
    def identify_error_patterns(self, issues):
        """识别错误模式"""
        
    def extract_solutions(self, issue):
        """提取解决方案"""
```

---

## 📈 数据质量指标

### 覆盖率

- CI 规则覆盖: 9 种 workflow 类型
- Review 类型覆盖: 设计/质量/性能/测试
- 问题类型覆盖: 5 类错误模式

### 数据量

- 目标 Review 样本: 50+ 条
- 目标 CI 规则: 30+ 条
- 目标 Issue Q&A: 100+ 对

### 质量

- Review 标注准确率: > 90%
- Issue 解决方案准确率: > 85%
- CI 规则完整性: > 80%

---

## ⏱️ 时间计划

### Day 1-2: Review 数据处理
- [x] 分析 34 reviews
- [ ] 分类意见类型
- [ ] 标注严重程度
- [ ] 生成 review 数据集

### Day 3: CI 规则提取
- [ ] 分析 175 workflows
- [ ] 提取质量标准
- [ ] 构建规则数据库

### Day 4: Issue 数据处理
- [ ] 分析 210 issues
- [ ] 提取 Q&A 对
- [ ] 构建诊断知识库

### Day 5: 数据集合并
- [ ] 关联 CI + Review
- [ ] 生成训练样本
- [ ] 划分数据集

---

## 🚀 开始执行

让我们从 **Task 1: Review 意见分类和标注** 开始！

这是最有价值的数据，因为它包含了人工审核的标准。

准备好了吗？
