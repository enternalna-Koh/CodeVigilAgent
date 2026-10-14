# GitHub 数据收集工具

## 用途

收集社区 Issues 和 PRs 数据，用于优化 ReviewAgent 智能体的知识库。

## 使用方法

### 方法 1：使用 Python 脚本

```bash
cd scripts
python collect_github_data.py
```

输出文件：
- `github_issues.txt` - Issue 列表
- `github_prs.txt` - PR 列表  
- `github_comments.txt` - 审核评论

### 方法 2：使用 GitHub CLI

```bash
# 安装 gh CLI: https://cli.github.com/

# 收集 vllm-ascend issues
gh issue list --repo vllm-project/vllm-ascend --state all --limit 50 > vllm_issues.txt

# 收集 torch-npu issues
gh issue list --repo Ascend/pytorch --state all --limit 50 > pytorch_issues.txt

# 收集 PR 审核评论（示例）
gh pr view 17344 --repo vllm-project/vllm-ascend --comments > pr_17344.txt
```

### 方法 3：手动收集（最简单）

直接浏览器打开：
- https://github.com/vllm-project/vllm-ascend/issues
- https://github.com/Ascend/pytorch/issues
- https://github.com/vllm-project/vllm-ascend/pulls?q=is%3Apr+is%3Aclosed

筛选重要的 Issues/PRs，复制内容发给 Claude。

## 重点关注

### Issues 数据
- ✅ 报错信息（完整堆栈）
- ✅ 环境配置（CANN/torch-npu/vLLM 版本）
- ✅ 复现步骤
- ✅ 解决方案

### PR 审核模式
- ✅ 代码规范要求
- ✅ 测试覆盖率要求
- ✅ 文档要求
- ✅ 性能验证标准
- ✅ 驳回原因

## 目标仓库

1. **vllm-project/vllm-ascend** (高优先级)
   - LLM 推理问题
   - 多卡部署经验

2. **Ascend/pytorch** (高优先级)
   - torch-npu API 兼容性
   - 算子实现问题

3. **Ascend/samples** (中优先级)
   - AscendCL 使用案例

4. **Ascend/ModelZoo-PyTorch** (中优先级)
   - 模型适配经验
