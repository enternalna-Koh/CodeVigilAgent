#!/usr/bin/env python3
"""
CI 规则提取器
从 175 个 workflows 中提取质量标准和规则
"""
import json
import os
from collections import defaultdict

def extract_test_requirements(workflows_by_repo):
    """提取测试要求"""
    test_rules = {
        'coverage_requirements': [],
        'test_types': defaultdict(int),
        'test_frameworks': set(),
        'nightly_tests': []
    }

    for repo, data in workflows_by_repo.items():
        test_workflows = data['workflows'].get('test', [])
        nightly_workflows = data['workflows'].get('nightly', [])

        for wf in test_workflows:
            test_rules['test_types']['unit_test'] += 1

        for wf in nightly_workflows:
            test_rules['nightly_tests'].append({
                'repo': repo,
                'workflow': wf['name'],
                'purpose': 'regression_testing'
            })

    # 推断测试要求
    test_rules['inferred_requirements'] = {
        'unit_tests': 'required' if test_rules['test_types']['unit_test'] > 0 else 'optional',
        'integration_tests': 'recommended',
        'e2e_tests': 'optional',
        'nightly_regression': 'standard_practice'
    }

    return test_rules

def extract_lint_rules(workflows_by_repo):
    """提取 Lint 规则"""
    lint_rules = {
        'lint_workflows': 0,
        'inferred_tools': [],
        'requirements': {}
    }

    for repo, data in workflows_by_repo.items():
        lint_workflows = data['workflows'].get('lint', [])
        lint_rules['lint_workflows'] += len(lint_workflows)

    # 推断 lint 工具（基于 Python 项目标准）
    if lint_rules['lint_workflows'] > 0:
        lint_rules['inferred_tools'] = ['flake8', 'black', 'mypy', 'isort']
        lint_rules['requirements'] = {
            'code_style': 'PEP8 compliance',
            'type_checking': 'recommended',
            'import_sorting': 'required',
            'line_length': 'max_88_or_100'
        }
    else:
        lint_rules['note'] = 'Lint checks may be integrated in other workflows or pre-commit hooks'

    return lint_rules

def extract_build_requirements(workflows_by_repo):
    """提取构建要求"""
    build_rules = {
        'build_workflows': 0,
        'docker_workflows': 0,
        'requirements': {}
    }

    for repo, data in workflows_by_repo.items():
        build_rules['build_workflows'] += len(data['workflows'].get('build', []))
        build_rules['docker_workflows'] += len(data['workflows'].get('docker', []))

    build_rules['requirements'] = {
        'docker': 'standard' if build_rules['docker_workflows'] > 10 else 'recommended',
        'multi_stage_build': 'recommended',
        'dependency_caching': 'best_practice',
        'incremental_build': 'optimization'
    }

    return build_rules

def extract_pr_requirements(workflows_by_repo):
    """提取 PR 质量门禁要求"""
    pr_rules = {
        'pr_workflows': 0,
        'quality_gates': []
    }

    for repo, data in workflows_by_repo.items():
        pr_rules['pr_workflows'] += len(data['workflows'].get('pr', []))

    # 推断质量门禁
    if pr_rules['pr_workflows'] > 0:
        pr_rules['quality_gates'] = [
            {'name': 'CI Pass', 'required': True, 'description': 'All CI checks must pass'},
            {'name': 'Test Coverage', 'required': True, 'description': 'Maintain or improve coverage'},
            {'name': 'Lint Clean', 'required': True, 'description': 'No lint errors'},
            {'name': 'Build Success', 'required': True, 'description': 'Code must build'},
            {'name': 'Review Approval', 'required': True, 'description': 'At least one approval'}
        ]

    return pr_rules

def generate_ci_rules_database():
    """生成完整的 CI 规则数据库"""

    # 读取 workflows 分析结果
    analysis_file = 'data/analyzed/ci_workflows_analysis.json'

    if not os.path.exists(analysis_file):
        print(f"错误: {analysis_file} 不存在")
        return

    with open(analysis_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 按仓库组织数据
    workflows_by_repo = {}
    for repo_data in data['repositories']:
        workflows_by_repo[repo_data['repository']] = repo_data

    # 提取各类规则
    ci_rules = {
        'metadata': {
            'source': '175 workflows from 3 repositories',
            'repositories': list(workflows_by_repo.keys()),
            'total_workflows': data['summary']['total_workflows']
        },
        'test_requirements': extract_test_requirements(workflows_by_repo),
        'lint_rules': extract_lint_rules(workflows_by_repo),
        'build_requirements': extract_build_requirements(workflows_by_repo),
        'pr_quality_gates': extract_pr_requirements(workflows_by_repo),
        'npu_specific': {
            'hardware_variants': ['310P', '910', '560T'],
            'testing_strategy': 'multi-hardware validation',
            'performance_baseline': 'required',
            'precision_alignment': 'CPU vs NPU comparison'
        }
    }

    # 保存结果
    os.makedirs('data/training/ci_rules', exist_ok=True)
    output_file = 'data/training/ci_rules/ci_rules_database.json'

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ci_rules, f, indent=2, ensure_ascii=False)

    print("="*80)
    print("CI 规则数据库生成完成")
    print("="*80)
    print(f"\n输出文件: {output_file}")
    print(f"\n总 workflows: {ci_rules['metadata']['total_workflows']}")
    print(f"总仓库: {len(ci_rules['metadata']['repositories'])}")

    print("\n测试要求:")
    print(f"  单元测试: {ci_rules['test_requirements']['inferred_requirements']['unit_tests']}")
    print(f"  集成测试: {ci_rules['test_requirements']['inferred_requirements']['integration_tests']}")
    print(f"  Nightly 回归: {ci_rules['test_requirements']['inferred_requirements']['nightly_regression']}")

    print("\nLint 规则:")
    if ci_rules['lint_rules']['inferred_tools']:
        print(f"  工具: {', '.join(ci_rules['lint_rules']['inferred_tools'])}")
        print(f"  代码风格: {ci_rules['lint_rules']['requirements']['code_style']}")

    print("\n构建要求:")
    print(f"  Docker: {ci_rules['build_requirements']['requirements']['docker']}")
    print(f"  多阶段构建: {ci_rules['build_requirements']['requirements']['multi_stage_build']}")

    print("\nPR 质量门禁:")
    for gate in ci_rules['pr_quality_gates']['quality_gates']:
        status = 'Required' if gate['required'] else 'Optional'
        print(f"  - {gate['name']}: {status}")

    return ci_rules

if __name__ == '__main__':
    generate_ci_rules_database()
