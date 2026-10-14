#!/bin/bash

# CI 配置收集脚本
# 收集 GitHub Actions, GitLab CI, Jenkins 等配置文件

REPOS=(
    "Ascend/pytorch"
    "vllm-project/vllm-ascend"
    "Ascend/sglang"
    "Ascend/ModelZoo-PyTorch"
    "Ascend/samples"
    "Ascend/AscendSpeed"
    "Ascend/tools"
)

echo "========================================"
echo "收集 CI 配置文件"
echo "========================================"

mkdir -p data/ci_configs

for repo in "${REPOS[@]}"; do
    owner=$(echo $repo | cut -d'/' -f1)
    name=$(echo $repo | cut -d'/' -f2)
    
    echo ""
    echo "收集 $repo CI 配置..."
    
    # GitHub Actions workflows
    curl -s "https://api.github.com/repos/$repo/contents/.github/workflows" \
        -o "data/ci_configs/${owner}_${name}_workflows.json"
    
    # 检查是否有 workflows
    if grep -q "name" "data/ci_configs/${owner}_${name}_workflows.json" 2>/dev/null; then
        echo "  OK: GitHub Actions workflows found"
    else
        echo "  --: No GitHub Actions"
    fi
    
    sleep 2
    
    # GitLab CI
    curl -s "https://api.github.com/repos/$repo/contents/.gitlab-ci.yml" \
        -o "data/ci_configs/${owner}_${name}_gitlab-ci.json"
    
    # Jenkins
    curl -s "https://api.github.com/repos/$repo/contents/Jenkinsfile" \
        -o "data/ci_configs/${owner}_${name}_jenkinsfile.json"
    
    sleep 1
done

echo ""
echo "========================================"
echo "CI 配置收集完成"
echo "========================================"
ls -lh data/ci_configs/ | tail -20

