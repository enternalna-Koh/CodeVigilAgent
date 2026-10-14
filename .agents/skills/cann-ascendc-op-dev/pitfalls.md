# 通用踩坑表（AscendC / 社区任务）

## A. 流程与目录

| 现象 | 原因 | 解法 |
|------|------|------|
| 老师说目录不对 | 用了旧月份/错误 tasklist 名 | `git ls-tree` 对照上游；迁到现网目录 |
| 设计 PR 混了实现代码 | 阶段不对 | 设计阶段只留 `design.md` |
| 两个 open PR | 改目录后未关旧 | 关旧开新，保持 1 个 open |
| CLA 红 | 未签/邮箱不一致 | 签署后 `/check-cla` |
| 评审无响应 | 未 @ 人或标题不规范 | 标题加【社区任务】；@ 讨论 39 检视人 |

## B. Kernel / Host（跨算子）

| 现象 | 原因 | 解法 |
|------|------|------|
| `__simt_vf__` may only call `__simt_callee__` | helper 误标 vf | helper → `__simt_callee__` |
| must return void | vf 非 void | entry/helper 返回类型改为 void 或降为 callee |
| pointer not `__gm__`/`__ubuf__` | 裸指针进 SIMT | 加地址空间属性 |
| UB 溢出 / 精度炸 | tile 过大或类型转换漏 | 按 UB 与 dtype 重算 tile；半精度注意累加类型 |
| 多核结果不稳定 | Atomic 累加顺序 | 确定性路径：预处理重排 / 单写者 / 固定归约 |
| tilingKey 走错分支 | Host 未传清 | 明确 key 语义与单测覆盖 |

## C. 工程与 CI

| 现象 | 原因 | 解法 |
|------|------|------|
| codecheck 超行数 | 单文件过大 | 拆分 header / cpp |
| CI 报已修过的错 | 构建旧 commit | 看日志 COMMIT_ID；再 `/compile` |
| 本机无法验收性能 | 无任务指定 NPU | hidevlab / 官方云；本地只改代码 |
| PowerShell 命令失败 | `&&` | 改用 `;` |
| `stat/needs-squash` | 分支 >1 commit | soft-reset 到 base → **单 commit** → `--force-with-lease`；勿堆 fix commit |
| clang-format Failed（files modified） | 本地未按 CI 版式排版 | 用 **clang-format 18.1.8**（与 pre-commit 同 rev）`-style=file -i`；常见 `#endif  //`→`#endif //` |
| OAT NoLicenseHeader | 新文件缺 CANN 头 | 抄仓内同目录 License 头 |
| 误关 MR 又开新号 | 网页误点 Close | 优先 **Reopen** 原 MR；勿并行多开同分支 MR |

## D. 精度 / 性能 / 验收

| 现象 | 原因 | 解法 |
|------|------|------|
| 精度 FAIL | golden/容差/dtype | 对齐任务书与 opbase；检查 cast 与 accumulate dtype |
| 性能差一截 | 未走专用 kernel | 对照设计分核；profile 后再改 |
| 验收「缺逐条表」 | 只有 Summary 截图 | 输出每条 PASS + 性能 vs 标杆表 |
| 更新后仍旧结论 | 未重提 IT | 材料变更必须重新提交验收 |

## E. hidevlab / Basic API / MX

| 现象 | 原因 | 解法 |
|------|------|------|
| 改了头文件样例行为不变 | 样例吃系统 `$ASC` | **选择性** `cp` 本次改动的 intf/impl/utils 头 → `$ASC`（先 bak） |
| 整目录 `cp tip basic_api` / `dav_3510` / `impl/utils` | tip 与 CANN 9.1.0 头不匹配 | **禁止**；从 `*.bak.*` 整树恢复后再只 sync 改动文件 |
| `no member FLOAT8` / `asc_dump_*` / `tuple get` constexpr / `asc_time_stamp` inline | tip `dav_3510` 或 tip `utils` 盖坏 9.1.0 | 回滚 bak；不要用 git tag 整棵替换 `$ASC/impl/utils` 当「修复」除非与安装包同版本且完整 |
| `Std::ceil_div` / `cmath.h` file not found | tip 样例依赖；删/残缺系统 `cmath.h` | 样例本地 `CeilDiv`；声明+定义若不补齐就不要动系统 cmath |
| `fixpipe_l0c2ub` verify 全 0（编得过） | ASC 污染 / mix 路径坏；未必是指针 diff | L1/GM 对照；bak+5 文件；仍全 0 → 新实例；IT 交独立 `*_PASS_*.log` |
| IT 打开旧主日志仍见 ub `result error` | 主日志未更新 | ZIP/`logs/README` 写明 **PASS 文件覆盖**；表单点名文件名；材料变更须 **重新提交** |
| 精度分支与 feat diverged 上千 commit | 在脏 worktree 上 `checkout -B` | 基于 `fork/it/precision-logs-*` 只加 log；**勿 pull 合并**；`git add -f` |
| 下一例 cmake 找不到 CMakeLists | `run_one` 留在 `*/build` | 子 shell `(cd …)` 或每次回仓根 |
| MX `max_diff` 数百万 | 缺 `en_dtypes`/`ml_dtypes`，FP4/FP8 golden 退化成 uint8 | `pip install ml_dtypes==0.2.0 en_dtypes==0.0.4` 后重跑 gen_data |
| Sparse 950 失败 | 样例仅 A2/A3 / `__NPU_ARCH__==2201` | 台账 SKIP |
| Dump/SPM 无法指针测 | Dump Cal 吃 Tensor；SPM 是 TPipe 成员 | 台账 SKIP |
| GM 指针 cache 不对 | 裸 `__gm__*` 无 ExtractCacheMode | `cacheMode=0` + 易用性 Issue；真 cache 用 GlobalTensor |
| UT COMPILE：`redefinition of Fixpipe/LoadData/...` + default-arg redef | Host/tikicpulib UT 里 `__cbuf__/__gm__/__ca__/...` **展开为空**，多 AS 指针重载塌成同一 `T*`；仅 `#ifndef ASCENDC_CPU_DEBUG` **不够**（adv UT 常不定义该宏） | 多 AS 公开指针入口用 **Device-only**：`#if !defined(ASCENDC_CPU_DEBUG) && defined(__CCE_IS_AICORE__)`；`*Cal`/`*Impl` 按名不撞；勿靠给 UT cmake 强加 `ASCENDC_CPU_DEBUG` |
| 以为 CPU twin 有 `__NPU_ARCH__` 就安全 | 架构宏在、地址空间宏仍空 | 以是否 `__CCE_IS_AICORE__`（且非 CPU_DEBUG）为准门控重载 |

## F. 原则

1. **任务书数字不可抄错任务**（门禁、shape、标杆每任务不同）。  
2. **先过编译器/静态检查，再追性能。**  
3. **设计通过再堆代码**；并行开发风险自负，合入仍以评审通过为准。  
4. **交付可点击**：报告放 GitCode 链接，不依赖「在我电脑上」。  
5. **架构不适用写 SKIP**，勿硬跑假 PASS。  
