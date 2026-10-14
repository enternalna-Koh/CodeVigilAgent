---
name: vllm-ascend-practices
description: vLLM-Ascend 大模型推理部署实践 - 常见问题、性能优化、多卡部署
version: 1.0.0
tags: [vllm, llm-inference, multi-gpu, kv-cache, ascend]
---

# vLLM-Ascend 大模型推理实践

基于 vllm-ascend 社区问题和部署经验整理的 LLM 推理最佳实践。

## §0 vLLM-Ascend 概述

### 架构特点

```text
vLLM (上游)
   ↓ 适配层
vLLM-Ascend
   ↓ 后端
torch-npu + CANN
   ↓ 硬件
Ascend 910B / A2
```

**核心优化**
- PagedAttention - KV Cache 分页管理
- Continuous Batching - 动态批处理
- Tensor Parallelism - 张量并行（多卡）
- Flash Attention - 注意力加速

### 版本依赖

| vLLM-Ascend | PyTorch | torch-npu | CANN | 硬件 |
|-------------|---------|-----------|------|------|
| 0.23.0 / 0.23.0.post1 | 2.10.0 | 2.10.0.post4 | 未核验 | 未核验 |
| 0.21.0rc1 | 2.10.0 | 2.10.0 | 未核验 | 未核验 |
| 0.18.0 | 2.9.0 | 2.9.0 | 未核验 | 未核验 |
| 0.11.0 | 2.7.1 | 2.7.1 | 未核验 | 未核验 |

来源：PyPI 各版本发布元数据 `https://pypi.org/pypi/vllm-ascend/<版本>/json` 的 `requires_dist`（项目主页 `vllm-project/vllm-ascend`），核验日期 2026-10-14。
PyTorch / torch-npu 两列是这些发布包声明的精确依赖（`==`）；CANN 与硬件不在 PyPI 元数据中，未核验，请以对应版本官方文档为准。
升级 vLLM-Ascend 后必须重新对照该版本的 `requires_dist`，不要沿用旧版本的 torch-npu 版本号。

**兼容性检查**

```bash
# 检查版本
python -c "import vllm; print(f'vLLM: {vllm.__version__}')"
python -c "import torch_npu; print(f'torch-npu: {torch_npu.__version__}')"
cat /usr/local/Ascend/ascend-toolkit/latest/version.cfg

# 验证 NPU 可用
python -c "import torch; import torch_npu; print(torch.npu.device_count())"
```

## §1 常见部署问题

### 问题 1.1：依赖版本不匹配

**典型报错**

```python
ImportError: torch_npu version mismatch
ModuleNotFoundError: No module named 'torch_npu'
RuntimeError: CANN NNAL Package not found
```

**诊断与解决**

```bash
# 1. 检查 torch-npu 是否安装
pip show torch-npu

# 2. 确认 CANN 版本匹配
ls /usr/local/Ascend/ascend-toolkit/

# 3. 安装匹配版本（示例，版本取自 PyPI vllm-ascend 0.23.0 的 requires_dist）
pip uninstall torch torch-npu -y
pip install torch==2.10.0
pip install torch-npu==2.10.0.post4

# 4. 安装 vllm-ascend（该版本要求 Python >=3.10）
pip install vllm-ascend==0.23.0
```

**部署清单**
- [ ] PyTorch 版本与 torch-npu 匹配
- [ ] torch-npu 版本与 CANN 匹配
- [ ] vllm-ascend 版本与上述兼容
- [ ] CANN NNAL Package 已安装（`/usr/local/Ascend/nnae/latest/`）

### 问题 1.2：请求卡死 / 推理冻结

**典型现象**

```text
Client freezes at X% progress
Server stops receiving new requests
Running reqs: 0, KV Cache: 0 (but client still waiting)
```

**原因分析**

1. **KV Cache 管理问题**：PagedAttention 分页失败
2. **请求调度阻塞**：Prefill-Decode 调度死锁
3. **多卡通信超时**：HCCL 集合通信卡住

**解决方案**

```bash
# 方案 A：调整 KV Cache 配置
vllm serve model_name \
    --gpu-memory-utilization 0.85 \  # 降低显存占用（默认 0.9）
    --max-num-batched-tokens 8192 \  # 减小 batch token 数
    --max-num-seqs 128 \             # 限制并发请求数
    --block-size 16                  # KV block 大小

# 方案 B：禁用 Prefix Caching（如果卡死发生在此阶段）
vllm serve model_name \
    --enable-prefix-caching false

# 方案 C：增加超时时间
vllm serve model_name \
    --timeout 300 \                  # 请求超时（秒）
    --max-model-len 4096             # 限制最大序列长度
```

**监控脚本**

```python
import requests
import time

def monitor_vllm_health(base_url="http://localhost:8000"):
    """监控 vLLM 服务健康状态"""
    while True:
        try:
            # 检查健康状态
            resp = requests.get(f"{base_url}/health", timeout=5)
            
            # 获取运行统计
            stats = requests.get(f"{base_url}/v1/stats", timeout=5).json()
            
            print(f"[{time.strftime('%H:%M:%S')}]")
            print(f"  Running: {stats.get('num_running_reqs', 0)}")
            print(f"  Waiting: {stats.get('num_waiting_reqs', 0)}")
            print(f"  KV Cache: {stats.get('gpu_cache_usage_perc', 0):.1f}%")
            
            # 告警：无运行请求但有等待
            if stats.get('num_running_reqs', 0) == 0 and stats.get('num_waiting_reqs', 0) > 0:
                print("⚠️ WARNING: Requests waiting but none running!")
        
        except Exception as e:
            print(f"❌ Health check failed: {e}")
        
        time.sleep(10)

# 使用
monitor_vllm_health()
```

**审核要点**
- [ ] 部署脚本包含 `--gpu-memory-utilization` 配置
- [ ] 生产环境设置合理的 `--timeout`
- [ ] 监控脚本检测请求卡死情况
- [ ] README 说明卡死问题的排查步骤

### 问题 1.3：多节点 OOM

**典型报错**

```text
RuntimeError: NPU out of memory
Atlas 900 A2 PoDc (4 nodes, 32 cards) OOM on startup
Service irrecoverable after OOM
```

**原因**

1. **模型分片不均**：某些卡负载过高
2. **KV Cache 预分配过大**：`--gpu-memory-utilization` 过高
3. **通信 buffer 开销**：HCCL 占用额外显存
4. **中间激活累积**：长序列推理时激活值占用

**诊断**

```bash
# 1. 查看各卡显存占用
npu-smi info

# 2. 启用显存跟踪
export VLLM_LOGGING_LEVEL=DEBUG
vllm serve ... 2>&1 | grep -i "memory"

# 3. 计算理论显存需求
# 模型权重：参数量 * bytes_per_param * (1 + optimizer_overhead)
# KV Cache：max_tokens * hidden_size * num_layers * 2 * bytes_per_kv
# 激活值：batch_size * seq_len * hidden_size * bytes
```

**解决方案**

```bash
# 方案 A：降低 KV Cache 占用
vllm serve model_name \
    --gpu-memory-utilization 0.75 \  # 从 0.9 降到 0.75
    --max-num-seqs 64 \              # 减半并发数
    --max-model-len 2048             # 缩短最大长度

# 方案 B：启用 CPU Offload（部分模型支持）
vllm serve model_name \
    --cpu-offload-gb 32 \            # 卸载 32GB 到 CPU
    --enforce-eager                  # 禁用 graph capture（减少显存）

# 方案 C：调整并行策略
vllm serve model_name \
    --tensor-parallel-size 8 \       # 增大 TP（更细粒度分片）
    --pipeline-parallel-size 1       # 暂不使用 PP

# 方案 D：量化
vllm serve model_name \
    --quantization awq \             # 或 gptq / fp8
    --dtype half                     # FP16（默认）
```

**多节点配置示例**

```bash
# Ray 集群启动（4 节点 32 卡）
ray start --head --port=6379 --node-ip-address=<head_ip>

# 其他节点
ray start --address=<head_ip>:6379

# vLLM 启动
vllm serve model_name \
    --tensor-parallel-size 8 \       # 每节点 8 卡
    --pipeline-parallel-size 4 \     # 4 个节点
    --gpu-memory-utilization 0.8 \
    --distributed-executor-backend ray
```

**审核要点**
- [ ] 多卡配置经过显存计算验证
- [ ] 启动脚本包含 OOM 重试逻辑
- [ ] README 给出不同模型的推荐配置（7B/13B/70B/175B）
- [ ] 监控显存水位，设置告警阈值（>90%）

### 问题 1.4：KV Cache 传输失败

**典型报错**

```text
Mooncake bootstrap failed
KV transfer timeout
Prefill-disaggregation request waiting indefinitely
Error not propagated to scheduler
```

**原因**

vLLM Ascend 在 Prefill/Decode 分离架构下，KV Cache 跨节点传输可能失败但错误未正确传播。

**临时方案**

```bash
# 禁用 Prefill-Decode 分离
vllm serve model_name \
    --disable-prefill-disaggregation

# 或调整超时
vllm serve model_name \
    --kv-transfer-timeout 60  # 增加传输超时（秒）
```

**监控与告警**

```python
import logging

def check_kv_transfer_health(log_file="/var/log/vllm.log"):
    """检测 KV 传输失败"""
    with open(log_file) as f:
        for line in f:
            if "KV transfer" in line and ("failed" in line or "timeout" in line):
                logging.error(f"KV transfer issue detected: {line}")
                # 触发告警或重启
```

**审核要点**
- [ ] 生产环境禁用 Prefill-Disaggregation（直到上游修复）
- [ ] 日志监控 KV 传输错误
- [ ] 文档说明该功能的已知问题

## §2 性能优化

### 2.1 吞吐量优化

**Benchmark 基线**

```bash
# 使用 vLLM benchmark 工具
python -m vllm.entrypoints.openai.api_server \
    --model model_name \
    --port 8000 &

# 压测
python benchmarks/benchmark_serving.py \
    --backend vllm \
    --model model_name \
    --num-prompts 1000 \
    --request-rate 10 \
    --dataset-name random
```

**关键参数调优**

```bash
vllm serve model_name \
    # === 吞吐量相关 ===
    --max-num-seqs 256 \              # ↑ 增大并发（显存允许）
    --max-num-batched-tokens 16384 \  # ↑ 增大 batch token
    --gpu-memory-utilization 0.95 \   # ↑ 最大化 KV Cache
    \
    # === 调度策略 ===
    --scheduling-policy fcfs \        # 或 priority
    --enable-chunked-prefill \        # 分块 prefill（降低延迟方差）
    --max-num-on-the-fly 8 \          # 允许 8 个请求同时 prefill
    \
    # === 硬件优化 ===
    --tensor-parallel-size 8 \
    --enable-prefix-caching \         # 前缀缓存（重复 prompt）
    --disable-log-requests            # 减少日志开销
```

**预期性能**

| 模型 | 硬件 | TP | Throughput | 延迟 P50 |
|------|------|----|-----------:|----------|
| Qwen2.5-7B | 1x910B | 1 | ~2000 tok/s | 20ms |
| Qwen2.5-72B | 8x910B | 8 | ~800 tok/s | 50ms |
| Qwen3.5-122B | 8x910B | 8 | ~500 tok/s | 80ms |
| Llama-3.1-70B | 8x910B | 8 | ~750 tok/s | 55ms |

### 2.2 延迟优化

**关键配置**

```bash
vllm serve model_name \
    # === 降低延迟 ===
    --max-num-seqs 32 \               # ↓ 减小并发（减少排队）
    --gpu-memory-utilization 0.8 \    # 留出 buffer
    --enable-chunked-prefill \        # 分块 prefill
    --max-num-batched-tokens 4096 \   # ↓ 减小 batch（降低单次延迟）
    \
    # === 抢占策略 ===
    --preemption-mode recompute \     # 或 swap（根据场景）
    --swap-space 4                    # CPU 交换空间（GB）
```

### 2.3 Flash Attention 配置

```bash
# 启用 Flash Attention（默认开启）
vllm serve model_name \
    --use-flash-attn

# 若遇到问题可禁用
vllm serve model_name \
    --disable-flash-attn
```

**故障排查**

```python
# 检查是否使用 Flash Attention
import torch_npu

# 查看日志
# [INFO] Using Flash Attention implementation
# 若显示 naive attention，检查：
# 1. torch-npu 版本是否支持
# 2. 模型 head_dim 是否符合要求（64/128）
```

## §3 模型适配

### 3.1 支持的模型架构

| 架构 | 代表模型 | 状态 |
|------|----------|------|
| Llama | Llama-3/3.1, Qwen, Yi | ✅ 全支持 |
| Mixtral | Mixtral-8x7B/8x22B | ✅ 支持 |
| GLM | ChatGLM2/3/4 | ✅ 支持 |
| Baichuan | Baichuan-13B/2-13B | ✅ 支持 |
| Phi | Phi-3 | ✅ 支持 |
| Gemma | Gemma-2B/7B | ⚠️ 部分支持 |
| Qwen-VL | Qwen2-VL | ⚠️ 实验性 |

### 3.2 自定义模型适配

**最小适配示例**

```python
# vllm_ascend/model_executor/models/my_model.py

from vllm.model_executor.models.llama import LlamaForCausalLM
import torch_npu

class MyModelForCausalLM(LlamaForCausalLM):
    """自定义模型，继承 Llama 架构"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义初始化
    
    def forward(self, *args, **kwargs):
        # 自定义前向传播
        return super().forward(*args, **kwargs)

# 注册模型
from vllm.model_executor.model_loader import _MODEL_REGISTRY
_MODEL_REGISTRY["MyModel"] = MyModelForCausalLM
```

### 3.3 量化模型

**支持的量化格式**

```bash
# AWQ
vllm serve model_name-awq \
    --quantization awq \
    --dtype half

# GPTQ
vllm serve model_name-gptq \
    --quantization gptq

# FP8（实验性）
vllm serve model_name \
    --quantization fp8 \
    --kv-cache-dtype fp8
```

**精度验证**

```python
# 对比 FP16 vs INT4 精度
from lm_eval import evaluator

results_fp16 = evaluator.simple_evaluate(
    model="vllm",
    model_args=f"pretrained={model_path},dtype=half",
    tasks=["mmlu", "ceval"],
)

results_awq = evaluator.simple_evaluate(
    model="vllm",
    model_args=f"pretrained={model_path}-awq,quantization=awq",
    tasks=["mmlu", "ceval"],
)

print(f"Accuracy drop: {results_fp16['mmlu'] - results_awq['mmlu']:.2%}")
```

## §4 生产部署 Checklist

### 启动配置

```bash
#!/bin/bash
# vllm_start.sh

# 环境变量
export VLLM_LOGGING_LEVEL=INFO
export VLLM_TRACE_FUNCTION=0
export NCCL_DEBUG=WARN  # HCCL 日志级别

# 启动服务
vllm serve ${MODEL_PATH} \
    --host 0.0.0.0 \
    --port 8000 \
    --served-model-name ${MODEL_NAME} \
    \
    # === 并行配置 ===
    --tensor-parallel-size ${TP_SIZE:-1} \
    --pipeline-parallel-size ${PP_SIZE:-1} \
    \
    # === 性能配置 ===
    --gpu-memory-utilization 0.85 \
    --max-num-seqs 128 \
    --max-num-batched-tokens 8192 \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    \
    # === 稳定性配置 ===
    --timeout 120 \
    --max-model-len 4096 \
    --disable-log-requests \
    \
    # === 监控 ===
    --enable-metrics \
    --metric-export-port 9090
```

### 监控指标

```yaml
# Prometheus 采集配置
scrape_configs:
  - job_name: 'vllm'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'
```

**关键指标**

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `vllm:num_requests_running` | 运行中请求数 | - |
| `vllm:num_requests_waiting` | 等待中请求数 | >100 |
| `vllm:gpu_cache_usage_perc` | KV Cache 使用率 | >95% |
| `vllm:time_to_first_token_seconds` | TTFT | P95 >2s |
| `vllm:time_per_output_token_seconds` | TPOT | P95 >0.1s |
| `vllm:request_success_total` | 成功请求数 | - |
| `vllm:request_failure_total` | 失败请求数 | >1% |

### 故障恢复

```bash
# systemd 服务配置
[Unit]
Description=vLLM Inference Service
After=network.target

[Service]
Type=simple
User=vllm
WorkingDirectory=/opt/vllm
ExecStart=/opt/vllm/vllm_start.sh
Restart=on-failure
RestartSec=10s
StartLimitInterval=0

# 健康检查
HealthCheckInterval=30s
HealthCheckCommand=/usr/bin/curl -f http://localhost:8000/health

[Install]
WantedBy=multi-user.target
```

## §5 常见错误速查

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `torch_npu not found` | 依赖缺失 | 安装 torch-npu |
| `CANN NNAL Package not found` | CANN 组件缺失 | 安装 NNAL |
| `NPU out of memory` | 显存不足 | 降低 `--gpu-memory-utilization` |
| `Request timeout` | 推理超时 | 增加 `--timeout` |
| `KV transfer failed` | 跨节点传输失败 | 禁用 prefill-disaggregation |
| `Model not supported` | 模型架构不支持 | 参考适配指南 |
| `HCCL error` | 多卡通信失败 | 检查网络、HCCL 配置 |

## §6 参考资源

**官方文档**
- [vLLM-Ascend Docs](https://docs.vllm.ai/projects/ascend/)
- [vLLM-Ascend FAQ](https://docs.vllm.ai/projects/ascend/en/latest/faqs.html)
- [GitHub Issues](https://github.com/vllm-project/vllm-ascend/issues)

**社区案例**
- [Qwen2.5-7B 部署教程](https://docs.vllm.ai/projects/ascend/en/v0.23.0/tutorials/models/Qwen2.5-7B.html)
- [多节点部署实践](https://www.hiascend.com/document)
- [性能调优指南](https://gitcode.com/cann/cann-recipes-infer)
