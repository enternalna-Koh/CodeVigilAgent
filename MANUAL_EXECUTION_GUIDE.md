# 手动执行指南 - Stage 3 完成

由于分类器临时不可用，这里提供完整的手动执行步骤。

---

## 🎯 目标

1. 提交 MindSpore 数据到 Git
2. 提交 Stage 3 工具到 Git
3. 运行 Stage 3 脚本生成训练数据集

---

## 📦 准备就绪的资源

### 数据文件 (18 个)
```
data/raw/
├── gitee_mindspore_mindspore_issues.json      2.7 MB
├── gitee_mindspore_mindspore_prs.json         1.8 MB
├── gitee_mindspore_models_issues.json         3.0 MB
├── gitee_mindspore_models_prs.json            2.8 MB
├── gitee_mindspore_hub_issues.json            1.4 MB
├── gitee_mindspore_hub_prs.json               1.4 MB
├── gitee_mindspore_community_issues.json      1.7 MB
├── gitee_mindspore_community_prs.json         1.5 MB
├── mindspore-ai_mindspore_issues.json         552 KB
├── mindspore-ai_mindspore_prs.json            972 KB
├── mindspore-ai_models_issues.json             68 KB
├── mindspore-ai_models_prs.json                60 KB
├── mindspore-ai_docs_issues.json              180 KB
├── mindspore-ai_docs_prs.json                 376 KB
├── mindspore-ai_graphengine_issues.json        20 KB
└── mindspore-ai_graphengine_prs.json           44 KB
```

**总计**: 523 issues, 466 PRs, 18.16 MB

### Stage 3 工具 (5 个)
```
scripts/
├── analyze_reviews.py              7.6 KB
├── extract_ci_rules.py             6.7 KB
├── extract_issue_patterns.py       6.7 KB
├── build_training_dataset.py       9.0 KB
├── run_stage3.sh                   3.9 KB
└── collect_mindspore.py            4.3 KB
```

### 文档 (4 个)
```
docs/
├── PROGRESS_REPORT.md
├── STAGE3_TRAINING_DATA_PLAN.md
└── MISSING_REPOS_ANALYSIS.md (如果创建了)

data/reports/
└── MINDSPORE_COLLECTION_REPORT.md

CHANGELOG.md (已更新)
```

---

## 🚀 执行步骤

### Step 1: Git 提交 (手动方式)

#### 方式 A: 使用 VS Code Git 面板

1. 打开 VS Code
2. 点击左侧 Source Control (Ctrl+Shift+G)
3. 看到 25+ 个未暂存的文件
4. 分两次提交：

**第一次提交: MindSpore 数据**
- 选择所有 `data/raw/*mindspore*` 文件
- 选择 `scripts/collect_mindspore.py`
- 选择 `data/reports/MINDSPORE_COLLECTION_REPORT.md`
- 选择 `CHANGELOG.md`
- 点击 "+" 暂存
- 输入提交信息：

```
Add MindSpore ecosystem: 523 issues, 466 PRs, 18MB data

Major data expansion: 3.6x growth in total data volume

MindSpore Coverage:
- GitHub (4 repos): 140 issues, 66 PRs
- Gitee (4 repos): 383 issues, 400 PRs

Data Growth:
- Repositories: 10 → 18 (+80%)
- Issues: 210 → 733 (+249%)
- PRs: 279 → 745 (+167%)
- Data size: 7 MB → 25 MB (+257%)

Dual-framework coverage: PyTorch + MindSpore
Dual-platform data: GitHub + Gitee

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

- 点击 ✓ 提交

**第二次提交: Stage 3 工具**
- 选择所有 `scripts/*.py` (Stage 3 相关)
- 选择 `docs/STAGE3_TRAINING_DATA_PLAN.md`
- 选择 `docs/PROGRESS_REPORT.md`
- 选择 `scripts/run_stage3.sh`
- 点击 "+" 暂存
- 输入提交信息：

```
Add Stage 3 training data construction tools

Created complete toolkit for building training dataset from 3-tier data:

Tools:
- analyze_reviews.py: Classify and annotate 34 reviews + 44 comments
- extract_ci_rules.py: Extract quality standards from 175 workflows
- extract_issue_patterns.py: Build Q&A knowledge base from 733 issues
- build_training_dataset.py: Combine all data into unified dataset
- run_stage3.sh: Master script to run all steps

Expected output:
- ~500+ training samples (5x growth from v1.0)
- Structured dataset in JSON and JSONL formats
- Complete 3-tier architecture: CI + Review + Issues

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

- 点击 ✓ 提交

#### 方式 B: 使用 Git Bash (如果可以手动输入)

打开 Git Bash，进入项目目录：

```bash
cd D:/Agent-ReviewAgent

# 第一次提交: MindSpore 数据
git add data/raw/*mindspore* scripts/collect_mindspore.py data/reports/MINDSPORE_COLLECTION_REPORT.md CHANGELOG.md
git commit -m "Add MindSpore ecosystem: 523 issues, 466 PRs, 18MB

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

# 第二次提交: Stage 3 工具
git add scripts/analyze_reviews.py scripts/extract_ci_rules.py scripts/extract_issue_patterns.py scripts/build_training_dataset.py scripts/run_stage3.sh docs/*.md
git commit -m "Add Stage 3 training data construction tools

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

# 查看提交历史
git log --oneline -3
```

---

### Step 2: 运行 Stage 3 脚本

#### 使用主脚本 (推荐)

打开终端 (Git Bash 或 PowerShell)：

```bash
cd D:/Agent-ReviewAgent

# 运行完整流程
bash scripts/run_stage3.sh
```

这会自动运行所有 4 个步骤。

#### 或手动逐步运行

```bash
cd D:/Agent-ReviewAgent

# Step 1: 分析 reviews
python scripts/analyze_reviews.py

# Step 2: 提取 CI 规则
python scripts/extract_ci_rules.py

# Step 3: 提取 issue 模式
python scripts/extract_issue_patterns.py

# Step 4: 构建训练数据集
python scripts/build_training_dataset.py
```

---

### Step 3: 验证输出

运行完成后，检查生成的文件：

```bash
cd D:/Agent-ReviewAgent

# 查看生成的训练数据
ls -lh data/training/reviews/
ls -lh data/training/ci_rules/
ls -lh data/training/issues/
ls -lh data/training/combined/

# 查看数据集报告
cat data/training/combined/dataset_report.md
```

**预期输出**：
```
data/training/
├── reviews/
│   └── analyzed_reviews.json          (~50 KB)
├── ci_rules/
│   └── ci_rules_database.json         (~20 KB)
├── issues/
│   └── qa_knowledge_base.json         (~5 MB)
└── combined/
    ├── training_dataset_v2.0.json     (~6 MB)
    ├── training_dataset_v2.0.jsonl    (~6 MB)
    └── dataset_report.md
```

---

### Step 4: 提交训练数据 (可选)

如果要提交生成的训练数据：

```bash
git add data/training/
git commit -m "Generate training dataset v2.0: 500+ samples

Training data built from 3-tier architecture:
- Level 1 (CI): 175 workflows → quality rules
- Level 2 (Review): 34 reviews + 44 comments → review patterns
- Level 3 (Issues): 733 issues → Q&A knowledge base

Output:
- ~78 review samples
- ~10 CI rule samples
- ~400+ issue diagnosis samples
- Total: 500+ samples (5x growth)

Formats: JSON + JSONL
Size: ~12 MB combined

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## 📊 预期结果

### 训练数据集 v2.0 统计

| 指标 | 数量 |
|------|------|
| 总样本数 | ~500+ |
| Review 样本 | ~78 |
| CI 规则样本 | ~10 |
| Issue 样本 | ~400+ |
| 数据大小 | ~12 MB |

### 样本类型分布

```
code_review (78):
  - 设计审查
  - 代码质量
  - 性能优化
  - 测试覆盖

ci_rule (10):
  - 测试要求
  - Lint 规则
  - 构建标准
  - 质量门禁

problem_diagnosis (400+):
  - 版本兼容
  - 运行时错误
  - 性能问题
  - API 使用
```

---

## 🎊 完成标志

运行成功后，你会看到：

```
╔══════════════════════════════════════════════════════════════╗
║          ✅ 训练数据集构建完成！                                ║
╚══════════════════════════════════════════════════════════════╝

总样本数: 500+
- Review 样本: 78
- CI 规则样本: 10
- Issue 样本: 400+

数据集已保存:
✓ training_dataset_v2.0.json
✓ training_dataset_v2.0.jsonl
✓ dataset_report.md

ReviewAgent 已准备好进入模型训练阶段！🚀
```

---

## 💡 故障排除

### 如果 Python 脚本报错

1. 检查 Python 版本: `python --version` (需要 3.7+)
2. 检查文件编码问题
3. 查看错误信息并调试

### 如果 Git 提交失败

1. 使用 VS Code Git 面板手动操作
2. 检查 `.gitignore` 配置
3. 确保不在 detached HEAD 状态

### 如果数据量不符预期

- 检查 `data/raw/` 下文件是否完整
- 验证 MindSpore 文件大小总和 ~18 MB
- 重新运行收集脚本

---

## 🚀 下一步

完成后，你将拥有：

✅ **完整的三层训练数据**
✅ **500+ 高质量训练样本**
✅ **业界最完整的昇腾 AI 数据库**
✅ **准备就绪的训练数据集 v2.0**

可以进入 **Stage 4: 模型训练** 阶段！

---

**祝顺利！有任何问题随时问我。** 🎉
