---
name: model-migration
description: CANN 模型迁移知识包 - CUDA/PyTorch/ONNX → 昇腾 NPU 适配指南
version: 1.0.0
tags: [migration, torch-npu, model-conversion, onnx, ge]
---

# CANN 模型迁移 Skill

## §0 迁移路径概览

### 主流迁移方式

```text
方式 A：PyTorch → torch-npu（在线推理）
  ├─ 优势：代码改动最小，调试便捷
  ├─ 适用：训练迁移、快速验证、动态 shape
  └─ 劣势：首次编译慢，资源占用较高

方式 B：PyTorch → ONNX → OM（离线推理）
  ├─ 优势：推理性能最优，资源占用低
  ├─ 适用：生产部署、静态 shape、嵌入式
  └─ 劣势：调试困难，不支持复杂控制流

方式 C：直接 AscendCL API 开发
  ├─ 优势：最大控制力，极致性能
  ├─ 适用：C++ 项目、边缘设备、特定场景
  └─ 劣势：开发成本高，需深入理解硬件
```

## §1 torch-npu 迁移清单

### 1.1 环境准备

```bash
# 1. 安装 CANN 开发套件（根据硬件选择版本）
# 910: CANN 8.0+
# 310P: CANN 6.3+
# A3: CANN 8.5+

# 2. 安装 torch-npu（版本需匹配 PyTorch）
pip install torch-npu==2.1.0.post6  # 示例版本

# 3. 验证安装
python -c "import torch; import torch_npu; print(torch.npu.is_available())"
```

### 1.2 代码适配模式

**基础迁移（3 步）**

```python
import torch
import torch_npu  # 1. 导入 torch-npu

model = MyModel()
model = model.npu()  # 2. 模型迁移到 NPU

input_tensor = torch.randn(1, 3, 224, 224)
input_tensor = input_tensor.npu()  # 3. 数据迁移到 NPU

output = model(input_tensor)
```

**Device-only 门控（避免 CPU 环境污染）**

```python
# 文件头部
try:
    import torch_npu
    NPU_AVAILABLE = torch.npu.is_available()
except ImportError:
    NPU_AVAILABLE = False

# 使用时
if NPU_AVAILABLE:
    device = torch.device('npu:0')
else:
    device = torch.device('cpu')
```

### 1.3 常见 API 映射

| CUDA API | torch-npu API | 注意事项 |
|----------|---------------|----------|
| `.cuda()` | `.npu()` | 支持设备 ID：`.npu(0)` |
| `torch.cuda.is_available()` | `torch.npu.is_available()` | - |
| `torch.cuda.device_count()` | `torch.npu.device_count()` | - |
| `torch.cuda.synchronize()` | `torch.npu.synchronize()` | - |
| `torch.cuda.empty_cache()` | `torch.npu.empty_cache()` | - |
| `torch.cuda.current_device()` | `torch.npu.current_device()` | - |
| `with torch.cuda.device(id)` | `with torch.npu.device(id)` | - |

### 1.4 自定义算子适配

**场景 1：PyTorch 原生算子缺失 NPU 实现**

```python
# 方案 A：注册 NPU 实现
@torch.npu.jit.script
def custom_op_npu(x, y):
    # 使用 NPU 支持的算子组合实现
    return torch.npu.npu_xxx(x, y)

# 方案 B：回退到 CPU（性能差，避免使用）
def custom_op(x):
    if x.is_npu:
        x_cpu = x.cpu()
        result = cpu_only_op(x_cpu)
        return result.npu()
    return cpu_only_op(x)
```

**场景 2：C++ 扩展算子**

需重新编译为 NPU 版本，参考 AscendC 算子开发流程（见 `cann-ascendc-op-dev` skill）。

### 1.5 精度对齐验证

**标准流程**

```python
import torch
import torch_npu
import numpy as np

def verify_accuracy(model, input_data, tolerance=1e-3):
    """
    对比 CPU 和 NPU 推理精度
    
    Args:
        model: PyTorch 模型
        input_data: 输入张量（CPU）
        tolerance: 允许误差
    """
    # CPU baseline
    model_cpu = model.cpu().eval()
    with torch.no_grad():
        output_cpu = model_cpu(input_data.cpu())
    
    # NPU inference
    model_npu = model.npu().eval()
    with torch.no_grad():
        output_npu = model_npu(input_data.npu())
    
    # 对比
    output_npu_cpu = output_npu.cpu()
    diff = torch.abs(output_cpu - output_npu_cpu)
    max_diff = diff.max().item()
    mean_diff = diff.mean().item()
    relative_diff = (diff / (torch.abs(output_cpu) + 1e-8)).mean().item()
    
    print(f"Max diff: {max_diff:.6f}")
    print(f"Mean diff: {mean_diff:.6f}")
    print(f"Relative diff: {relative_diff:.2%}")
    
    assert relative_diff < tolerance, f"精度超标：{relative_diff:.2%} > {tolerance:.2%}"
    return True
```

**逐层对比（精度超标时）**

```python
def layer_wise_check(model, input_data):
    """逐层对比 CPU vs NPU 输出，定位精度问题"""
    hooks = []
    cpu_outputs = {}
    npu_outputs = {}
    
    def get_hook(name, storage):
        def hook(module, input, output):
            storage[name] = output.detach().cpu() if hasattr(output, 'cpu') else output
        return hook
    
    # 注册 hooks
    for name, module in model.named_modules():
        hooks.append(module.register_forward_hook(get_hook(name, cpu_outputs)))
    
    # CPU forward
    model.cpu().eval()
    with torch.no_grad():
        _ = model(input_data.cpu())
    
    # 清理 hooks 并重新注册
    for h in hooks:
        h.remove()
    hooks = []
    for name, module in model.named_modules():
        hooks.append(module.register_forward_hook(get_hook(name, npu_outputs)))
    
    # NPU forward
    model.npu().eval()
    with torch.no_grad():
        _ = model(input_data.npu())
    
    # 对比每层
    for name in cpu_outputs:
        if name in npu_outputs:
            cpu_out = cpu_outputs[name]
            npu_out = npu_outputs[name]
            if isinstance(cpu_out, torch.Tensor) and isinstance(npu_out, torch.Tensor):
                diff = (cpu_out - npu_out).abs().mean().item()
                print(f"{name}: mean_diff={diff:.6f}")
    
    for h in hooks:
        h.remove()
```

## §2 ONNX → OM 转换

### 2.1 导出 ONNX

```python
import torch
import torch.onnx

model = MyModel().eval()
dummy_input = torch.randn(1, 3, 224, 224)

torch.onnx.export(
    model,
    dummy_input,
    "model.onnx",
    export_params=True,
    opset_version=11,  # 推荐 11 或 13
    do_constant_folding=True,
    input_names=['input'],
    output_names=['output'],
    dynamic_axes={
        'input': {0: 'batch_size'},  # 动态 batch（可选）
        'output': {0: 'batch_size'}
    }
)
```

### 2.2 使用 ATC 转换为 OM

```bash
# 基础转换
atc --model=model.onnx \
    --framework=5 \
    --output=model \
    --input_format=NCHW \
    --input_shape="input:1,3,224,224" \
    --soc_version=Ascend910  # 或 Ascend310P3

# 带优化选项
atc --model=model.onnx \
    --framework=5 \
    --output=model_opt \
    --input_format=NCHW \
    --input_shape="input:1,3,224,224" \
    --soc_version=Ascend910 \
    --fusion_switch_file=fusion_switch.cfg \  # 算子融合配置
    --precision_mode=allow_fp32_to_fp16 \      # 混合精度
    --log=info \
    --optypelist_for_implmode="Gelu" \        # 特定算子优化
    --op_select_implmode=high_performance      # 性能优先模式
```

**常用参数**

| 参数 | 说明 | 示例 |
|------|------|------|
| `--framework` | 框架类型：0=Caffe, 3=TF, 5=ONNX | `5` |
| `--soc_version` | 硬件型号 | `Ascend910` / `Ascend310P3` |
| `--input_shape` | 输入 shape | `"input:1,3,224,224"` |
| `--dynamic_dims` | 动态 shape 档位 | `"1,4,8;1,8,16"` |
| `--precision_mode` | 精度模式 | `allow_fp32_to_fp16` / `force_fp16` |
| `--insert_op_conf` | AIPP 配置（预处理） | `aipp.cfg` |

### 2.3 转换常见问题

**问题 1：算子不支持**

```text
ERROR: The operator [xxx] is not supported
```

解决方案：
- 检查 ONNX opset 版本（推荐 11/13）
- 查看 CANN 算子支持列表
- 自定义算子实现（参考 AscendC 开发）
- 使用算子映射配置

**问题 2：动态 shape 转换失败**

```bash
# 方案 A：指定档位
--dynamic_dims="1,4,8,16"  # batch size 档位

# 方案 B：动态 batch + image size
--input_shape="input:-1,3,-1,-1" \
--dynamic_image_size="224,224;384,384"
```

**问题 3：精度下降**

```bash
# 强制 FP32（调试用）
atc --precision_mode=force_fp32 ...

# 混合精度 + 算子白名单
atc --precision_mode=allow_fp32_to_fp16 \
    --keep_dtype=model.onnx.json ...  # 指定保持 FP32 的算子
```

## §3 常见迁移陷阱

### 3.1 In-place 操作

```python
# ❌ 错误：NPU 不支持某些 in-place 操作
x += y  # 可能报错

# ✅ 正确：显式赋值
x = x + y
```

### 3.2 数据类型不匹配

```python
# ❌ 错误：NPU 不支持某些混合精度计算
x_fp16 = torch.randn(10, dtype=torch.float16).npu()
y_fp32 = torch.randn(10, dtype=torch.float32).npu()
z = x_fp16 + y_fp32  # 可能报错

# ✅ 正确：统一数据类型
z = x_fp16 + y_fp32.half()
```

### 3.3 CPU Tensor 混入

```python
# ❌ 错误：NPU tensor 和 CPU tensor 混合计算
x_npu = torch.randn(10).npu()
y_cpu = torch.randn(10)
z = x_npu + y_cpu  # 报错

# ✅ 正确：确保同设备
z = x_npu + y_cpu.npu()
```

### 3.4 不支持的控制流

```python
# ⚠️ 避免：复杂控制流在 OM 模型中不支持
def forward(self, x):
    if x.sum() > 0:  # 动态条件
        return self.path_a(x)
    else:
        return self.path_b(x)

# ✅ 改进：静态图或 torch-npu
```

## §4 性能基线建立

### 4.1 Benchmark 脚本模板

```python
import torch
import torch_npu
import time
import numpy as np

def benchmark(model, input_shape, device='npu', warmup=10, iterations=100):
    """
    推理性能测试
    
    Returns:
        dict: {avg_latency, throughput, p50, p95, p99}
    """
    model = model.to(device).eval()
    dummy_input = torch.randn(*input_shape).to(device)
    
    # Warmup
    with torch.no_grad():
        for _ in range(warmup):
            _ = model(dummy_input)
    
    if device == 'npu':
        torch.npu.synchronize()
    
    # Benchmark
    latencies = []
    with torch.no_grad():
        for _ in range(iterations):
            start = time.time()
            _ = model(dummy_input)
            if device == 'npu':
                torch.npu.synchronize()
            latencies.append((time.time() - start) * 1000)  # ms
    
    latencies = np.array(latencies)
    return {
        'avg_latency_ms': latencies.mean(),
        'std_latency_ms': latencies.std(),
        'p50_ms': np.percentile(latencies, 50),
        'p95_ms': np.percentile(latencies, 95),
        'p99_ms': np.percentile(latencies, 99),
        'throughput_qps': 1000.0 / latencies.mean()
    }

# 使用示例
model = MyModel()
results = benchmark(model, (1, 3, 224, 224), device='npu')
print(f"Latency: {results['avg_latency_ms']:.2f} ± {results['std_latency_ms']:.2f} ms")
print(f"Throughput: {results['throughput_qps']:.2f} QPS")
```

### 4.2 CPU vs NPU 对比

```python
cpu_results = benchmark(model, (1, 3, 224, 224), device='cpu')
npu_results = benchmark(model, (1, 3, 224, 224), device='npu')

speedup = cpu_results['avg_latency_ms'] / npu_results['avg_latency_ms']
print(f"加速比: {speedup:.2f}x")
```

## §5 迁移验收标准

### 5.1 功能验收

- [x] 模型可在 NPU 上正常加载
- [x] 推理输出 shape 与预期一致
- [x] 边界输入（全零/全一/极值）无崩溃
- [x] Batch size 变化可正常处理（若支持动态）

### 5.2 精度验收

- [x] CPU baseline vs NPU 相对误差 <1%（FP32/FP16）
- [x] INT8 量化：相对误差 <5%，关键指标（如分类准确率）下降 <2%
- [x] 逐层对比（若精度超标）：定位精度损失层

### 5.3 性能验收

- [x] 建立 CPU/NPU 基线性能
- [x] NPU 推理延迟优于 CPU（目标 >5x 加速）
- [x] 吞吐量满足业务要求（QPS）
- [x] 内存占用合理（<硬件显存容量 80%）

### 5.4 工程验收

- [x] 依赖文档：CANN 版本、torch-npu 版本
- [x] 运行文档：环境配置、启动命令
- [x] 测试用例：功能测试 + 精度验证脚本
- [x] 性能报告：基线数据 + 优化后数据

## §6 参考资源

- [CANN Learning Hub - 模型迁移教程](https://gitcode.com/cann/cann-learning-hub)
- [torch-npu 官方文档](https://github.com/Ascend/pytorch)
- [ATC 工具使用指南](https://www.hiascend.com/document)
- [昇腾社区 - 模型迁移案例](https://www.hiascend.com/developer)
