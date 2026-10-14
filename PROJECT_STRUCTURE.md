# ReviewAgent 项目结构

```
ReviewAgent/
├── .cursor/
│   ├── agents/                          # 智能体定义
│   │   ├── cann-op-checker.md          # AscendC 算子检查智能体
│   │   └── cann-inference-advisor.md   # 推理部署顾问智能体
│   │
│   └── skills/                          # 知识包
│       ├── cann-ascendc-op-dev/        # 算子开发
│       │   ├── SKILL.md                # 主知识文件
│       │   ├── README.md               # 快速导航
│       │   ├── official-requirements.md # 官方要求摘录
│       │   ├── pitfalls.md             # 踩坑指南
│       │   ├── acceptance-pack.md      # 验收打包清单
│       │   ├── examples-basic-api-cube.md
│       │   └── examples-spmv.md
│       │
│       ├── model-migration/            # 模型迁移
│       │   ├── SKILL.md                # 迁移完整指南
│       │   └── README.md
│       │
│       ├── inference-optimization/     # 推理优化
│       │   ├── SKILL.md                # 性能优化方法论
│       │   └── README.md
│       │
│       ├── deployment-practices/       # 部署实践
│       │   ├── SKILL.md                # 生产部署方案
│       │   └── README.md
│       │
│       ├── common-issues-patterns/     # 常见问题库
│       │   ├── SKILL.md                # 典型问题与审核模式
│       │   └── README.md
│       │
│       └── vllm-ascend-practices/      # vLLM 推理
│           ├── SKILL.md                # LLM 推理部署实践
│           └── README.md
│
├── README.md                           # 项目主文档
├── CHANGELOG.md                        # 版本更新日志
├── LICENSE                             # Apache 2.0
└── PROJECT_STRUCTURE.md               # 本文件
```

## 文件说明

### 智能体 (Agents)

智能体是任务处理的入口，定义了：
- 角色定位与边界
- 知识依赖（需要读取哪些 skill）
- 检查维度与清单
- 内置红线（强制检查项）
- 报告模板与严重级别

### 知识包 (Skills)

每个 skill 包含：
- `SKILL.md` - 主知识文件，按 § 分节
- `README.md` - 快速导航与使用场景
- 其他附录文件（官方文档摘录、示例代码、踩坑指南）

### 核心文档

- **README.md** - 项目概览、使用指南、技术栈
- **CHANGELOG.md** - 版本更新记录
- **LICENSE** - Apache 2.0 开源许可
- **PROJECT_STRUCTURE.md** - 项目结构说明（本文件）

## 扩展指南

### 添加新智能体

1. 在 `.cursor/agents/` 创建 `<name>.md`
2. 定义 frontmatter（name, description, triggers）
3. 编写角色定位、知识依赖、检查清单
4. 设计报告模板
5. 更新 README.md

### 添加新知识包

1. 在 `.cursor/skills/` 创建目录 `<skill-name>/`
2. 编写 `SKILL.md`（主知识文件）
3. 编写 `README.md`（快速导航）
4. 添加参考资料与示例
5. 更新相关智能体的知识依赖

### 贡献规范

- Skill 文档按 § 分节（§0, §1, §2...）
- 包含可执行代码示例（带注释）
- 引用权威资料来源（官方文档/社区案例）
- 避免过时信息（标注 CANN 版本）
- Markdown 格式规范（表格/代码块/链接）

## 技术架构

```text
用户对话
   ↓
Claude Code / Cursor
   ↓
智能体路由（根据 triggers）
   ↓
加载对应智能体 (.cursor/agents/*.md)
   ↓
按需读取知识包 (.cursor/skills/*/SKILL.md)
   ↓
执行检查/分析/建议
   ↓
输出结构化报告
```

## 维护清单

- [ ] 定期更新官方文档链接（CANN 版本升级）
- [ ] 收集社区新案例补充到 skill
- [ ] 根据用户反馈优化检查清单
- [ ] 增加更多参考代码模板
- [ ] 完善错误处理与边界情况

## 相关资源

- [Claude Code 文档](https://docs.anthropic.com/claude/docs)
- [Cursor Agents 指南](https://cursor.sh/agents)
- [昇腾开发者社区](https://www.hiascend.com/developer)
