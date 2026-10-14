# deployment-practices

CANN 推理服务部署实践 - 服务化、容器化、监控、生产最佳实践

## 内容结构

- **SKILL.md** - 主知识文件，包含：
  - §0 部署架构选择
  - §1 服务化封装（FastAPI/gRPC）
  - §2 容器化部署（Docker/K8s）
  - §3 监控与可观测性（Prometheus/Grafana）
  - §4 生产 Checklist
  - §5 故障处理
  - §6 参考案例

## 使用场景

- REST API 推理服务
- 容器化部署（Docker/K8s）
- 生产环境监控告警
- 高可用架构设计
- 故障诊断与恢复

## 技术栈

- **服务框架**：FastAPI / gRPC
- **容器编排**：Docker Compose / Kubernetes
- **监控**：Prometheus + Grafana
- **链路追踪**：OpenTelemetry + Jaeger
- **负载均衡**：Nginx / K8s Service

## 生产要求

- P95 延迟满足 SLA
- 健康检查 + 优雅关闭
- 结构化日志 + 指标采集
- 限流熔断 + 降级策略

## 参考案例

- [MolScribe 容器化](https://ai.gitcode.com/Ascend-SACT/MolScribe)
- [X-VLA FastAPI 服务](https://ai.gitcode.com/Bug_Factory_w/X-VLA-WidowX)
