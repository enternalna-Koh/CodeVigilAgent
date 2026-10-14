# vllm-project/vllm-ascend 数据分析报告

生成时间: 2026-10-14 14:00:32

## Issues 统计

- Open: 2
- Closed: 8
- Total: 10

## 常见问题模式

### Timeout (3 issues)

- [#17923](https://github.com/vllm-project/vllm-ascend/issues/17923): [Bug]: KV-pool lookup server thread dies silently on any handler exception, hanging the scheduler indefinitely
- [#18178](https://github.com/vllm-project/vllm-ascend/issues/18178): [Bug] EPLB init fails with "HIXL EPLB register memory failed with status 103900" when speculative decoding (draft model) + expandable_segments:True on Ascend A3
- [#16484](https://github.com/vllm-project/vllm-ascend/issues/16484): [Bug][A5][GLM DSpark] Runtime state changes can break compiled accuracy

### Compatibility (2 issues)

- [#10210](https://github.com/vllm-project/vllm-ascend/issues/10210): [Bug]: Failed in a test when submitting PR to vllm_ascendv0.18.0
- [#17731](https://github.com/vllm-project/vllm-ascend/issues/17731): [Bug][Triton] FP8 RoPE fails to compile on Ascend 910B3 (f32 to E4M3FN)

### CANN (9 issues)

- [#14150](https://github.com/vllm-project/vllm-ascend/issues/14150): [Contribution] 任务 #9：[Correctness] `_invalid_block_ids` 锁保护范围审计
- [#17923](https://github.com/vllm-project/vllm-ascend/issues/17923): [Bug]: KV-pool lookup server thread dies silently on any handler exception, hanging the scheduler indefinitely
- [#10210](https://github.com/vllm-project/vllm-ascend/issues/10210): [Bug]: Failed in a test when submitting PR to vllm_ascendv0.18.0
- [#17731](https://github.com/vllm-project/vllm-ascend/issues/17731): [Bug][Triton] FP8 RoPE fails to compile on Ascend 910B3 (f32 to E4M3FN)
- [#18345](https://github.com/vllm-project/vllm-ascend/issues/18345): [Bug]:  In the A2/A3 environment, when the extract_slice API of triton-ascend is used to split data and the start address is not 32-byte aligned, data obtaining errors occur.

### Accuracy (4 issues)

- [#18345](https://github.com/vllm-project/vllm-ascend/issues/18345): [Bug]:  In the A2/A3 environment, when the extract_slice API of triton-ascend is used to split data and the start address is not 32-byte aligned, data obtaining errors occur.
- [#18178](https://github.com/vllm-project/vllm-ascend/issues/18178): [Bug] EPLB init fails with "HIXL EPLB register memory failed with status 103900" when speculative decoding (draft model) + expandable_segments:True on Ascend A3
- [#16484](https://github.com/vllm-project/vllm-ascend/issues/16484): [Bug][A5][GLM DSpark] Runtime state changes can break compiled accuracy
- [#16954](https://github.com/vllm-project/vllm-ascend/issues/16954): [Doc]: GLM-5 & GLM-5.1文档latest中A3PD分离配置    --kv-cache-dtype int8 \     --attention_config.indexer_kv_dtype int8 \ 服务启动失败

## PR 统计

- Total PRs: 50
- Merged: 41
- Avg Comments: 0.0

### PR 类型分布

- other: 15
- refactor: 1
- feature: 16
- bugfix: 10
- documentation: 8

### 常见标签

