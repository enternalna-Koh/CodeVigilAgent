# ReviewAgent 项目更新日志

---

## v1.6.2 更新复核修复 (2026-10-17)

- 修复 /save 被导出截获、待应用补丁无法保存及恢复后写错工作目录；保存失败可见，同名会话优先于 cwd 文件
- 保留新增命令，恢复会话模型覆盖、活动配置路径、补丁类型校验、空回答失败与旧补丁清理
- 专业规则缺失/超预算停止审查；/review 显示实际引擎、回退原因和专业状态；部分 diff 不得 approve
- 恢复中文 Git 路径、换行保持、合格 Python 版本探测；npm test 共用解释器启动器
- 恢复 MIT 根许可证及原 15 项专项回归，新增会话/审查/测试入口专项；不更改第三方许可

---

## 许可证变更 (2026-10-16)

- 按用户要求，将根项目许可证由 Apache-2.0 改为 MIT
- 同步 LICENSE、package.json、package-lock.json 根包声明及 README 徽章
- 保留第三方依赖与来源声明，既有历史记录不改写

---

## 可靠性复核修复 (2026-10-15)

- `/model` 的显式选择在当前会话中覆盖环境配置，使用当前 `--config` 路径；重启仍按环境变量优先
- 自动路由保留裸错误码排查；无上下文的“查版本”先要求指定组件
- 专业上下文按完整章节装载；缺失或超预算返回 `incomplete`，不再虚报 ready
- 场景识别排除 diff 删除行及仓库根目录/分支文字；用户目录规则回退可记录来源
- `/fix` 验证 JSON 字段类型，失败可重试且清除旧补丁；专业规则不再二次截断
- 空模型答案返回失败；中文 Git 路径可定位；`/apply` 保留文件换行
- 部分 diff 的 approve 降为 comment；Node 启动器跳过 Python 2/3.6
- 依赖安装后回归：111 项 Python 测试通过，npm/Node 版本入口通过

---

## v1.2.0 / v3.3 - Hermes 风格全局 CLI (2026-10-15)

- npm 包名 `reviewagent`；唤醒命令 `reviewagent` / `ra`（保留 `review`）
- 用户配置家目录 `~/.reviewagent`（`REVIEWAGENT_HOME`）
- `config` / `doctor` / `model` 子命令
- 环境变量优先：`OPENAI_*` / `ANTHROPIC_*` / `AI_*`，兼容 cc-switch
- 文档：`docs/INSTALL_HERMES_STYLE.md`、`docs/CC_SWITCH.md`

---

## v3.2 - 可靠性回归落地 + 专业 Agent CLI (2026-10-15)

### 同步自远程 `5a82576`
- Windows Python 启动器共用、`added_lines` 规则、AI JSON 校验、截断 coverage、chat 失败退出码
- 实测报告与协作任务单

### 本机续优化
- Python 3.10：`scripts/toml_compat.py` 替代硬依赖 `tomllib`
- F8 最小实现：`--scenario` / `--require-scenario` + `specialist_context`
- 推理 Agent 精度/性能语义去绝对阈值
- `package.json` license 与 Apache-2.0 LICENSE 对齐
- 回归：48 tests OK

---

## v3.1 - 双智能体路由与 CLI 合入 (2026-10-14)

### 智能体
- ✅ `cann-op-checker` / `cann-inference-advisor` 增加分流表与 CLI 证据入口
- ✅ Skills 同步到 `.agents/skills/`；Codex TOML 同步到 `.codex/agents/`
- ✅ 新增 [AGENTS.md](AGENTS.md) 路由表

### CLI / 质量
- ✅ 正式入口 `ascend_cli.py`（review / search / chat / test）纳入版本库
- ✅ 离线回归：`python -m unittest discover -s tests -v`（25 cases）
- ✅ `package.json` repository 指向真实 GitHub 仓

---

## v3.0 - 训练数据构建 (2026-10-14)

### 🎯 Stage 3: 训练数据构建完成准备

#### 工具创建
- ✅ `analyze_reviews.py` - Review 意见分析和标注
- ✅ `extract_ci_rules.py` - CI 规则提取
- ✅ `extract_issue_patterns.py` - Issue 模式提取
- ✅ `build_training_dataset.py` - 训练数据集构建
- ✅ `run_stage3.sh` - Stage 3 主流程脚本

#### 数据结构设计
- ✅ code_review 样本格式
- ✅ ci_rule 样本格式
- ✅ problem_diagnosis 样本格式
- ✅ 统一的训练数据集结构

---

## v2.6 - MindSpore 生态扩展 (2026-10-14)

### 🚀 重大扩展：MindSpore 数据收集

#### 新增数据规模
- **18 个文件**: MindSpore 相关数据
- **18.16 MB**: 新增数据量
- **523 issues**: MindSpore 问题数据
- **466 PRs**: MindSpore 代码审查数据

#### GitHub 覆盖 (4 仓库)
- ✅ mindspore-ai/mindspore (100 issues, 46 PRs)
- ✅ mindspore-ai/models (18 issues, 3 PRs)
- ✅ mindspore-ai/docs (17 issues, 15 PRs)
- ✅ mindspore-ai/graphengine (5 issues, 2 PRs)

#### Gitee 覆盖 (4 仓库)
- ✅ mindspore/mindspore (100 issues, 100 PRs)
- ✅ mindspore/models (100 issues, 100 PRs)
- ✅ mindspore/hub (83 issues, 100 PRs)
- ✅ mindspore/community (100 issues, 100 PRs)

#### 数据增长对比
| 指标 | Before | After | 增长 |
|------|--------|-------|------|
| 仓库 | 10 | 18 | +80% |
| Issues | 210 | 733 | +249% |
| PRs | 279 | 745 | +167% |
| 数据量 | 7 MB | 25 MB | +257% |

#### 关键价值
- ✅ 双框架视角 (PyTorch + MindSpore)
- ✅ 双平台数据 (GitHub + Gitee)
- ✅ 中英文双语覆盖
- ✅ Gitee 数据量是 GitHub 的 2.7 倍

---

## v2.5 - 社区数据批量收集 (2026-10-14)

### 扩展到 10 个仓库

#### 核心框架
- Ascend/pytorch (64 issues)
- vllm-project/vllm-ascend (10 issues)

#### LLM 推理
- Ascend/sglang (2 issues, 2 PRs)

#### 模型和工具
- Ascend/samples (21 issues)
- Ascend/ModelZoo-PyTorch (58 issues)

#### GitCode 生态
- pytorch-ecosystem (100 issues, 100 PRs)
- torchair (55 issues)

#### 总计
- 210 issues
- 279 PRs
- 6.6 MB 数据

---

## v2.4 - GitCode 集成 (2026-10-14)

### 新增数据源
- ✅ GitCode API 支持
- ✅ pytorch-ecosystem 数据收集

---

## v2.3 - 真实社区问题集成 (2026-10-14)

### 问题模式库
- 5 类错误模式
- 5 个高频错误码
- 版本兼容性矩阵
- vLLM vs SGLang 对比

---

## v2.2 - vLLM-Ascend 扩展 (2026-10-14)

### 新增仓库
- vllm-project/vllm-ascend
- 10 issues 收集

---

## v2.1 - 问题模式库 (2026-10-14)

### 初始数据收集
- Ascend/pytorch: 64 issues

---

## v2.0 - AI Inference 全栈 (Initial)

### 智能体扩展
- ✅ cann-op-checker (算子检查)
- ✅ ai-inference-agent (推理优化)

### 知识包
- 9 个 skill packs
- 覆盖全生命周期

---

## v1.0 - CANN 算子检查器 (Initial)

### 初始功能
- 算子代码审查
- 分级报告
- IT 交付验收
