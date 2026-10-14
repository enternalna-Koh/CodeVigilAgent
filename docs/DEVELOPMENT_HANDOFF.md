# 协同修改交接

## 正式运行路径

`review` (npm) → `bin/review.js` → `review.py` → `ascend_cli.py`。
`ascend.bat` 和 `chat.bat` 也进入 `ascend_cli.py`，保留调用者工作目录。
对话核心是 `scripts/conversation_agent.py`；本地案例索引在
`scripts/knowledge_search.py`；输入在 `scripts/chat_input.py`。

`chat.py`、`chat_v2.py` 仍保留供对比，不是正式入口。新版功能应先进入共享核心，
再由 UI 使用，避免仅在旧聊天脚本中实现后与正式入口脱节。
`review.py 文件名`、`--config`、`--stats` 是保留的旧快捷方式。

## 已确认的能力边界

对话先获取显式 PR/Issue 并检索案例，再运行最多三步的模型选择工具循环。
目前支持 web_search / local_search / fetch_pr_issue；采用跨 provider 的 JSON 调查协议，
并非 provider 原生 function calling。默认 auto 按需联网，on 每轮搜索，off 不获取外部资料。
获取器只支持 GitHub PR/Issue，限制评论分页和上下文大小。
支持当前进程内连续追问，不支持跨进程恢复。
没有流式输出、网页正文抓取或自动代码修复。网页搜索只获取摘要。
所有聊天版本通过 `scripts/web_search.py` 共用搜索后端，正式入口仍使用 ConversationAgent。

## 下一批修改优先级

1. 统一模型错误、流式事件和取消请求接口。
2. 在现有三步只读调查循环上扩展仓库文件读取和代码搜索，完善证据质量与
   工具参数验证。工具结果保留来源和范围。
3. 接入会话保存/恢复，限制上下文大小，避免把旧分析对象混进新任务结论。
4. 建立真实 PR/Issue 的评估用例；修复和测试执行作为独立授权能力。

## 验证和协作

`python -m unittest discover -s tests -v` 为离线回归检查。
`npm test` 目前只验证版本入口，不代表完整 Agent 质量。
真实 GitHub 和 AI 服务的端到端回答质量尚未验证。

当前工作区包含多方未提交修改，不能根据 HEAD diff 区分贡献者。
修改前重新读取相关文件，避免覆盖其他 AI 的新内容。
API 密钥和平台 token 不应提交，保留各方未提交修改，不批量 stage/commit。
