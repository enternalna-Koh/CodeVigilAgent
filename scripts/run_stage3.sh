#!/bin/bash
# Stage 3: 训练数据构建 - 主流程脚本

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    Stage 3: 训练数据构建                                       ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# 创建输出目录
mkdir -p data/training/{reviews,ci_rules,issues,combined}

# Task 1: Review 意见分析和标注
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Task 1: Review 意见分析和标注"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python scripts/analyze_reviews.py
echo ""

# Task 2: CI 规则提取
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Task 2: CI 规则提取"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python scripts/extract_ci_rules.py
echo ""

# Task 3: Issue 模式提取
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Task 3: Issue 诊断知识库构建"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python scripts/extract_issue_patterns.py
echo ""

# 汇总统计
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "数据处理完成汇总"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "生成的训练数据:"
ls -lh data/training/reviews/ 2>/dev/null | grep -v "^total" | awk '{print "  Reviews:     "$9" ("$5")"}'
ls -lh data/training/ci_rules/ 2>/dev/null | grep -v "^total" | awk '{print "  CI Rules:    "$9" ("$5")"}'
ls -lh data/training/issues/ 2>/dev/null | grep -v "^total" | awk '{print "  Issues:      "$9" ("$5")"}'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Stage 3 数据处理完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "下一步: 合并数据集并生成训练样本"
echo "  运行: python scripts/build_training_dataset.py"
echo ""
