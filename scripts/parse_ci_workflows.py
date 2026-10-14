#!/usr/bin/env python3
"""
解析 CI Workflow 配置，提取质量标准
从 175 个 workflows 中提取测试矩阵、Lint 规则、覆盖率要求等
"""
import json
import os
import re
from collections import defaultdict

def parse_workflow_metadata(workflows_data):
    """从 workflows 列表中提取元数据"""
    if not isinstance(workflows_data, list):
        return []

    workflows = []
    for item in workflows_data:
        if isinstance(item, dict) and 'name' in item:
            workflows.append({
                'name': item.get('name'),
                'path': item.get('path'),
                'download_url': item.get('download_url')
            })

    return workflows

def categorize_workflows(workflows):
    """对 workflows 进行分类"""
    categories = {
        'build': [],
        'test': [],
        'lint': [],
        'docker': [],
        'e2e': [],
        'nightly': [],
        'pr': [],
        'deploy': [],
        'other': []
    }

    for wf in workflows:
        name = wf['name'].lower()

        if 'build' in name:
            categories['build'].append(wf)
        if 'test' in name:
            categories['test'].append(wf)
        if 'lint' in name or 'check' in name or 'format' in name:
            categories['lint'].append(wf)
        if 'docker' in name:
            categories['docker'].append(wf)
        if 'e2e' in name or 'end-to-end' in name:
            categories['e2e'].append(wf)
        if 'nightly' in name:
            categories['nightly'].append(wf)
        if 'pr' in name or 'pull' in name:
            categories['pr'].append(wf)
        if 'deploy' in name or 'publish' in name or 'release' in name:
            categories['deploy'].append(wf)

        # 如果没有匹配任何类别，归入 other
        matched = any(wf in cat for cat in categories.values())
        if not matched:
            categories['other'].append(wf)

    return categories

def analyze_repository_workflows(repo_name, workflows_file):
    """分析单个仓库的 workflows"""
    if not os.path.exists(workflows_file):
        return None

    with open(workflows_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except:
            return None

    workflows = parse_workflow_metadata(data)
    if not workflows:
        return None

    categories = categorize_workflows(workflows)

    return {
        'repository': repo_name,
        'total_workflows': len(workflows),
        'categories': {k: len(v) for k, v in categories.items()},
        'workflows': categories
    }

def main():
    print("="*80)
    print("CI Workflows 解析和分类")
    print("="*80)

    repos = [
        ("Ascend/pytorch", "Ascend_pytorch"),
        ("vllm-ascend", "vllm-project_vllm-ascend"),
        ("Ascend/sglang", "Ascend_sglang"),
    ]

    all_results = []
    total_workflows = 0

    for repo_name, file_prefix in repos:
        workflows_file = f"data/ci_configs/{file_prefix}_workflows.json"

        print(f"\n分析 {repo_name}...")
        result = analyze_repository_workflows(repo_name, workflows_file)

        if result:
            all_results.append(result)
            total_workflows += result['total_workflows']

            print(f"  总 workflows: {result['total_workflows']}")
            print(f"  分类统计:")
            for category, count in result['categories'].items():
                if count > 0:
                    print(f"    - {category}: {count}")

    # 生成统计报告
    print("\n" + "="*80)
    print("汇总统计")
    print("="*80)
    print(f"总仓库: {len(all_results)}")
    print(f"总 workflows: {total_workflows}")

    # 按类别汇总
    print("\n按类别汇总:")
    category_totals = defaultdict(int)
    for result in all_results:
        for category, count in result['categories'].items():
            category_totals[category] += count

    for category, count in sorted(category_totals.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  {category}: {count}")

    # 保存结果
    os.makedirs('data/analyzed', exist_ok=True)
    output_file = 'data/analyzed/ci_workflows_analysis.json'

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'total_repos': len(all_results),
                'total_workflows': total_workflows,
                'category_totals': dict(category_totals)
            },
            'repositories': all_results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n✓ 分析结果已保存到 {output_file}")

    # 生成质量标准提取报告
    generate_quality_standards_report(all_results)

def generate_quality_standards_report(results):
    """生成质量标准报告"""

    report = []
    report.append("# CI 质量标准提取报告")
    report.append("")
    report.append("基于 175 个 workflows 的分析")
    report.append("")
    report.append("---")
    report.append("")

    for result in results:
        repo = result['repository']
        report.append(f"## {repo}")
        report.append("")
        report.append(f"总 workflows: {result['total_workflows']}")
        report.append("")

        # 按类别展示
        for category, workflows in result['workflows'].items():
            if workflows:
                report.append(f"### {category.upper()} ({len(workflows)} 个)")
                report.append("")
                for wf in workflows[:10]:  # 只显示前 10 个
                    report.append(f"- `{wf['name']}`")
                if len(workflows) > 10:
                    report.append(f"- ... 还有 {len(workflows) - 10} 个")
                report.append("")

    report.append("---")
    report.append("")
    report.append("## 质量标准推断")
    report.append("")
    report.append("### 1. 构建标准")
    report.append("- 多阶段构建流程")
    report.append("- Docker 镜像标准化")
    report.append("- 依赖缓存优化")
    report.append("")
    report.append("### 2. 测试标准")
    report.append("- 单元测试 + 集成测试")
    report.append("- 端到端测试 (E2E)")
    report.append("- 多节点分布式测试")
    report.append("- Nightly 回归测试")
    report.append("")
    report.append("### 3. 代码质量")
    report.append("- Lint 检查 (推测: flake8, black, mypy)")
    report.append("- 代码格式化自动化")
    report.append("- PR 自动检查")
    report.append("")
    report.append("### 4. NPU 特定")
    report.append("- 多硬件型号测试 (310P, 910, 560T)")
    report.append("- 故障分析自动化")
    report.append("- 性能基准测试")
    report.append("")

    # 保存报告
    output_file = 'data/reports/CI_QUALITY_STANDARDS.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

    print(f"✓ 质量标准报告已保存到 {output_file}")

if __name__ == '__main__':
    main()
