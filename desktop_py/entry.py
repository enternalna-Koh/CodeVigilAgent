# -*- coding: utf-8 -*-
"""打包入口：默认启动桌面 GUI；带 --cli 参数时跑 CLI 子命令。

打包成单个 exe 后，桌面端不能再调 `py -3 ascend_cli.py`（目标机器可能没装
Python），改为「同一个 exe 加 --cli 参数」跑 CLI，stdout 仍是 JSON，行为与源码
版完全一致。PyInstaller 会把 ascend_cli 与 scripts/ 一并打进去。
"""
from __future__ import annotations

import os
import sys

# 源码运行时也要能直接 `py desktop_py/entry.py` 启动，这里把仓库根补进 sys.path；
# 打包后这些路径不存在也无害（导入走 PyInstaller 的内建加载器）。
_ENTRY_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_ENTRY_DIR)
for _p in (_ROOT, _ENTRY_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def run_cli() -> None:
    from ascend_cli import main as cli_main
    sys.exit(cli_main())


def run_gui() -> None:
    from app import App
    App().mainloop()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        del sys.argv[1]
        run_cli()
        return
    run_gui()


if __name__ == "__main__":
    main()
