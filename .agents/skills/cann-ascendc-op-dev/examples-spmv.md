# 案例：SpMV（08-SPMV）——流程复用，数字勿照搬

本案例说明 skill 在真实任务上的落点；**其它算子只复用方法**。

## 关键链接

| 项 | URL |
|----|-----|
| 设计文档（已合入） | https://gitcode.com/cann/cann-ops-competitions/blob/master/04_tasks/01_community-task-2026/tasklist/08-SPMV/hongwei-2026/docs/design.md |
| 设计 PR | https://gitcode.com/cann/cann-ops-competitions/merge_requests/1222 |
| 合入仓 MR | https://gitcode.com/cann/ops-sparse/merge_requests/158 |
| 交付包 | https://gitcode.com/hongwei-2026/ops-sparse/tree/feat/spmv-arch35-hongwei-2026/docs/acceptance/deliverables |

## 任务特征（举例）

- 合入：`cann/ops-sparse` → `sparse/spmv/arch35/`  
- 硬件：Atlas 950PR  
- 性能：相对标杆 ≥0.5×（P-01~P-04）  
- 精度用例：`case_200.json` 200 条 + 仓内功能套件  

## 可复用经验

1. 目录从错误的 `05-3-SPMV` 迁到 `08-SPMV` 才过评审。  
2. AscendC 9.2：SIMT helper 必须 `__simt_callee__`。  
3. IT 曾因缺少「逐条结果表」驳回 → 补 scripts/cases/logs/screenshots/results。  
4. 设计已合入但实现被其它团队抢先时，简历/交付口径写清「设计合入」。
