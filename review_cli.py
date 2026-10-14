#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReviewAgent CLI - 命令行界面
"""
import sys
import os
import argparse
import json
from pathlib import Path

# 设置编码
if sys.platform == 'win32':
    # Reconfigure the existing streams instead of wrapping their buffers;
    # wrapping can suppress argparse output when the process exits on Windows.
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 添加项目路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

try:
    from scripts.smart_reviewer import SmartReviewer
    from scripts.ai_adapter import get_ai_client
    from scripts.repo_context import RepoContextError, collect_repo_context, format_repo_prompt
except ImportError as e:
    print(f"[ERROR] 导入失败: {e}")
    print(f"[INFO] 请确保在项目根目录运行")
    sys.exit(1)


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                      ReviewAgent CLI v1.0                         ║
║               智能代码审查助手 - 昇腾 NPU 专用                      ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def cmd_review(args):
    """审查命令"""
    print("[INFO] 启动智能审查...")
    print()

    reviewer = SmartReviewer(args.config)

    # 读取输入
    repo_context = None
    if args.git_diff or args.staged:
        try:
            repo_context = collect_repo_context(staged=args.staged)
        except RepoContextError as exc:
            print(f"[ERROR] {exc}")
            return 1
        content = format_repo_prompt(repo_context)
        print(f"[INPUT] Git 仓库: {repo_context['root']}")
        print(f"[INPUT] 分支: {repo_context['branch']}")
        print(f"[INPUT] 变更文件: {len(repo_context['changed_files'])}")

    elif args.file:
        if not os.path.exists(args.file):
            print(f"[ERROR] 文件不存在: {args.file}")
            return 1

        with open(args.file, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"[INPUT] 读取文件: {args.file}")

    elif args.text:
        content = args.text
        print(f"[INPUT] 文本长度: {len(content)} 字符")

    else:
        # 从标准输入读取
        print("[INPUT] 等待标准输入 (Ctrl+D 结束):")
        content = sys.stdin.read()

    print()

    # 执行审查
    report = reviewer.review(content, metadata={
        'source': 'git' if repo_context else ('file' if args.file else 'text'),
        'repository': repo_context,
    })

    # 输出报告
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[OUTPUT] 报告已保存: {args.output}")
        print()

    # 打印到控制台
    if not args.quiet:
        reviewer.print_report(report)

    return 0


def cmd_test(args):
    """测试命令"""
    print("[INFO] 运行内置测试用例...")
    print()

    from scripts.smart_reviewer import test_with_real_cases
    test_with_real_cases()

    return 0


def cmd_config(args):
    """配置命令"""
    config_file = args.config or 'config/ai_config.json'

    if args.show:
        # 显示当前配置
        if not os.path.exists(config_file):
            print(f"[ERROR] 配置文件不存在: {config_file}")
            print(f"[INFO] 使用: review config --init 创建配置")
            return 1

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        print(f"[CONFIG] 当前配置 ({config_file}):")
        print(f"  Provider: {config.get('provider', 'N/A')}")
        print(f"  Model: {config.get('model', 'N/A')}")
        print(f"  API Key: {'*' * 20 + config.get('api_key', '')[-10:] if config.get('api_key') else 'N/A'}")

        return 0

    if args.init:
        # 初始化配置
        template_file = 'config/ai_config.json.template'

        if os.path.exists(config_file) and not args.force:
            print(f"[ERROR] 配置文件已存在: {config_file}")
            print(f"[INFO] 使用 --force 覆盖")
            return 1

        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {
                "provider": "deepseek",
                "api_key": "YOUR_API_KEY_HERE",
                "model": "deepseek-chat"
            }

        os.makedirs(os.path.dirname(config_file), exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print(f"[OK] 配置文件已创建: {config_file}")
        print(f"[INFO] 请编辑文件并填入你的 API Key")

        return 0

    if args.set:
        # 设置配置项
        key, value = args.set.split('=', 1)

        if not os.path.exists(config_file):
            print(f"[ERROR] 配置文件不存在，请先运行: review config --init")
            return 1

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        config[key] = value

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print(f"[OK] 已设置: {key} = {value}")

        return 0

    # 默认显示配置
    return cmd_config(argparse.Namespace(show=True, config=config_file, init=False, set=None, force=False))


def cmd_stats(args):
    """统计命令 - 显示数据统计"""
    print("[INFO] ReviewAgent 数据统计")
    print("=" * 70)
    print()

    # 统计数据文件
    data_dir = Path('data/raw')

    if not data_dir.exists():
        print("[ERROR] data/raw 目录不存在")
        return 1

    files = list(data_dir.glob('*.json'))

    total_size = sum(f.stat().st_size for f in files)

    issues_count = 0
    prs_count = 0

    for f in files:
        if '_issues.json' in f.name:
            issues_count += 1
        elif '_prs.json' in f.name:
            prs_count += 1

    print(f"数据文件总数: {len(files)}")
    print(f"总大小: {total_size / 1024 / 1024:.2f} MB")
    print(f"Issues 文件: {issues_count}")
    print(f"PRs 文件: {prs_count}")
    print()

    # 显示训练数据
    training_dir = Path('data/training')
    if training_dir.exists():
        print("训练数据:")
        for subdir in ['reviews', 'ci_rules', 'issues', 'combined']:
            subdir_path = training_dir / subdir
            if subdir_path.exists():
                files = list(subdir_path.glob('*.json'))
                if files:
                    size = sum(f.stat().st_size for f in files)
                    print(f"  {subdir}: {len(files)} 文件, {size / 1024:.2f} KB")

    return 0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        prog='review',
        description='ReviewAgent - 智能代码审查助手',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 审查文件
  review code.py

  # 审查文本
  review --text "def foo(): pass"

  # 从标准输入审查
  cat code.py | review

  # 保存报告
  review code.py --output report.json

  # 运行测试
  review test

  # 配置管理
  review config --init
  review config --show
  review config --set provider=openai

  # 查看统计
  review stats
"""
    )

    # 全局参数
    parser.add_argument('--config', '-c',
                       help='AI 配置文件路径 (默认: config/ai_config.json)')
    parser.add_argument('--version', '-v', action='version', version='ReviewAgent v1.0')

    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 默认命令：直接审查
    parser.add_argument('file', nargs='?', help='要审查的文件')
    parser.add_argument('--text', '-t', help='直接提供文本内容')
    parser.add_argument('--output', '-o', help='保存报告到文件 (JSON)')
    parser.add_argument('--quiet', '-q', action='store_true', help='静默模式，不打印报告')
    parser.add_argument('--git-diff', action='store_true', help='审查当前 Git 工作区 diff')
    parser.add_argument('--staged', action='store_true', help='只审查 Git 暂存区 diff')

    # test 命令
    test_parser = subparsers.add_parser('test', help='运行内置测试用例')

    # config 命令
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_parser.add_argument('--init', action='store_true', help='初始化配置文件')
    config_parser.add_argument('--show', action='store_true', help='显示当前配置')
    config_parser.add_argument('--set', help='设置配置项 (格式: key=value)')
    config_parser.add_argument('--force', action='store_true', help='强制覆盖已存在的配置')

    # stats 命令
    stats_parser = subparsers.add_parser('stats', help='显示数据统计')

    args = parser.parse_args()

    # 如果没有任何参数，显示帮助
    if len(sys.argv) == 1:
        print_banner()
        parser.print_help()
        return 0

    # 执行命令
    try:
        if args.command == 'test':
            return cmd_test(args)
        elif args.command == 'config':
            return cmd_config(args)
        elif args.command == 'stats':
            return cmd_stats(args)
        else:
            # 默认审查命令
            return cmd_review(args)

    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
        return 130
    except Exception as e:
        print(f"[ERROR] {e}")
        if '--debug' in sys.argv:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
