---
name: inference-optimization
description: CANN 推理性能优化知识包 - Profiling 分析、算子融合、图优化、内存管理
version: 1.0.0
tags: [optimization, profiling, performance, graph-optimization, memory]
---

# CANN 推理性能优化 Skill

## §0 优化方法论

### 优化金字塔

```text
Level 4: 架构级优化 (10-100x)
  └─ 模型结构、算法选择、量化策略

Level 3: 图优化 (2-10x)
  └─ 算子融合、常量折叠、子图替换

Level 2: 算子优化 (1.5-5x)
  └─ 内核调优、内存访问、并行策略

Level 1: 系统优化 (1.2-2x)
  └─ Stream 并发、内存池、预处理优化
```

**原则**：自顶向下优化，先抓大头再抠细节。

## §1 性能 Profiling

### 1.1 工具选择

| 工具 | 适用场景 | 粒度 | 输出 |
|------|----------|------|------|
| **msprof** | AscendCL/GE 推理 | 算子级 | Timeline/算子耗时/内存 |
| **Ascend PyTorch Profiler** | torch-npu 训练/推理 | 算子级 | Chrome trace/TensorBoard |
| **GE Profiler** | 图执行分析 | 子图/Pass | 图优化日志 |

### 1.2 msprof 使用（AscendCL）

**采集数据**

```bash
# 采集所有数据（第一次分析）
msprof --application="python inference.py" \
       --output=./profiling_data \
       --ai-core=on \
       --aicpu=on \
       --runtime-api=on \
       --task-time=on \
       --sys-hardware=on

# 采集特定阶段（性能瓶颈已知）
msprof --application="python inference.py" \
       --output=./profiling_data \
       --ai-core=on
```

**分析结果**

```bash
# 生成可视化报告
msprof --export=on \
       --output=./profiling_data

# 查看算子耗时 Top-N
grep "op_name" profiling_data/msprof_*.csv | \
  sort -t',' -k5 -rn | head -20
```

**关键指标**

- **Task Duration**：算子实际执行时间
- **Stream Gap**：Stream 间隙（调度开销）
- **Memory Copy**：Host-Device 拷贝耗时
- **AICPU Time**：CPU 算子耗时（应最小化）

### 1.3 Ascend PyTorch Profiler

```python
import torch
import torch_npu
from torch_npu.profiler import Profile

model = MyModel().npu().eval()
input_data = torch.randn(1, 3, 224, 224).npu()

# Profiling
with Profile(
    activities=[torch_npu.profiler.ProfilerActivity.NPU],
    record_shapes=True,
    profile_memory=True,
    with_stack=True
) as prof:
    with torch.no_grad():
        for _ in range(10):
            _ = model(input_data)
            torch.npu.synchronize()

# 导出 Chrome trace
prof.export_chrome_trace("trace.json")

# 打印 Top-K 算子
print(prof.key_averages().table(sort_by="npu_time_total", row_limit=20))
```

**分析要点**

```python
# 1. 识别瓶颈算子（耗时占比 >10%）
top_ops = prof.key_averages(group_by_input_shape=True).table(
    sort_by="npu_time_total", row_limit=10
)

# 2. 内存峰值
memory_stats = prof.key_averages().table(sort_by="npu_memory_usage")

# 3. 数据传输开销
data_transfer = prof.events().filter(lambda x: "Memcpy" in x.name)
```

### 1.4 性能瓶颈分类

| 瓶颈类型 | 特征 | 优化方向 |
|----------|------|----------|
| **计算密集** | AI Core 利用率高 | 算子融合、混合精度 |
| **内存墙** | Memory Copy 占比高 | 减少拷贝、内存复用 |
| **调度开销** | Stream Gap 大 | 多 Stream 并发、异步执行 |
| **AICPU 瓶颈** | AICPU 耗时高 | 迁移到 AI Core、预处理优化 |

## §2 图优化（GE）

### 2.1 自动图优化

**启用 GE 优化 Pass**

```bash
# ATC 转换时启用
atc --model=model.onnx \
    --framework=5 \
    --output=model_opt \
    --soc_version=Ascend910 \
    --fusion_switch_file=fusion_config.cfg \  # 算子融合配置
    --enable_small_channel=1 \                 # 小通道优化
    --op_select_implmode=high_performance \    # 性能优先
    --optypelist_for_implmode="Gelu,LayerNorm" # 特定算子高性能实现
```

**fusion_config.cfg 示例**

```ini
[Common]
# 启用所有融合 Pass
fusion_switch=on

[UB_FUSION]
# Elemwise 融合
ubfusion_conv_bn_reduce=on
ubfusion_bn_update_grad=on

[BUFFER_FUSION]
# Buffer 融合（减少内存访问）
bufferfusion_conv_bn_add_relu=on
```

### 2.2 常见融合模式

| 模式 | 融合前 | 融合后 | 加速比 |
|------|--------|--------|--------|
| **Conv-BN-ReLU** | Conv → BN → ReLU | ConvBNReLU | 1.5-2x |
| **MatMul-Add** | MatMul → Add(bias) | MatMulBiasAdd | 1.2-1.5x |
| **Elemwise 链** | Add → Mul → ReLU | FusedElemwise | 2-3x |
| **LayerNorm** | Reduce → Sub → Div | LayerNormFused | 2-4x |

### 2.3 手动子图替换

**场景：GELU 优化**

```python
# 原实现（慢）
def gelu_slow(x):
    return 0.5 * x * (1 + torch.tanh(
        math.sqrt(2 / math.pi) * (x + 0.044715 * x**3)
    ))

# NPU 优化实现
def gelu_fast(x):
    return torch.npu.npu_gelu(x)  # 单算子实现

# 或在 ONNX 中映射
# ATC 参数：--insert_op_conf=gelu_mapping.json
```

### 2.4 图优化验证

```bash
# 1. 导出优化后的图
atc --model=model.onnx \
    --framework=5 \
    --output=model_opt \
    --dump_graph=on \  # 导出图结构
    --log=debug

# 2. 对比优化前后算子数量
grep "op_type" ge_dump/graph_*.txt | wc -l

# 3. 验证精度
python verify_accuracy.py --model_om=model_opt.om
```

## §3 算子级优化

### 3.1 混合精度

**自动混合精度（AMP）**

```python
import torch
import torch_npu

model = MyModel().npu()
scaler = torch_npu.amp.GradScaler()

# 推理时启用 FP16
with torch_npu.amp.autocast():
    output = model(input_data.npu())
```

**手动混合精度**

```python
# 敏感层保持 FP32，其他用 FP16
class MixedPrecisionModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 64, 3).half()  # FP16
        self.bn1 = nn.BatchNorm2d(64)  # FP32（BN 对精度敏感）
        self.conv2 = nn.Conv2d(64, 128, 3).half()
        
    def forward(self, x):
        x = x.half()
        x = self.conv1(x)
        x = self.bn1(x.float()).half()  # FP32 BN
        x = self.conv2(x)
        return x
```

**精度 vs 性能权衡**

| 策略 | FP32 → FP16 加速比 | 精度损失 | 适用场景 |
|------|-------------------|----------|----------|
| **全 FP16** | 1.5-2x | <1% | CV 模型、推理 |
| **混合精度** | 1.3-1.8x | <0.5% | NLP、训练 |
| **动态范围** | 1.2-1.5x | ~0% | 精度敏感任务 |

### 3.2 算子替换

**低效算子识别**

```python
# Profiling 后识别慢算子
# 示例：Softmax 在大 vocab 时慢

# 原实现
logits = model(x)  # [B, vocab_size=100k]
probs = F.softmax(logits, dim=-1)  # 慢

# 优化：Top-K 采样（避免全量 softmax）
values, indices = torch.topk(logits, k=50, dim=-1)
probs = F.softmax(values, dim=-1)  # 快 100x
```

### 3.3 自定义算子优化

**何时需要自定义算子**

- Profiling 显示某算子占比 >20%
- 现有算子组合无法高效实现
- 特定硬件特性未利用（如 Cube 单元）

**开发流程**

参考 `.cursor/skills/cann-ascendc-op-dev/SKILL.md`。

## §4 系统级优化

### 4.1 多 Stream 并发

**单 Stream（串行）**

```python
# 慢：推理任务串行执行
for data in dataloader:
    output = model(data.npu())
    result = post_process(output)
```

**多 Stream（并行）**

```python
import torch_npu

# 创建多个 Stream
stream1 = torch_npu.Stream()
stream2 = torch_npu.Stream()

# Pipeline：预处理 || 推理 || 后处理
with torch_npu.stream(stream1):
    # 预处理
    preprocessed = preprocess(data)

with torch_npu.stream(stream2):
    # 推理（与下一个预处理并行）
    output = model(preprocessed)

torch_npu.synchronize()
```

**性能提升**：1.3-2x（取决于 CPU 预处理占比）

### 4.2 内存优化

**问题：频繁 malloc/free**

```python
# ❌ 慢：每次推理都 allocate
for data in dataloader:
    input_tensor = torch.randn(1, 3, 224, 224).npu()
    output = model(input_tensor)
```

**方案 A：内存复用**

```python
# ✅ 快：复用 buffer
input_buffer = torch.empty(1, 3, 224, 224).npu()

for data in dataloader:
    input_buffer.copy_(data)
    output = model(input_buffer)
```

**方案 B：内存池**

```python
import torch_npu

# 启用 caching allocator
torch_npu.set_per_process_memory_fraction(0.8, device=0)

# 预分配
torch_npu.empty_cache()
dummy_run(model)  # Warmup 预分配内存
```

### 4.3 Batch 优化

**静态 Batching**

```python
# 累积到固定 batch size
batch = []
for data in dataloader:
    batch.append(data)
    if len(batch) == BATCH_SIZE:
        batch_tensor = torch.stack(batch).npu()
        outputs = model(batch_tensor)
        batch = []
```

**动态 Batching（服务化）**

```python
import asyncio
from collections import deque

class DynamicBatcher:
    def __init__(self, model, max_batch_size=32, max_wait_ms=10):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.queue = deque()
        
    async def infer(self, data):
        future = asyncio.Future()
        self.queue.append((data, future))
        
        if len(self.queue) >= self.max_batch_size:
            await self._flush()
        else:
            asyncio.create_task(self._wait_and_flush())
        
        return await future
    
    async def _flush(self):
        if not self.queue:
            return
        
        batch_data = []
        futures = []
        while self.queue and len(batch_data) < self.max_batch_size:
            data, future = self.queue.popleft()
            batch_data.append(data)
            futures.append(future)
        
        batch_tensor = torch.stack(batch_data).npu()
        outputs = self.model(batch_tensor)
        
        for i, future in enumerate(futures):
            future.set_result(outputs[i])
    
    async def _wait_and_flush(self):
        await asyncio.sleep(self.max_wait_ms / 1000)
        await self._flush()
```

### 4.4 预处理优化

**瓶颈识别**

```python
# Profiling：如果 CPU 预处理占比 >30%，需优化
import time

start = time.time()
preprocessed = preprocess(image)  # Resize, Normalize, ToTensor
cpu_time = time.time() - start

start = time.time()
output = model(preprocessed.npu())
torch_npu.synchronize()
npu_time = time.time() - start

if cpu_time > npu_time * 0.3:
    print("⚠️ 预处理成为瓶颈")
```

**优化方案**

```python
# 方案 A：使用 AIPP（硬件加速预处理）
# ATC 转换时配置
"""
aipp.cfg:
aipp_op {
    aipp_mode: static
    input_format: YUV420SP_U8
    src_image_size_w: 1920
    src_image_size_h: 1080
    crop: true
    load_start_pos_w: 0
    load_start_pos_h: 0
    crop_size_w: 224
    crop_size_h: 224
    mean_chn_0: 123.675
    mean_chn_1: 116.28
    mean_chn_2: 103.53
    min_chn_0: 0.017
    min_chn_1: 0.017
    min_chn_2: 0.017
}
"""

# 方案 B：GPU 预处理（若有 GPU）
# 方案 C：多进程预处理
from torch.multiprocessing import Pool

def parallel_preprocess(images, num_workers=4):
    with Pool(num_workers) as pool:
        return pool.map(preprocess, images)
```

## §5 量化优化

### 5.1 INT8 量化

**PTQ（训练后量化）**

```python
# 使用 AMCT（Ascend Model Compression Toolkit）
from amct_pytorch import quantize

model = MyModel().eval()
dummy_input = torch.randn(1, 3, 224, 224)

# 生成量化配置
config = {
    "calibration": "MinMax",  # 或 "Percentile", "KL"
    "skip_layers": ["layer.0.conv1"],  # 跳过精度敏感层
}

# 量化
quantized_model = quantize.create_quant_model(
    model, 
    dummy_input, 
    config_file="./quant_config.json"
)

# Calibration
for data in calibration_loader:
    quantized_model(data)

# 导出量化模型
quantize.export_quant_model(quantized_model, "model_int8.onnx")
```

**精度验证**

```python
def validate_int8(model_fp32, model_int8, test_loader):
    fp32_acc = evaluate(model_fp32, test_loader)
    int8_acc = evaluate(model_int8, test_loader)
    
    drop = (fp32_acc - int8_acc) / fp32_acc * 100
    print(f"FP32: {fp32_acc:.2%}, INT8: {int8_acc:.2%}, Drop: {drop:.2f}%")
    
    assert drop < 2.0, f"精度下降过大：{drop:.2f}%"
```

### 5.2 量化策略选择

| 策略 | 加速比 | 精度损失 | 适用场景 |
|------|--------|----------|----------|
| **对称量化** | 2-3x | 1-2% | CV 分类 |
| **非对称量化** | 2-3x | 0.5-1% | 检测/分割 |
| **Per-channel** | 2-3x | <1% | Conv 层多 |
| **混合位宽** | 1.5-2x | <0.5% | 精度敏感模型 |

## §6 优化 Checklist

### 6.1 必做优化（适用所有场景）

- [ ] **Profiling 分析**：识别 Top-3 瓶颈算子
- [ ] **混合精度**：FP32 → FP16（验证精度 <1% 损失）
- [ ] **内存复用**：避免频繁 malloc/free
- [ ] **Batch 优化**：使用最大可行 batch size
- [ ] **GE 图优化**：启用算子融合（离线推理）

### 6.2 进阶优化（瓶颈明确后）

- [ ] **多 Stream 并发**：CPU 预处理占比 >20%
- [ ] **自定义算子**：单算子占比 >20%
- [ ] **INT8 量化**：精度容忍 <2% 损失
- [ ] **AIPP 硬件预处理**：图像预处理成为瓶颈
- [ ] **动态 Batching**：服务化部署，QPS 要求高

### 6.3 优化验收标准

| 指标 | 基线 | 目标 | 备注 |
|------|------|------|------|
| **延迟** | Baseline (ms) | <Baseline / 2 | P50/P95/P99 |
| **吞吐** | Baseline (QPS) | >Baseline * 2 | 稳定吞吐 |
| **精度** | FP32 | 相对误差 <1% | 关键指标 |
| **显存** | - | <80% 容量 | 峰值占用 |
| **CPU 利用率** | - | <50% | 避免 CPU 瓶颈 |

## §7 常见性能问题

### 问题 1：NPU 利用率低

**排查**

```bash
# 实时监控
npu-smi info

# 关键指标
# - Utilization: <30% → 瓶颈不在计算
# - Memory Usage: 接近满 → 内存瓶颈
```

**原因与方案**

- CPU 预处理慢 → 多进程/AIPP
- 内存拷贝多 → 减少 Host-Device 传输
- Batch size 小 → 增大 batch

### 问题 2：性能不稳定

**现象**

```python
# 前几次推理慢，后续正常
Iter 1: 100ms
Iter 2: 50ms
Iter 3: 10ms  # 稳定
```

**解决**

```python
# Warmup：预编译 + 预分配内存
def warmup(model, input_shape, iterations=10):
    dummy_input = torch.randn(*input_shape).npu()
    model = model.npu().eval()
    
    with torch.no_grad():
        for _ in range(iterations):
            _ = model(dummy_input)
            torch.npu.synchronize()
```

### 问题 3：精度下降

**定位**

```python
# 逐层对比（见 model-migration skill）
layer_wise_check(model_fp32, model_opt, test_data)
```

**常见原因**

- FP16 下溢/上溢 → 混合精度策略
- 算子融合精度问题 → 禁用特定融合
- 量化 calibration 不足 → 增加 calibration 数据

## §8 参考资源

**官方文档**

- [CANN 性能调优指南](https://www.hiascend.com/document)
- [Ascend PyTorch Profiler](https://gitee.com/ascend/pytorch)
- [AMCT 量化工具](https://www.hiascend.com/software/cann/commercial)

**社区案例**

- [YOLOv10 NPU 优化实战](https://ai.gitcode.com/luckymitty/yolov10-npu)：延迟 4.2ms，38.9x 加速
- [CANN 图优化技术解析](https://devpress.csdn.net/awstech/6a9211d73bda720d4b361ab8.html)
- [Ascend C 算子性能优化](https://www.hiascend.com/developer/techArticles/20240823-1)
