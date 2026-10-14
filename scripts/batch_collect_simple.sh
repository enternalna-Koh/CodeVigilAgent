#!/bin/bash

# 要收集的新仓库列表
REPOS=(
    "Ascend/mindspore"
    "Ascend/ModelZoo-PyTorch"
    "Ascend/AscendSpeed"
    "Ascend/samples"
    "Ascend/tools"
    "Ascend/ascend-pytorch-crowdsource-op"
)

echo "========================================"
echo "批量收集 Ascend 社区数据"
echo "========================================"

for repo in "${REPOS[@]}"; do
    owner=$(echo $repo | cut -d'/' -f1)
    name=$(echo $repo | cut -d'/' -f2)
    
    echo ""
    echo "收集 $repo..."
    
    # Issues
    curl -s "https://api.github.com/repos/$repo/issues?state=all&per_page=100" \
        -o "data/raw/${owner}_${name}_issues.json"
    
    if [ -f "data/raw/${owner}_${name}_issues.json" ]; then
        echo "  OK: Issues saved"
    fi
    
    sleep 2
    
    # PRs
    curl -s "https://api.github.com/repos/$repo/pulls?state=all&per_page=100" \
        -o "data/raw/${owner}_${name}_prs.json"
    
    if [ -f "data/raw/${owner}_${name}_prs.json" ]; then
        echo "  OK: PRs saved"
    fi
    
    sleep 2
done

echo ""
echo "========================================"
echo "收集完成！"
echo "========================================"
ls -lh data/raw/ | tail -20

