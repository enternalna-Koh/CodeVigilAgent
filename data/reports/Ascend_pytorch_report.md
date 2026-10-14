# Ascend/pytorch 数据分析报告

生成时间: 2026-10-14 14:00:41

## Issues 统计

- Open: 40
- Closed: 24
- Total: 64

## 常见问题模式

### OOM (1 issues)

- [#101](https://github.com/Ascend/pytorch/issues/101): SFTTrainer Out of Memory: Full-parameter fine-tuning on 8*910B (64G) for long context model Qwen3-4B-Instruct-2507.

### Timeout (8 issues)

- [#166](https://github.com/Ascend/pytorch/issues/166): ProcessGroupHCCL creation fails with fftsplus SDMA device error (507049) when another process uses CaMem sleep mode on the same NPU
- [#154](https://github.com/Ascend/pytorch/issues/154): [Bug]: torch.compile在编译时会出现硬件访问超时问题
- [#153](https://github.com/Ascend/pytorch/issues/153): [Bug]: 310P 布尔掩码 index_put_ 导致设备上下文崩溃（aicpu 错误 507018）
- [#150](https://github.com/Ascend/pytorch/issues/150): [bug] interpolate doesn't work with small scale_factor values
- [#144](https://github.com/Ascend/pytorch/issues/144): torch_npu 2.10 + CANN 9.0 on soc_version 104: torch.nn.functional.linear fails with MatMul/TransData

### Compatibility (5 issues)

- [#148](https://github.com/Ascend/pytorch/issues/148): torch_npu 2.1.0 + CANN 8.0.0 在昇腾910B上微调Qwen3-ASR 模型
- [#56](https://github.com/Ascend/pytorch/issues/56): torch.nn.MaxPool1d 类似算子的支持
- [#144](https://github.com/Ascend/pytorch/issues/144): torch_npu 2.10 + CANN 9.0 on soc_version 104: torch.nn.functional.linear fails with MatMul/TransData
- [#139](https://github.com/Ascend/pytorch/issues/139): RFC: 为 torch_npu MemPool 增加 `sub_block_alignment` 参数
- [#3](https://github.com/Ascend/pytorch/issues/3): Unsupported data type for HCCL process group

### CANN (53 issues)

- [#170](https://github.com/Ascend/pytorch/issues/170): os.environ.get取值异常
- [#167](https://github.com/Ascend/pytorch/issues/167): torch_npu.profiler 在 warmup → RECORD 跃迁时丢失窗口头部的设备侧数据，实际采集次数少于 active
- [#166](https://github.com/Ascend/pytorch/issues/166): ProcessGroupHCCL creation fails with fftsplus SDMA device error (507049) when another process uses CaMem sleep mode on the same NPU
- [#163](https://github.com/Ascend/pytorch/issues/163): [Bug]: NPU 环境下 Dynamo 处理零参数 id() 时抛出 IndexError 而非 TypeError，与 PyTorch 原生行为不一致，影响设备测试解耦
- [#147](https://github.com/Ascend/pytorch/issues/147): 【bug】torch_npu不支持flex_attention，使用flex_attention进行训练会报错

### Performance (5 issues)

- [#154](https://github.com/Ascend/pytorch/issues/154): [Bug]: torch.compile在编译时会出现硬件访问超时问题
- [#148](https://github.com/Ascend/pytorch/issues/148): torch_npu 2.1.0 + CANN 8.0.0 在昇腾910B上微调Qwen3-ASR 模型
- [#125](https://github.com/Ascend/pytorch/issues/125): [Bug] ATC allow_mix_precision / allow_fp32_to_fp16 在 SAM3 vision encoder FPN neck 上造成灾难性精度崩溃 (与 torch_npu fp16 行为不一致)
- [#69](https://github.com/Ascend/pytorch/issues/69): F.interpolate on NPU is REALLY slow, even slower than CPU
- [#100](https://github.com/Ascend/pytorch/issues/100): 模型是否支持FP8格式模型推理？

### Accuracy (23 issues)

- [#170](https://github.com/Ascend/pytorch/issues/170): os.environ.get取值异常
- [#166](https://github.com/Ascend/pytorch/issues/166): ProcessGroupHCCL creation fails with fftsplus SDMA device error (507049) when another process uses CaMem sleep mode on the same NPU
- [#154](https://github.com/Ascend/pytorch/issues/154): [Bug]: torch.compile在编译时会出现硬件访问超时问题
- [#150](https://github.com/Ascend/pytorch/issues/150): [bug] interpolate doesn't work with small scale_factor values
- [#148](https://github.com/Ascend/pytorch/issues/148): torch_npu 2.1.0 + CANN 8.0.0 在昇腾910B上微调Qwen3-ASR 模型

## PR 统计

- Total PRs: 26
- Merged: 2
- Avg Comments: 0.0

### PR 类型分布

- bugfix: 3
- other: 19
- feature: 2
- documentation: 1
- refactor: 1

### 常见标签

- ascend-cla/yes: 14
- ascend-cla/no: 11
