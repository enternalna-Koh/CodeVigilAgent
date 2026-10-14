---
name: common-issues-patterns
description: torch-npu 社区常见问题、审核模式、典型错误与解决方案汇总
version: 1.0.0
tags: [troubleshooting, common-issues, review-patterns, debugging]
---

# torch-npu 常见问题与审核模式

基于社区实践案例、技术文章和部署经验整理的典型问题库。

## §0 问题分类

```text
Level 1: 环境与依赖 (30%)
  └─ CANN 版本不匹配、驱动问题、Python 环境

Level 2: API 兼容性 (25%)
  └─ 算子不支持、参数差异、返回值类型

Level 3: 精度问题 (20%)
  └─ 数值误差超标、NaN/Inf、累积误差

Level 4: 性能异常 (15%)
  └─ 速度慢于预期、内存泄漏、利用率低

Level 5: 运行时错误 (10%)
  └─ 段错误、超时、设备初始化失败
```

## §1 环境与依赖问题

### 问题 1.1：CANN 与 torch-npu 版本不匹配

**典型报错**

```python
ImportError: libtorch_npu.so: cannot open shared object file
RuntimeError: CANN version mismatch: expected 8.0.RC2, got 7.0.0
```

**原因**

torch-npu 编译时链接的 CANN 版本与运行环境不一致。

**解决方案**

```bash
# 1. 检查版本对应关系
python -c "import torch; import torch_npu; print(f'PyTorch: {torch.__version__}, torch-npu: {torch_npu.__version__}')"

# 2. 查看 CANN 版本
cat /usr/local/Ascend/ascend-toolkit/latest/version.cfg

# 3. 安装匹配的 torch-npu
# 参考官方兼容性矩阵：
# PyTorch 2.1.0 → torch-npu 2.1.0.post3 → CANN 8.0.RC1+
# PyTorch 2.0.1 → torch-npu 2.0.1.post6 → CANN 7.0.0+
```

**审核要点**
- [ ] README 明确标注 CANN、PyTorch、torch-npu 三者版本
- [ ] requirements.txt 固定 torch-npu 版本号
- [ ] Dockerfile 使用官方基础镜像或明确 CANN 版本

### 问题 1.2：设备权限不足

**典型报错**

```
RuntimeError: Failed to initialize NPU device: Permission denied
ACL Error: ACL_ERROR_RT_NO_DEVICE (100001)
```

**原因**

用户无权限访问 `/dev/davinci*` 设备节点。

**解决方案**

```bash
# 检查设备节点
ls -l /dev/davinci*

# 添加用户到 HwHiAiUser 组
sudo usermod -aG HwHiAiUser $USER

# 容器化部署需映射设备
docker run --device /dev/davinci0 \
           --device /dev/davinci_manager \
           --device /dev/devmm_svm \
           --device /dev/hisi_hdc \
           ...
```

**审核要点**
- [ ] 部署文档包含权限配置步骤
- [ ] Docker Compose 正确映射所有必需设备节点
- [ ] K8s 配置使用设备插件或 privileged 模式

### 问题 1.3：环境变量缺失

**典型报错**

```
OSError: libascendcl.so: cannot open shared object file
```

**原因**

CANN 动态库路径未加入 `LD_LIBRARY_PATH`。

**解决方案**

```bash
# 在 ~/.bashrc 或脚本中添加
source /usr/local/Ascend/ascend-toolkit/set_env.sh

# 或手动设置
export LD_LIBRARY_PATH=/usr/local/Ascend/ascend-toolkit/latest/lib64:$LD_LIBRARY_PATH
export PYTHONPATH=/usr/local/Ascend/ascend-toolkit/latest/python/site-packages:$PYTHONPATH
export PATH=/usr/local/Ascend/ascend-toolkit/latest/bin:$PATH
export ASCEND_HOME=/usr/local/Ascend/ascend-toolkit/latest
```

**审核要点**
- [ ] 启动脚本包含环境变量设置
- [ ] 容器镜像已正确设置 ENV
- [ ] systemd service 文件包含 `Environment=` 配置

## §2 API 兼容性问题

### 问题 2.1：算子不支持

**典型报错**

```python
RuntimeError: The operator [aten::some_op] is not supported on NPU
NotImplementedError: npu::some_function not implemented
```

**高频不支持算子**

| 算子 | 原因 | 替代方案 |
|------|------|----------|
| `torch.sparse.*` | 稀疏张量支持有限 | 转密集或自定义实现 |
| `torch.linalg.svd` | 部分线性代数算子 | CPU 回退或简化算法 |
| `torch.complex*` | 复数支持不完整 | 拆分实部虚部 |
| `torch.jit.trace` | JIT 编译限制 | 使用 eager mode |
| `F.interpolate(mode='bicubic')` | 插值模式限制 | 改用 'bilinear' |

**解决方案**

```python
# 方案 A：CPU 回退（性能差）
if torch.npu.is_available() and not hasattr(torch.npu, 'some_op'):
    x_cpu = x.cpu()
    result = torch.some_op(x_cpu)
    result = result.npu()

# 方案 B：等效实现
# 例如：bicubic → bilinear
output = F.interpolate(x, size=(H, W), mode='bilinear', align_corners=True)

# 方案 C：条件编译
USE_NPU = torch.npu.is_available() and hasattr(torch.npu, 'some_op')
if USE_NPU:
    result = torch.npu.some_op(x)
else:
    result = fallback_implementation(x)
```

**审核要点**
- [ ] README 列出不支持的算子及替代方案
- [ ] 代码中有 CPU 回退或等效实现
- [ ] 不能静默失败或返回错误结果

### 问题 2.2：In-place 操作限制

**典型报错**

```python
RuntimeError: npu does not support inplace operation for view
RuntimeError: inplace add on npu is not allowed for this dtype
```

**常见场景**

```python
# ❌ 错误：view 上的 in-place
x = tensor.view(-1, 10)
x += 1  # 报错

# ✅ 正确：非 in-place
x = tensor.view(-1, 10)
x = x + 1

# ❌ 错误：混合精度 in-place
x_fp16 = x.half()
x_fp16.add_(y_fp32)  # 报错

# ✅ 正确：统一类型
x_fp16.add_(y_fp32.half())
```

**审核要点**
- [ ] 避免在 view/reshape 结果上使用 `+=`, `-=`, `*=` 等
- [ ] 混合精度计算显式转换类型
- [ ] 代码注释说明为何不用 in-place

### 问题 2.3：参数默认值差异

**典型案例**

```python
# CUDA 默认：torch.nn.BatchNorm2d(eps=1e-5, momentum=0.1)
# NPU：相同默认值，但数值行为可能不同

# 问题：精度敏感场景需调整
# ✅ 显式指定参数
bn = nn.BatchNorm2d(128, eps=1e-3, momentum=0.01)  # 更稳定

# 问题：torch.topk 的 largest/sorted 参数
# CUDA: largest=True, sorted=True
# NPU: 部分情况未排序

# ✅ 强制指定
values, indices = torch.topk(logits, k=10, largest=True, sorted=True)
```

**审核要点**
- [ ] 关键算子显式指定所有参数（不依赖默认值）
- [ ] 精度敏感层（BN/LN）调整 eps 参数
- [ ] README 说明调整理由

## §3 精度问题

### 问题 3.1：FP16 下溢/上溢

**典型现象**

```python
# 训练/推理过程中出现 NaN 或 Inf
loss = nan
output contains inf values
```

**诊断**

```python
def check_tensor_health(tensor, name="tensor"):
    """检查张量健康状态"""
    if torch.isnan(tensor).any():
        print(f"❌ {name} contains NaN")
    if torch.isinf(tensor).any():
        print(f"❌ {name} contains Inf")
    
    max_val = tensor.abs().max().item()
    min_val = tensor[tensor != 0].abs().min().item() if (tensor != 0).any() else 0
    
    print(f"{name}: max={max_val:.2e}, min={min_val:.2e}")
    
    # FP16 范围：6e-5 ~ 65504
    if max_val > 60000:
        print(f"⚠️ {name} may overflow in FP16")
    if min_val < 1e-4 and min_val > 0:
        print(f"⚠️ {name} may underflow in FP16")
```

**解决方案**

```python
# 方案 A：混合精度 - 敏感层用 FP32
class MixedPrecisionModel(nn.Module):
    def __init__(self):
        self.conv = nn.Conv2d(...).half()  # FP16
        self.bn = nn.BatchNorm2d(...)      # FP32（BN 敏感）
        self.fc = nn.Linear(...).half()
    
    def forward(self, x):
        x = x.half()
        x = self.conv(x)
        x = self.bn(x.float()).half()  # BN 用 FP32
        x = self.fc(x)
        return x

# 方案 B：Loss scaling（训练）
from torch_npu.amp import GradScaler
scaler = GradScaler()

# 方案 C：调整学习率
# FP16 训练建议降低 LR，避免梯度爆炸
optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)  # 原 1e-3
```

**审核要点**
- [ ] 精度测试覆盖边界输入（全零、极大值、极小值）
- [ ] 训练代码使用 GradScaler
- [ ] 文档说明 FP16 的数值范围限制

### 问题 3.2：累积误差

**典型现象**

```python
# 单步精度对齐，但多步后误差累积
# Step 1: CPU vs NPU diff = 1e-4 ✓
# Step 10: diff = 1e-2 ✗
# Step 100: diff = 0.5 ✗✗
```

**原因**

- 浮点运算顺序差异
- 累加误差传播
- Softmax/LayerNorm 实现差异

**解决方案**

```python
# 方案 A：定期同步（训练时）
if step % 100 == 0:
    # 从 CPU baseline 重新加载状态
    model.load_state_dict(cpu_checkpoint)

# 方案 B：提高中间精度
# 关键累加操作用 FP32
acc = torch.zeros(size, dtype=torch.float32).npu()
for x in inputs:
    acc += x.float()  # 累加用 FP32
result = acc.half()

# 方案 C：Kahan 求和（高精度累加）
def kahan_sum(inputs):
    s = torch.zeros_like(inputs[0])
    c = torch.zeros_like(inputs[0])
    for x in inputs:
        y = x - c
        t = s + y
        c = (t - s) - y
        s = t
    return s
```

**审核要点**
- [ ] 多步推理的精度测试（至少 100 步）
- [ ] 累加/归约操作考虑精度损失
- [ ] 文档说明可接受的误差范围

### 问题 3.3：算子融合精度损失

**典型现象**

```python
# GE 图优化后精度下降
# 原因：Conv+BN+ReLU 融合实现与逐层计算有差异
```

**定位**

```bash
# 禁用特定融合 Pass
export ENABLE_FUSION=0

# 或在 fusion_switch.cfg 中禁用
[UB_FUSION]
ubfusion_conv_bn_reduce=off
```

**解决方案**

```python
# 方案 A：禁用问题融合
# ATC 转换时配置
atc --fusion_switch_file=no_fusion.cfg ...

# 方案 B：逐层精度对比
# 使用 GE dump 功能导出每层输出
export DUMP_GE_GRAPH=3
export DUMP_OP=ConvBNReLU  # 重点算子
```

**审核要点**
- [ ] 图优化前后精度对比测试
- [ ] 提供禁用融合的配置选项
- [ ] README 说明精度权衡

## §4 性能异常

### 问题 4.1：NPU 利用率低

**诊断**

```bash
# 实时监控
watch -n 1 npu-smi info

# 关键指标
# Utilization: <30% → 有瓶颈
# Power: 远低于 TDP → 未充分利用
```

**常见原因与方案**

| 原因 | 特征 | 解决方案 |
|------|------|----------|
| **CPU 预处理慢** | CPU 100%，NPU <30% | 多进程预处理 / AIPP |
| **Batch size 小** | 单次推理 <5ms | 增大 batch 或动态 batching |
| **内存拷贝多** | MemCpy 耗时 >20% | Pin memory / 减少 H2D |
| **Stream 串行** | Stream gap 大 | 多 Stream 并发 |
| **算子未优化** | AICPU 占比高 | 自定义算子迁移到 AI Core |

**审核要点**
- [ ] Profiling 数据分析 CPU/NPU 利用率
- [ ] 识别瓶颈并给出具体优化方案
- [ ] 性能报告包含优化前后对比

### 问题 4.2：内存泄漏

**典型现象**

```python
# 长时间运行后 OOM
# npu-smi 显示显存持续增长
RuntimeError: NPU out of memory
```

**诊断**

```python
import torch_npu

# 打印显存使用
print(f"Allocated: {torch.npu.memory_allocated() / 1e9:.2f} GB")
print(f"Reserved: {torch.npu.memory_reserved() / 1e9:.2f} GB")

# 清空缓存
torch.npu.empty_cache()

# 跟踪内存分配
torch.npu.memory._record_memory_history()
```

**常见原因**

```python
# ❌ 错误 1：中间变量累积
for data in dataloader:
    loss = model(data)
    losses.append(loss)  # loss 持有计算图

# ✅ 正确：detach
losses.append(loss.detach().cpu())

# ❌ 错误 2：未释放张量
outputs = []
for data in dataloader:
    out = model(data)
    outputs.append(out)  # 全部留在显存

# ✅ 正确：及时处理
for data in dataloader:
    out = model(data)
    process(out)  # 处理后自动释放

# ❌ 错误 3：循环引用
self.cache = {data: model(data)}  # model 持有 self

# ✅ 正确：使用 weakref 或及时清理
```

**审核要点**
- [ ] 长时间运行测试（>1000 次推理）
- [ ] 显存监控无持续增长
- [ ] 代码中无明显的张量累积

### 问题 4.3：首次推理慢

**典型现象**

```python
# Warmup 前：1000ms
# Warmup 后：10ms
```

**原因**

- 图编译（首次执行）
- 内存预分配
- 算子库加载

**解决方案**

```python
# 标准 warmup
def warmup(model, input_shape, device='npu', iterations=10):
    model = model.to(device).eval()
    dummy = torch.randn(*input_shape).to(device)
    
    with torch.no_grad():
        for _ in range(iterations):
            _ = model(dummy)
    
    torch.npu.synchronize()
    print("✓ Warmup completed")

# 服务启动时执行
warmup(model, (1, 3, 224, 224))
```

**审核要点**
- [ ] 服务启动脚本包含 warmup
- [ ] 性能测试排除首次推理
- [ ] 文档说明预热必要性

## §5 PR 审核常见反馈模式

基于社区实践整理的审核人常见要求：

### 代码质量

- [ ] **类型标注**：关键函数添加类型提示
- [ ] **错误处理**：API 调用检查返回值，异常有上下文
- [ ] **日志规范**：使用 logging 模块，分级记录
- [ ] **Magic number**：硬编码数字提取为常量

### 测试覆盖

- [ ] **单元测试**：新增功能有对应测试
- [ ] **精度测试**：迁移代码必须有 CPU vs NPU 对比
- [ ] **边界测试**：覆盖空输入、极值、异常情况

### 文档完整性

- [ ] **README 更新**：新增 API 或参数说明
- [ ] **CHANGELOG**：记录不兼容变更
- [ ] **示例代码**：复杂功能提供 minimal example

### 性能要求

- [ ] **Benchmark**：性能改进需要前后对比数据
- [ ] **Profiling**：优化 PR 附带 profiling 截图
- [ ] **回归测试**：确保优化不影响精度

### 兼容性

- [ ] **版本兼容**：标注支持的 PyTorch/CANN 版本
- [ ] **向后兼容**：API 变更保留旧接口或提供迁移指南
- [ ] **平台兼容**：代码在 910/310/A3 上可运行

## §6 快速诊断流程

```text
问题发生 → 定位层级

1. 环境层
   ├─ CANN 版本？ → cat version.cfg
   ├─ torch-npu 版本？ → python -c "import torch_npu; print(torch_npu.__version__)"
   └─ 设备可见？ → npu-smi info

2. API 层
   ├─ 算子支持？ → 查官方算子清单
   ├─ 参数匹配？ → 对比 CUDA 文档
   └─ 返回值一致？ → 单元测试

3. 数值层
   ├─ 精度对齐？ → CPU vs NPU diff
   ├─ NaN/Inf？ → check_tensor_health()
   └─ 累积误差？ → 多步测试

4. 性能层
   ├─ 利用率？ → npu-smi
   ├─ 瓶颈？ → msprof / Ascend PyTorch Profiler
   └─ 内存？ → torch.npu.memory_allocated()
```

## §7 参考资源

- [torch-npu FAQ](https://gitee.com/ascend/pytorch/wikis/FAQ)
- [昇腾社区问答](https://www.hiascend.com/forum)
- [CANN 故障处理指南](https://www.hiascend.com/document)
