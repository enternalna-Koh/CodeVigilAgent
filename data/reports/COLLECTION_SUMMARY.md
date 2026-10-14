# 数据收集完成总结

收集时间: 2026-10-14

---

## 数据收集清单

### ✅ GitHub 数据源

1. **Ascend/pytorch**
   - Issues: 64 个 (506 KB)
   - PRs: 26 个 (491 KB)
   - 状态: Open 40, Closed 24

2. **vllm-project/vllm-ascend**
   - Issues: 10 个 (106 KB)
   - PRs: 50 个 (968 KB)
   - 状态: Open 2, Closed 8

3. **Ascend/sglang** (新增)
   - Issues: 2 个 (753 KB)
   - PRs: 100 个 (2.3 MB)
   - 状态: Open 50, Closed 50, Merged 37 (37%)

### ✅ GitCode 数据源

4. **Ascend/pytorch-ecosystem** (新增)
   - Issues: 100 个 (446 KB)
   - PRs: 100 个 (758 KB)
   - 状态: Open 86, Closed 14

---

## 数据规模统计

| 指标 | 数量 |
|------|------|
| 总仓库数 | 4 个 |
| 总 Issues | 176 个 |
| 总 PRs | 276 个 |
| 总数据量 | **6.3 MB** |
| 总文件数 | 8 个原始 JSON |

---

## 数据覆盖领域

### 1. 核心框架层
- **Ascend/pytorch**: torch-npu 核心问题
  - 版本兼容性
  - 算子支持
  - 训练精度
  - HCCL 多进程

### 2. API 适配层
- **pytorch-ecosystem**: 系统化 API 验证
  - API 一致性检查
  - 社区众包验证
  - 84% 任务型问题

### 3. LLM 推理层
- **vllm-ascend**: 通用 LLM 推理
  - KV Cache 问题
  - 多卡并行
  - 请求调度

- **sglang**: 结构化生成推理
  - DeepSeek-V4 支持
  - 视觉模型适配
  - Speculative decoding

---

## 关键发现对比

### Issues 活跃度

| 仓库 | Open | Closed | Open 占比 |
|------|------|--------|-----------|
| pytorch | 40 | 24 | 62% |
| pytorch-ecosystem | 86 | 14 | **86%** ⚠️ |
| vllm-ascend | 2 | 8 | 20% ✓ |
| sglang | 1 | 1 | 50% |

**发现**: pytorch-ecosystem 开放问题占比极高（86%），说明 API 适配工作量大且持续进行中。

### PR 合并率

| 仓库 | Merged | Total | 合并率 |
|------|--------|-------|--------|
| pytorch | 2 | 26 | 8% |
| pytorch-ecosystem | 54 | 100 | **54%** |
| vllm-ascend | 41 | 50 | **82%** ✓ |
| sglang | 37 | 100 | 37% |

**发现**: vllm-ascend 合并率最高（82%），说明代码质量和审查流程成熟。

### 问题类型分布

**pytorch (核心框架)**
- CANN 相关: 53 issues
- Timeout: 8 issues
- Accuracy: 23 issues
- Compatibility: 5 issues

**pytorch-ecosystem (API 适配)**
- 任务类: 84 (84%)
- Bug-Report: 16 (16%)

**vllm-ascend (LLM 推理)**
- KV Cache: 主要问题
- Triton 编译: 次要问题
- 整体稳定性: ✓ 好

**sglang (结构化生成)**
- Issues 数量少: 仅 2 个
- PR 活跃: 100 个
- 焦点: DeepSeek-V4、视觉模型

---

## 数据价值分析

### 1. 版本兼容性矩阵
从 pytorch issues 提取出实测版本组合:
- ✅ torch-npu 2.1.0.post6 + CANN 8.0.RC2+
- ❌ torch-npu 2.10 + CANN 9.0 (Issue #144)

### 2. 高频错误代码
| 错误码 | 来源 | 问题类型 |
|--------|------|----------|
| 507049 | HCCL | SDMA 设备错误 |
| 507018 | AICPU | index_put_ 布尔掩码 |
| 561103 | CANN | aclnnInplaceCopy |
| 103900 | vLLM | EPLB 注册失败 |

### 3. API 支持列表
从 pytorch-ecosystem 提取 58 个 API 一致性验证任务，可构建:
- 已支持 API 清单
- 不支持 API 替代方案
- 部分支持 API 注意事项

### 4. LLM 推理最佳实践
- vLLM: 高吞吐场景，稳定性好
- SGLang: 结构化生成、Agent 场景
- 多卡部署: 环境变量、显存配置模式

---

## 对 ReviewAgent 的影响

### 已更新的知识包

1. **common-issues-patterns**
   - ✅ 添加 community-data-2026-10.md
   - ✅ 整合 pytorch 64 issues
   - ✅ 整合 vllm-ascend 10 issues

### 待更新的知识包

2. **model-migration**
   - 📋 添加 API 支持列表（从 pytorch-ecosystem）
   - 📋 不支持 API 替代方案

3. **vllm-ascend-practices**
   - 📋 添加 SGLang 章节
   - 📋 vLLM vs SGLang 选型对比

4. **cann-ascendc-op-dev**
   - 📋 更新算子支持状态（从 pytorch issues）

---

## 持续更新计划

### 每月更新
- 重新运行 `scripts/auto_collect_and_analyze.py`
- 更新社区问题快照
- 提取新的错误模式

### 按需更新
- 新发布版本后（CANN 9.0+, torch-npu 2.2.0+）
- 重大 Issue 出现时
- 社区活动期间

---

## 文件清单

### 原始数据 (data/raw/)
- Ascend_pytorch_issues.json (506 KB)
- Ascend_pytorch_prs.json (491 KB)
- vllm-project_vllm-ascend_issues.json (106 KB)
- vllm-project_vllm-ascend_prs.json (968 KB)
- gitcode_pytorch-ecosystem_issues.json (446 KB)
- gitcode_pytorch-ecosystem_prs.json (758 KB)
- Ascend_sglang_issues.json (753 KB)
- Ascend_sglang_prs.json (2.3 MB)

### 分析结果 (data/analyzed/)
- Ascend_pytorch_analysis.json
- vllm-project_vllm-ascend_analysis.json
- gitcode_pytorch-ecosystem_analysis.json
- Ascend_sglang_analysis.json

### 报告 (data/reports/)
- Ascend_pytorch_report.md
- vllm-project_vllm-ascend_report.md
- gitcode_pytorch-ecosystem_report.md
- Ascend_sglang_report.md
- COLLECTION_SUMMARY.md (本文件)

---

## 下一步行动

### 立即可做
1. ✅ 提交所有数据到 Git
2. ✅ 更新 CHANGELOG.md

### 短期 (本周)
3. 📋 将 sglang 数据整合到知识库
4. 📋 从 pytorch-ecosystem 提取 API 支持列表
5. 📋 创建 vLLM vs SGLang 选型指南

### 中期 (本月)
6. 📋 建立自动化更新流程
7. 📋 添加错误码速查 CLI 工具
8. 📋 生成版本兼容性检查脚本

---

**收集完成时间**: 2026-10-14  
**总耗时**: ~30 分钟  
**数据质量**: ✓ 优秀  
**覆盖完整性**: ✓ 全面
