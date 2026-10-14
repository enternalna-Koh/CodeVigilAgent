# vllm-ascend-practices

vLLM-Ascend 大模型推理部署实践 - 常见问题、性能优化、多卡部署

## 内容结构

- **SKILL.md** - 主知识文件，包含：
  - §0 vLLM-Ascend 概述（架构、版本依赖）
  - §1 常见部署问题（依赖、请求卡死、OOM、KV Cache）
  - §2 性能优化（吞吐量、延迟、Flash Attention）
  - §3 模型适配（支持模型、自定义适配、量化）
  - §4 生产部署 Checklist
  - §5 常见错误速查
  - §6 参考资源

## 适用场景

- LLM 推理服务部署
- 多卡/多节点并行推理
- 吞吐量与延迟优化
- 模型量化部署
- 生产环境故障排查

## 核心问题覆盖

基于 [vllm-ascend 社区](https://github.com/vllm-project/vllm-ascend) 真实案例：

### 高频问题
1. **请求卡死** - Client 冻结、服务不接收新请求
2. **多节点 OOM** - 32 卡集群启动失败
3. **KV Cache 传输失败** - Prefill-Decode 分离架构问题
4. **依赖版本不匹配** - CANN/torch-npu/vllm 版本冲突

### 性能目标
- Qwen2.5-7B (1x910B): ~2000 tok/s
- Qwen2.5-72B (8x910B): ~800 tok/s
- P95 TTFT: <2s
- P95 TPOT: <100ms

## 关键配置

```bash
# 生产推荐配置
vllm serve model_name \
    --gpu-memory-utilization 0.85 \
    --max-num-seqs 128 \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    --timeout 120
```

## 参考资源

- [vLLM-Ascend 官方文档](https://docs.vllm.ai/projects/ascend/)
- [FAQ 常见问题](https://docs.vllm.ai/projects/ascend/en/latest/faqs.html)
- [社区 Issue 跟踪](https://github.com/vllm-project/vllm-ascend/issues)
