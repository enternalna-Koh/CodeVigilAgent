# 实例：Basic API CUBE 指针化（类型 B）

任务示例：`09-AscendC-Basic-API-CUBE` · 合入仓 `cann/asc-devkit`  
硬件：Ascend950PR · CANN 9.1.0 · `dav-3510` · 基线 tag `v9.1.0`  
性能：**无门禁**

## 流程摘要

1. 设计 PR → competitions 合入；asc-devkit 开设计归档 Issue  
2. fork `asc-devkit`，分支基于 `v9.1.0`  
3. 改 `include/basic_api` + `impl/basic_api`；新增 `GetUnderlyingPtr`  
4. **sync 到 `$ASC`** 后再编官方 examples  
5. 上游 MR；邀请 Ascend-CANN；易用性 Issue（cacheMode=0）+ 腾讯文档  
6. IT 五件套 ZIP  

## 950 实测建议矩阵

| 样例 | 架构 | 建议 |
|------|------|------|
| load_data_2dv2 / mmad / fixpipe_l0c2gm | 3510 | 必测（核心） |
| fixpipe_l0c2l1 / l0c2ub | 3510 | 必测（扩展） |
| mmad_load3dv2 S4 | 3510 | 必测（3D） |
| mmad_mx / load_data_2dmx | 3510 | **可测必试** |
| mmad_with_sparse | 仅 A2/A3 | **SKIP** |
| Dump / SPM | 无独立样例 | **SKIP** + 台账 |

## hidevlab 坑

- `run_one` 留在 `*/build` → 下一路径套娃 → 用子 shell 或 `cd` 回仓根  
- `mmad_load3dv2` 的 `gen_data` **必须** `-m -k -n`  
- gen_data 参数格式因样例而异；`test pass!` 以 verify 为准  
- 改 `.asc` 后确认 make 重新编译了 `.asc.o`，否则仍是旧 Tensor 路径  

### `$ASC` 污染与 Fixpipe UB（2026-09 实战）

| 现象 | 根因 | 正确做法 |
|------|------|----------|
| `Std::ceil_div` / `cmath.h` not found / `used before defined` | tip 样例依赖 `Std::ceil_div`；乱拷/`mv` 了 `$ASC/.../cmath.h` | 样例本地 `CeilDiv`；**勿**整棵 sync `impl/utils` |
| `FLOAT8`/`asc_dump_*`/`tuple get`/`asc_time_stamp` 编译炸 | tip `dav_3510/` 或 tip `impl/utils` 盖到 9.1.0 | 从 `basic_api.bak.*` 整树恢复；只 sync **5 个指针文件** |
| `fixpipe_l0c2ub` **actual 全 0**、L1/GM 仍可能绿 | `$ASC` 被污染或半残恢复 | bak 恢复 + 仅 5 文件；编过后再 verify；仍全 0 → **新 hidevlab / 重装 cann**，勿再动 utils |
| A/B：纯 bak 也全 0 | 环境已坏，不是指针 diff 单独引入 | 先 L1 对照；确认后再怪代码 |
| IT 要「精度详情日志」 | 主日志里 ub 曾 FAIL | 单独交付 `*_S1_PASS_*.log`（含 `test pass!`）；表单写清**以 PASS 文件为准**覆盖旧 FAIL |

**安全 sync（CUBE ptr）：**

```bash
# bak 后只拷这 5 个（路径相对仓根）
sudo cp -a include/basic_api/kernel_operator_fixpipe_intf.h "$ASC/include/basic_api/"
sudo cp -a include/basic_api/kernel_operator_mm_intf.h "$ASC/include/basic_api/"
sudo cp -a impl/basic_api/kernel_operator_fixpipe_intf_impl.h "$ASC/impl/basic_api/"
sudo cp -a impl/basic_api/kernel_operator_mm_intf_impl.h "$ASC/impl/basic_api/"
sudo mkdir -p "$ASC/impl/basic_api/utils"
sudo cp -a impl/basic_api/utils/kernel_utils_ptr.h "$ASC/impl/basic_api/utils/"
```

精度日志可推 fork 分支（如 `it/precision-logs-*`）；`git add -f`（若 `*.log` 被 ignore）；分支与 feat 历史 diverged 时 **勿 pull 合并**，在 fork 精度分支上 cherry-pick/只加 log 再 push。

## CI 硬坑（!6109 实战）

1. **多 AS 指针重载必须 Device-only 门控**  
   `#if !defined(ASCENDC_CPU_DEBUG) && defined(__CCE_IS_AICORE__)`  
   否则 `ascendc_ut_adv_api_kernel_*` 在空地址空间宏下报 `redefinition`。
2. **pre-commit = clang-format 18.1.8**；本地用同版本 `-i` 后再推。
3. **`stat/needs-squash`**：始终保持相对 master **1 个 tip commit**。
4. 推 tip 后确认标签：`cann-cla/yes` + `ci-pipeline-passed`；再 `@chenyiyuan` `@wuyang_hw` 检视。

## 交付链接样例（hongwei-2026）

- PR：https://gitcode.com/cann/asc-devkit/merge_requests/6109  
- Issue：#1685 #1686  
- tip：以 MR HEAD / `ci-pipeline-passed` 为准  
- 精度分支：`it/precision-logs-20260921`（含 `fixpipe_l0c2l1` / `l0c2ub` S1 PASS log）  
- ZIP：`hongwei-2026_CUBE_ptr_IT_deliverables.zip`（五件套；`logs/*_S1_PASS_*.log` 覆盖旧主日志 ub FAIL）  

