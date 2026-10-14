# 社区真实问题补充（基于 2026-10-14 数据收集）

本文档基于真实的 GitHub Issues 数据，补充常见问题模式。

## 数据来源

- **Ascend/pytorch**: 64 issues (40 open, 24 closed)
- **vllm-project/vllm-ascend**: 10 issues (2 open, 8 closed)
- **收集时间**: 2026-10-14

---

## §1 torch-npu 核心问题模式

### 问题 1.1：版本兼容性矩阵问题

**典型 Issue**: #144, #148, #99

**问题描述**
- torch_npu 2.10 + CANN 9.0 → `torch.nn.functional.linear` 失败
- torch_npu 2.1.0 + CANN 8.0.0 → Qwen3-ASR 微调失败
- torch_npu 2.7.1 + CANN 8.3.RC1 → 不兼容

**根本原因**

版本三元组必须严格匹配：
```
PyTorch version <-> torch-npu version <-> CANN version
```

**诊断脚本**

```bash
# 检查当前环境
python << 'EOF'
import torch
import torch_npu

print(f"PyTorch: {torch.__version__}")
print(f"torch-npu: {torch_npu.__version__}")

import subprocess
result = subprocess.run(['cat', '/usr/local/Ascend/ascend-toolkit/latest/version.cfg'], 
                       capture_output=True, text=True)
print(f"CANN: {result.stdout}")

# 验证兼容性
try:
    x = torch.randn(2, 3).npu()
    y = torch.nn.functional.linear(x, torch.randn(4, 3).npu())
    print("✓ 基础算子测试通过")
except Exception as e:
    print(f"✗ 兼容性测试失败: {e}")
EOF
```

**已知兼容组合**

| PyTorch | torch-npu | CANN | 状态 |
|---------|-----------|------|------|
| 2.1.0 | 2.1.0.post6 | 8.0.RC2+ | ✅ 稳定 |
| 2.1.0 | 2.1.0.post3 | 8.0.RC1 | ✅ 稳定 |
| 2.10 | ? | 9.0 | ❌ Issue #144 |
| 2.7.1 | 2.7.1 | 8.3.RC1 | ❌ Issue #99 |

### 问题 1.2：精度传播误差（训练场景）

**典型 Issue**: #107

**问题描述**

```
Ascend 910B vs NVIDIA H20
模型: Qwen-3VL-8B
场景: SFT 训练

观察：
- Forward loss 差距 <1%  ✓
- Layer 35 (最后层) main_grad 误差 <1%  ✓
- Layer 1 (第一层) main_grad 误差 50%-100%+  ✗

误差逐层放大，反向传播越往前误差越大
```

**可能原因**

1. **数值精度累积**：FP16 反向传播误差累积
2. **算子实现差异**：某些 backward 算子的数值稳定性
3. **梯度缩放问题**：loss_scale 设置不当

**排查步骤**

```python
# 1. 逐层梯度监控
import torch
import torch_npu

class GradientMonitor:
    def __init__(self, model):
        self.grads = {}
        for name, param in model.named_parameters():
            if param.requires_grad:
                param.register_hook(lambda grad, n=name: self.save_grad(n, grad))
    
    def save_grad(self, name, grad):
        self.grads[name] = {
            'mean': grad.abs().mean().item(),
            'max': grad.abs().max().item(),
            'std': grad.std().item()
        }
        return grad

# 2. 对比 NPU vs CPU 梯度
model_npu = model.npu()
model_cpu = model.cpu()

loss_npu = model_npu(input_npu)
loss_cpu = model_cpu(input_cpu)

loss_npu.backward()
loss_cpu.backward()

# 逐层对比
for (name_npu, param_npu), (name_cpu, param_cpu) in zip(
    model_npu.named_parameters(), 
    model_cpu.named_parameters()
):
    grad_diff = (param_npu.grad.cpu() - param_cpu.grad).abs().max()
    print(f"{name_npu}: grad_diff = {grad_diff:.6f}")
```

**临时缓解**

```python
# 1. 使用 FP32 累积梯度
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)
scaler = torch.cuda.amp.GradScaler()  # 使用梯度缩放

# 2. 梯度裁剪
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

# 3. 降低学习率
lr = 1e-5  # 比 GPU 版本降低一个数量级
```

### 问题 1.3：HCCL 超时与多进程问题

**典型 Issue**: #54, #166, #96

**问题 1.3.1**: `HCCL_EXEC_TIMEOUT=0` 不生效

```bash
# 设置无效
export HCCL_EXEC_TIMEOUT=0

# 正确做法（Issue #54 解决方案）
# 1. 检查环境变量是否真的传入
python -c "import os; print(os.environ.get('HCCL_EXEC_TIMEOUT'))"

# 2. 在 Python 代码中显式设置
import os
os.environ['HCCL_EXEC_TIMEOUT'] = '0'
import torch.distributed as dist
```

**问题 1.3.2**: ProcessGroupHCCL 创建失败（错误 507049）

```
fftsplus SDMA device error (507049) 
when another process uses CaMem sleep mode on the same NPU
```

**根本原因**：多进程竞争 NPU 资源

**解决方案**

```bash
# 方案 A：禁用 CaMem sleep mode
export CAMEM_SLEEP_MODE=0

# 方案 B：进程间 NPU 分配
torchrun --nproc_per_node=8 \
    --master_port=29500 \
    train.py \
    --local_rank $LOCAL_RANK

# 在代码中显式绑定
import torch_npu
torch_npu.npu.set_device(local_rank)
```

**问题 1.3.3**: 多进程 RuntimeError: devptr INTERNAL ASSERT FAILED

```
910B 多进程训练出现:
RuntimeError: devptr INTERNAL ASSERT FAILED
```

**排查清单**

- [ ] 每个进程是否独占一个 NPU（不要多进程共享）
- [ ] `torch_npu.npu.set_device()` 是否在 `dist.init_process_group()` 之前调用
- [ ] 是否存在跨进程的 tensor 共享（禁止）
- [ ] DataLoader 的 `num_workers` 是否过大（建议 ≤4）

### 问题 1.4：torch.compile 编译失败

**典型 Issue**: #154, #102, #97

**问题 1.4.1**: 编译时硬件访问超时

```python
import torch
import torch_npu

model = MyModel().npu()
model = torch.compile(model)  # ← 超时

# 报错：硬件访问超时
```

**临时方案**

```python
# 禁用 compile（回退到 eager mode）
model = MyModel().npu()
# model = torch.compile(model)  # 暂时注释

# 或使用 reduce-overhead 模式
model = torch.compile(model, mode="reduce-overhead")
```

**问题 1.4.2**: UB overflow 错误

```
Issue #102: 编译 layer_norm 和 addmm_silu 算子
报错: error: ub overflow
```

**原因**：Unified Buffer 大小超限

**解决方案**

```python
# 环境变量调整 UB 大小
import os
os.environ['ASCEND_UB_FUSION'] = '0'  # 禁用 UB 融合

# 或减小 batch size
```

### 问题 1.5：算子不支持或行为不一致

**典型 Issue**: #56, #150, #147

**问题汇总**

| 算子 | 问题 | Issue | 状态 |
|------|------|-------|------|
| `MaxPool1d` | 不支持 | #56 | Open |
| `interpolate` | small scale_factor 失败 | #150 | Open |
| `flex_attention` | 不支持 | #147 | Open |
| `scaled_dot_product_attention` | bool mask 错误 | #88 | Closed ✓ |

**临时方案**

```python
# MaxPool1d → MaxPool2d
import torch.nn as nn

# 不支持
pool1d = nn.MaxPool1d(kernel_size=3)

# 替代方案
pool2d = nn.MaxPool2d(kernel_size=(1, 3))
x_2d = x.unsqueeze(2)  # (B, C, L) -> (B, C, 1, L)
out = pool2d(x_2d).squeeze(2)

# interpolate small scale_factor
# 如果 scale_factor < 0.1 会失败
# 改用显式的 size 参数
out = F.interpolate(input, size=target_size, mode='bilinear')
```

---

## §2 vLLM-Ascend 核心问题模式

### 问题 2.1：KV Cache 相关错误

**典型 Issue**: #17923, #18178

**问题 2.1.1**: KV-pool lookup server 线程静默死亡

```
Symptom: 
- Scheduler 无限期挂起
- 请求等待但无响应
- 没有明显的错误日志

Root Cause:
KV-pool lookup server thread dies silently on any handler exception
```

**诊断**

```python
# 检查 KV cache 服务状态
import requests

resp = requests.get("http://localhost:8000/v1/stats")
stats = resp.json()

if stats['num_waiting_reqs'] > 0 and stats['num_running_reqs'] == 0:
    print("⚠️ KV cache server 可能已死亡")
```

**临时方案**

```bash
# 禁用 KV cache lookup（性能下降但稳定）
vllm serve model \
    --disable-kv-cache-manager
```

**问题 2.1.2**: EPLB 初始化失败（错误 103900）

```
[Bug] EPLB init fails with "HIXL EPLB register memory failed with status 103900"
when speculative decoding (draft model) + expandable_segments:True on Ascend A3
```

**解决方案**

```bash
# 禁用 expandable_segments
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:False

vllm serve model \
    --speculative-model draft_model \
    --num-speculative-tokens 5
```

### 问题 2.2：Triton 编译问题

**典型 Issue**: #17731, #18345

**问题 2.2.1**: FP8 RoPE 编译失败（910B3）

```
[Bug][Triton] FP8 RoPE fails to compile on Ascend 910B3 (f32 to E4M3FN)
```

**临时方案**

```bash
# 回退到 FP16
vllm serve model \
    --dtype half \
    # --quantization fp8  # 暂时禁用
```

**问题 2.2.2**: extract_slice 32字节对齐问题（A2/A3）

```
triton-ascend extract_slice API 起始地址非32字节对齐导致数据错误
```

**已修复** (Closed)，升级到最新版本

### 问题 2.3：GLM-5 配置问题

**典型 Issue**: #16954

```
GLM-5 & GLM-5.1 文档中 A3 PD 分离配置：
--kv-cache-dtype int8 \
--attention_config.indexer_kv_dtype int8 \
服务启动失败
```

**正确配置**

```bash
# 修正后的配置
vllm serve glm-5-model \
    --kv-cache-dtype auto \  # 使用 auto 而非 int8
    --enable-prefix-caching
```

---

## §3 高频错误代码速查

### CANN 错误代码

| 错误码 | 含义 | 典型场景 | Issue |
|--------|------|----------|-------|
| 507049 | SDMA device error | 多进程竞争 NPU | #166 |
| 507018 | AICPU 错误 | index_put_ 布尔掩码 | #153 |
| 561103 | aclnnInplaceCopy failed | copy_d2d 失败 | #90 |
| 103900 | EPLB register memory failed | speculative decoding | #18178 |

### torch-npu 常见报错

```python
# 1. MatMul/TransData 失败
RuntimeError: torch.nn.functional.linear fails with MatMul/TransData
→ 检查 torch-npu 与 CANN 版本兼容性

# 2. NPU out of memory
RuntimeError: NPU out of memory
→ 降低 batch size 或使用梯度累积

# 3. copy_d2d 失败
RuntimeError: copy_d2d:build/.../torch_npu.dir/...:104 NPU function error
→ 检查 tensor 设备一致性（不要混用 CPU/NPU）

# 4. HCCL timeout
RuntimeError: HCCL timeout
→ 设置 HCCL_EXEC_TIMEOUT=0 或增大超时时间
```

---

## §4 最佳实践（从问题中总结）

### 4.1 环境配置

```bash
# 1. 严格版本匹配
pip install torch==2.1.0
pip install torch-npu==2.1.0.post6
# 确保 CANN 8.0.RC2+

# 2. 必要的环境变量
export HCCL_EXEC_TIMEOUT=1800
export CAMEM_SLEEP_MODE=0
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:False

# 3. 多卡训练
export MASTER_ADDR=localhost
export MASTER_PORT=29500
export WORLD_SIZE=8
export RANK=0
```

### 4.2 代码模式

```python
# 1. 设备绑定（多进程）
import torch_npu
torch_npu.npu.set_device(local_rank)  # 必须在 init_process_group 之前

# 2. 梯度累积（解决 OOM）
for i, batch in enumerate(dataloader):
    loss = model(batch) / accumulation_steps
    loss.backward()
    
    if (i + 1) % accumulation_steps == 0:
        optimizer.step()
        optimizer.zero_grad()

# 3. 精度监控
def check_tensor_health(tensor, name):
    if torch.isnan(tensor).any():
        print(f"⚠️ NaN detected in {name}")
    if torch.isinf(tensor).any():
        print(f"⚠️ Inf detected in {name}")
```

### 4.3 避坑指南

**❌ 不要做的事**

1. ❌ 跨进程共享 NPU tensor
2. ❌ 混用 CPU 和 NPU tensor（显式 `.cpu()` / `.npu()`）
3. ❌ 在 `dist.init_process_group()` 之前使用 NPU 算子
4. ❌ DataLoader `num_workers` 设置过大（>4）
5. ❌ 忽略版本兼容性矩阵

**✅ 应该做的事**

1. ✅ 逐层监控梯度（训练场景）
2. ✅ 使用梯度裁剪（防止爆炸）
3. ✅ 设置合理的超时时间
4. ✅ 定期检查 tensor 健康状态（NaN/Inf）
5. ✅ 保留 CPU baseline 对比

---

## §5 社区活跃问题（2026-10 快照）

### Ascend/pytorch

**Open Issues (高优先级)**
- #170: os.environ.get 取值异常
- #167: torch_npu.profiler 丢失设备侧数据
- #166: ProcessGroupHCCL SDMA 错误
- #163: Dynamo 行为不一致
- #154: torch.compile 硬件访问超时

**总计**: 40 open, 24 closed

### vllm-project/vllm-ascend

**Open Issues**
- #14150: _invalid_block_ids 锁保护范围审计

**总计**: 2 open, 8 closed (稳定性较好)

---

*数据来源*: GitHub API  
*收集时间*: 2026-10-14  
*工具*: `scripts/auto_collect_and_analyze.py`
