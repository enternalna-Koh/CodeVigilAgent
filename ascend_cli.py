#!/usr/bin/env python3
"""昇腾 AI Infra Agent CLI.

The first version focuses on a reliable repository review workflow. AI tool
loops and automatic patching can be added behind the same command surface.
"""

import argparse
import json
import sys
from pathlib import Path

from scripts.repo_context import RepoContextError, collect_repo_context, format_repo_prompt
from scripts.smart_reviewer import SmartReviewer
from scripts.agent_tools import find_test_commands, run_command
from scripts.knowledge_search import KnowledgeSearch, PROJECT_ROOT
from scripts.ai_adapter import get_ai_client
from scripts.conversation_agent import ConversationAgent
from scripts.chat_input import read_message
from scripts.specialist_context import resolve_specialist


def review(args: argparse.Namespace) -> int:
    try:
        context = collect_repo_context(staged=args.staged, max_diff_chars=args.max_diff)
    except RepoContextError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not context["diff"].strip():
        print("[INFO] 暂存区没有可审查的 diff。" if args.staged else "[INFO] 没有可审查的已跟踪文件 diff；未跟踪文件尚未纳入审查。")
        return 0
    if context["diff_truncated"]:
        if args.require_full:
            print(f"[ERROR] diff 共 {context['diff_total_chars']} 字符，超出 --max-diff {args.max_diff}，"
                  "无法完成完整审查；请调大 --max-diff 或分批提交。", file=sys.stderr)
            return 1
        print("[WARN] diff 超出大小限制，当前结果仅覆盖前半部分（报告中 coverage=partial）。", file=sys.stderr)

    prompt = format_repo_prompt(context)
    paths = context.get("changed_files") or []
    specialist = resolve_specialist(prompt, paths=paths, explicit=getattr(args, "scenario", None))
    require_scenario = bool(getattr(args, "require_scenario", False) or getattr(args, "scenario", None))
    # 显式 --scenario 或 --require-scenario：含糊/缺失则停；默认自动判定失败时退回通用审查
    if specialist.status == "missing_agent" or (require_scenario and specialist.status == "needs_context"):
        payload = {
            "needs_context": specialist.status == "needs_context",
            "specialist_context": specialist.as_dict(),
            "question": specialist.question or "这是算子社区任务，还是推理部署？",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"[NEED CONTEXT] {payload['question']}")
            print(f"  reason: {specialist.reason}")
            print("  使用 --scenario operator|inference 明确场景后重试。")
        if args.output:
            Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    if specialist.status == "ready":
        meta = specialist.as_dict()
        meta["text_loaded"] = bool(specialist.text)
        specialist_text = specialist.text
    else:
        meta = specialist.as_dict()
        meta["status"] = "skipped"
        meta["text_loaded"] = False
        specialist_text = ""
        if not args.json:
            print(f"[INFO] 未加载专业 Agent（{specialist.reason or specialist.status}）；使用通用审查。"
                  "需要时可加 --scenario operator|inference。", file=sys.stderr)

    reviewer = SmartReviewer(args.config, verbose=not args.json)
    if args.offline:
        reviewer.has_ai = False
    report = reviewer.review(
        prompt,
        metadata={"source": "repository", "repository": context},
        verbose=not args.json,
        specialist_text=specialist_text,
        specialist_meta=meta,
    )
    result = report.get("review_result", {})
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OUTPUT] 报告已保存: {args.output}", file=sys.stderr)
    if not args.json:
        reviewer.print_report(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if result.get("error") else 0


def test(args: argparse.Namespace) -> int:
    commands = find_test_commands(args.path)
    if not commands:
        print("[INFO] 未识别到 pytest 或 npm 测试入口。")
        return 0
    for command in commands:
        print(f"[TEST] {' '.join(command)}")
        result = run_command(command, cwd=args.path, timeout=args.timeout)
        print(result["output"])
        if result["returncode"] != 0:
            return 1
    return 0


def search(args: argparse.Namespace) -> int:
    knowledge = KnowledgeSearch()
    results = knowledge.search(args.query, args.limit, args.kind)
    if args.json:
        print(json.dumps({'indexed_records': len(knowledge.documents), 'references': results,
                          'warnings': knowledge.warnings}, ensure_ascii=False, indent=2))
    else:
        print(f"本地索引: {len(knowledge.documents)} 条；匹配案例: {len(results)} 条")
        for warning in knowledge.warnings:
            print(f"[WARN] {warning}")
        for item in results:
            print(f"\n[{item['kind']}] {item['title']}\n{item['url']}\n{item['excerpt']}")
        if results:
            print('\n历史原文仅供参考，未验证其解决方案或适用版本。')
    return 0


def chat(args: argparse.Namespace) -> int:
    try:
        client = get_ai_client(args.config)
    except Exception as exc:
        print(f"[ERROR] AI 未配置: {exc}")
        print("[INFO] 先运行 python review_cli.py config --init，或设置 AI_API_KEY。")
        return 1

    agent = ConversationAgent(client, network=args.network,
                              progress=lambda message: print(f"[Agent] {message}"))
    print("ReviewAgent 对话模式。发送 GitHub PR/Issue 链接即可分析，之后可直接追问。")
    print("命令: /paste 多行输入，/context 当前分析对象，/help /clear /exit")
    print(f'联网模式: {agent.network}；/network auto|on|off 切换（off 关闭外部资料获取，AI 仍使用配置的服务）')
    if args.multiline:
        print('已开启多行模式：回车换行，/send 发送，/cancel 取消。')
    if args.message:
        print(agent.answer(args.message))
        return 0 if agent.last_ok else 1
    while True:
        try:
            text = read_message(multiline=args.multiline)
        except KeyboardInterrupt:
            print('\n已取消本次输入。输入 /exit 退出。')
            continue
        except EOFError:
            print()
            return 0
        if text in ('/exit', '/quit', '/q'):
            return 0
        if text.startswith('/network'):
            parts = text.split()
            if len(parts) == 2 and parts[1] in ('auto', 'on', 'off'):
                agent.network = parts[1]
            print(f'联网模式: {agent.network}。用法: /network auto|on|off')
            continue
        if text == '/sources':
            print(json.dumps(agent.last_tools, ensure_ascii=False, indent=2))
            continue
        if text == '/clear':
            agent.clear()
            print('已清除当前对话和 PR/Issue 上下文。')
            continue
        if text == '/context':
            if not agent.context_summary:
                print('当前没有获取到的 PR/Issue。')
            for context in agent.context_summary:
                print(f"[{context['type']}] {context['title']}\n{context['url']}")
                for warning in context['warnings']:
                    print(f'[范围限制] {warning}')
            continue
        if text == '/help':
            print('发送 PR/Issue URL 开始分析；可继续追问。')
            print('/paste 进入多行输入，/send 发送，/cancel 取消；多行模式支持空行和缩进。')
            print('/network auto|on|off 切换联网资料获取；/sources 查看最近调查来源。')
            continue
        if not text:
            continue
        print(f"\nAgent> {agent.answer(text)}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="ascend", description="昇腾 AI Infra 开发 Agent")
    parser.add_argument("--version", action="version", version="ReviewAgent 1.1")
    subparsers = parser.add_subparsers(dest="command")

    review_parser = subparsers.add_parser("review", help="审查当前 Git 工作区")
    review_parser.add_argument("--staged", action="store_true", help="只审查暂存区")
    review_parser.add_argument("--config", default=str(PROJECT_ROOT / "config/ai_config.json"))
    review_parser.add_argument("--offline", action="store_true", help="使用本地规则和案例检索，不调用 AI")
    review_parser.add_argument("--output", "-o")
    review_parser.add_argument("--json", action="store_true", help="输出 JSON")
    review_parser.add_argument("--max-diff", type=int, default=12000)
    review_parser.add_argument("--require-full", action="store_true",
                               help="diff 超出 --max-diff 时直接失败，不给出只覆盖部分改动的审查结果")
    review_parser.add_argument("--scenario", choices=["operator", "inference"],
                               help="加载专业 Agent：operator=算子社区任务，inference=推理部署；省略则自动判定，含糊时退回通用审查")
    review_parser.add_argument("--require-scenario", action="store_true",
                               help="自动判定含糊时返回 needs_context（退出码 2），不进行通用审查")
    review_parser.set_defaults(func=review)

    test_parser = subparsers.add_parser("test", help="运行项目测试")
    test_parser.add_argument("--path", default=".")
    test_parser.add_argument("--timeout", type=int, default=120)
    test_parser.set_defaults(func=test)

    search_parser = subparsers.add_parser('search', help='搜索本地昇腾 Issue/PR 案例，无需 AI')
    search_parser.add_argument('query')
    search_parser.add_argument('--limit', type=int, choices=range(1, 21), default=5)
    search_parser.add_argument('--kind', choices=['issue', 'pr'])
    search_parser.add_argument('--json', action='store_true')
    search_parser.set_defaults(func=search)

    chat_parser = subparsers.add_parser('chat', help='自然语言分析 PR/Issue，并连续追问')
    chat_parser.add_argument('--config', default=str(PROJECT_ROOT / 'config/ai_config.json'))
    chat_parser.add_argument('--message', '-m', help='一次性自然语言请求')
    chat_parser.add_argument('--multiline', action='store_true', help='每条消息都使用多行输入，/send 发送')
    chat_parser.add_argument('--network', choices=['auto', 'on', 'off'], default='auto',
                             help='auto 按需联网；on 每轮搜索；off 禁用外部资料获取（AI 调用仍联网）')
    chat_parser.set_defaults(func=chat)

    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(['chat'])
    if args.command == 'review' and args.max_diff <= 0:
        parser.error('--max-diff 必须大于 0')
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
