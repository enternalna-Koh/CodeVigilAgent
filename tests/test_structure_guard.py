# -*- coding: utf-8 -*-
"""结构守卫：让「加功能把文件撑胖」在测试里就暴露。

背景（评审原话）：
    「整体结构上有点拥挤，如果后面加新的功能会影响」

光靠自觉没用，所以把规则写成测试：
    1. 关键文件有行数预算，超了必须显式调预算（等于承认要重构或接受膨胀）
    2. 分层不能反向：scripts/ 不许 import ascend_cli
    3. 新斜杠命令必须放 scripts/cli_commands/ 并声明 COMMANDS
    4. handle_chat_slash 不许再变长（新命令走注册表）
    5. 根目录文件数不超过 20

超预算怎么办：
    优先拆模块；确实要加，就在下面 BUDGETS 里改数字，并在提交信息里写清理由。
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 行数预算 = 当前值 + 少量余量。改这里等于公开承认「这个文件又要变胖了」。
BUDGETS = {
    'ascend_cli.py': 1820,
    'chat_v2.py': 800,
    'scripts/smart_reviewer.py': 830,
    'scripts/conversation_agent.py': 920,
    'scripts/term_frame.py': 620,
    'desktop-app/win/cvapp/shell.py': 300,
    'desktop-app/win/cvapp/runner.py': 200,
    'desktop-app/win/cvapp/lifecycle.py': 80,
    'desktop_py/app.py': 1000,
    'desktop_py/cli_runtime.py': 250,
    'desktop_py/entry.py': 80,
    'desktop_py/session_controller.py': 400,
    'desktop_py/settings_dialog.py': 380,
    'scripts/gateway_key.py': 80,
    'scripts/patch_paths.py': 380,
}

# 单个函数的行数上限（针对「什么都往里塞」的重灾区）
FUNCTION_BUDGETS = {
    ('ascend_cli.py', 'handle_chat_slash'): 640,
}

FORBIDDEN_IMPORT = re.compile(r'(?m)^\s*(?:import|from)\s+ascend_cli\b')

# 唯一允许 import ascend_cli 的桌面文件：打包入口本身。
# 理由：打成单个 exe 后目标机器没有 Python，只能用「同一个 exe 加 --cli」
# 在进程内跑 CLI；这是入口层的正向依赖，不是 GUI 能力文件的反向依赖。
# 名单必须保持只有这一项，下面 LayeringTests 有断言钉住。
LAYERING_ENTRY_ALLOWED = {'desktop_py/entry.py'}


class FileSizeTests(unittest.TestCase):
    def test_file_line_budgets(self):
        over = []
        for name, budget in BUDGETS.items():
            path = ROOT / name
            self.assertTrue(path.is_file(), f'预算表里的文件不存在: {name}')
            lines = len(path.read_text(encoding='utf-8').splitlines())
            if lines > budget:
                over.append(f'{name}: {lines} 行 > 预算 {budget}')
        self.assertEqual(over, [], '文件超出行数预算，先拆模块；确有必要再调 BUDGETS：\n' + '\n'.join(over))

    def test_function_line_budgets(self):
        for (name, function), budget in FUNCTION_BUDGETS.items():
            tree = ast.parse((ROOT / name).read_text(encoding='utf-8'))
            found = [n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == function]
            self.assertTrue(found, f'{name} 里找不到 {function}')
            size = found[0].end_lineno - found[0].lineno + 1
            self.assertLessEqual(
                size, budget,
                f'{name}:{function} 已 {size} 行，超过 {budget}。'
                '新命令请放 scripts/cli_commands/，不要继续塞进这个函数。')

    def test_root_file_count(self):
        files = [p for p in ROOT.iterdir() if p.is_file()]
        self.assertLessEqual(len(files), 20,
                             f'根目录文件 {len(files)} 个，超过 20；能用子目录归档的就归档')


class LayeringTests(unittest.TestCase):
    def test_scripts_do_not_import_ascend_cli(self):
        """能力层不能反向依赖入口层，否则拆不动。"""
        offenders = []
        for path in (ROOT / 'scripts').rglob('*.py'):
            text = path.read_text(encoding='utf-8', errors='replace')
            if FORBIDDEN_IMPORT.search(text):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], f'这些脚本反向 import 了 ascend_cli: {offenders}')

    def test_desktop_layer_is_standalone(self):
        offenders = []
        for directory in ('desktop-app/win/cvapp', 'desktop_py'):
            for path in (ROOT / directory).rglob('*.py'):
                relative = str(path.relative_to(ROOT)).replace('\\', '/')
                if relative in LAYERING_ENTRY_ALLOWED:
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
                if FORBIDDEN_IMPORT.search(text):
                    offenders.append(relative)
        self.assertEqual(offenders, [], f'桌面层不应依赖 CLI 入口: {offenders}')

    def test_layering_exemption_stays_narrow(self):
        self.assertEqual(LAYERING_ENTRY_ALLOWED, {'desktop_py/entry.py'})
        self.assertTrue((ROOT / 'desktop_py' / 'entry.py').is_file(),
                        '豁免对应的打包入口必须真实存在')


    def test_desktop_capabilities_do_not_import_window_entry(self):
        for name in ('cli_runtime.py', 'session_controller.py', 'settings_dialog.py'):
            path = ROOT / 'desktop_py' / name
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                else:
                    continue
                self.assertFalse(any(module in ('app', 'desktop_py.app') for module in modules),
                                 f'{name} 不能反向依赖桌面入口')


class SlashRegistryTests(unittest.TestCase):
    def setUp(self):
        from scripts import cli_commands
        cli_commands.reset_cache()

    def test_registry_loads_convenience_commands(self):
        from scripts.cli_commands import load_handlers
        handlers, warnings = load_handlers()
        self.assertEqual(warnings, [])
        for name in ('/copy', '/dir', '/cost', '/commands'):
            self.assertIn(name, handlers, f'{name} 没有注册')

    def test_builtin_commands_are_not_hijacked(self):
        from scripts.cli_commands import SlashContext, dispatch, load_handlers
        handlers, _ = load_handlers()
        for builtin in ('/review', '/fix', '/help', '/model', '/open'):
            self.assertNotIn(builtin, handlers,
                             f'{builtin} 是内置命令，不能在扩展注册表里重定义')
            self.assertFalse(dispatch(builtin, SlashContext(agent=None, repo_root='.')))

    def test_dispatch_unknown_returns_false(self):
        from scripts.cli_commands import SlashContext, dispatch
        self.assertFalse(dispatch('/not-a-command-20261112',
                                  SlashContext(agent=None, repo_root='.')))

    def test_dispatch_calls_handler(self):
        from unittest.mock import patch
        from scripts.cli_commands import SlashContext, dispatch

        class Agent:
            last_reply = '回答内容'

        with patch('scripts.cli_commands.convenience.copy_text',
                   return_value=(True, '已复制')) as copier:
            handled = dispatch('/copy', SlashContext(agent=Agent(), repo_root='.'))
        self.assertTrue(handled)
        copier.assert_called_once_with('回答内容')

    def test_each_command_module_declares_commands(self):
        for path in (ROOT / 'scripts' / 'cli_commands').glob('*.py'):
            if path.name == '__init__.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            assigned = {t.id for node in tree.body if isinstance(node, ast.Assign)
                        for t in node.targets if isinstance(t, ast.Name)}
            self.assertIn('COMMANDS', assigned,
                          f'{path.name} 没有声明 COMMANDS，注册表不会加载它')


if __name__ == '__main__':
    unittest.main()
