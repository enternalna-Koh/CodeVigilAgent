"""Utilities for collecting a safe, compact Git repository context."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional


class RepoContextError(RuntimeError):
    """Raised when the requested directory is not a usable Git repository."""


def _run_git(repo: Path, *args: str, max_output: Optional[int] = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise RepoContextError(f"无法执行 git: {exc}") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RepoContextError(message or "git 命令执行失败")

    output = result.stdout
    return output if max_output is None else output[:max_output]


def is_git_repo(path: Path) -> bool:
    try:
        _run_git(path, "rev-parse", "--show-toplevel")
        return True
    except RepoContextError:
        return False


def collect_repo_context(
    path: str = ".",
    staged: bool = False,
    include_untracked: bool = True,
    max_diff_chars: int = 50000,
) -> Dict:
    """Collect repository metadata and a bounded diff for an Agent run."""
    repo = Path(path).resolve()
    if not is_git_repo(repo):
        raise RepoContextError(f"不是 Git 仓库: {repo}")

    root = Path(_run_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
    branch = _run_git(root, "branch", "--show-current").strip() or "(detached)"
    status = _run_git(root, "status", "--short", max_output=4000)
    diff_args = ["diff", "--no-ext-diff", "--unified=3"]
    if staged:
        diff_args.insert(1, "--cached")
    full_diff = _run_git(root, *diff_args)
    diff = full_diff[:max_diff_chars]

    file_args = ["diff", "--name-only"]
    if staged:
        file_args.append("--cached")
    changed_files: List[str] = _run_git(root, *file_args).splitlines()
    untracked = [line[3:].strip().strip('"') for line in status.splitlines() if line.startswith('?? ')]

    return {
        "root": str(root),
        "branch": branch,
        "staged": staged,
        "status": status,
        "changed_files": changed_files,
        "diff": diff,
        "diff_truncated": len(full_diff) > max_diff_chars,
        "diff_total_chars": len(full_diff),
        "untracked_files": untracked,
    }


def format_repo_prompt(context: Dict) -> str:
    """Turn repository context into a bounded prompt section."""
    files = "\n".join(f"- {name}" for name in context.get("changed_files", [])) or "(无工作区变更)"
    scope = ""
    if context.get("diff_truncated"):
        scope = (
            f"\n【审查范围警告】diff 已被截断：下面只包含完整 diff {context.get('diff_total_chars', '?')} 字符中的前 "
            f"{len(context.get('diff', ''))} 字符，末尾可能在文件或代码行中间被切断，后面的改动没有提供给你。"
            "只能对已提供部分下结论；不得把未提供的改动当作没有问题，"
            "也不得因为已看到的部分没有问题就给出 approve。\n"
        )
    return f"""Git PR diff 审查任务。只根据下面的 diff 指出可证实的问题；不要把状态列表当成代码内容。
diff 中以 "-" 开头的行是已删除的代码，只有 "+" 开头的行才是改动后的代码；不要把删除行当作现有问题。{scope}
仓库上下文:
- 根目录: {context.get('root', '')}
- 分支: {context.get('branch', '')}
- 检查范围: {'暂存区' if context.get('staged') else '工作区'}
- 变更文件:
{files}

Git 状态:
{context.get('status', '(clean)') or '(clean)'}

Git diff:
{context.get('diff', '(无 diff)') or '(无 diff)'}

未跟踪文件仅列在状态中，尚未纳入 diff，也未经过审查。
"""
