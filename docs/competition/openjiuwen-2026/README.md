# openJiuwen 智能体创新大赛 · 初赛材料包

对应赛事：[华为云 openJiuwen 智能体创新大赛](https://developer.huaweicloud.com/competition/information/1300000328/submission)

| 项 | 内容 |
|----|------|
| 作品名称 | **CodeVigil Agent**（昇腾 AI Infra 审查与排障智能体） |
| 参考方向 | **Coding**（主）· 可兼报 **科研**（社区知识沉淀） |
| 开源仓库 | https://github.com/enternalna-Koh/ReviewAgent （对外品牌 CodeVigil Agent；CLI `reviewagent`） |
| 许可证 | MIT |
| 当前版本 | 1.8.0 |
| 创意截止 | **2026-11-10** |
| DEMO 窗口 | 2026-11-25 — 2026-12-27（需创意晋级） |

## 本目录文件

| 文件 | 用途 |
|------|------|
| [01-作品名称与简介.md](01-作品名称与简介.md) | 问卷/官网「作品名称、项目简介」 |
| [02-应用场景说明.md](02-应用场景说明.md) | 目标用户、痛点、场景 |
| [03-技术方案.md](03-技术方案.md) | 架构、工具、Skills/MCP、安全边界 |
| [04-创意PPT大纲.md](04-创意PPT大纲.md) | 按官方模板填页说明 |
| [【openJiuwen创新大赛创意作品】CodeVigil队.pptx](【openJiuwen创新大赛创意作品】CodeVigil队.pptx) | **已填好的创意 PPT**（含实机命令截图） |
| [05-提交检查清单.md](05-提交检查清单.md) | 报名→打包→上传步骤 |
| `assets/` | `/help` `/skill` `/mcp` 截图与拼图源文件 |
| `build_ppt.py` | 从官方模板重新生成 PPT 的脚本 |

## 本地核验（2026-10-28）

- 已同步 `origin/main` → `cb0a123`
- `python -m unittest discover -s tests -q`：**209 OK**
- `npm test`：**209 OK**；`reviewagent --version` → 1.8.0
- 无 token 时 `collect --community opengauss` 正确非零退出且不写假数据

## openJiuwen / WorkSwarm 说明

初赛创意阶段**不强制**使用 WorkSwarm。本作品当前为 **Hermes 风格 CLI Agent**（自研编排 + 多模型 + Skills + MCP）。DEMO 阶段可规划：

1. 将 `/review` `/fix` `/ship` 等能力封装为 WorkSwarm 可调用工具；
2. 或用 WorkflowAgent 编排「取 PR → 专业场景路由 → 出报告 → 可选补丁」流水线。

评审加分以「真实接入深度」为准；材料中如实标注现状与演进路径，不虚构已接入。

## 联系与合规提醒

- 赛事邮箱：`contest@openjiuwen.com`
- 提交阶段需华为云实名；问卷队名须与华为云「我的团队」一致
- 演示数据须脱敏；勿提交 `.env`、Token、真实用户数据
