# CI/CD 配置与社区对话数据收集计划

创建时间: 2026-10-14

---

## 🎯 数据收集目标

### 1. CI/CD 配置数据

**价值**：CI 通过的代码说明符合基本质量标准

**收集内容**：
- GitHub Actions workflows (.github/workflows/*.yml)
- GitLab CI 配置 (.gitlab-ci.yml)
- Jenkins 流水线 (Jenkinsfile)
- 测试脚本和配置
- Lint 规则 (pylint, flake8, black)
- 代码覆盖率要求

**重点仓库**：
- Ascend/pytorch - torch-npu CI 标准
- vllm-project/vllm-ascend - LLM 推理测试
- Ascend/sglang - 结构化生成测试
- pytorch-ecosystem - API 一致性测试

### 2. PR Review 对话数据

**价值**：审核人的反馈体现真实的代码质量要求

**收集内容**：
- PR comments (审核意见)
- Review threads (讨论线程)
- Change requests (修改要求)
- Approval patterns (通过模式)

**关键信息**：
- 代码规范要求
- 测试覆盖率标准
- 文档完整性
- API 设计原则
- 性能要求证明

### 3. Issue 讨论数据

**价值**：开发者与维护者的问答包含隐性知识

**收集内容**：
- Issue comments (问题讨论)
- 解决方案演进过程
- 技术决策依据
- 已知限制和 workaround

---

## 📊 数据分层策略

### Level 1: CI 配置 (客观标准)

```
CI Pass = 基线质量保证
  ├─ 语法检查通过
  ├─ 单元测试通过
  ├─ 代码覆盖率达标
  ├─ Lint 规则符合
  └─ 构建成功
```

**训练用途**：
- 自动代码质量检查
- 生成测试用例
- 识别常见错误模式

### Level 2: PR Review 对话 (人工审核标准)

```
Human Review = 更高质量要求
  ├─ 设计合理性
  ├─ 代码可读性
  ├─ 性能优化建议
  ├─ 边界条件处理
  └─ 文档完整性
```

**训练用途**：
- 学习审核人的思维模式
- 识别需要人工判断的场景
- 理解隐性的编码规范

### Level 3: Issue 讨论 (问题解决模式)

```
Community Knowledge = 实战经验
  ├─ 常见误用模式
  ├─ 环境配置陷阱
  ├─ 版本兼容问题
  ├─ 性能优化技巧
  └─ 最佳实践案例
```

**训练用途**：
- 构建问题诊断知识库
- 学习解决方案演进
- 理解技术决策权衡

---

## 🔄 数据收集流程

### 阶段 1: CI 配置收集 (已启动)

```bash
# 收集 workflow 文件
scripts/collect_ci_configs.sh

# 分析 CI 通过标准
scripts/analyze_ci_standards.py
```

**产出**：
- CI 配置文件 (YAML/JSON)
- 测试标准文档
- Lint 规则汇总

### 阶段 2: PR Review 对话收集

```python
# 收集 PR comments
for pr in merged_prs:
    - 获取 review comments
    - 提取 change requests
    - 识别通过/拒绝模式
```

**产出**：
- PR review 数据集
- 审核模式分析
- 常见反馈类型

### 阶段 3: Issue 讨论收集

```python
# 收集 Issue 讨论线程
for issue in closed_issues:
    - 提取问题描述
    - 收集讨论过程
    - 总结解决方案
```

**产出**：
- Issue 对话数据集
- 问答配对
- 解决方案模式

---

## 🎓 训练数据构建

### 数据集 A: CI-Pass 代码库

**正样本**：CI 通过的代码
- 格式正确
- 测试完整
- 符合规范

**负样本**：CI 失败的代码
- 从失败的 commits 提取
- 识别常见错误

### 数据集 B: Human Review 标注

**结构**：
```json
{
  "code_diff": "...",
  "ci_status": "passed",
  "review_comments": [
    {
      "reviewer": "maintainer_name",
      "line": 42,
      "comment": "Consider using np.allclose for float comparison",
      "type": "suggestion",
      "severity": "medium"
    }
  ],
  "decision": "approved_with_changes"
}
```

### 数据集 C: Q&A 对话库

**结构**：
```json
{
  "question": "torch-npu 2.10 与 CANN 9.0 兼容吗?",
  "context": "Issue #144",
  "answer": "不兼容，推荐使用 torch-npu 2.1.0.post6 + CANN 8.0.RC2+",
  "evidence": "Issue discussion + test results",
  "confidence": "high"
}
```

---

## 📈 训练策略

### 阶段 1: 规则学习 (CI 标准)

**目标**: 学习客观的代码质量标准

**方法**:
- 分析 CI 配置提取规则
- 统计 CI 失败原因
- 构建自动检查器

**产出**: 基础代码审查能力

### 阶段 2: 模式学习 (Human Review)

**目标**: 学习人工审核的判断标准

**方法**:
- 对比 CI Pass 但 Review 拒绝的案例
- 提取审核人的关注点
- 识别需要人工判断的场景

**产出**: 进阶审查建议能力

### 阶段 3: 知识学习 (Community Dialog)

**目标**: 积累实战经验和隐性知识

**方法**:
- 挖掘 Issue 讨论中的技术决策
- 总结常见问题的解决方案
- 构建领域知识图谱

**产出**: 问题诊断和建议能力

---

## 🛠️ 实现工具

### 1. CI 配置解析器

```python
class CIConfigParser:
    def extract_test_requirements(yaml_config):
        # 提取测试覆盖率要求
        # 提取 lint 规则
        # 提取构建步骤
        pass
```

### 2. PR Review 提取器

```python
class PRReviewExtractor:
    def collect_review_comments(pr_number):
        # 获取所有 review comments
        # 分类 (suggestion/change_request/approval)
        # 提取代码上下文
        pass
```

### 3. 对话数据结构化器

```python
class DialogStructurer:
    def build_qa_pairs(issue_thread):
        # 识别问题和回答
        # 提取技术细节
        # 标注置信度
        pass
```

---

## 📋 下一步行动

### 立即执行

1. ✅ 收集 CI workflow 配置
2. 📋 分析 CI 测试标准
3. 📋 提取 lint 规则

### 本周完成

4. 📋 收集 merged PRs 的 review comments
5. 📋 统计常见 review 反馈类型
6. 📋 构建 review 模式数据库

### 本月完成

7. 📋 收集 closed issues 的讨论线程
8. 📋 构建 Q&A 数据集
9. 📋 训练基础审查模型原型
10. 📋 评估模型准确率

---

## 🎯 预期成果

### 短期 (1 个月)

- CI 标准数据库
- PR Review 模式库
- 500+ Q&A 对话对

### 中期 (3 个月)

- 自动化代码审查原型
- 问题诊断知识库
- 审核建议生成器

### 长期 (6 个月)

- 完整的代码审查 AI
- 实时问题诊断系统
- 持续学习更新机制

---

## 💡 关键洞察

**你的观点非常正确**:

1. **CI ≠ 完美**
   - CI 只能检查可编程的规则
   - 设计、可读性需要人工审核

2. **对话价值巨大**
   - 蕴含隐性知识
   - 体现真实判断标准
   - 记录技术决策过程

3. **分层训练策略**
   - 先学规则 (CI)
   - 再学判断 (Review)
   - 最后学经验 (Dialog)

**这将是 ReviewAgent 的下一个重大升级！** 🚀

---

**文档版本**: v1.0  
**创建时间**: 2026-10-14  
**状态**: 规划中，CI 收集已启动
