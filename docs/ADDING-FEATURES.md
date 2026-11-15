# 新增功能指南

三种常见场景，照着抄即可。共同原则：

1. **新功能放新文件**，不改已有布局/界面代码
2. **只移动不改逻辑**——重构和加功能不要混在一次提交里
3. **加功能必须加测试**，否则下一个人不敢动

---

## 场景一：给桌面版加一个按钮（最常见）

### 第 1 步：新建文件

`desktop-app/win/cvapp/features/export.py`

```python
"""导出功能：把输出区内容存成 Markdown。"""
from __future__ import annotations

import os
import tkinter.filedialog as filedialog

from .base import Feature

def export_markdown(app) -> None:
    text = app.output.text.get('1.0', 'end').strip()
    if not text:
        return
    path = filedialog.asksaveasfilename(
        title='导出为 Markdown',
        defaultextension='.md',
        filetypes=[('Markdown', '*.md'), ('文本', '*.txt')],
    )
    if not path:
        return
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    app.append(f'\n已导出 → {path}\n', 'accent')

FEATURES = [
    Feature(
        id='export.md', group='输出', label='导出 Markdown',
        handler=export_markdown, order=30, shortcut='<Control-s>',
    ),
]
```

### 第 2 步：重启桌面版

不需要改 `shell.py`、不需要改 `app.py`、不需要在任何清单里登记——
启动时 `pkgutil` 会自动发现 `features/` 下所有模块。

按钮会自动出现在侧边栏「输出」分组的第 3 个位置（`order=30`）。

### 可用的 Feature 字段

| 字段 | 说明 |
|------|------|
| `id` | 唯一标识，重复会被跳过并报错 |
| `group` | 侧边栏分组：`会话` / `审查` / `输出` / `系统`，新分组会自动追加到末尾 |
| `label` | 按钮文字 |
| `handler` | `handler(app)`；输入类功能是 `handler(app, text)` |
| `order` | 同组排序，小的在上 |
| `kind` | `normal` / `accent`（青色强调）/ `danger`（红色） |
| `placement` | `sidebar`（默认）或 `input`（底部输入框提交） |
| `requires_repo` | True 时未选仓库会先弹提示，不会执行 |
| `only_while_running` | True 时只在任务运行中可点（如「取消」） |
| `shortcut` | tkinter 按键序列，如 `<F5>`、`<Control-s>` |
| `panel_factory` | 给了它，按钮变成「显示 / 隐藏右侧面板」，见场景五 |

### 第 3 步：加测试（可选但推荐）

桌面版依赖 tkinter，无头环境不好测。建议把**逻辑**抽成纯函数再测：

```python
# 纯函数便于测试
def render_markdown(text: str) -> str:
    ...

# handler 只负责收集参数 + 调纯函数
def export_markdown(app):
    ...
```

---

## 场景二：给 CLI 加一个子命令

### 第 1 步：写处理函数

`ascend_cli.py` 里加（放在其他 `*_cmd` 函数旁边）：

```python
def stats_cmd(args: argparse.Namespace) -> int:
    from scripts.session_store import list_sessions
    rows = list_sessions()
    print(f'共 {len(rows)} 个会话')
    return 0
```

### 第 2 步：注册参数

`main()` 里照着现有的写：

```python
stats_parser = sub.add_parser('stats', help='会话统计')
stats_parser.set_defaults(func=stats_cmd)
```

### ⚠️ 注意：`ascend_cli.py` 是测试接缝

`tests/` 里有 50+ 处 `patch('ascend_cli.read_config')` 这类补丁。
加功能时**不要**把已有函数搬到别的模块，否则补丁会打在旧命名空间上，测试全红。
新功能可以放新模块，但在 `ascend_cli.py` 里保留一层薄封装。

### 第 3 步：加测试

`tests/test_stats_cmd.py`，至少覆盖：正常返回 0、无数据时不崩、参数解析正确。

---

## 场景三：给对话加一个斜杠命令

> **不要**再往 `ascend_cli.py` 的 `handle_chat_slash()` 里加 if 了 ——
> 那个函数已经 600 多行，正是「结构拥挤」的来源。新命令放注册表目录。

### 第 1 步：新建文件

`scripts/cli_commands/stats.py`

```python
"""会话统计命令。"""
from scripts.session_store import list_sessions
from . import SlashContext

def show_stats(ctx: SlashContext, arg: str) -> None:
    print(f'当前共 {len(list_sessions())} 个会话')

COMMANDS = {'/stats': show_stats}
```

### 第 2 步：完成

重启后 `/stats` 自动可用：

- 不需要改 `ascend_cli.py`
- 不需要在别处登记（`pkgutil` 自动发现）
- 内置命令优先：同名不会抢占 `/review`、`/help` 等
- 某个模块导入失败只跳过并记警告，不影响其它命令

### 第 3 步：加测试

在 `tests/` 下断言：`load_handlers()` 里有这个命令、`dispatch()` 返回 True。
`tests/test_structure_guard.py` 会自动检查新模块是否声明了 `COMMANDS`。

### 命名注意

先查内置命令表。踩过一次：便利命令原本叫 `/open`，
但 `/open` 已是「打开历史会话」的内置别名，内置优先导致它永远不生效，
最后改名为 `/dir`。结构守卫里已经把 `/open` 锁进内置名单，防止再犯。

---

## 场景四：写一个自定义命令（不改代码）

如果只是想把某类提问固定下来，**不需要改 Python**——放一个 Markdown 就行。

### 第 1 步：新建文件

`<仓库>/.reviewagent/commands/安全.md`（随仓库共享）
或 `~/.reviewagent/commands/安全.md`（所有项目可用）

```markdown
---
description: 按 OWASP 检查这段代码
argument-hint: <文件路径>
---
请按 OWASP Top 10 检查 @$ARGUMENTS：
1. 注入（SQL / 命令 / 路径穿越）
2. 认证与会话
3. 敏感数据是否进日志
只报真实风险，给出最小修复。
```

### 第 2 步：直接用

```text
/安全 src/api.py
/commands          # 确认它被识别到了
```

- `$ARGUMENTS` 会被替换成命令后面的参数；没写占位符时参数附在末尾
- 子目录会变成命名空间：`commands/db/slow.md` → `/db:slow`
- 项目级同名命令覆盖用户级
- 命名冲突不会抢占内置命令（`/help`、`/review` 等始终优先）

> 正文里可以写 `@文件`，执行时会自动附带文件内容——和第 1 步的组合是常用玩法。

---

## 场景五：加一个右侧面板

面板不是弹窗，是在主区域右边「推出来」的一列（历史会话就是这么做的）。
仍然是新建一个文件，仍然不用改 shell：

```python
# cvapp/features/history.py（简化）
from ..history_panel import HistoryPanel
from .base import Feature

FEATURES = [
    Feature(id='history.panel', group='会话', label='历史会话',
            panel_factory=HistoryPanel, shortcut='<Control-h>'),
]
```

约定：

| 约定 | 说明 |
|------|------|
| 构造函数 | `panel_factory(parent, app) -> tk 控件`，parent 是固定宽度的槽位 |
| 可选 `refresh()` | 展开面板时、以及每次任务结束都会调用（用来刷新列表） |
| 数据层单独放 | 别在控件里拼 `subprocess`，照 `cvapp/sessions.py` 那样抽一层纯逻辑再测 |
| 同时只显示一个 | `PanelHost` 会自动收起上一个面板，按钮再点一次收起 |

---

---

## 提交前检查清单

```bat
:: 1. 全量测试
python -m unittest discover -s tests

:: 2. JS 测试
node tests\test_wizard_confirm.js

:: 3. CLI 还能启动
python ascend_cli.py --version
python ascend_cli.py doctor

:: 4. 桌面版还能打开（看侧边栏是否出现新按钮）
python desktop-app\win\app.py
```

- [ ] 新功能在独立文件里，没有往 `shell.py` / `app.py` 里塞业务逻辑
- [ ] 没有改动 `ascend_cli.py` 里已有函数的模块归属
- [ ] 新增测试通过，旧测试也全绿
- [ ] `docs/ARCHITECTURE.md` 的目录表如果新增了目录，同步更新
