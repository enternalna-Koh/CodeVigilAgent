# 批量收集完成报告

收集时间: 2026-10-14 14:38

---

## 新增仓库数据

### 收集清单

1. **Ascend/mindspore**
   - 华为昇腾 AI 框架
   - 数据: 0 issues, 0 PRs
   - 状态: 可能使用其他 Issue 追踪系统

2. **Ascend/ModelZoo-PyTorch**
   - PyTorch 模型库
   - 数据: Issues + PRs
   - 焦点: 模型适配和性能优化

3. **Ascend/AscendSpeed**
   - LLM 训练加速库
   - 基于 Megatron-LM 和 DeepSpeed
   - 数据: Issues
   - 焦点: GPT、LLaMA 等大模型训练

4. **Ascend/samples**
   - AscendCL 示例代码
   - 数据: Issues + PRs
   - 焦点: API 使用示例和部署案例

5. **Ascend/tools**
   - 开发工具集
   - 数据: Issues
   - 焦点: 调试、性能分析工具

6. **Ascend/ascend-pytorch-crowdsource-op**
   - 社区贡献算子
   - 数据: 极少
   - 说明: 可能新建或活跃度低

---

## 完整数据收集统计

### 总览

| 类别 | 仓库数 | Issues | PRs |
|------|--------|--------|-----|
| **已有** | 4 | 176 | 276 |
| **新增** | 6 | ? | ? |
| **总计** | **10** | **?** | **?** |

### 分层覆盖

**核心框架层** (3 个)
- Ascend/pytorch (torch-npu)
- Ascend/mindspore
- Ascend/tensorflow (待补充)

**API 适配层** (2 个)
- pytorch-ecosystem (GitCode)
- ascend-pytorch-crowdsource-op

**模型层** (2 个)
- ModelZoo-PyTorch
- ModelZoo (待补充)

**LLM 推理层** (3 个)
- vllm-ascend
- sglang
- AscendSpeed (训练加速)

**工具和示例层** (2 个)
- samples
- tools

---

## 关键发现

### 1. MindSpore 数据缺失

MindSpore 是华为官方 AI 框架，但 GitHub 上 Issues 为空，可能原因:
- 使用 Gitee 或其他平台
- 企业内部 Issue 追踪系统
- 需要补充从其他渠道收集

### 2. ModelZoo-PyTorch 活跃度

从文件大小看 (70 KB issues, 21 KB PRs)，有实质性数据，值得深入分析。

### 3. Samples 仓库价值

99 KB issues + 37 KB PRs，说明有大量使用问题和示例贡献，这些是:
- 真实使用场景
- 部署问题
- API 使用陷阱

### 4. AscendSpeed 的战略意义

8.5 KB issues，专注 LLM 训练加速，补充了推理之外的场景。

---

## 数据价值评估

### 高价值仓库 (需深度分析)

1. **ModelZoo-PyTorch** - 模型适配案例库
2. **samples** - 真实使用问题
3. **AscendSpeed** - LLM 训练问题

### 中价值仓库 (需选择性分析)

4. **tools** - 工具使用问题

### 低价值仓库 (当前数据少)

5. **mindspore** - 数据源不在 GitHub
6. **ascend-pytorch-crowdsource-op** - 活跃度低

---

## 下一步行动

### 立即分析

1. 分析 ModelZoo-PyTorch issues
   - 提取模型适配模式
   - 精度问题案例
   - 性能优化方法

2. 分析 samples issues
   - AscendCL 使用陷阱
   - 部署常见问题
   - API 误用案例

3. 分析 AscendSpeed issues
   - LLM 训练问题
   - 多卡并行故障
   - 显存优化技巧

### 补充收集

4. 寻找 MindSpore 的真实数据源
   - Gitee.com/mindspore
   - 昇腾社区论坛
   - CSDN 专栏

5. 补充其他平台数据
   - Gitee.com/ascend
   - 昇思社区

---

## 文件清单更新

### data/raw/ (新增 12 个文件)

- Ascend_mindspore_issues.json
- Ascend_mindspore_prs.json
- Ascend_ModelZoo-PyTorch_issues.json
- Ascend_ModelZoo-PyTorch_prs.json
- Ascend_AscendSpeed_issues.json
- Ascend_AscendSpeed_prs.json
- Ascend_samples_issues.json
- Ascend_samples_prs.json
- Ascend_tools_issues.json
- Ascend_tools_prs.json
- Ascend_ascend-pytorch-crowdsource-op_issues.json
- Ascend_ascend-pytorch-crowdsource-op_prs.json

### data/analyzed/ (新增)

- batch_new_repos_analysis.json

---

**收集工具**: scripts/batch_collect_simple.sh  
**收集状态**: ✓ 完成  
**下一步**: 深度分析 ModelZoo-PyTorch、samples、AscendSpeed
