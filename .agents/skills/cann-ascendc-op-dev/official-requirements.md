# 官方要求摘录（CANN 社区任务 2026）

来源以 GitCode 原文为准；本文件便于 Agent 快速对照。若与线上不一致，**以线上为准**。

## 1. 参与方式（README）

来源：https://gitcode.com/cann/cann-ops-competitions/blob/master/04_tasks/01_community-task-2026/README.md

1. **认领任务**：https://gitcode.com/org/cann/discussions/22  
2. **创建提交目录**：以团队名 / GitCode 账号为名  
3. **输出设计文档**：参考设计模板，提交到对应算子目录 `docs/design.md`，评审并合入  
4. **开发算子**：`docs/`、`examples/`、`op_api/`（可选）、`op_host/`、`op_kernel/`、`tests/`  
5. **提交作品**：PR 到任务书对应仓（设计仓 competitions；代码仓见任务书）

## 2. 目录结构

设计阶段最少：

```text
YourTeamName/
└── docs/
    └── design.md           # 必选
```

任务完成时 README 期望：

```text
YourTeamName/
├── docs/
│   ├── aclnn{OpName}.md    # API 文档（必选，若任务走 aclnn）
│   └── design.md
├── examples/               # 必选
├── op_api/                 # 可选
├── op_host/                # 必选
├── op_kernel/              # 必选
├── tests/                  # 可选但强烈建议
├── CMakeLists.txt          # 必选
└── README.md               # 必选
```

实际 2026 多数算子：**设计合入 `cann-ops-competitions`，代码合入任务书指定的 `ops-*` 仓路径**。两套结构都要会读任务书。

路径形态：

```text
04_tasks/01_community-task-2026/tasklist/<任务编号-算子名>/<TeamName>/docs/design.md
```

## 3. 设计文档模板结构（required）

模板：https://gitcode.com/cann/cann-ops-competitions/blob/master/04_tasks/01_community-task-2026/resources/design_template.md

| 大章 | 要点 |
|------|------|
| 需求背景 | 需求来源、背景介绍、对标实现现状、功能分析 |
| 需求分析 | 需求描述、需求拆解（功能点列表） |
| 详细设计 | 公式、dtype、shape；Host tiling/分核/UB；Kernel Init/Process；硬件表；约束 |
| 可维可测 | 精度标准、性能标准、兼容性 |

文档要求（README）：含算子功能、设计思路、性能优化方案。  
API 文档要求：函数原型、参数、返回值、约束、示例。

## 4. 流程与注意事项（讨论 39 要点）

来源：https://gitcode.com/org/cann/discussions/39

### 设计审核

- 提交 **PR 到 competitions 对应目录**，不是只开 Issue  
- PR 标题：`【社区任务】${算子名称}算子设计文档`  
- 对照设计文档 checklist 自查  
- 评论区 @ 检视人（帖内账号为准）；按评论修改后再 @ 复核  
- 评审通过后评论会告知 **【审核通过】**  

### 验收阶段常见状态

- 提交交付件 → 初审 → 排队测试 → 测试中 →（不通过则驳回短信）→ PR 合入 → 最终审核  
- 测试通过后可能停止其他报名者测试（以官方通知为准）  
- 代码 PR 合入后逐条回复检视意见  

### 求助

- 任务讨论帖留言，或在对应代码仓提 Issue  
- Issue 标题前缀：`【社区任务】`  
- 正文补充【队名】【任务序号】，并 @ 指定支持账号  

## 5. 代码与质量（README）

- 遵循 Ascend C 编码规范  
- 提供完整测试用例  
- 确保精度和性能达标（**具体阈值看任务书**）  

## 6. 设计文档 Checklist（实操版）

提交前打勾：

- [ ] 路径：`tasklist/<现网任务目录>/<账号>/docs/design.md`  
- [ ] 标题含【社区任务】与算子名  
- [ ] PR diff **仅本任务设计文档**（无其它任务/密钥）  
- [ ] 模板四大块齐全；含公式、dtype、Host/Kernel、硬件、约束  
- [ ] 有可执行级测试用例设计（F/Q/B/N 或任务书矩阵）  
- [ ] 有架构/流程示意（Mermaid 或图）  
- [ ] 性能/精度写的是标准与方案，未伪造「已通过」  
- [ ] 提交邮箱/CLA 与 GitCode 账号一致；需要时 `/check-cla`  
- [ ] @ 检视人；全局仅 1 个 open 设计 PR  

## 7. 任务书差异（Agent 必查字段）

每开新任务，从任务书抽出一张表：

| 字段 | 填什么 |
|------|--------|
| 任务编号/目录名 | 如 `08-SPMV`、`08-11-sageAttention2` |
| 适配硬件 | 如 Atlas 950PR / A2 |
| CANN 版本 | 如 9.1.0 / 9.2.0-beta |
| 开发框架 | Ascend C / +CATLASS / PyTorch 适配等 |
| 合入仓与路径 | ops-sparse / ops-transformer / … |
| 对标 | cuSPARSE / FIA / TBE / 开源 CUDA |
| 精度标准 | 链接或条文 |
| 性能门禁 | 0.5× 标杆、1.6× FIA 等 |
| 自测用例包 | case_200.json、官方 ATK 等 |
| 交付件列表 | 设计/自测代码/报告/代码地址 |
