#!/usr/bin/env python3
"""
使用 AI 进行代码审查
支持多种 AI 服务
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ai_adapter import get_ai_client
import json


def review_code_with_ai(code: str, config_file: str = None) -> dict:
    """
    使用 AI 审查代码

    Args:
        code: 要审查的代码
        config_file: AI 配置文件路径

    Returns:
        审查结果字典
    """
    # 获取 AI 客户端
    try:
        client = get_ai_client(config_file)
    except ValueError as e:
        return {
            'error': str(e),
            'help': '请配置 AI API: config/ai_config.json 或设置环境变量 AI_API_KEY'
        }

    # 构建审查提示
    system_prompt = """你是一个专业的代码审查专家，专注于昇腾 NPU 相关代码。

审查标准:
1. 代码正确性
2. 性能优化
3. 内存管理
4. 错误处理
5. 代码风格

请给出:
- 问题列表（如果有）
- 改进建议
- 严重程度（high/medium/low）
"""

    prompt = f"""请审查以下代码:

```
{code}
```

请以 JSON 格式返回结果:
{{
  "issues": [
    {{"type": "...", "severity": "...", "description": "...", "suggestion": "..."}}
  ],
  "summary": "..."
}}
"""

    # 调用 AI
    response = client.chat(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.3,  # 低温度，更确定的输出
        max_tokens=2000
    )

    # 尝试解析 JSON 响应
    try:
        # 提取 JSON 部分（如果 AI 返回了额外说明）
        if '```json' in response:
            json_str = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            json_str = response.split('```')[1].split('```')[0]
        else:
            json_str = response

        result = json.loads(json_str.strip())
        result['raw_response'] = response
        return result
    except:
        # 如果无法解析 JSON，返回原始响应
        return {
            'raw_response': response,
            'note': 'AI 响应无法解析为 JSON，返回原始文本'
        }


def analyze_issue_with_ai(issue_title: str, issue_body: str, config_file: str = None) -> dict:
    """
    使用 AI 分析 issue 并提供解决方案

    Args:
        issue_title: issue 标题
        issue_body: issue 内容
        config_file: AI 配置文件路径

    Returns:
        分析结果字典
    """
    try:
        client = get_ai_client(config_file)
    except ValueError as e:
        return {'error': str(e)}

    system_prompt = """你是昇腾 NPU 开发专家。

基于你的知识:
1. 分析问题根因
2. 提供解决方案
3. 推荐相关资源
"""

    prompt = f"""Issue 分析:

标题: {issue_title}

内容:
{issue_body[:1000]}  # 限制长度

请提供:
1. 问题类型分类
2. 根因分析
3. 解决方案建议
4. 相关的文档或 issue 链接（如果知道）

以 JSON 格式返回。
"""

    response = client.chat(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.5,
        max_tokens=1500
    )

    return {'analysis': response}


def batch_analyze_reviews(reviews_file: str, config_file: str = None):
    """
    批量分析已收集的 reviews，提取审查模式

    Args:
        reviews_file: reviews JSON 文件路径
        config_file: AI 配置文件路径
    """
    if not os.path.exists(reviews_file):
        print(f"Error: {reviews_file} not found")
        return

    with open(reviews_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    try:
        client = get_ai_client(config_file)
    except ValueError as e:
        print(f"Error: {e}")
        return

    print("分析 review 模式...")

    # 收集所有 review 内容
    all_reviews = []
    for pr in data:
        if isinstance(pr, dict):
            reviews = pr.get('reviews', [])
            comments = pr.get('comments', [])

            for review in reviews:
                if isinstance(review, dict) and review.get('body'):
                    all_reviews.append(review['body'])

            for comment in comments:
                if isinstance(comment, dict) and comment.get('body'):
                    all_reviews.append(comment['body'])

    # 只分析前 20 个（避免 token 超限）
    sample_reviews = all_reviews[:20]

    system_prompt = """你是代码审查专家。分析这些真实的 review 意见，找出常见模式。"""

    prompt = f"""这里有 {len(sample_reviews)} 条真实的代码审查意见:

{chr(10).join([f"{i+1}. {r[:100]}" for i, r in enumerate(sample_reviews)])}

请总结:
1. 常见的审查关注点（top 5）
2. 审查标准和模式
3. 高频问题类型

以结构化格式返回。
"""

    response = client.chat(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.4,
        max_tokens=2000
    )

    print("\n" + "="*80)
    print("Review 模式分析结果")
    print("="*80)
    print(response)

    # 保存结果
    output_file = 'data/analyzed/ai_review_patterns.txt'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(response)

    print(f"\n结果已保存: {output_file}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AI-powered code review')
    parser.add_argument('--config', help='AI config file', default='config/ai_config.json')
    parser.add_argument('--mode', choices=['review', 'issue', 'batch'], default='review')
    parser.add_argument('--file', help='Input file')

    args = parser.parse_args()

    if args.mode == 'review':
        # 示例：审查代码
        sample_code = """
def process_data(data):
    result = []
    for i in range(len(data)):
        result.append(data[i] * 2)
    return result
"""
        result = review_code_with_ai(sample_code, args.config)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.mode == 'batch':
        # 批量分析 reviews
        reviews_file = args.file or 'data/pr_reviews/vllm-project_vllm-ascend_reviews.json'
        batch_analyze_reviews(reviews_file, args.config)

    else:
        print("Specify mode: --mode review|issue|batch")
