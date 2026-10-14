#!/bin/bash

# 收集 PR Review 数据 (修复版)
# 使用 curl 收集 PR review comments

REPOS=(
    "Ascend/pytorch"
    "vllm-project/vllm-ascend"
    "Ascend/sglang"
)

echo "========================================"
echo "收集 PR Review 数据"
echo "========================================"

mkdir -p data/pr_reviews

for repo in "${REPOS[@]}"; do
    owner=$(echo $repo | cut -d'/' -f1)
    name=$(echo $repo | cut -d'/' -f2)
    
    echo ""
    echo "处理 $repo..."
    
    # 读取已收集的 PRs
    prs_file="data/raw/${owner}_${name}_prs.json"
    
    if [ ! -f "$prs_file" ]; then
        echo "  跳过: PRs 数据不存在"
        continue
    fi
    
    # 提取前 10 个 merged PRs 的编号
    pr_numbers=$(cat "$prs_file" | python -c "
import json, sys
data = json.load(sys.stdin)
merged = [pr['number'] for pr in data if pr.get('merged_at')][:10]
print(' '.join(map(str, merged)))
" 2>/dev/null)
    
    if [ -z "$pr_numbers" ]; then
        echo "  没有找到 merged PRs"
        continue
    fi
    
    echo "  找到 PRs: $pr_numbers"
    echo "  开始收集 review comments..."
    
    # 创建输出数组
    echo "[" > "data/pr_reviews/${owner}_${name}_reviews.json"
    
    first=true
    count=0
    
    for pr_num in $pr_numbers; do
        echo "    PR #$pr_num..."
        
        # 获取 PR reviews
        reviews=$(curl -s "https://api.github.com/repos/$repo/pulls/$pr_num/reviews" 2>/dev/null)
        
        # 获取 review comments
        comments=$(curl -s "https://api.github.com/repos/$repo/pulls/$pr_num/comments" 2>/dev/null)
        
        # 检查是否有数据
        review_count=$(echo "$reviews" | python -c "import json, sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        comment_count=$(echo "$comments" | python -c "import json, sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        
        if [ "$review_count" != "0" ] || [ "$comment_count" != "0" ]; then
            if [ "$first" = false ]; then
                echo "," >> "data/pr_reviews/${owner}_${name}_reviews.json"
            fi
            first=false
            
            echo "{" >> "data/pr_reviews/${owner}_${name}_reviews.json"
            echo "  \"pr_number\": $pr_num," >> "data/pr_reviews/${owner}_${name}_reviews.json"
            echo "  \"reviews\": $reviews," >> "data/pr_reviews/${owner}_${name}_reviews.json"
            echo "  \"comments\": $comments" >> "data/pr_reviews/${owner}_${name}_reviews.json"
            echo "}" >> "data/pr_reviews/${owner}_${name}_reviews.json"
            
            count=$((count + 1))
            echo "      -> $review_count reviews, $comment_count comments"
        fi
        
        sleep 2  # API rate limit
    done
    
    echo "]" >> "data/pr_reviews/${owner}_${name}_reviews.json"
    echo "  OK: 已保存 $count 个 PR reviews"
done

echo ""
echo "========================================"
echo "收集完成"
echo "========================================"
ls -lh data/pr_reviews/

