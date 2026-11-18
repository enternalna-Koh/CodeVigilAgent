# 架构说明

> 这份文档回答两个问题：**东西都放在哪**、**加新功能该动哪里**。
>
> 背景：评审反馈「整体结构上有点拥挤，如果后面加新的功能会影响」。
> 本文记录针对这条反馈做的结构调整，以及**故意没动**的部分（附原因）。

---

## 一、原来拥挤在哪

| 位置 | 问题 |
|------|------|
| 仓库根目录 | 30+ 项：9 份文档、11 个 `.bat`、6 个根 `.py`，其中 3 个是已失效的旧入口 |
| `desktop-app/win/app.py` | 383 行、**一个类**同时管布局、按钮、子进程、配置读写、设置对话框 |
| 桌面版操作行 | 5 个按钮挤在一排，再加功能只能继续往右排 |
| `chat_v2.py` | 1008 行，颜色/字形/盒子绘制（约 240 行）和对话流程混在一个文件 |

结论：不是"文件多"，而是**职责边界不清**——改一处要动同一个文件，加功能必然互相影响。

---

## 二、现在的分层

```
┌──────────────────────────────────────────────────────────────┐
│ 入口层   启动脚本 → app.py / ascend_cli.py / bin/*.js         │
│          只做参数解析与启动，不放业务逻辑                      │
├──────────────────────────────────────────────────────────────┤
│ 编排层   cvapp.shell（桌面版窗口骨架）                        │
│          ascend_cli 的命令函数（review / chat / doctor ...）   │
│          决定"先做什么、再做什么"                             │
├──────────────────────────────────────────────────────────────┤
│ 能力层   cvapp.runner（子进程）  cvapp.features（功能）        │
│          scripts.smart_reviewer（审查） scripts.github_fetcher │
│          一个能力只做一件事，可单独测试                        │
├──────────────────────────────────────────────────────────────┤
│ 基础层   cvapp.theme / cvapp.widgets / scripts.term_ui         │
│          scripts.term_frame / scripts.console_safe / config    │
│          颜色、字体、宽度、编码、配置                          │
└──────────────────────────────────────────────────────────────┘
```

**依赖方向只能从上往下。** 基础层不允许 import 编排层，能力层不允许认识界面。
这样换界面（终端 ↔ 桌面）不用改业务，改业务不用动界面。

---

## 三、目录职责

| 路径 | 职责 | 加功能时会动到吗 |
|------|------|-----------------|
| `ascend_cli.py` | CLI 入口与命令编排（测试的 patch 接缝） | 加子命令时会 |
| `chat_v2.py` | 终端对话流程 | 加对话能力时会 |
| `scripts/term_ui.py` | 终端颜色 / 字形 / 盒子绘制 | 一般不动 |
| `scripts/term_frame.py` | **宽度计算的唯一出处**（定位渲染 + 补空格兜底） | 一般不动 |
| `scripts/smart_reviewer.py` | 审查主流程 | 加审查规则时会 |
| `scripts/custom_commands.py` | 自定义斜杠命令（读 `.reviewagent/commands`） | 一般不动 |
| `scripts/file_mentions.py` | `@文件` 引用解析与安全边界 | 一般不动 |
| `scripts/git_hooks.py` | pre-commit 钩子安装/卸载 | 一般不动 |
| `scripts/usage_meter.py` | `/cost` 用量估算 | 一般不动 |
| `scripts/cli_commands/` | 斜杠命令注册表：新命令加文件，不改入口 | 加内置命令时 |
| `scripts/system_open.py` `clipboard.py` `config_backup.py` | 打开目录 / 剪贴板 / 配置备份 | 一般不动 |
| `scripts/model_catalog.py` | 厂商与模型清单的唯一出处（CLI `model --list` 的 CATALOG） | 加模型时只改这里 |
| `scripts/model_choices.py` | 下拉选项的纯逻辑（选厂商 / 选模型 / 自定义降级），CLI 与桌面共用 | 一般不动 |
| `tests/test_structure_guard.py` | 结构守卫：行数预算、分层、注册表约定 | 调预算时 |
| `desktop-app/win/app.py` | 桌面版入口，20 行 | 不动 |
| `desktop_py/app.py` | 当前 Windows 桌面启动入口与布局；通过职责模块组合行为 | 修改窗口交互时 |
| `desktop_py/entry.py` | 打包入口：默认启 GUI，带 `--cli` 时在同一进程内跑 CLI；是唯一允许 import `ascend_cli` 的桌面文件 | 修改打包产物时 |
| `desktop_py/cli_runtime.py` | CLI 子进程、异步结果队列、取消与关闭回收 | 修改任务执行时 |
| `desktop_py/session_controller.py` | 发送/审查编排、会话读取与代次保护 | 修改会话交互时 |
| `desktop_py/settings_dialog.py` | 当前桌面模型设置与配置保存 | 修改设置交互时 |
| `scripts/gateway_key.py` | 新旧桌面共用的服务商/地址与密钥归属 | 修改密钥归属时 |
| `scripts/process_tree.py`、`scripts/_win_process_job.py`、`scripts/_posix_process_group.py` | 无界面进程树基础能力：创建归属、终止、释放及可关闭查询集合；Windows 原生作业接口及 POSIX 回收时序独立封装 | 修改进程生命周期时 |
| `scripts/patch_paths.py` | 补丁事务的固定目录句柄及安全文件操作 | 修改补丁文件访问时 |
| `desktop_py/md_render.py` | 聊天消息的 Markdown 样式、气泡与文字复制；用户气泡以普通 `place` 布局叠放文字，映射且目标宽度稳定后测量完整高度，避免 Canvas 内嵌窗口的独立尺寸协商 | 修改聊天消息呈现时 |
| `desktop_py/ui_kit.py` | 共用颜色、字体和滚动容器 | 修改界面基础组件时 |
| `desktop-app/win/cvapp/shell.py` | 窗口骨架：侧边栏 + 工作区 | 一般不动 |
| `desktop-app/win/cvapp/features/` | **桌面版功能注册表** | 加桌面功能只动这里 |
| `desktop-app/win/cvapp/panels.py` | 右侧面板槽位：按需创建 / 显示隐藏 / 任务后刷新 | 加第二个右侧面板时 |
| `desktop-app/win/cvapp/history_panel.py` | 历史会话面板（WorkBuddy 式列表 + 渲染对话） | 改历史回顾界面时 |
| `desktop-app/win/cvapp/sessions.py` | 历史会话数据层：调 `sessions` 子命令 + 纯格式化（无 tkinter） | 改会话读取逻辑时 |
| `desktop-app/win/cvapp/theme.py` | 颜色 / 字体 / 尺寸唯一来源 | 改配色时 |
| `desktop-app/CodeVigilAgentApp.swift` | macOS 版（SwiftUI），模型下拉复用 CLI `model --list --json` | 改 Mac 界面时 |
| `bin/` | Node 层 CLI（`reviewagent` 命令） | 加 npm 子命令时会 |
| `launchers/` | 次要启动脚本 | 不动 |
| `legacy/` | 已退役入口，只留档 | 不动 |
| `tests/` | Python 行为/安全/结构回归与 JavaScript 向导测试；数量以本次测试输出为准 | 每次加功能都要加 |

---

## 四、桌面版的扩展点（重点）

`启动桌面版.bat` 当前启动 `desktop_py/app.py`。此入口通过 `CliRuntime` 与
`SessionController` 组合执行和会话能力：窗口控件只在主线程访问；耗时工作使用仓库快照；
任务与历史读取分别带身份校验。任务运行时禁止切换仓库、历史或新建会话，关闭窗口负责回收子进程。
运行器直接启动当前 Python 解释器，避免只终止 Windows 启动器而留下实际后台任务。
新旧运行器共用 `scripts.process_tree`：Windows 挂起创建，加入带关闭终止标志的作业后恢复，归属失败拒绝运行；POSIX 独立会话/进程组，Linux 借助 `waitid(WNOWAIT)` 先终止组再回收组长，避免组号在回收后被复用；其他平台（实测 macOS 不支持该组合）自动退回普通等待，`waitid` 任何系统级异常都降级而不中断运行器。取消和释放由每进程生命周期锁串行化，释放后迟到请求不再发信号。取消、超时、关闭以及正常结束均释放受控后代，不按进程名或全机枚举终止；独立退出观察不依赖继承输出管道先关闭。
旧历史面板以 `ProcessOwner` 持有查询，线程局部作用域传至会话数据层；面板关闭阻止后续创建，创建与登记之间发生关闭则立即回收。默认非面板数据调用保留原接口。
POSIX 后代主动创建新会话可脱离进程组，本机制不是对恶意工具的沙箱；Windows 作业不允许后代脱离。在不支持 `WNOWAIT` 的平台，组长回收后到整组终止之间仍有极短窗口，理论上存在组号复用风险，属已知限制。历史重绘辅助测试单独捕捉其 App 的 Tk 回调异常，异常会导致失败而非仅打印。
会话绑定规范仓库路径；手动修改仓库输入后拒绝沿用旧会话并保留问题，需显式新建对话或恢复原仓库。
保留的旧客户端在历史恢复期间同样阻止发送，并以请求令牌释放等待状态。
当前入口与这两个职责模块均纳入结构预算及实际方法回归。新旧客户端共用 `scripts.gateway_key`，
服务商或接口地址改变时清空密钥，返回原作用域才恢复原密钥。

补丁事务通过 `scripts.patch_paths` 固定目录身份：Windows 不共享目录删除权限并使用相对句柄，
POSIX 使用 `dir_fd` 和 `O_NOFOLLOW`。相对目标中的链接/重解析目录被拒绝；Windows 只读目标在
整批验证阶段拒绝。POSIX 防护保证不沿被替换的路径写入另一目录；原目录本身被移动后，句柄仍指向
原目录对象，不保证目录在提交瞬间仍处于原来的路径位置。
Windows 通过已打开句柄检查规范名称，拒绝 8.3 短名别名；读取快照拒绝多硬链接，
同一批补丁不允许重复文件身份。提交前校验内容和身份；回滚遇到用户保存冲突时保留原备份而不覆盖。
这些检查不是操作系统级原子比较交换：最后一次检查与替换之间仍有并发窗口，应用期间应暂停其他写入。
统一 Git 运行器显式关闭 `core.fsmonitor`，差异读取另外禁止外部 diff 和 textconv。
对话的回答上下文保留完整附件；工具规划使用单独的用户原文历史，旧会话缺失来源时不从混合正文推断授权。

下面的注册式扩展点属于保留的 `cvapp` 客户端；该客户端仍有独立回归，修改它不会自动修改当前入口。

原来的操作行：

```
[审查当前改动] [离线审查] [模型设置] [取消] [清空输出]
```

现在是**左侧分组侧边栏**，每组下面都留了空间：

```
功能
├── 会话        ← 加对话 / 历史类功能放这里
│   ├── 历史会话       Ctrl+H   （右侧面板）
│   └── 新会话         Ctrl+N
├── 审查        ← 加审查类功能放这里
│   ├── 审查当前改动   F5
│   └── 离线审查       Shift+F5
├── 输出        ← 加输出/导出类功能放这里
│   ├── 清空输出       Ctrl+L
│   └── 取消任务       Esc
└── 系统        ← 加设置/关于类功能放这里
    └── 模型设置       Ctrl+,
```

加一个功能 = **在 `cvapp/features/` 新建一个文件**，不需要改布局、不需要改 shell、不需要在别处登记：

```python
# cvapp/features/export.py
from .base import Feature

def export_markdown(app):
    ...

FEATURES = [
    Feature(id='export.md', group='输出', label='导出 Markdown',
            handler=export_markdown, order=30),
]
```

**右侧面板也是功能**：给 `Feature` 传 `panel_factory=(parent, app) -> 控件`，
按钮就变成「显示 / 隐藏面板」，shell 不用改。面板可选实现 `refresh()`，
会在展开时和任务结束后被调用（历史会话就靠它更新轮次 / 预览）。

```python
# cvapp/features/history.py（节选）
Feature(id='history.panel', group='会话', label='历史会话',
        panel_factory=HistoryPanel, shortcut='<Control-h>'),
```

程序启动时用 `pkgutil` 自动发现该目录下所有模块并读取 `FEATURES`。
一个模块导入失败只会被跳过并显示在状态栏，不会拖垮整个窗口。

详见 [ADDING-FEATURES.md](ADDING-FEATURES.md)。

### 不改代码的扩展点

用户侧还有三个「连 Python 都不用改」的入口：

| 扩展点 | 加什么 | 怎么加 |
|--------|--------|--------|
| `.reviewagent/commands/*.md` | 自定义斜杠命令（`/并发`、`/报错`…） | 放一个 Markdown，`/commands` 立即可见；正文可用 `$ARGUMENTS` |
| 消息里的 `@路径` | 把仓库文件内容带进对话 | 直接写 `@src/a.py`；只允许仓库内、单文件 ≤64 KB、每次 ≤8 个 |
| `install-hook` | 提交前自动离线审查 | `python ascend_cli.py install-hook --severity high`；`--fail-on` 控制退出码 |
| `scripts/cli_commands/*.py` | 内置斜杠命令（`/copy`、`/dir`…） | 新建文件写 `COMMANDS = {'/名字': 函数}`，自动发现；**不要改 `handle_chat_slash()`** |

会话用量用 `/cost` 查看（字符级估算，不报金额）。

### 结构守卫（让「拥挤」在测试里失败）

`tests/test_structure_guard.py` 把评审的担心变成可执行规则：

| 规则 | 作用 |
|------|------|
| 关键文件行数预算 | `ascend_cli.py` 等超预算就红，必须拆模块或显式调预算 |
| `handle_chat_slash` 函数预算 | 禁止继续往同一个函数堆命令，新命令走注册表 |
| 分层方向 | `scripts/` 不许 import `ascend_cli`，桌面层不许依赖 CLI 入口；唯一豁免 `desktop_py/entry.py`（打包入口，名单由测试钉死不得扩张） |
| 注册表约定 | `cli_commands/` 下每个模块必须声明 `COMMANDS` |
| 根目录文件数 ≤20 | 防止文件重新堆回根目录 |

超预算时的正确做法：先拆模块；确实要加，再改预算数字，并在提交信息里写理由。

---

## 五、故意没动的地方

重构的原则是「只移动，不改逻辑」。以下三处评估后**保留原样**：

| 位置 | 为什么不动 |
|------|-----------|
| `ascend_cli.py`（1510 行） | 286 项测试里有 50+ 处 `patch('ascend_cli.read_config')` 之类的补丁，它就是这个项目的**测试接缝**。拆成包会让补丁打在别的命名空间上，测试全红，而收益只是行数变少。 |
| `review_cli.py`（331 行） | 文档里被引用 56 次，是公开命令。移走会让大量文档失效。 |
| `chat_v2.py` 的 `ReviewAgentChat` | 拆出样式层后剩 768 行，剩下的是**高内聚**的对话流程（会话、斜杠命令、流式输出），继续切只会让人更难找代码。 |

> 判断标准来自 `pc-code-refactor` 技能：**按职责拆分，不按行数拆分**；
> 一个有凝聚力的 600 行文件，好过三个各 200 行但乱切的文件。

---

## 六、行为等价清单（重构后必须不变的）

桌面版重构只换结构，以下全部保持：

- 启动方式：`app.py` 仍是入口，双击 `启动桌面版.bat` / 桌面快捷方式不受影响
- 子进程参数：`review`、`review --offline`、`chat --message ... --network auto`
- 环境变量：`REVIEWAGENT_RENDER=pad`、`PYTHONIOENCODING=utf-8`、`PYTHONPATH=仓库根`
- 配置路径：`~/.reviewagent/ai_config.json`（与终端版共用）
- 上次仓库：`desktop-app/win/last_repo.txt`
- 字体策略：输出区仍用「新宋体」等 1:2 等宽字体
- 退出码处理、取消行为、ANSI 着色

---

## 七、验证方式

```bat
:: 全量测试（约 2 分钟）
python -m unittest discover -s tests

:: JS 向导回退测试
node tests\test_wizard_confirm.js

:: CLI 冒烟
python ascend_cli.py --version
python ascend_cli.py doctor

:: 桌面版（窗口应出现侧边栏）
python desktop-app\win\app.py
```
