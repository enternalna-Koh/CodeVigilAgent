# ReviewAgent - 数据收集完成报告

## 🎉 任务完成总结

### 📊 数据收集成果

**成功收集了 74 个真实的社区问题**

| 仓库 | Open Issues | Closed Issues | 总计 | PRs |
|------|-------------|---------------|------|-----|
| Ascend/pytorch | 40 | 24 | **64** | 26 (2 merged) |
| vllm-project/vllm-ascend | 2 | 8 | **10** | 50 (41 merged) |

### 📁 生成的数据文件

```
data/
├── raw/                          # 原始 JSON 数据
│   ├── Ascend_pytorch_issues.json
│   ├── Ascend_pytorch_prs.json
│   ├── vllm-project_vllm-ascend_issues.json
│   └── vllm-project_vllm-ascend_prs.json
│
├── analyzed/                     # 分析后的结构化数据
│   ├── Ascend_pytorch_analysis.json
│   └── vllm-project_vllm-ascend_analysis.json
│
└── reports/                      # 人类可读报告
    ├── Ascend_pytorch_report.md
    └── vllm-project_vllm-ascend_report.md
```

**数据规模**: ~35,000 行 JSON 数据

### 🔍 关键发现

#### 1. 版本兼容性问题（最高优先级）

**问题 Issues**: #144, #148, #99

| PyTorch | torch-npu | CANN | 状态 |
|---------|-----------|------|------|
| 2.1.0 | 2.1.0.post6 | 8.0.RC2+ | ✅ **推荐** |
| 2.1.0 | 2.1.0.post3 | 8.0.RC1 | ✅ 稳定 |
| 2.10 | ? | 9.0 | ❌ 已知问题 |
| 2.7.1 | 2.7.1 | 8.3.RC1 | ❌ 不兼容 |

#### 2. 精度传播误差（训练场景）

**典型案例**: Issue #107 - Qwen-3VL-8B SFT 训练

```
Forward loss 差距: <1%  ✓
Layer 35 (最后层) 梯度误差: <1%  ✓
Layer 1 (第一层) 梯度误差: 50%-100%+  ✗
```

**根本原因**: FP16 反向传播误差累积

**解决方案**:
- FP32 累积梯度
- 梯度裁剪 (max_norm=1.0)
- 降低学习率

#### 3. HCCL 多进程问题

**高频 Issues**: #54, #166, #96

| 问题 | 错误码 | 解决方案 |
|------|--------|----------|
| HCCL_EXEC_TIMEOUT=0 不生效 | - | Python 代码中显式设置 |
| ProcessGroupHCCL 创建失败 | 507049 | `CAMEM_SLEEP_MODE=0` |
| 多进程 devptr 断言失败 | - | 每进程独占 NPU |

#### 4. torch.compile 编译问题

**Issues**: #154, #102, #97

- 硬件访问超时
- UB overflow 错误
- 缺少 triton_heuristics 模块

**临时方案**: 禁用 compile 或使用 `mode="reduce-overhead"`

#### 5. vLLM-Ascend 稳定性评估

**关键指标**:
- Open Issues: **仅 2 个**（vs torch-npu 的 40 个）
- PR 合并率: **82%** (41/50)
- 问题类型: 主要是 KV cache 和 Triton 编译

**已知问题**:
- KV-pool lookup server 线程静默死亡 (#17923) - 已修复
- EPLB 初始化失败 (错误 103900) - 有解决方案

### 📚 新增知识文档

**community-data-2026-10.md** (新增)

包含以下章节：

1. **§1 torch-npu 核心问题模式** (5 大类)
   - 版本兼容性矩阵
   - 精度传播误差诊断
   - HCCL 超时与多进程
   - torch.compile 编译失败
   - 算子不支持或行为不一致

2. **§2 vLLM-Ascend 核心问题模式** (3 大类)
   - KV Cache 相关错误
   - Triton 编译问题
   - GLM-5 配置问题

3. **§3 高频错误代码速查**
   - CANN 错误码表
   - torch-npu 常见报错

4. **§4 最佳实践**
   - 环境配置清单
   - 代码模式示例
   - 避坑指南

5. **§5 社区活跃问题快照**
   - 当前 open issues 列表
   - 优先级排序

### 🛠️ 工具改进

**scripts/auto_collect_and_analyze.py** (完善版)

功能：
- ✅ 自动获取 GitHub Issues/PRs
- ✅ 错误模式分类（OOM/Timeout/Compatibility/Performance/Accuracy）
- ✅ 生成结构化报告（JSON + Markdown）
- ✅ 支持多仓库批量收集
- ✅ 避免 rate limit（自动重试）

### 📈 统计数据

#### 问题分类统计

**Ascend/pytorch**:
- CANN 相关: **53 issues**
- Timeout: **8 issues**
- Accuracy: **23 issues**
- Performance: **5 issues**
- Compatibility: **5 issues**
- OOM: **1 issue**

**vllm-project/vllm-ascend**:
- CANN: **9 issues**
- Timeout: **3 issues**
- Accuracy: **4 issues**
- Compatibility: **2 issues**

#### PR 类型分布

**Ascend/pytorch**:
- Bugfix: 3
- Feature: 2
- Documentation: 1
- Refactor: 1
- Other: 19

**vllm-project/vllm-ascend**:
- Feature: 16
- Bugfix: 10
- Documentation: 8
- Other: 15
- Refactor: 1

### 🎯 实际价值

通过这次数据收集，ReviewAgent 现在可以：

1. **精准诊断版本兼容性问题**
   - 识别不兼容的版本组合
   - 推荐已验证的稳定组合

2. **快速定位高频错误**
   - 错误码 507049/507018/561103/103900 即时匹配
   - 提供已验证的解决方案

3. **预测潜在问题**
   - torch.compile 使用场景告警
   - 多进程训练配置检查

4. **提供社区最佳实践**
   - 基于真实案例的代码模式
   - 从问题中提炼的避坑指南

### 🚀 下一步

1. **持续更新**
   - 定期运行 `scripts/auto_collect_and_analyze.py`
   - 每月更新社区问题快照

2. **扩展数据源**
   - Ascend/samples Issues
   - Ascend/ModelZoo-PyTorch Issues
   - 昇腾社区论坛精华帖

3. **智能体优化**
   - 将高频问题模式编码到检查逻辑
   - 自动生成诊断脚本

### 📦 Git 提交

```bash
e0bfaa3 Integrate real community issues data into knowledge base
  - 新增 community-data-2026-10.md (真实问题补充)
  - 收集 74 个 issues 数据
  - 生成结构化报告
  - 35,000+ 行 JSON 数据

38deb23 Add comprehensive project summary
a23159e Add GitHub data collection tools
2f5b668 Add vLLM-Ascend specialized knowledge pack
4f24c0a Add common-issues-patterns skill for community troubleshooting
```

---

## ✅ 任务完成检查清单

- [x] 收集 Ascend/pytorch Issues (64 个)
- [x] 收集 vllm-project/vllm-ascend Issues (10 个)
- [x] 分析错误模式并分类
- [x] 提取版本兼容性矩阵
- [x] 生成结构化报告
- [x] 创建知识文档补充
- [x] 更新 CHANGELOG
- [x] 提交到 Git

---

**生成时间**: 2026-10-14  
**数据来源**: GitHub API  
**工具**: scripts/auto_collect_and_analyze.py  
**状态**: ✅ 完成
