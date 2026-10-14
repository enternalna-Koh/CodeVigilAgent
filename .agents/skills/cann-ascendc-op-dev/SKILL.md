---
name: cann-ascendc-op-dev
description: >-
  End-to-end AscendC / CANN community-task development for ANY 2026 task type:
  ops (math/nn/sparse/transformer), Basic API pointerization (CUBE/VECTOR/DMA /
  asc-devkit), design→MR→CI→IT. Covers claim, design.md, Host/Kernel/SIMT,
  hidevlab 950, architecture skip ledgers, codecheck, precision/perf gates,
  Ascend-CANN invite, and acceptance-pack ZIPs. Use for SpMV, SageAttention,
  Basic API CUBE, or any cann-ops-competitions tasklist entry.
---

# CANN AscendC / 社区任务通用开发 Skill

适用：**全部** CANN 社区任务 2026——算子仓合入 **或** Basic API / 库接口扩展（`asc-devkit`）等。  
目标：认领 → 设计 → 实现 → 自测 → IT 验收 → 合入，少踩目录、架构、CI、交付坑。

## 何时启用

- 任意 `tasklist/<任务>/` 认领与开发  
- `design.md` / competitions PR / 设计评审  
- 合入仓：`ops-math` / `ops-nn` / `ops-sparse` / `ops-transformer` / **`asc-devkit`** 等（**以任务书为准**）  
- hidevlab 950 / CANN 9.x、样例改指针、系统头 sync  
- CI：`/compile` `/check-cla`、codecheck、AscendC SIMT  
- IT 五件套 ZIP + Ascend-CANN Developer  

## 官方入口（先读任务书）

| 资源 | 链接 |
|------|------|
| 社区任务 README | https://gitcode.com/cann/cann-ops-competitions/blob/master/04_tasks/01_community-task-2026/README.md |
| 设计模板 | https://gitcode.com/cann/cann-ops-competitions/blob/master/04_tasks/01_community-task-2026/resources/design_template.md |
| 认领讨论 | https://gitcode.com/org/cann/discussions/22 |
| 流程注意 | https://gitcode.com/org/cann/discussions/39 |
| 精度（常用） | https://gitcode.com/cann/opbase/blob/master/docs/zh/ops_precision_standard/experimental_standard.md |

**优先级**：任务书条文 > 官方讨论/模板 > 本 skill。

详见 [official-requirements.md](official-requirements.md)。

---

## 0. 任务分型（先分型再动手）

| 类型 | 典型目录/书名 | 合入仓 | 自测形态 | 性能 |
|------|---------------|--------|----------|------|
| A 算子开发 | SpMV / SageAttention / 数学算子 | ops-\* | build.sh + case + perf | 常有 Gate |
| B 库/API 扩展 | Basic API 指针化 CUBE/VECTOR/DMA | **asc-devkit** | 官方 `examples/` 改指针 + verify | **可能无门禁** |
| C 仅文档 | 设计评审阶段 | competitions | 无 | 无 |

**Agent 第一步**：从任务书抄齐——任务编号、tasklist 目录名、合入仓、硬件（950/A2/A3）、CANN 版本、精度链接、性能表（或「无」）、交付件清单、易用性腾讯文档链接。

---

## 1. 端到端流程（通用）

```text
认领 → 核对 tasklist 现网目录名 → 设计 PR（仅 design.md）→ @评审 →【审核通过】
  → fork 合入仓 → 开发/自测 → 上游 MR + /compile /check-cla
  → 邀请 Ascend-CANN → 五件套 ZIP → IT 提交 → 通过后合入
```

### 1.1 目录与 PR

```text
04_tasks/01_community-task-2026/tasklist/<任务目录>/<Team或账号>/docs/design.md
```

- 一个任务全局只保持 **1 个 open 设计 PR**  
- 设计阶段 **不夹带** 实现代码  

### 1.2 设计必含

需求背景 / 需求分析 / 详细设计 / 可维可测；测试用例要能落地（F/Q/B/N 或签名台账）。  
**禁止**把未跑通结果写成已通过。

### 1.3 合入仓不要猜

| 举例 | 仓 |
|------|-----|
| 数学 | cann/ops-math |
| 稀疏 | cann/ops-sparse |
| NN | cann/ops-nn |
| Attention | cann/ops-transformer |
| Basic API / CUBE 指针化 | **cann/asc-devkit**（`include/basic_api` + `impl/basic_api`） |

### 1.4 验收固定动作

1. 自测达标（精度 + 性能或「无门禁」说明）  
2. fork 邀请 **`Ascend-CANN` = Developer**（网页确认成员列表）  
3. 易用性 Issue（标题带 `【AscendC CAPI社区任务】` 或 `【社区任务】`）+ 腾讯文档归档  
4. IT 上传五件套；驳回须 **重新提交**  
5. 设计归档 Issue（若任务书要求写到合入仓 issues）  

---

## 2. 类型 B 专章：Basic API / asc-devkit

### 2.1 约束

- 只改任务书清单内 API（CUBE / VECTOR / DMA **分册互不改**）  
- 保留 Tensor 重载；新增硬件指针重载，直调既有 `*Cal`/`*Impl`  
- `GetUnderlyingPtr`：指针直传，Tensor 走 `GetPhyAddr()`  
- 裸 `__gm__*` 常 **无法 ExtractCacheMode** → 固定 `cacheMode=0` 并开易用性 Issue  

### 2.2 hidevlab 铁律（`$ASC` sync）

```text
样例默认 include 系统 $ASC 头，不是 working tree。
测指针重载前必须把「本次改动的头」同步进 $ASC。
```

**推荐：选择性 sync（防污染）**

1. 先备份：`cp -a $ASC/include/basic_api $ASC/include/basic_api.bak.$(date +%Y%m%d_%H%M%S)`（`impl` 同理）  
2. **只拷本次改过的文件**（CUBE 指针化常见 5 件）：  
   - `include/basic_api/kernel_operator_{mm,fixpipe}_intf.h`  
   - `impl/basic_api/kernel_operator_{mm,fixpipe}_intf_impl.h`  
   - `impl/basic_api/utils/kernel_utils_ptr.h`  
3. **禁止**整棵 `cp tip → $ASC`：  
   - ❌ `impl/basic_api/dav_3510/`（tip 与 CANN 9.1.0 枚举/`__asc_aicore` 对不上）  
   - ❌ `impl/utils/` / `include/utils/`（`cmath`/`tuple`/`asc_time` 版本炸）  
4. 污染后：从 `*.bak.*` **整树恢复** `basic_api`，再只 sync 上述改动文件  

**样例与 `ceil_div`**

- tip 样例常写 `AscendC::Std::ceil_div`；**9.1.0 系统头可能没有**  
- 自测可：`v9.1.0` 样例，或样例内本地 `CeilDiv` / 去掉 `#include "utils/std/cmath.h"`  
- **不要**为补 `ceil_div` 把 tip 的整棵 `impl/utils` 拷进 `$ASC`

- 基线 tag 常钉 **`v9.1.0`**  
- 架构：`dav-3510` = 950；`dav-2201` = A2/A3  
- `run_one` 必须用**绝对路径**，避免卡在 `*/build` 套路径  

### 2.3 架构跳过台账（验收可接受）

| 现象 | 处理 |
|------|------|
| 样例 README 仅 A2/A3（如 Sparse） | **SKIP** + 台账写原因 |
| API `#if __NPU_ARCH__==2201` | 950 SKIP |
| 无官方样例且 Cal 仍吃 Tensor（Dump/部分 Sparse Load） | 台账 D/SKIP，勿假 PASS |
| MX 等 950 明确支持 | **必须尝试实机** |

### 2.4 实例

CUBE 指针化（`09-AscendC-Basic-API-CUBE`）要点见 [examples-basic-api-cube.md](examples-basic-api-cube.md)。

---

## 3. 实现层（算子 + API 共用）

### 3.1 工程

- Ascend C 规范；Host/Kernel 分离（算子）或 intf/impl 分离（Basic API）  
- Windows PowerShell 用 `;` 不用 `&&`  
- 真机：hidevlab；本机 CPU **不能**替代 950 门禁  

### 3.2 SIMT（arch35 高频）

| 规则 | 做法 |
|------|------|
| `__simt_vf__` | 仅 launch；`void` + `__launch_bounds__` |
| 指针 | 仅 `__gm__` / `__ubuf__` |
| helper | `__simt_callee__` |

见 [pitfalls.md](pitfalls.md)。

### 3.3 CI

- 行数/复杂度超限 → 拆文件  
- MR：`/compile` `/check-cla`  
- 失败先对 tip COMMIT_ID  
- **asc-devkit Basic API**：多地址空间指针重载必须 Device-only（见 [pitfalls.md](pitfalls.md) §E）；pre-commit 对齐 **clang-format 18.1.8**；标签 `stat/needs-squash` → 压成单 commit  
- CI 绿后立刻 `@` 任务检视人（CUBE 常见 `@chenyiyuan` `@wuyang_hw`），勿等合入窗关掉  


### 3.4 精度 / 性能

- 精度：任务书 → 否则 opbase 实验标准  
- 性能：有表则抄进脚本常量；**写明「无门禁」**也算合规  

---

## 4. IT 五件套（ZIP 必须长这样）

见 [acceptance-pack.md](acceptance-pack.md)。

```text
deliverables/
  README.md
  scripts/          # 一键自测 + README
  cases/            # 用例清单
  logs/             # 原始日志
  screenshots/      # 关键截图
  results/
    func_results.md # 功能/精度逐条
    perf_results.md # 性能逐条或「无门禁」
```

提交前勾选：设计合入、Ascend-CANN、五件套、IT 上传、易用性文档归档。

---

## 5. Agent 执行清单（任意新任务）

```text
- [ ] 分型 A/B/C；抄任务书：目录名/仓/硬件/CANN/精度/性能/交付件
- [ ] 上游 tasklist 现网目录名核对
- [ ] design.md → competitions PR → @评审 → 审核通过
- [ ] fork 合入仓；基线 tag/分支正确（asc-devkit 常 v9.1.0）
- [ ] 实现；类型 B **选择性** sync `$ASC`（禁 tip `dav_3510`/`utils` 整棵）
- [ ] 可测样例全绿；不可测项写入 SKIP 台账（勿假 PASS）
- [ ] MR + /compile /check-cla；设计/易用性 Issue
- [ ] 邀请 Ascend-CANN（网页确认）
- [ ] 按 acceptance-pack 打 ZIP → IT
- [ ] 腾讯文档归档易用性链接
```

---

## 6. 实例附录

- [examples-spmv.md](examples-spmv.md) — 类型 A（ops-sparse）  
- [examples-basic-api-cube.md](examples-basic-api-cube.md) — 类型 B（asc-devkit CUBE）  

**禁止**把 SpMV 门禁数字或合入路径照搬到其他任务。

## 附加文件

- [official-requirements.md](official-requirements.md)  
- [pitfalls.md](pitfalls.md)  
- [acceptance-pack.md](acceptance-pack.md)  
- [examples-spmv.md](examples-spmv.md)  
- [examples-basic-api-cube.md](examples-basic-api-cube.md)  
