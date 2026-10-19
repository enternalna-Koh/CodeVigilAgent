---
name: api-consistency-community
description: >-
  Ascend for PyTorch API 一致性社区任务语境：官方 skill 路径、赛事说明引用、
  审核时以任务书为准。不内置未核验的精度/覆盖率阈值。
---

# API 一致性社区任务（Ascend for PyTorch）

## §0 权威来源（优先级）

1. **赛事 / 任务说明原文**（群公告同步）：[API 一致性对齐任务说明](https://docs.qq.com/doc/DT3R3eVNWdm1yUkdR)（含学习视频与任务规范；以文档更新为准）
2. **官方 Agent Skills（已迁移）**：  
   `https://gitcode.com/Ascend/pytorch-ecosystem/tree/master/01_tasks/resources/tools/agent_skills`
3. 本仓采集的 `pytorch-ecosystem` Issue/PR 案例（`data/raw/gitcode_*`）
4. 本 skill 仅作导航，**不得**覆盖任务书条文

## §1 可安装官方 Skill

在 ReviewAgent 对话中：

```text
/skill install torch-npu-pr-review
/skill install torch-npu-api-target-analyse
/skill load torch-npu-pr-review
```

| Skill | 用途 |
|-------|------|
| `torch-npu-pr-review` | PR / Issue / 成果包审核与结构化报告 |
| `torch-npu-api-target-analyse` | API 目标分析与成果包 |
| `torch-npu-doc-writer` | 文档补齐 |
| `torch-npu-remote-runner` / `torch-npu-server-runner` | 远程/服务侧运行辅助 |

安装目标目录：`~/.reviewagent/skills/`（不写入待审仓库）。

## §2 昇腾文档 MCP（内置）

官方只读文档 MCP：`ascend-doc-mcp`（见 Ascend/agent-skills `docs/doc-mcp`）。

```text
/mcp
/mcp tools ascend-doc
```

需要 Node.js ≥ 22 与 `npx`。MCP **只读文档**，不执行仓库写操作；最终结论仍由模型生成，生产前请核对文档原文链接。

## §3 审核红线（本工具）

- 阈值、必测 API 列表、分支矩阵：**只引用任务书 / 官方 skill**，本文件不抄数字。
- AtomGit 链接先规范化为 `https://gitcode.com/` 再拉取。
- 缺 CI / 缺师生评论时标注「未知」，不编造通过结论。
- 群内激励/课程信息仅作社区语境，不作为验收条款。

## §4 与本仓其他 skill 的关系

| 场景 | 优先 |
|------|------|
| API 一致性社区任务 / pytorch-ecosystem | 本 skill → `torch-npu-pr-review` |
| 通用 torch-npu 迁移 | `model-migration` |
| 算子社区任务 | `cann-ascendc-op-dev` + cann-op-checker |
