#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReviewAgent CLI 入口
全局命令: review
"""
import sys
import os
import argparse
from pathlib import Path

# 设置项目路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Windows 编码 + ANSI 颜色
try:
    from scripts.term_style import enable_windows_ansi, ensure_utf8_stdio
    ensure_utf8_stdio()
    enable_windows_ansi()
except Exception:
    if sys.platform == 'win32':
        import io
        if not isinstance(sys.stdout, io.TextIOWrapper) or (sys.stdout.encoding or '').lower() != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)


ASCII_LOGO = r"""
    ____            _                ___                    __
   / __ \___ _   __(_)__ _      __  /   | ____ ____  ____  / /_
  / /_/ / _ \ | / / / _ \ | /| / / / /| |/ __ `/ _ \/ __ \/ __/
 / _, _/  __/ |/ / /  __/ |/ |/ / / ___ / /_/ /  __/ / / / /_
/_/ |_|\___/|___/_/\___/|__/|__/ /_/  |_\__, /\___/_/ /_/\__/
                                        /____/
"""


def show_logo():
    """显示 Logo"""
    # 使用颜色（如果支持）
    try:
        # ANSI 颜色
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        RESET = '\033[0m'

        print(f"{CYAN}{ASCII_LOGO}{RESET}")
        print(f"{GREEN}智能代码审查助手 - 专为昇腾 NPU 打造{RESET}")
        print(f"{CYAN}{'=' * 70}{RESET}")
        print()
    except:
        print(ASCII_LOGO)
        print("智能代码审查助手 - 专为昇腾 NPU 打造")
        print("=" * 70)
        print()


def main():
    """主入口"""
    # All current Agent commands share one runtime. Keep old file/config/stats
    # shortcuts below for backwards compatibility.
    agent_cmds = (
        'chat', 'review', 'search', 'test', 'config', 'doctor', 'model',
        '--help', '-h', '--version',
    )
    if len(sys.argv) == 1 or sys.argv[1] in agent_cmds:
        from ascend_cli import main as agent_main
        return agent_main()
    parser = argparse.ArgumentParser(
        prog='reviewagent',
        description='ReviewAgent - Ascend AI Infra 智能体',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  review               进入对话模式
  review code.py       快速审查文件
  review --config      配置 AI 服务
  review --help        显示帮助
        """
    )

    parser.add_argument('file', nargs='?', help='要审查的文件（可选）')
    parser.add_argument('--config', action='store_true', help='配置向导')
    parser.add_argument('--stats', action='store_true', help='显示统计')
    parser.add_argument('--version', action='version', version='ReviewAgent v1.0')

    args = parser.parse_args()

    # 只显示一次 Logo
    show_logo()

    # 如果有文件参数，快速审查
    if args.file:
        print(f"[快速审查模式] 审查文件: {args.file}\n")
        from review_cli import cmd_review
        import argparse as ap
        review_args = ap.Namespace(
            file=args.file,
            text=None,
            output=None,
            quiet=False,
            config=str(SCRIPT_DIR / 'config/ai_config.json'),
            git_diff=False,
            staged=False
        )
        return cmd_review(review_args)

    # 配置模式
    if args.config:
        print()  # 空行
        from chat_v2 import ReviewAgentChat
        agent = ReviewAgentChat()
        agent.setup_wizard()
        return 0

    # 统计模式
    if args.stats:
        from review_cli import cmd_stats
        return cmd_stats(argparse.Namespace())

    # 默认进入对话模式
    print("启动对话模式...\n")
    from chat_v2 import ReviewAgentChat
    agent = ReviewAgentChat()
    # 不显示 welcome（已经显示了 Logo）
    agent.run_without_welcome()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n再见！")
        sys.exit(0)
