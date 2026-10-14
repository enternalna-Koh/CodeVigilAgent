#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReviewAgent 对话式智能体
支持自然语言交互，自动理解用户意图并执行相应操作
"""
import sys
import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# 设置编码和行缓冲（Windows）
if sys.platform == 'win32':
    import io
    # 只在需要时重新包装 stdout/stderr
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding.lower() != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from scripts.smart_reviewer import SmartReviewer
    from scripts.ai_adapter import AIClient, get_ai_client
except ImportError:
    print("[ERROR] 导入失败，请确保在项目根目录运行")
    sys.exit(1)


class ConversationalAgent:
    """对话式智能体"""

    def __init__(self):
        """初始化对话智能体"""
        self.ai_client = None
        self.reviewer = None
        self.conversation_history = []
        self.config_file = 'config/ai_config.json'

        # 检查配置
        self.check_and_setup()

    def check_and_setup(self):
        """检查并设置 AI 配置"""
        if not os.path.exists(self.config_file):
            print("\n[WELCOME] 欢迎使用 ReviewAgent 对话式智能体！", flush=True)
            print("=" * 70, flush=True)
            print("\n首次使用需要配置 AI 服务。", flush=True)
            self.interactive_setup()
        else:
            try:
                self.ai_client = get_ai_client(self.config_file)
                self.reviewer = SmartReviewer(self.config_file)
                print("\n[INFO] AI 配置已加载", flush=True)
            except Exception as e:
                print(f"\n[ERROR] 配置加载失败: {e}", flush=True)
                print("[INFO] 重新配置...", flush=True)
                self.interactive_setup()

    def interactive_setup(self):
        """交互式配置向导"""
        print("\n" + "=" * 70)
        print("AI 配置向导")
        print("=" * 70)

        print("\n支持的 AI 服务:")
        print("  1. DeepSeek (推荐，性价比最高)")
        print("  2. OpenAI (GPT-4, GPT-3.5)")
        print("  3. Claude (Anthropic)")
        print("  4. GLM (智谱清言)")

        while True:
            choice = input("\n请选择 AI 服务 (1-4): ").strip()

            if choice == '1':
                provider = 'deepseek'
                model = 'deepseek-chat'
                print("\n[选择] DeepSeek")
                break
            elif choice == '2':
                provider = 'openai'
                model = 'gpt-4'
                print("\n[选择] OpenAI")
                break
            elif choice == '3':
                provider = 'claude'
                model = 'claude-3-opus-20240229'
                print("\n[选择] Claude")
                break
            elif choice == '4':
                provider = 'glm'
                model = 'glm-4'
                print("\n[选择] GLM")
                break
            else:
                print("[ERROR] 无效选择，请输入 1-4")

        print(f"\n请输入你的 {provider.upper()} API Key:")
        api_key = input("API Key: ").strip()

        # 保存配置
        config = {
            "provider": provider,
            "api_key": api_key,
            "model": model
        }

        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print("\n[OK] 配置已保存！")

        # 初始化 AI 客户端
        try:
            self.ai_client = get_ai_client(self.config_file)
            self.reviewer = SmartReviewer(self.config_file)
            print("[OK] AI 服务已连接")
        except Exception as e:
            print(f"[ERROR] 连接失败: {e}")
            sys.exit(1)

    def understand_intent(self, user_input: str) -> Dict:
        """
        理解用户意图

        Returns:
            {
                'intent': 'review_code' | 'review_pr' | 'review_issue' | 'fetch_and_review' | 'chat' | 'help',
                'entities': {...},
                'confidence': 0.0-1.0
            }
        """
        user_input_lower = user_input.lower()

        # 检测 URL
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, user_input)

        # 意图识别
        intents = {
            'review_code': ['审查', 'review', '检查', 'check', '看看', '分析'],
            'review_pr': ['pr', 'pull request', 'merge request'],
            'review_issue': ['issue', 'bug', '问题', '错误'],
            'fetch_and_review': ['链接', 'url', 'github', 'gitee'],
            'help': ['帮助', 'help', '怎么用', 'how'],
            'config': ['配置', 'config', '设置', 'api key'],
        }

        detected_intent = 'chat'  # 默认聊天
        confidence = 0.5

        for intent, keywords in intents.items():
            for keyword in keywords:
                if keyword in user_input_lower:
                    detected_intent = intent
                    confidence = 0.8
                    break

        # 如果有 URL，通常是要审查
        if urls:
            detected_intent = 'fetch_and_review'
            confidence = 0.9

        # 如果包含代码块，通常是要审查代码
        if '```' in user_input or 'def ' in user_input or 'class ' in user_input:
            detected_intent = 'review_code'
            confidence = 0.85

        return {
            'intent': detected_intent,
            'entities': {
                'urls': urls,
                'has_code': '```' in user_input or 'def ' in user_input,
                'text': user_input
            },
            'confidence': confidence
        }

    def extract_code_from_message(self, text: str) -> str:
        """从消息中提取代码"""
        # 提取代码块
        code_blocks = re.findall(r'```(?:python|py)?\n(.*?)\n```', text, re.DOTALL)
        if code_blocks:
            return '\n\n'.join(code_blocks)

        # 如果没有代码块标记，但有代码特征
        if 'def ' in text or 'class ' in text:
            return text

        return text

    def fetch_url_content(self, url: str) -> Optional[str]:
        """获取 URL 内容"""
        try:
            import urllib.request

            # 添加 headers
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')
                return content[:5000]  # 限制长度
        except Exception as e:
            return None

    def handle_review_code(self, content: str):
        """处理代码审查"""
        print("\n[ACTION] 执行代码审查...")

        code = self.extract_code_from_message(content)

        report = self.reviewer.review(code)
        self.reviewer.print_report(report)

    def handle_fetch_and_review(self, urls: List[str]):
        """处理 URL 获取和审查"""
        print(f"\n[ACTION] 获取并审查 URL 内容...")

        for url in urls:
            print(f"\n[FETCH] {url}")
            content = self.fetch_url_content(url)

            if content:
                print("[OK] 内容已获取")

                # 使用 AI 理解内容
                prompt = f"""分析这个 URL 的内容并总结:

URL: {url}
内容: {content[:1000]}...

这是什么类型的内容? (PR/Issue/Code/其他)
主要内容是什么?
"""

                analysis = self.ai_client.chat(prompt, temperature=0.3, max_tokens=300)
                print(f"\n[ANALYSIS]\n{analysis}")

                # 执行审查
                report = self.reviewer.review(content)
                self.reviewer.print_report(report)
            else:
                print("[ERROR] 无法获取内容")

    def handle_chat(self, user_input: str):
        """处理普通聊天"""
        # 构建上下文
        messages = []

        # 系统提示
        system_prompt = """你是 ReviewAgent，一个专业的代码审查助手。

你的能力:
1. 审查代码（支持文件、文本、URL）
2. 分析 PR 和 Issue
3. 回答昇腾 NPU 相关问题
4. 提供编程建议

请简洁、专业地回答用户问题。
"""

        messages.append({"role": "system", "content": system_prompt})

        # 添加历史记录（最近5轮）
        for msg in self.conversation_history[-5:]:
            messages.append(msg)

        # 当前消息
        messages.append({"role": "user", "content": user_input})

        # 调用 AI
        response = self.ai_client.chat_with_history(messages, temperature=0.7, max_tokens=500)

        print(f"\n[AGENT] {response}")

        # 保存到历史
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

    def handle_help(self):
        """显示帮助"""
        help_text = """
╔═══════════════════════════════════════════════════════════════╗
║                  ReviewAgent 使用指南                          ║
╚═══════════════════════════════════════════════════════════════╝

支持的操作:

1. 审查代码
   - 直接粘贴代码
   - 发送文件路径
   - 使用代码块 ```python ... ```

2. 审查 PR/Issue
   - 发送 GitHub/Gitee URL
   - 粘贴 PR/Issue 内容

3. 自然对话
   - 问技术问题
   - 咨询编程建议
   - 讨论昇腾 NPU 相关

4. 命令
   - help - 显示此帮助
   - config - 重新配置 AI
   - clear - 清除对话历史
   - exit/quit - 退出

示例:
  > 审查这段代码: def foo(): return 1/0
  > https://github.com/user/repo/pull/123
  > 昇腾 NPU 和 CUDA 有什么区别？
  > help
"""
        print(help_text)

    def process_message(self, user_input: str):
        """处理用户消息"""
        user_input = user_input.strip()

        if not user_input:
            return

        # 特殊命令
        if user_input.lower() in ['exit', 'quit', 'q']:
            print("\n[INFO] 再见！")
            sys.exit(0)

        if user_input.lower() == 'help':
            self.handle_help()
            return

        if user_input.lower() == 'clear':
            self.conversation_history = []
            print("\n[INFO] 对话历史已清除")
            return

        if user_input.lower() == 'config':
            self.interactive_setup()
            return

        # 理解意图
        intent_result = self.understand_intent(user_input)
        intent = intent_result['intent']
        entities = intent_result['entities']

        print(f"\n[INTENT] 检测到意图: {intent} (置信度: {intent_result['confidence']:.0%})")

        # 执行相应操作
        try:
            if intent == 'review_code':
                self.handle_review_code(user_input)

            elif intent == 'fetch_and_review':
                if entities['urls']:
                    self.handle_fetch_and_review(entities['urls'])
                else:
                    print("[ERROR] 未检测到有效的 URL")

            elif intent == 'help':
                self.handle_help()

            else:
                # 默认聊天
                self.handle_chat(user_input)

        except Exception as e:
            print(f"\n[ERROR] 处理失败: {e}")
            print("[INFO] 尝试使用 'help' 查看帮助")

    def run(self):
        """运行对话循环"""
        print("\n" + "=" * 70, flush=True)
        print("ReviewAgent 对话式智能体 v1.0", flush=True)
        print("=" * 70, flush=True)
        print("\n输入 'help' 查看使用指南", flush=True)
        print("输入 'exit' 退出\n", flush=True)

        while True:
            try:
                user_input = input("\n[YOU] > ").strip()

                if not user_input:
                    continue

                self.process_message(user_input)

            except KeyboardInterrupt:
                print("\n\n[INFO] 使用 'exit' 退出")
            except EOFError:
                break


def main():
    """主函数"""
    agent = ConversationalAgent()
    agent.run()


if __name__ == '__main__':
    main()
