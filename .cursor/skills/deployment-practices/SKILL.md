---
name: deployment-practices
description: CANN 推理服务部署实践 - 服务化、容器化、监控、生产最佳实践
version: 1.0.0
tags: [deployment, service, docker, monitoring, production]
---

# CANN 推理服务部署实践 Skill

## §0 部署架构选择

### 架构对比

```text
架构 A：单机服务
  ├─ 适用：低 QPS (<1000)，单模型
  ├─ 优势：简单，延迟低
  └─ 劣势：无容错，扩展性差

架构 B：微服务 + 负载均衡
  ├─ 适用：中高 QPS (1k-10k)，多模型
  ├─ 优势：高可用，可扩展
  └─ 劣势：复杂度高，延迟略增

架构 C：Serverless
  ├─ 适用：波动 QPS，成本敏感
  ├─ 优势：弹性伸缩，按量计费
  └─ 劣势：冷启动，NPU 支持有限
```

**推荐**：中小规模先用架构 A，QPS >1000 后升级到架构 B。

## §1 服务化封装

### 1.1 FastAPI 服务模板

**基础服务**

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
import torch_npu
import numpy as np
from typing import List, Optional
import uvicorn

app = FastAPI(title="CANN Inference Service", version="1.0.0")

# 全局模型（启动时加载）
model = None
device = None

class InferenceRequest(BaseModel):
    data: List[List[float]]  # [[...], [...]]
    batch_size: Optional[int] = 1

class InferenceResponse(BaseModel):
    predictions: List[List[float]]
    latency_ms: float

@app.on_event("startup")
async def load_model():
    """启动时加载模型"""
    global model, device
    
    try:
        device = torch.device('npu:0')
        model = torch.jit.load('model.pt').to(device).eval()
        
        # Warmup
        dummy_input = torch.randn(1, 3, 224, 224).to(device)
        with torch.no_grad():
            for _ in range(10):
                _ = model(dummy_input)
                torch.npu.synchronize()
        
        print("✅ Model loaded successfully")
    except Exception as e:
        print(f"❌ Model loading failed: {e}")
        raise

@app.get("/health")
async def health_check():
    """健康检查"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {
        "status": "healthy",
        "device": str(device),
        "npu_available": torch.npu.is_available()
    }

@app.post("/predict", response_model=InferenceResponse)
async def predict(request: InferenceRequest):
    """推理接口"""
    import time
    
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # 预处理
        input_tensor = torch.tensor(request.data).to(device)
        
        # 推理
        start = time.time()
        with torch.no_grad():
            output = model(input_tensor)
            torch.npu.synchronize()
        latency = (time.time() - start) * 1000
        
        # 后处理
        predictions = output.cpu().numpy().tolist()
        
        return InferenceResponse(
            predictions=predictions,
            latency_ms=round(latency, 2)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # NPU 推理通常单进程
        log_level="info"
    )
```

### 1.2 生产级增强

**并发控制**

```python
import asyncio
from asyncio import Semaphore

# 限制并发请求数（避免 OOM）
MAX_CONCURRENT = 4
inference_semaphore = Semaphore(MAX_CONCURRENT)

@app.post("/predict")
async def predict(request: InferenceRequest):
    async with inference_semaphore:
        # 原推理逻辑
        return await _do_inference(request)
```

**请求队列 + 动态 Batching**

```python
from collections import deque
from asyncio import Event, create_task

class BatchInferenceQueue:
    def __init__(self, model, max_batch_size=32, max_wait_ms=10):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.queue = deque()
        self.processing = False
        
    async def infer(self, data):
        """异步推理接口"""
        future = asyncio.Future()
        self.queue.append((data, future))
        
        if not self.processing:
            create_task(self._process_queue())
        
        return await future
    
    async def _process_queue(self):
        """批处理队列"""
        self.processing = True
        
        while self.queue:
            # 等待凑够 batch 或超时
            batch_data = []
            futures = []
            
            deadline = asyncio.get_event_loop().time() + self.max_wait_ms / 1000
            
            while len(batch_data) < self.max_batch_size:
                if not self.queue:
                    # 等待新请求或超时
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(remaining, 0.001))
                    if not self.queue:
                        break
                
                data, future = self.queue.popleft()
                batch_data.append(data)
                futures.append(future)
            
            if not batch_data:
                break
            
            # 批量推理
            try:
                batch_tensor = torch.stack(batch_data).to(device)
                with torch.no_grad():
                    outputs = self.model(batch_tensor)
                
                # 分发结果
                for i, future in enumerate(futures):
                    future.set_result(outputs[i].cpu())
            
            except Exception as e:
                for future in futures:
                    future.set_exception(e)
        
        self.processing = False

# 全局队列
batch_queue = None

@app.on_event("startup")
async def init_queue():
    global batch_queue
    batch_queue = BatchInferenceQueue(model, max_batch_size=16, max_wait_ms=10)

@app.post("/predict_batched")
async def predict_batched(request: InferenceRequest):
    input_tensor = torch.tensor(request.data)
    output = await batch_queue.infer(input_tensor)
    return {"prediction": output.tolist()}
```

**超时处理**

```python
from asyncio import wait_for, TimeoutError

INFERENCE_TIMEOUT = 5.0  # 秒

@app.post("/predict")
async def predict(request: InferenceRequest):
    try:
        result = await wait_for(
            _do_inference(request),
            timeout=INFERENCE_TIMEOUT
        )
        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Inference timeout")
```

### 1.3 错误处理与降级

```python
import logging
from functools import wraps

logger = logging.getLogger(__name__)

# 降级模型（轻量级备份）
fallback_model = None

def with_fallback(func):
    """装饰器：失败时使用降级模型"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Primary inference failed: {e}")
            
            if fallback_model is not None:
                logger.info("Using fallback model")
                return await _fallback_inference(*args, **kwargs)
            else:
                raise
    
    return wrapper

@app.post("/predict")
@with_fallback
async def predict(request: InferenceRequest):
    # 主推理逻辑
    pass
```

## §2 容器化部署

### 2.1 Dockerfile 模板

**基础镜像**

```dockerfile
# 使用昇腾官方基础镜像
FROM ascendhub.huawei.com/public-ascendhub/ascend-pytorch:23.0.RC3-ubuntu20.04

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 拷贝代码和模型
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "server.py"]
```

**优化镜像（多阶段构建）**

```dockerfile
# Stage 1: 构建环境
FROM ascendhub.huawei.com/public-ascendhub/ascend-pytorch:23.0.RC3 AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

# Stage 2: 运行环境
FROM ascendhub.huawei.com/public-ascendhub/ascend-infer:23.0.RC3

WORKDIR /app

# 只拷贝必要的依赖
COPY --from=builder /build/deps /usr/local/lib/python3.8/site-packages

# 拷贝代码和模型
COPY server.py .
COPY model.pt .

# 非 root 用户运行
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "server.py"]
```

### 2.2 Docker Compose 编排

```yaml
# docker-compose.yml
version: "3.8"

services:
  inference-service:
    build:
      context: .
      dockerfile: Dockerfile
    image: cann-inference:latest
    container_name: inference-service
    ports:
      - "8000:8000"
    devices:
      - /dev/davinci0:/dev/davinci0  # 映射 NPU 设备
      - /dev/davinci_manager:/dev/davinci_manager
      - /dev/devmm_svm:/dev/devmm_svm
      - /dev/hisi_hdc:/dev/hisi_hdc
    volumes:
      - /usr/local/Ascend/driver:/usr/local/Ascend/driver:ro
      - ./logs:/app/logs
    environment:
      - ASCEND_VISIBLE_DEVICES=0  # 指定 NPU 卡号
      - GLOG_v=2  # 日志级别
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 8G

  # Nginx 负载均衡（可选）
  nginx:
    image: nginx:alpine
    container_name: nginx-lb
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - inference-service
    restart: unless-stopped
```

**Nginx 配置（nginx.conf）**

```nginx
upstream inference_backend {
    least_conn;  # 最少连接数负载均衡
    server inference-service-1:8000;
    server inference-service-2:8000;
    server inference-service-3:8000;
}

server {
    listen 80;
    
    location /predict {
        proxy_pass http://inference_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    location /health {
        proxy_pass http://inference_backend;
        access_log off;
    }
}
```

### 2.3 Kubernetes 部署

**Deployment 配置**

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cann-inference
  labels:
    app: cann-inference
spec:
  replicas: 3
  selector:
    matchLabels:
      app: cann-inference
  template:
    metadata:
      labels:
        app: cann-inference
    spec:
      containers:
      - name: inference
        image: registry.example.com/cann-inference:v1.0
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: ASCEND_VISIBLE_DEVICES
          value: "0"
        resources:
          limits:
            # 昇腾 NPU 资源（需要设备插件）
            ascend.com/Ascend910: 1
            memory: "8Gi"
            cpu: "4"
          requests:
            ascend.com/Ascend910: 1
            memory: "4Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        volumeMounts:
        - name: ascend-driver
          mountPath: /usr/local/Ascend/driver
          readOnly: true
      volumes:
      - name: ascend-driver
        hostPath:
          path: /usr/local/Ascend/driver
---
apiVersion: v1
kind: Service
metadata:
  name: cann-inference-service
spec:
  selector:
    app: cann-inference
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

## §3 监控与可观测性

### 3.1 指标采集

**Prometheus 指标**

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# 定义指标
REQUEST_COUNT = Counter(
    'inference_requests_total',
    'Total inference requests',
    ['endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'inference_latency_seconds',
    'Inference latency',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

NPU_UTILIZATION = Gauge(
    'npu_utilization_percent',
    'NPU utilization',
    ['device_id']
)

NPU_MEMORY = Gauge(
    'npu_memory_used_bytes',
    'NPU memory usage',
    ['device_id']
)

@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    return Response(content=generate_latest(), media_type="text/plain")

@app.post("/predict")
async def predict(request: InferenceRequest):
    import time
    
    start = time.time()
    status = "success"
    
    try:
        # 推理逻辑
        result = await _do_inference(request)
        return result
    
    except Exception as e:
        status = "error"
        raise
    
    finally:
        # 记录指标
        REQUEST_COUNT.labels(endpoint="/predict", status=status).inc()
        REQUEST_LATENCY.observe(time.time() - start)

# 后台任务：采集 NPU 指标
import asyncio

async def collect_npu_metrics():
    """定期采集 NPU 使用率和内存"""
    while True:
        try:
            # 使用 npu-smi 采集（需解析输出）
            import subprocess
            result = subprocess.run(
                ["npu-smi", "info", "-t", "usages", "-i", "0", "-c", "0"],
                capture_output=True,
                text=True
            )
            
            # 解析并更新指标（示例）
            # NPU_UTILIZATION.labels(device_id="0").set(utilization)
            # NPU_MEMORY.labels(device_id="0").set(memory_used)
        
        except Exception as e:
            logger.error(f"Failed to collect NPU metrics: {e}")
        
        await asyncio.sleep(10)

@app.on_event("startup")
async def start_metrics_collector():
    asyncio.create_task(collect_npu_metrics())
```

**Grafana Dashboard 配置**

```json
{
  "dashboard": {
    "title": "CANN Inference Monitoring",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(inference_requests_total[1m])"
          }
        ]
      },
      {
        "title": "P95 Latency",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(inference_latency_seconds_bucket[5m]))"
          }
        ]
      },
      {
        "title": "NPU Utilization",
        "targets": [
          {
            "expr": "npu_utilization_percent"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(inference_requests_total{status=\"error\"}[1m]) / rate(inference_requests_total[1m])"
          }
        ]
      }
    ]
  }
}
```

### 3.2 日志规范

**结构化日志**

```python
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """JSON 格式日志"""
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

# 配置日志
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())

logger = logging.getLogger("inference")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# 使用
logger.info("Inference completed", extra={
    "request_id": "abc123",
    "latency_ms": 15.2,
    "model_version": "v1.0"
})
```

### 3.3 链路追踪

**OpenTelemetry 集成**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# 初始化 tracer
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)

trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

@app.post("/predict")
async def predict(request: InferenceRequest):
    with tracer.start_as_current_span("inference") as span:
        span.set_attribute("model.version", "v1.0")
        span.set_attribute("batch_size", len(request.data))
        
        with tracer.start_as_current_span("preprocess"):
            preprocessed = preprocess(request.data)
        
        with tracer.start_as_current_span("model.forward"):
            output = model(preprocessed)
        
        with tracer.start_as_current_span("postprocess"):
            result = postprocess(output)
        
        return result
```

## §4 生产 Checklist

### 4.1 性能要求

- [ ] **延迟 SLA**：P95 < 目标值（如 100ms）
- [ ] **吞吐量**：QPS 满足业务峰值 * 1.5 倍
- [ ] **并发能力**：最大并发请求数验证
- [ ] **资源利用率**：NPU 利用率 >60%，CPU <70%

### 4.2 可靠性要求

- [ ] **健康检查**：存活探针 + 就绪探针
- [ ] **超时机制**：请求超时、模型推理超时
- [ ] **熔断降级**：失败率阈值触发降级
- [ ] **优雅关闭**：SIGTERM 信号处理，等待请求完成

### 4.3 可观测性要求

- [ ] **指标完整**：QPS、延迟、错误率、NPU 指标
- [ ] **日志规范**：结构化、分级、可搜索
- [ ] **告警配置**：延迟超标、错误率高、资源异常
- [ ] **链路追踪**：关键路径可追踪

### 4.4 安全要求

- [ ] **认证鉴权**：API Key / OAuth2
- [ ] **限流保护**：IP 限流、用户限流
- [ ] **输入验证**：数据类型、范围、大小检查
- [ ] **敏感信息**：日志脱敏、模型加密

## §5 故障处理

### 常见故障与解决

| 故障 | 现象 | 排查 | 解决 |
|------|------|------|------|
| **NPU 初始化失败** | 503 错误 | `npu-smi info` | 检查驱动、权限 |
| **OOM** | 推理卡死 | 内存监控 | 减小 batch size、限流 |
| **延迟抖动** | P99 >> P50 | Profiling | GC 调优、Warmup |
| **吞吐下降** | QPS 降低 | CPU/NPU 利用率 | 增加实例、优化瓶颈 |
| **模型加载慢** | 启动慢 | - | 预编译、缓存模型 |

## §6 参考案例

- [MolScribe 容器化部署](https://ai.gitcode.com/Ascend-SACT/MolScribe)
- [Qwen3-Omni vLLM 服务](https://ai.gitcode.com/Ascend-SACT/Qwen3-Omni-30B-A3B-Instruct_vllm-ascend)
- [X-VLA FastAPI 服务化](https://ai.gitcode.com/Bug_Factory_w/X-VLA-WidowX)
