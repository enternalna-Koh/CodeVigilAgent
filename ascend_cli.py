#!/usr/bin/env python3
"""ReviewAgent — Ascend AI Infra Agent CLI (Hermes-style).

Wake: `reviewagent` (or `review` / `ra`)
Install: `npm install -g reviewagent`
Model: env via cc-switch (OPENAI_* / ANTHROPIC_* / AI_*) or `reviewagent config`
"""

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.repo_context import RepoContextError, collect_repo_context, format_repo_prompt
from scripts.smart_reviewer import SmartReviewer
from scripts.agent_tools import find_test_commands, run_command
from scripts.knowledge_search import KnowledgeSearch, PROJECT_ROOT
from scripts.ai_adapter import get_ai_client, load_config_from_env, load_config_from_file, merge_config
from scripts.conversation_agent import ConversationAgent
from scripts.chat_input import read_message
from scripts.term_style import (
    brand,
    enable_windows_ansi,
    ensure_utf8_stdio,
    mute,
    ok,
    warn,
)
from scripts.think_ui import begin_think, end_think, think_progress
from scripts.md_term import print_markdown_box
from scripts.specialist_context import resolve_specialist
from scripts.agent_home import ensure_home, resolve_config_file, config_path, home_dir, write_config, read_config
from scripts.model_catalog import (
    apply_target_to_config,
    format_catalog_help,
    gateway_changed,
    resolve_model_request,
)


def _default_config(cli_value: str = None) -> str:
    if cli_value and cli_value not in ('unused.json',):
        return cli_value
    return resolve_config_file(None)


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

    reviewer = SmartReviewer(_default_config(args.config), verbose=not args.json)
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


def doctor(args: argparse.Namespace) -> int:
    """Environment / config health check (Hermes-style)."""
    from scripts.agent_home import ensure_home
    print('ReviewAgent doctor')
    print(f'  home: {ensure_home()}')
    print(f'  config: {resolve_config_file(getattr(args, "config", None))}')
    print(f'  package: {PROJECT_ROOT}')
    env = load_config_from_env()
    file_cfg = load_config_from_file(resolve_config_file(getattr(args, 'config', None)))
    merged = merge_config(file_cfg, env)
    print(f'  provider: {merged.get("provider") or "(unset)"}')
    print(f'  model: {merged.get("model") or "(unset)"}')
    print(f'  base_url: {merged.get("base_url") or "(default)"}')
    key = merged.get('api_key') or ''
    print(f'  api_key: {"set (" + key[:4] + "…)" if key else "MISSING"}')
    print(f'  env OPENAI_API_KEY: {"yes" if os.getenv("OPENAI_API_KEY") else "no"}')
    print(f'  env ANTHROPIC_API_KEY: {"yes" if os.getenv("ANTHROPIC_API_KEY") else "no"}')
    print(f'  env AI_API_KEY: {"yes" if os.getenv("AI_API_KEY") else "no"}')
    knowledge = KnowledgeSearch()
    print(f'  knowledge index: {len(knowledge.documents)} records')
    if not key:
        print('[HINT] run `reviewagent config` or export OPENAI_API_KEY (cc-switch compatible)')
        return 1
    try:
        get_ai_client(getattr(args, 'config', None))
        print('[OK] AI client can be constructed')
        return 0
    except Exception as exc:
        print(f'[ERROR] {exc}')
        return 1


def _interactive_setup() -> int:
    """Fallback wizard (prefer Node `reviewagent` / `config --wizard` TUI)."""
    ensure_home()
    path = config_path()
    data = read_config(str(path)) or {}
    print('ReviewAgent 首次配置（建议直接运行 `reviewagent`，会使用更美观的引导界面）')
    print(f'配置文件: {path}')
    print()
    providers = [
        ('deepseek', 'DeepSeek', [
            'deepseek-chat', 'deepseek-reasoner', 'deepseek-coder',
            'deepseek-v3', 'deepseek-r1', 'deepseek-r1-0528',
        ]),
        ('openai', 'OpenAI / 兼容网关', [
            'gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini',
            'o1', 'o3-mini', 'o4-mini', 'gpt-3.5-turbo',
        ]),
        ('claude', 'Claude', [
            'claude-opus-4-20250514', 'claude-sonnet-4-20250514',
            'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022',
        ]),
        ('glm', '智谱 GLM', [
            'glm-4', 'glm-4-plus', 'glm-4-air', 'glm-4-flash', 'glm-3-turbo',
        ]),
    ]
    print('选择 provider:')
    for i, (_pid, label, _models) in enumerate(providers, 1):
        print(f'  {i}. {label}')
    try:
        choice = input('编号 [1]: ').strip() or '1'
        idx = int(choice) - 1
        provider, _label, model_list = providers[idx] if 0 <= idx < len(providers) else providers[0]
    except (ValueError, EOFError, KeyboardInterrupt):
        print('\n[INFO] 已取消')
        return 1

    defaults = {
        'deepseek': ('deepseek-chat', ''),
        'openai': ('gpt-4o', 'https://api.openai.com/v1'),
        'claude': ('claude-3-5-sonnet-20241022', ''),
        'glm': ('glm-4', ''),
    }
    default_model, default_base = defaults.get(provider, ('deepseek-chat', ''))
    print('选择模型:')
    for i, name in enumerate(model_list, 1):
        mark = ' (默认)' if name == default_model else ''
        print(f'  {i}. {name}{mark}')
    print(f'  {len(model_list) + 1}. 自定义输入')
    try:
        mchoice = input(f'编号 [1]: ').strip() or '1'
        mi = int(mchoice) - 1
        if 0 <= mi < len(model_list):
            model = model_list[mi]
        else:
            model = input(f'自定义模型 ID [{default_model}]: ').strip() or default_model
        base_url = ''
        if provider == 'openai':
            base_url = input(f'base_url（OpenAI 兼容网关）[{default_base}]: ').strip() or default_base
        api_key = input('API Key（输入时可见，勿发给别人）: ').strip()
    except (EOFError, KeyboardInterrupt):
        print('\n[INFO] 已取消')
        return 1

    if not api_key or api_key == 'YOUR_API_KEY_HERE':
        print('[ERROR] 未填写有效 API Key')
        return 1

    data['provider'] = provider
    data['model'] = model
    data['api_key'] = api_key
    if base_url:
        data['base_url'] = base_url
    elif 'base_url' in data and provider != 'openai':
        data['base_url'] = ''
    written = write_config(data, str(path))
    print(f'[OK] 已保存 {written}')
    print('再运行: reviewagent')
    return 0


def config_cmd(args: argparse.Namespace) -> int:
    """Init / show / set provider config under ~/.reviewagent."""
    ensure_home()
    path = Path(resolve_config_file(args.config if getattr(args, 'config', None) else None))
    if getattr(args, 'wizard', False):
        return _interactive_setup()
    if args.init:
        ensure_home()
        print(f'[OK] home ready: {home_dir()}')
        print(f'[OK] config: {config_path()}')
        print('下一步任选其一:')
        print('  1) reviewagent config --wizard')
        print('  2) reviewagent config --set api_key=sk-xxx provider=deepseek')
        print('  3) 用 cc-switch 导出 OPENAI_API_KEY 后再运行 reviewagent')
        return 0
    if args.show or (not args.set and not args.init and not getattr(args, 'wizard', False)):
        data = read_config(str(path))
        safe = {**data, 'api_key': ('***' if data.get('api_key') and data.get('api_key') != 'YOUR_API_KEY_HERE' else data.get('api_key'))}
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        print(f'\n# file: {path}')
        return 0
    if args.set:
        data = read_config(str(path)) or {}
        for item in args.set:
            if '=' not in item:
                print(f'[ERROR] 期望 key=value，收到: {item}')
                return 1
            key, value = item.split('=', 1)
            data[key.strip()] = value.strip()
        written = write_config(data, str(path))
        print(f'[OK] wrote {written}')
        return 0
    return 0


def model_cmd(args: argparse.Namespace) -> int:
    """Show or switch model/provider (writes ~/.reviewagent/ai_config.json)."""
    ensure_home()
    path = str(config_path())
    data = read_config(path) or {}
    if args.provider:
        data['provider'] = args.provider
    if args.name:
        data['model'] = args.name
    if args.base_url:
        data['base_url'] = args.base_url
        data.setdefault('provider', 'openai')
    if args.provider or args.name or args.base_url:
        write_config(data, path)
        print(f"[OK] provider={data.get('provider')} model={data.get('model')} base_url={data.get('base_url') or ''}")
        print(f'     config: {path}')
        print('提示: cc-switch 注入的环境变量会覆盖本文件。')
        return 0
    env = load_config_from_env()
    merged = merge_config(data, env)
    print(f"active provider: {merged.get('provider')}")
    print(f"active model:    {merged.get('model')}")
    print(f"base_url:        {merged.get('base_url') or '(default)'}")
    print(f"source:          {'env' if env.get('api_key') else 'file'} (+merge)")
    return 0


def _slash_cmd(text: str):
    """Split leading slash command. '/model x' → ('/model', 'x'); 'hello' → (None, 'hello')."""
    raw = (text or '').strip()
    if not raw.startswith('/'):
        return None, raw
    parts = raw.split(maxsplit=1)
    return parts[0].lower(), (parts[1] if len(parts) > 1 else '')


def handle_chat_slash(text: str, agent: ConversationAgent, reload_client=None) -> str:
    """Dispatch in-chat slash commands.

    Returns: 'exit' | 'handled' | 'pass' (not a known slash cmd / not a slash).
    Uses exact command tokens so /model is never eaten by /mode.
    """
    head = (text or '').strip().splitlines()[0].strip().lower() if text else ''
    if head in ('exit', 'quit', 'q'):
        print(ok('已退出对话。'))
        return 'exit'

    cmd, arg = _slash_cmd(text)
    if cmd is None:
        return 'pass'

    if cmd in ('/exit', '/quit', '/q'):
        print(ok('已退出对话。'))
        return 'exit'

    if cmd in ('/chat', '/daily'):
        print(ok(agent.set_chat_mode('chat')))
        return 'handled'

    if cmd in ('/work', '/infra', '/review-mode'):
        print(ok(agent.set_chat_mode('work')))
        return 'handled'

    if cmd == '/mode':
        if not arg:
            labels = {'auto': '自动分流', 'chat': '日常对话', 'work': '正式工作'}
            print(ok(f'当前对话模式: {labels.get(agent.chat_mode, agent.chat_mode)}'))
            print(mute('  /chat 日常  ·  /work 正式审查  ·  /mode auto'))
        else:
            print(ok(agent.set_chat_mode(arg.strip())))
        return 'handled'

    if cmd == '/network':
        parts = arg.split()
        if len(parts) == 1 and parts[0] in ('auto', 'on', 'off'):
            agent.network = parts[0]
        print(ok(f'联网模式: {agent.network}') + mute('  用法: /network auto|on|off'))
        return 'handled'

    if cmd == '/sources':
        print(json.dumps(agent.last_tools, ensure_ascii=False, indent=2))
        return 'handled'

    if cmd == '/clear':
        agent.clear()
        print(ok('已清除当前对话和 PR/Issue 上下文。'))
        return 'handled'

    if cmd == '/context':
        if not agent.context_summary:
            print(warn('当前没有获取到的 PR/Issue。'))
        for context in agent.context_summary:
            print(brand(f"[{context['type']}] ") + context['title'])
            print(mute(context['url']))
            for warning in context['warnings']:
                print(warn(f'[范围限制] {warning}'))
        return 'handled'

    if cmd == '/fix':
        explicit = None
        first = arg.split()[0] if arg.split() else ''
        if first in ('operator', 'inference', 'general'):
            explicit = None if first == 'general' else first
        begin_think('生成补丁预览')
        try:
            reply = agent.propose_fix(explicit_scenario=explicit)
        finally:
            end_think('预览就绪')
        _print_agent_reply(reply)
        if agent.pending_fix and agent.pending_fix.files:
            try:
                confirm = input(warn('确认写入本地？输入 y 立即 /apply，其它键仅保留预览: ')).strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = ''
                print()
            if confirm in ('y', 'yes', '是'):
                _print_agent_reply(agent.apply_pending_fix(confirm=True))
        return 'handled'

    if cmd in ('/apply', '/fix-apply'):
        _print_agent_reply(agent.apply_pending_fix(confirm=True))
        return 'handled'

    if cmd in ('/discard', '/fix-discard'):
        _print_agent_reply(agent.discard_fix())
        return 'handled'

    if cmd == '/model':
        ensure_home()
        path = str(config_path())
        data = read_config(path) or {}
        env = load_config_from_env()
        merged = merge_config(data, env)
        if not arg.strip():
            print(ok('当前模型'))
            print(mute(f"  provider: {merged.get('provider')}"))
            print(mute(f"  model:    {merged.get('model')}"))
            print(mute(f"  base_url: {merged.get('base_url') or '(default)'}"))
            key = merged.get('api_key') or ''
            print(mute(f"  api_key:  {'已配置 (' + key[:4] + '…)' if key else '未配置'}"))
            print(mute(f"  配置文件: {path}"))
            print(brand('换厂商/模型（会要求对应 API Key）:'))
            print(mute('  /model glm          → 智谱，默认 glm-4-flash'))
            print(mute('  /model glm-4-flash'))
            print(mute('  /model deepseek'))
            print(mute('  /model MiniMax-M1   → 同厂商只改模型名'))
            print(mute('  完整重配: reviewagent config --wizard'))
            print(mute(format_catalog_help()))
            return 'handled'

        target = resolve_model_request(arg.strip())
        if not target.get('ok'):
            print(warn(target.get('message') or '无法解析'))
            return 'handled'

        print(ok(target['message']))
        need_key = gateway_changed(merged, target)
        new_key = None

        if need_key:
            label = target.get('label') or target.get('file_provider') or '新厂商'
            print(warn(
                f'将从 {merged.get("provider")} / {merged.get("base_url") or "(default)"} '
                f'切换到 {label}（provider={target.get("file_provider")}）'
            ))
            print(mute('旧 API Key 不能通用，请填写新厂商的 Key；直接回车=取消本次切换'))
            try:
                new_key = input(f'{label} API Key › ').strip()
            except (EOFError, KeyboardInterrupt):
                print()
                print(warn('已取消，配置未改动'))
                return 'handled'
            if not new_key or new_key == 'YOUR_API_KEY_HERE':
                print(warn('未填写 API Key，已取消切换（避免只改模型名却连错网关）'))
                return 'handled'
        elif not target.get('file_provider'):
            # custom model id on current gateway
            print(mute(target['message']))
            data = apply_target_to_config(data, target)
            write_config(data, path)
            try:
                if reload_client:
                    reload_client()
                print(ok(f"已切换 model={data['model']}（仍用当前 API）"))
            except Exception as exc:
                print(warn(f'已写入配置，但重载失败: {exc}'))
            return 'handled'

        data = apply_target_to_config(data, target, api_key=new_key)
        write_config(data, path)
        try:
            if reload_client:
                reload_client()
            print(ok(
                f"已切换 provider={data.get('provider')} model={data.get('model')}"
                + (f" base_url={data.get('base_url')}" if data.get('base_url') else '')
                + ('，API Key 已更新' if new_key else '，立即生效')
            ))
        except Exception as exc:
            print(warn(f'已写入配置，但重载客户端失败: {exc}'))
            print(mute('可检查 Key/网络后重开对话，或 reviewagent config --wizard'))
        return 'handled'

    if cmd == '/help':
        print(brand('审核 / 质检怎么用'))
        print(ok('0) 自动分流（默认，一般不用手切）'))
        print(mute('   贴链接/社区任务正文 → 正式审查'))
        print(mute('   好的/嗯/闲聊/无关问题 → 日常对话'))
        print(mute('   「怎么改/下一步」→ 继续正式（沿用上下文）'))
        print(mute('   可选钉住: /chat /work · 恢复自动: /mode auto · /clear 清空'))
        print(ok('1) 贴链接'))
        print(mute('   https://gitcode.com/Ascend/pytorch/issues/3135'))
        print(ok('2) 多行输入'))
        print(mute('   Win: 粘贴多行后 Enter 发送；Shift+Enter 换行'))
        print(mute('   或 /paste → 粘贴 → /send'))
        print(mute('   一次最多 20 个链接（REVIEWAGENT_MAX_URLS 可调）'))
        print(ok('3) 换模型'))
        print(mute('   /model  ·  /model MiniMax-M1  ·  reviewagent config --wizard'))
        print(ok('4) 改补丁'))
        print(mute('   /fix → y 或 /apply（不自动 push）'))
        print(mute('退出: exit / /exit / Ctrl+C'))
        print(mute('/discard /context /sources /clear · /network auto|on|off'))
        return 'handled'

    if cmd in ('/paste', '/p', '/send', '/cancel'):
        print(warn('请在输入框使用该命令：/paste 进入多行，结束后 /send（或 /cancel）。'))
        return 'handled'

    # Unknown slash — still "handled" so we don't send "/foo" to the model as a review
    print(warn(f'未知命令: {cmd}') + mute('  输入 /help 查看可用命令'))
    return 'handled'


def chat(args: argparse.Namespace) -> int:
    ensure_utf8_stdio()
    enable_windows_ansi()
    try:
        client = get_ai_client(_default_config(args.config))
    except Exception as exc:
        print(f"[ERROR] AI 未配置: {exc}")
        if args.message:
            print("[INFO] 非交互模式：请先 `reviewagent config --wizard` 或设置 OPENAI_API_KEY。")
            return 1
        print("[INFO] 进入配置向导（也可 Ctrl+C 退出后自行设置环境变量 / cc-switch）…\n")
        if _interactive_setup() != 0:
            return 1
        try:
            client = get_ai_client(_default_config(args.config))
        except Exception as exc2:
            print(f"[ERROR] 配置后仍无法启动: {exc2}")
            return 1

    quiet = os.environ.get('REVIEWAGENT_NODE_UI') == '1'

    def _on_progress(message: str) -> None:
        think_progress(message)

    agent = ConversationAgent(
        client,
        network=args.network,
        progress=_on_progress,
    )

    def _reload_client():
        nonlocal client, agent
        client = get_ai_client(_default_config(args.config))
        agent.client = client

    if not args.message:
        if quiet:
            print(mute('  默认自动切换：贴任务/链接→正式 · 好的/闲聊→日常 · 怎么改→继续正式'))
            print(mute('  粘贴多行后 Enter 发送 · 可选钉住: /chat /work · /mode auto'))
            print(mute('  Win: Shift+Enter换行 · exit/Ctrl+C · /model · /paste'))
            print(mute('  命令: /help /mode /model /fix /apply /clear'))
        else:
            print(brand('ReviewAgent · Ascend AI Infra'))
            print(mute(f'config: {_default_config(args.config)}'))
            print(mute('多行可直接粘贴；换模型: /model MiniMax-M1'))
            print()
    if args.multiline:
        print(warn('已开启多行模式：回车换行，/send 发送，/cancel 取消。'))
    if args.message:
        begin_think('思考中')
        try:
            reply = agent.answer(args.message)
        finally:
            end_think('回答就绪')
        _print_agent_reply(reply)
        return 0 if agent.last_ok else 1
    while True:
        try:
            text = read_message(
                multiline=args.multiline,
                network=agent.network,
                chat_mode=getattr(agent, 'chat_mode', 'auto'),
                session_lane=getattr(agent, 'session_lane', 'chat'),
            )
        except KeyboardInterrupt:
            print('\n' + ok('已退出对话。'))
            return 0
        except EOFError:
            print()
            return 0
        if not text:
            continue
        action = handle_chat_slash(text, agent, reload_client=_reload_client)
        if action == 'exit':
            return 0
        if action == 'handled':
            continue
        begin_think('思考中')
        interrupted = False
        reply = ''
        try:
            reply = agent.answer(text)
        except KeyboardInterrupt:
            interrupted = True
        end_think('已中断' if interrupted else '回答就绪')
        if interrupted:
            print('\n' + ok('已退出对话。'))
            return 0
        _print_agent_reply(reply)


def _print_agent_reply(reply: str) -> None:
    """Render markdown with colors inside Agent box."""
    print_markdown_box(reply or '', title='Agent')


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="reviewagent",
        description="ReviewAgent — Ascend AI Infra 智能体（Hermes 风格唤醒）",
    )
    parser.add_argument("--version", action="version", version="ReviewAgent 1.5.0")
    subparsers = parser.add_subparsers(dest="command")

    review_parser = subparsers.add_parser("review", help="审查当前 Git 工作区")
    review_parser.add_argument("--staged", action="store_true", help="只审查暂存区")
    review_parser.add_argument("--config", default=None, help="AI 配置文件（默认 ~/.reviewagent/ai_config.json）")
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

    chat_parser = subparsers.add_parser('chat', help='唤醒对话 Agent（默认命令）')
    chat_parser.add_argument('--config', default=None)
    chat_parser.add_argument('--message', '-m', help='一次性自然语言请求')
    chat_parser.add_argument('--multiline', action='store_true', help='每条消息都使用多行输入，/send 发送')
    chat_parser.add_argument('--network', choices=['auto', 'on', 'off'], default='auto',
                             help='auto 按需联网；on 每轮搜索；off 禁用外部资料获取（AI 调用仍联网）')
    chat_parser.set_defaults(func=chat)

    config_parser = subparsers.add_parser('config', help='初始化/查看/设置 ~/.reviewagent 配置')
    config_parser.add_argument('--config', default=None)
    config_parser.add_argument('--init', action='store_true', help='创建 REVIEWAGENT_HOME 与模板配置')
    config_parser.add_argument('--wizard', action='store_true', help='交互式填写 provider / model / api_key')
    config_parser.add_argument('--show', action='store_true', help='显示当前配置（隐藏密钥）')
    config_parser.add_argument('--set', nargs='+', metavar='KEY=VALUE', help='写入配置项，如 provider=openai')
    config_parser.set_defaults(func=config_cmd)

    doctor_parser = subparsers.add_parser('doctor', help='检查 Python/配置/模型环境')
    doctor_parser.add_argument('--config', default=None)
    doctor_parser.set_defaults(func=doctor)

    model_parser = subparsers.add_parser('model', help='查看或切换 provider/model（可与 cc-switch 配合）')
    model_parser.add_argument('--provider', choices=['openai', 'deepseek', 'claude', 'glm'])
    model_parser.add_argument('--name', help='模型名，如 deepseek-chat / gpt-4o')
    model_parser.add_argument('--base-url', help='OpenAI 兼容网关 base_url')
    model_parser.set_defaults(func=model_cmd)

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
