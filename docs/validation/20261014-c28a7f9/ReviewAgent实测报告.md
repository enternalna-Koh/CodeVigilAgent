# ReviewAgent 实测报告

> 本报告记录基线提交 `c28a7f9` 的历史实测结果；后续修复复核与未完成项见[协作任务单](../../collaboration/任务单.md)。本次发布报告正文，正文所列 JSON 证据、临时样例与复现脚本仍保存在原本地交付目录，未随本报告上传。

日期：2026-10-14。仓库：[enternalna-Koh/ReviewAgent](https://github.com/enternalna-Koh/ReviewAgent)。测试提交：`c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb`。

**判断：值得作为昇腾 AI Infra 审查工具的基础复用，但当前还不足以承担可信的自动审查或验收。** 它已经有可运行的 Python CLI、公开 GitHub PR/Issue 获取、本地案例检索和对话运行时；主要短板是入口可用性、审查结果校验、专业知识准确性，以及 CLI 与专业智能体规则的连接。先修这些，再接前端，收益更明确。

本次实际运行了 CLI、仓库测试、Git diff 审查、GitHub 数据获取，以及真实 HTTP 传输链的本地模拟。另由当前会话模型按仓库的专业 Agent/Skill 文件检查一个样例。没有配置或调用真实外部 AI 模型，没有运行昇腾 NPU。模拟返回值只用于证明程序怎样处理响应，不能证明模型回答质量。

**能正常工作的部分**

| 项目 | 实际结果 | 证据 |
|---|---|---|
| Python 入口 | `py -3.13 ascend_cli.py --version` 成功，显示 ReviewAgent 1.1 | `03_python_launcher.json` |
| 仓库自带测试 | 25 项，24 通过，1 项错误；错误出在 Windows Node 包装入口 | `01_original_tests.json` |
| 本地检索 | 索引 1,453 条记录；`507049 HCCL` 第一条命中直接相关的 Ascend/pytorch #166 | `12_knowledge_search.json` |
| 公开 PR 获取 | #155 获取到 2 个文件补丁、9 条讨论评论；人工 review 和行级评论均为 0；未报获取警告 | `13_public_pr.json` |
| 公开 Issue 获取 | #166 正文和 1 条评论成功获取；未报获取警告 | `14_public_issue.json` |
| 专业规则使用样例 | 按 `cann-op-checker` 的规则发现缺 Device-only 门控；CPU 宏模拟编译失败，门控对照样例通过 | `16_specialist_example.json`、`智能体样例审查.md` |

检索同时如实警告了两个采集失败的数据文件。这里的 1,453 是成功建立索引的历史记录数量，不是已验证解法数量，也不是本次全部重新联网核实的数量。

**优先修复的问题**

P1 表示优先修复：阻断入口或直接损害审查可信度。P2 表示随后修复：影响集成、覆盖范围或文档一致性。这是本次优化排序，不是漏洞评级。

| 编号 | 优先级 | 已复现的问题 | 使用影响 |
|---|---|---|---|
| F1 | P1 | Windows 启动器只寻找 `python`，无法利用已安装且可通过 `py` 启动的 Python | 本机 `node bin/review.js --version` 返回 1，误报 Python 未安装 |
| F2 | P1 | 两个 Codex Agent TOML 文件含字面 `\n`，无法被 TOML 解析器读取 | 无法作为有效的 TOML 配置加载 |
| F3 | P1 | 离线规则把 diff 删除行当成现有代码 | `.cuda()` 已改为 `.npu()`，仍报 high 级 CUDA 问题 |
| F4 | P1 | AI 审查 JSON 缺少结构与字段校验 | `{}` 被显示为“发现问题：0 个”；`issues` 是字符串时报告崩溃 |
| F5 | P1 | vLLM-Ascend 0.23.0 的依赖指南写错 | 仓库要求 PyTorch 2.1.0，官方发布包要求 2.10.0 |
| F6 | P2 | diff 截断事实没有进入模型收到的提示词 | 模型只看到部分改动，却没有得到明确的审查范围警告 |
| F7 | P2 | 一次性对话失败仍返回退出码 0 | 前端或自动化可能把失败请求记成完成 |
| F8 | P2 | CLI 未加载专业 Agent/Skill；三个专门数据加载器读不到目标文件 | CLI 的通用规则不能代表专业算子/推理审查能力 |

**F1：Windows 入口误判 Python 未安装**

本机可通过 `py -3.13` 使用 Python 3.13，但 PATH 中的 `python` 是 Windows 应用执行别名。Python 直接入口成功，Node 包装入口报“Python 未安装或不在 PATH 中”。仓库测试里的 `test_cli_review_external_repository_json_and_output` 也在同一入口失败。

根因位置：[bin/review.js:30](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/bin/review.js#L30)，安装检查 [install.js:28](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/install.js#L28) 有相同假设。

最小修复：Windows 启动检查按顺序尝试有效的 `python` 与 `py -3`，保留对应的启动参数；安装检查与正式入口使用同一选择逻辑。增加一个“`python` 不可用、`py` 可用”的启动测试。本结论针对该 Windows 环境，不意味着所有 Windows 安装都会失败。

**F2：Codex 配置文件本身无效**

用 Python 标准库 `tomllib` 直接解析两个文件，结果如下：

```text
cann-op-checker.toml: Expected newline or end of document after a statement (line 1, column 25)
cann-inference-advisor.toml: Expected newline or end of document after a statement (line 1, column 32)
```

文件中的 `\n` 是两个字面字符，位置需要真实换行。证据：`04_codex_toml.json`。最小修复：重新正确序列化两个 TOML 文件，并把解析校验纳入检查。解析通过之后仍需在 Codex 中确认实际注册和调用；本次没有将格式修正等同于集成验证完成。

**F3：删除错误代码反而被报错**

实测 diff：

```diff
 def migrate_to_npu(tensor):
-    return tensor.cuda()
+    return tensor.npu()
```

工作区代码已经没有 `.cuda()`，离线 CLI 仍输出 `type: cuda call`、`severity: high`，建议改成 `.npu()`。这是已完成修正被误判，并非模型意见差异。

根因位置：[scripts/smart_reviewer.py:331](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/smart_reviewer.py#L331)。规则在完整提示文本上匹配，未区分添加、删除和上下文行。证据：`05_deleted_cuda_false_positive.json`。

最小修复：对变更审查只扫描新增代码，保留对应文件与新行号；若要做全文件审计，单独读取当前文件并明确范围。回归至少覆盖“删除 CUDA”“新增 CUDA”“上下文保留 CUDA”三个不同场景。

**F4：无效模型结果被当成审查成功**

本地 HTTP 模拟服务经正式 OpenAI-compatible 适配器返回字符串 `{}`。CLI 退出码为 0，普通报告显示“发现问题：0 个”。返回 `{"issues":"invalid-type"}` 时，打印器将字符串长度当成问题数，随后抛出 `AttributeError`。因此，仅能解析 JSON 不足以认定审查成功。

根因位置：[scripts/smart_reviewer.py:321](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/smart_reviewer.py#L321)、[打印器:478](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/smart_reviewer.py#L478)。证据：`06_empty_model_json.json`、`06b_empty_model_human_output.json`、`07_invalid_issues_type.json`。

最小修复：校验响应必须为对象、`issues` 必须存在且为数组、每个 issue 必须为对象并具备有效 severity 等必要字段。格式失败应产生明确错误和失败状态，禁止自动解释成“无问题”。模型确实返回空 `issues` 数组仍可正常接受。

**F5：专业知识包的版本矩阵不可靠**

仓库 [vllm-ascend-practices/SKILL.md:36](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/.cursor/skills/vllm-ascend-practices/SKILL.md#L36) 写：vLLM-Ascend 0.23.0 对应 PyTorch 2.1.0、torch-npu 2.1.0.post6；安装示例也使用这组版本。

核对 [PyPI 的该版本发布元数据](https://pypi.org/pypi/vllm-ascend/0.23.0/json)，其项目主页指向 `vllm-project/vllm-ascend`，该包声明：

```text
torch==2.10.0
torch-npu==2.10.0.post4
requires_python: >=3.10
```

这是同一发布版本的明确依赖冲突。证据：`15_vllm_official_dependency.json`、`15b_vllm_package_provenance.json`。本次未实际安装这些大型 NPU 依赖；不能据此宣称已完成全部 CANN、驱动与硬件的兼容性验证。

最小修复：为版本矩阵记录官方来源、对应 tag 和核验日期；安装示例从同一发布版本的依赖声明提取。知识文件应纳入版本更新检查，避免把旧 torch-npu 版本拼接到新 vLLM 版本上。

**F6：模型未收到 diff 截断警告**

构造大于 600 字符的 diff，并在尾部新增 `.cuda()`。完整 diff 可以看到该新增行；使用 `--max-diff 600` 后该行被裁掉。CLI 的 stderr 有范围警告，输出 JSON 的 repository metadata 也包含 `diff_truncated: true`，但捕获的实际 AI 请求里没有传入该标记或等价的范围说明。

根因位置：[scripts/repo_context.py:83](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/repo_context.py#L83)。证据：`09_truncated_review.json`、`09b_full_rule_review.json`、`09c_truncated_ai_request.json`。

模拟服务给出的 `approve` 被正常接受。这仅证明程序接受此结果，没有证明真实模型一定会漏报或批准。最小修复：提示词明确说明截断，输出增加 `coverage: partial`；完整审查要求下，分批处理或返回未完成，避免将部分审查结果展示为全量结论。

**F7：401 对话请求失败，进程仍报告成功**

本地服务返回 HTTP 401，正式 `chat --message` 显示“AI 调用失败”并保留错误信息，但退出码仍为 0。对话内部确实识别了错误，没有把错误写入正常历史；不足发生在 CLI 对外状态传播。

位置：[ascend_cli.py:100](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/ascend_cli.py#L100)、[scripts/conversation_agent.py:287](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/conversation_agent.py#L287)。证据：`08_http401_chat.json`。

最小修复：在会话结果中携带成功/失败状态，让一次性 CLI 在失败时返回非 0。后续前端可据同一状态显示“失败，可重试”，不用从自然语言里猜成功与否。没有将“存在审查问题但退出码为 0”列为缺陷，因为仓库未约定把审查意见作为 CI 门禁。

**F8：专业规则与 CLI 的能力存在断层**

实际捕获 AscendC 指针重载样例的 AI system prompt，收到的是通用代码质量、torch-npu、精度与多卡清单，没有加载 `cann-op-checker` 或其 Device-only、SIMT、交付规则。

此外，SmartReviewer 的三个加载器读取 `data/training/...`，仓库不存在该目录；实际得到 `ci_rules={}`、`review_patterns={}`、`issue_knowledge={}`，且没有提示这一缺失。本地 BM25 检索另有 1,453 条记录，不能把这三组空数据误说成“全部知识库为空”。

位置：[scripts/smart_reviewer.py:44](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/smart_reviewer.py#L44)、[review_with_ai:244](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/smart_reviewer.py#L244)、[会话通用提示词:14](https://github.com/enternalna-Koh/ReviewAgent/blob/c28a7f9e99c8fd3881f29d58afc3bc0e060e22eb/scripts/conversation_agent.py#L14)。证据：`10b_cann_ai_request.json`、`11_specialist_data.json`。

补充样例：让两组地址空间宏在 CPU 分支展开为空后，两个 `Copy(float*)` 重载产生重复定义。已有 C++ 编译器明确拒绝编译；专业 skill 第 62 行明确覆盖这一红线；离线 CLI 却输出空 `issues`。这是离线覆盖边界的验证，不能据此认定在线 AI 也必然漏报。

最小修复：让正式 CLI 按算子/推理场景加载相关 Agent 和必要 skill，记录加载来源与版本；对缺失数据显式告警或删除无实际用途的旧加载路径。先接入少量有明确证据的专业规则，再扩大覆盖。

**其他需要注意的不足**

1. 精度标准写成统一“CPU/NPU 差异 <1%”，BLOCKER 示例又写“>5%”，没有统一定义误差算法。应由任务、dtype 与验收指标决定容差，而非将该百分比视为通用合格线。位置：`.cursor/agents/cann-inference-advisor.md:77,137`。这属于规则审读发现，未实测到模型因此放行不合格任务。
2. 同一 Agent 既禁止臆造性能数据，又要求性能建议量化预期提升。无 profiling 或实测依据时应允许“待测”，否则容易诱导没有依据的数字。位置：`.cursor/agents/cann-inference-advisor.md:183` 附近。
3. 正式 URL 获取器只支持 GitHub PR/Issue，README 也已说明。#166 的评论明确指出 Ascend/pytorch 是镜像，实际维护入口在 GitCode。因而获取成功并不等于拿到了原仓完整解决过程；你的昇腾项目若依赖 GitCode/Gitee，还需要补适配或粘贴原文。
4. `LICENSE` 为 Apache-2.0，README 与 package.json 写 MIT。应让作者确认真实授权后统一，不能由本次测试擅自选择或改许可证。
5. 当前自带测试主要验证离线行为与模拟工具，不是审查准确率评测。本次也没有测出真实模型的误报率、漏报率、回答延迟或 NPU 性能。
6. `network=auto` 的调查循环每轮最多调用模型规划 3 次，再调用 1 次生成答案。接前端前应实测延迟、模型费用与长对话上下文增长；本次没有用模拟服务耗时估算真实成本。

**建议的优化顺序**

1. 修 Windows 启动器与 TOML，让用户按说明可以启动和加载。
2. 修 diff 行解析、模型 JSON 校验、失败状态与截断范围，先保证报告可被信任。
3. 核对版本矩阵与精度规则，把专业 skill 接入正式入口。
4. 建立一个小型、与知识库分开的评测集，包含正确修正、真实缺陷、无问题改动、上下文不足和服务失败；对有依据的结果统计误报/漏报。
5. 再接最小前端：提交 diff/链接、展示证据与来源、标记范围不完整与可重试错误。更广的 AI Infra 覆盖应按实际任务逐步扩展，不能把当前昇腾专用规则直接当成通用标准。

本轮只添加验证材料，没有修改 ReviewAgent 源文件，没有推送、提交 Issue 或联系仓库作者。测试结束后源仓库 `git status --short` 仍为空。

**复现入口**

脚本位于 `D:\workspace\Project_019_昇腾算子PR评审资料库\代码\reviewagent-validation`。只使用 Python 标准库、已有 Node/Git，额外的 CPU 宏样例使用本机已有 g++。重跑输出必须用新目录，避免覆盖原证据。

```powershell
$env:PYTHONUTF8 = '1'
$validationOutput = 'D:\workspace\Project_019_昇腾算子PR评审资料库\交付物\ReviewAgent实测\重跑-01'
py -3.13 'D:\workspace\Project_019_昇腾算子PR评审资料库\代码\reviewagent-validation\validate_reviewagent.py' --repo 'D:\workspace\Project_019_昇腾算子PR评审资料库\代码\ReviewAgent' --output $validationOutput --fetch
py -3.13 'D:\workspace\Project_019_昇腾算子PR评审资料库\代码\reviewagent-validation\check_specialist_example.py' --repo 'D:\workspace\Project_019_昇腾算子PR评审资料库\代码\ReviewAgent' --output $validationOutput
```

`--fetch` 仅用于重新读取两个公开 GitHub 样例，可能遇到网络错误或限流。省略它仍可重现本地入口、格式、规则和 HTTP 错误处理问题。脚本的断言用于确认缺陷已经复现；脚本成功退出不意味着仓库缺陷已修好。模拟配置里的 key 是本地假值，模拟服务只绑定 `127.0.0.1`，结束时自动关闭。

未检验真实外部模型、Cursor/Codex 的实际注册流程、完整 NPU 环境与真实验收性能；自动审查结论仍需证据复核。
