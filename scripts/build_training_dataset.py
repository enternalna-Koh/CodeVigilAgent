#!/usr/bin/env python3
"""
训练数据集构建器
将处理后的 3 层数据合并为最终训练数据集
"""
import json
import os
from datetime import datetime

def load_processed_data():
    """加载所有处理后的数据"""
    data = {
        'reviews': None,
        'ci_rules': None,
        'issues': None
    }

    # 加载 reviews
    reviews_file = 'data/training/reviews/analyzed_reviews.json'
    if os.path.exists(reviews_file):
        with open(reviews_file, 'r', encoding='utf-8') as f:
            data['reviews'] = json.load(f)

    # 加载 CI rules
    ci_rules_file = 'data/training/ci_rules/ci_rules_database.json'
    if os.path.exists(ci_rules_file):
        with open(ci_rules_file, 'r', encoding='utf-8') as f:
            data['ci_rules'] = json.load(f)

    # 加载 issues
    issues_file = 'data/training/issues/qa_knowledge_base.json'
    if os.path.exists(issues_file):
        with open(issues_file, 'r', encoding='utf-8') as f:
            data['issues'] = json.load(f)

    return data

def generate_review_samples(reviews_data):
    """从 review 数据生成训练样本"""
    samples = []

    if not reviews_data:
        return samples

    for pr in reviews_data.get('prs', []):
        # 为每个有意义的 review 创建样本
        for review in pr.get('reviews', []):
            sample = {
                'id': f"review_{pr['pr_number']}_{len(samples)}",
                'type': 'code_review',
                'task': 'review_code',
                'input': {
                    'pr_number': pr['pr_number'],
                    'context': 'Code review for vLLM-Ascend PR'
                },
                'output': {
                    'category': review['category'],
                    'severity': review['severity'],
                    'state': review['state'],
                    'feedback': review['body']
                },
                'metadata': {
                    'source': 'vllm-ascend',
                    'reviewer': review['reviewer']
                }
            }
            samples.append(sample)

        # 为 inline comments 创建样本
        for comment in pr.get('inline_comments', []):
            sample = {
                'id': f"comment_{pr['pr_number']}_{len(samples)}",
                'type': 'code_review',
                'task': 'review_code_line',
                'input': {
                    'pr_number': pr['pr_number'],
                    'file': comment['context']['file'],
                    'line': comment['context']['line']
                },
                'output': {
                    'category': comment['category'],
                    'severity': comment['severity'],
                    'feedback': comment['body']
                },
                'metadata': {
                    'source': 'vllm-ascend',
                    'author': comment['author']
                }
            }
            samples.append(sample)

    return samples

def generate_ci_samples(ci_rules_data):
    """从 CI 规则生成训练样本"""
    samples = []

    if not ci_rules_data:
        return samples

    # 测试要求样本
    test_req = ci_rules_data.get('test_requirements', {}).get('inferred_requirements', {})
    samples.append({
        'id': 'ci_test_requirements',
        'type': 'ci_rule',
        'task': 'check_test_requirements',
        'input': {
            'context': 'Code submission for NPU project'
        },
        'output': {
            'requirements': test_req,
            'verdict': 'Tests are required for code submission'
        },
        'metadata': {
            'source': '175 workflows analysis'
        }
    })

    # PR 质量门禁样本
    quality_gates = ci_rules_data.get('pr_quality_gates', {}).get('quality_gates', [])
    samples.append({
        'id': 'ci_pr_quality_gates',
        'type': 'ci_rule',
        'task': 'check_pr_quality',
        'input': {
            'context': 'PR quality check'
        },
        'output': {
            'quality_gates': quality_gates,
            'verdict': 'PR must pass all quality gates'
        },
        'metadata': {
            'source': '47 PR workflows'
        }
    })

    return samples

def generate_issue_samples(issues_data):
    """从 issue 数据生成训练样本"""
    samples = []

    if not issues_data:
        return samples

    qa_pairs = issues_data.get('qa_pairs', [])

    # 只选择有解决方案的 issues
    for qa in qa_pairs:
        if qa['answer'].get('has_solution'):
            sample = {
                'id': qa['id'],
                'type': 'problem_diagnosis',
                'task': 'diagnose_issue',
                'input': {
                    'title': qa['question']['title'],
                    'category': qa['question']['category'],
                    'error_codes': qa['question']['error_codes']
                },
                'output': {
                    'diagnosis': qa['answer'],
                    'status': qa['metadata']['state']
                },
                'metadata': {
                    'source': qa['repo'],
                    'issue_number': qa['issue_number'],
                    'url': qa['metadata']['url']
                }
            }
            samples.append(sample)

    return samples

def build_final_dataset():
    """构建最终训练数据集"""

    print("="*80)
    print("构建最终训练数据集")
    print("="*80)

    # 加载处理后的数据
    print("\n加载数据...")
    data = load_processed_data()

    # 生成各类训练样本
    print("\n生成训练样本...")

    review_samples = generate_review_samples(data['reviews'])
    print(f"  Review 样本: {len(review_samples)}")

    ci_samples = generate_ci_samples(data['ci_rules'])
    print(f"  CI 规则样本: {len(ci_samples)}")

    issue_samples = generate_issue_samples(data['issues'])
    print(f"  Issue 样本: {len(issue_samples)}")

    # 合并所有样本
    all_samples = review_samples + ci_samples + issue_samples
    print(f"\n总样本数: {len(all_samples)}")

    # 按类型统计
    type_counts = {}
    for sample in all_samples:
        t = sample['type']
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\n按类型统计:")
    for t, count in type_counts.items():
        print(f"  {t:20s}: {count:3d}")

    # 保存数据集
    os.makedirs('data/training/combined', exist_ok=True)

    dataset = {
        'metadata': {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'total_samples': len(all_samples),
            'type_distribution': type_counts,
            'sources': {
                'reviews': 'vllm-ascend PRs (9 PRs, 34 reviews, 44 comments)',
                'ci_rules': '175 workflows from 3 repositories',
                'issues': '210 issues from 10 repositories'
            }
        },
        'samples': all_samples
    }

    # 保存完整数据集
    output_file = 'data/training/combined/training_dataset_v1.0.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\n完整数据集已保存: {output_file}")

    # 生成 JSONL 格式（更适合训练）
    jsonl_file = 'data/training/combined/training_dataset_v1.0.jsonl'
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')

    print(f"JSONL 格式已保存: {jsonl_file}")

    # 生成统计报告
    report_file = 'data/training/combined/dataset_report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# 训练数据集报告 v1.0\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 数据规模\n\n")
        f.write(f"- 总样本数: {len(all_samples)}\n")
        f.write(f"- Review 样本: {len(review_samples)}\n")
        f.write(f"- CI 规则样本: {len(ci_samples)}\n")
        f.write(f"- Issue 样本: {len(issue_samples)}\n\n")
        f.write("## 数据来源\n\n")
        f.write("### Level 1: CI Pass 标准\n")
        f.write("- 175 workflows from 3 repositories\n")
        f.write("- 9 种类型分类\n\n")
        f.write("### Level 2: Human Review\n")
        f.write("- 9 PRs from vllm-ascend\n")
        f.write("- 34 reviews + 44 inline comments\n\n")
        f.write("### Level 3: Community Dialog\n")
        f.write("- 210 issues from 10 repositories\n")
        f.write("- 错误诊断和解决方案\n\n")
        f.write("## 训练任务类型\n\n")
        for t, count in type_counts.items():
            f.write(f"- {t}: {count} 样本\n")
        f.write("\n")

    print(f"统计报告已保存: {report_file}")

    print("\n" + "="*80)
    print("✅ 训练数据集构建完成！")
    print("="*80)

    return dataset

if __name__ == '__main__':
    build_final_dataset()
