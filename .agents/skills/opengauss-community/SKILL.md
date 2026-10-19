---
name: opengauss-community
description: >-
  openGauss 社区（Plugin / examples / docs）Issue/PR 审核要点：缺陷模板、
  CI 门禁、老师与审核人对话模式。配合本地采集的 review_dialogs 使用。
---

# openGauss 社区审核 Skill

## §0 范围

| 仓库 | 关注点 |
|------|--------|
| `opengauss/Plugin` | 插件缺陷、SIG 标签、复现步骤 |
| `opengauss/examples` | 示例可用性、版本匹配 |
| `opengauss/docs` | 文档 PR（如 #8872）、表述与链接正确性 |

数据源（本地采集后）：

- `data/raw/gitcode_opengauss_*_{issues,prs}.json`
- `data/ci_runs/gitcode_opengauss_*_ci.json`
- `data/review_dialogs/gitcode_opengauss_*_dialogs.json`

采集：`python ascend_cli.py collect --community opengauss`（需 `GITCODE_TOKEN`）。

## §1 Issue / 缺陷模板检查

优先确认是否具备：

- 测试类型 / 版本 / 问题描述 / OS 与硬件 / 复现步骤 / 期望与实际 / 日志
- 标签（如 `sig/Plugin`）与经办人（tester/assignee）是否合理
- 二进制/字符边界（如 `0x00` 截断类）需标出安全与数据完整性影响

缺项标 WARN，不可复现且无日志 → 要求补充，勿直接判关闭。

## §2 CI 流水

- 审查 PR 时读取上下文中的 `ci.check_runs`（若有）
- 失败项记录 `name` / `conclusion` / `details_url`；无 CI 数据标注「CI 未知」
- 不以「作者自称通过」替代门禁结论

## §3 老师与审核人对话

本地 `review_dialogs` 中 `role=reviewer` 的发言优先提炼：

- 必改项（模板缺失、用例不足、版本未声明）
- 风格：是否要求最小复现、是否指向 docs/examples
- 作者回复是否闭环（已修 / 将修 / 需澄清）

报告中区分 **审核意见** 与 **作者说明**，勿合并成单一叙述。

## §4 报告级别

| 级别 | 含义 |
|------|------|
| BLOCKER | 明显数据损坏/安全、CI 红且无豁免说明 |
| CRITICAL | 无法复现且缺关键环境信息仍声称已修 |
| WARN | 模板不完整、文档链接失效、缺讨论闭环 |
| NOTE | 风格/措辞、可选测试扩展 |

## §5 不做

- 不把昇腾 CANN 红线套到 openGauss
- 不编造未采集到的师生对话或 CI 结果
