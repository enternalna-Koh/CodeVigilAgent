# model-migration

CANN 模型迁移知识包 - CUDA/PyTorch/ONNX → 昇腾 NPU 适配指南

## 内容结构

- **SKILL.md** - 主知识文件，包含：
  - §0 迁移路径概览（PyTorch/ONNX/AscendCL）
  - §1 torch-npu 迁移清单
  - §2 ONNX → OM 转换
  - §3 常见迁移陷阱
  - §4 性能基线建立
  - §5 迁移验收标准
  - §6 参考资源

## 使用场景

- CUDA 代码迁移到昇腾 NPU
- PyTorch 模型适配 torch-npu
- ONNX 模型转换为 OM 离线模型
- 精度对齐验证
- 性能基线建立

## 参考资源

- [CANN Learning Hub](https://gitcode.com/cann/cann-learning-hub)
- [torch-npu GitHub](https://github.com/Ascend/pytorch)
- 社区迁移案例：MolScribe、Qwen3、MMAudio 等
