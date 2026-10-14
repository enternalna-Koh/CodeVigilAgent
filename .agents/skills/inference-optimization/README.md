# inference-optimization

CANN 推理性能优化知识包 - Profiling 分析、算子融合、图优化、内存管理

## 内容结构

- **SKILL.md** - 主知识文件，包含：
  - §0 优化方法论（四层金字塔）
  - §1 性能 Profiling（msprof/Ascend PyTorch Profiler）
  - §2 图优化（GE 算子融合）
  - §3 算子级优化（混合精度/算子替换）
  - §4 系统级优化（多 Stream/内存池/Batch）
  - §5 量化优化（INT8 PTQ）
  - §6 优化 Checklist
  - §7 常见性能问题
  - §8 参考资源

## 使用场景

- 推理性能瓶颈分析
- 算子融合与图优化
- 混合精度加速（FP16/INT8）
- 内存与并发优化
- 生产环境性能调优

## 关键工具

- msprof - AscendCL profiling
- Ascend PyTorch Profiler - torch-npu profiling
- AMCT - 量化工具

## 性能目标

- CPU → NPU 加速比 >5x
- FP32 → FP16 加速比 1.5-2x
- INT8 量化加速比 2-3x（精度损失 <2%）

## 参考案例

- [YOLOv10 NPU 优化](https://ai.gitcode.com/luckymitty/yolov10-npu) - 38.9x 加速
- [CANN 图优化技术解析](https://devpress.csdn.net/awstech/6a9211d73bda720d4b361ab8.html)
