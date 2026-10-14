# ReviewAgent — Agent 路由

| Agent | 何时用 |
|-------|--------|
| [cann-op-checker](.cursor/agents/cann-op-checker.md) | AscendC / 社区任务算子、design.md、ops-\*/asc-devkit MR、IT 五件套 |
| [cann-inference-advisor](.cursor/agents/cann-inference-advisor.md) | 模型迁移、torch-npu、推理优化、服务部署、vLLM-Ascend |

含糊「昇腾检查」时先问：算子社区任务，还是推理部署？

## Skills

| Skill | 用途 |
|-------|------|
| `cann-ascendc-op-dev` | 算子开发/验收规范 |
| `common-issues-patterns` | 社区常见问题速查 |
| `model-migration` | 迁移与精度对齐 |
| `inference-optimization` | Profiling / 图优化 |
| `deployment-practices` | 服务化与容器 |
| `vllm-ascend-practices` | LLM 推理专项 |

镜像目录：`.cursor/`（Cursor）与 `.agents/`（通用）；Codex 见 `.codex/agents/*.toml`。

## CLI（本地）

```bash
python ascend_cli.py review --offline --json
python ascend_cli.py search "507049 HCCL"
python -m unittest discover -s tests -v
```
