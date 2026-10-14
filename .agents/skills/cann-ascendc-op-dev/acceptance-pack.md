# 通用 IT / 社区任务验收打包

适用于任意算子；列名按任务书性能表改。

## 五件套

```text
deliverables/
  README.md                 # 复现说明 + 链接
  scripts/                  # 一键自测脚本 + 测试工程 + README
  cases/                    # 官方/自建用例（json/csv/源码）
  logs/                     # 功能、精度、性能原始日志
  screenshots/              # 关键通过截图
  results/
    func_results.{md,csv}   # 功能/精度逐条
    perf_results.{md,csv}   # 性能逐条 vs 标杆
```

## 功能/精度表最少列

`序号 | case_id或用例名 | 关键参数 | 精度对比结论 | 结果 | 是否满足交付要求`

## 性能表最少列

`编号 | shape或配置 | 稀疏度或其它 | 自测耗时 | 标杆 | 门禁Gate | 相对标杆 | 是否满足交付 | 结果`

门禁计算：**以任务书为准**（例如「≥0.5×标杆」⇔ `测得 ≤ 2×标杆`）。

## 提交前

- [ ] 设计文档已合入 competitions  
- [ ] 代码分支/目录/邀请 Ascend-CANN 就绪  
- [ ] 五件套 + 逐条表  
- [ ] IT **重新**提交（若曾驳回或材料更新）  
- [ ] MR/Issue 贴上 deliverables 目录链接  

## 与任务书 §交付件映射

| 任务书项 | 本包对应 |
|----------|----------|
| 设计文档 | competitions 已合入链接 +（若要求）合入仓设计 Issue |
| 自测用例及测试代码 | `scripts/` + `cases/` + README |
| 自测报告 | 总报告 MD + `results/` + `screenshots/` + `logs/` |
| 易用性 Issue | Issue 链接 + 腾讯文档归档（任务书给出的 sheet） |
| 待验收代码地址 | fork + 分支 + 目录 + MR；Ascend-CANN Developer |

## ZIP 命名建议

```text
<账号>_<任务短名>_IT_deliverables.zip
# 例：hongwei-2026_CUBE_ptr_IT_deliverables.zip
```

解压后顶层即 `deliverables/` 五件套，勿只塞散文件。

## 类型 B（asc-devkit）额外

- `results/signature_ledger.md`：API 签名覆盖 / SKIP 原因  
- `scripts/` 内须写清 **`$ASC` sync** 步骤（**选择性文件**，禁止整棵 tip `dav_3510`/`utils`）  
- tip SHA / 上游 MR / Issue 链接写进 `README.md` 与 `IT_ACCEPTANCE.md`（勿留已关闭的旧 MR 号）  
- 截图若暂无 PNG：`screenshots/*.md` 写清 hidevlab 通过项 + 建议用户补终端截图；**勿假写已附图**  
- IT 若要求「任务书自带用例精度详情」：`logs/` 放带 `test pass!` 的原始 log；若主日志曾 FAIL，**另交 `*_PASS_*.log` 并在 README/表单写明覆盖关系**；更新材料后 **重新提交** IT  

