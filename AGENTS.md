# ReviewAgent — Agent 路由

| Agent | 何时用 |
|-------|--------|
| [cann-op-checker](.cursor/agents/cann-op-checker.md) | AscendC / 社区任务算子、design.md、ops-\*/asc-devkit MR、IT 五件套 |
| [cann-inference-advisor](.cursor/agents/cann-inference-advisor.md) | 模型迁移、torch-npu、推理优化、服务部署、vLLM-Ascend、API 一致性任务 |
| [opengauss-community-advisor](.cursor/agents/opengauss-community-advisor.md) | openGauss Plugin / examples / docs、师生审核对话、社区 CI |

含糊时先问：昇腾算子社区任务、昇腾推理部署，还是 openGauss？

## Skills

| Skill | 用途 |
|-------|------|
| `cann-ascendc-op-dev` | 算子开发/验收规范 |
| `common-issues-patterns` | 社区常见问题速查 |
| `model-migration` | 迁移与精度对齐 |
| `inference-optimization` | Profiling / 图优化 |
| `deployment-practices` | 服务化与容器 |
| `vllm-ascend-practices` | LLM 推理专项 |
| `api-consistency-community` | Ascend for PyTorch API 一致性任务导航 |
| `opengauss-community` | openGauss 社区审核要点 |

官方可装（对话 `/skill install`）：`torch-npu-pr-review` 等，见  
`https://gitcode.com/Ascend/pytorch-ecosystem/tree/master/01_tasks/resources/tools/agent_skills`

内置 MCP：`ascend-doc`（`npx -y ascend-doc-mcp@latest`），对话 `/mcp`。

镜像目录：`.cursor/`（Cursor）与 `.agents/`（通用）；Codex 见 `.codex/agents/*.toml`。

## CLI（本地）

```bash
python ascend_cli.py review --offline --json
python ascend_cli.py review --scenario opengauss --offline --json
python ascend_cli.py collect --community opengauss
python ascend_cli.py search "507049 HCCL"
python -m unittest discover -s tests -v
```
