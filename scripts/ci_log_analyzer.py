"""Heuristic analyzer for pasted Ascend / torch-npu / GitCode CI failure logs."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


# (pattern, kind, hint)
RULES: List[Tuple[str, str, str]] = [
    (r'ERROR:\s*Codecheck|codecheck\s+failed|CodeCheck', 'codecheck',
     '对照社区 Codecheck 规则；常见为命名、头文件、危险函数、版权头。'),
    (r'precision\s+(fail|failed|mismatch)|精度.*(失败|不通过)|allclose|rtol|atol', 'precision',
     '核对 golden / dtype / 随机种子；确认是否在允许误差内，排查 bf16/fp16。'),
    (r'perf(?:ormance)?\s+(fail|failed|regress)|性能.*(不达标|失败)|baseline.*ms', 'perf',
     '对比基线与 profiling；查 tiling、同步、Host-Device 拷贝、多核切分。'),
    (r'ACL_(ERROR|ERROR_CODE)|acl[A-Z]\w+\s+failed|AscendCL', 'acl',
     '查 ACL 返回码与环境（CANN 版本、驱动、设备可见性）。'),
    (r'HCCL|hccl|5070\d{2}|通信.*失败|allreduce|all_gather', 'hccl',
     '核对 RANK/WORLD_SIZE、网卡、HCCL buffer；对照本地 HCCL 案例库。'),
    (r'torch_npu|NPUExecution|npuSynchronize|OpType.*not support', 'torch_npu',
     '确认 torch_npu 与 CANN 版本匹配；查算子是否已适配或需走 CPU fallback。'),
    (r'ModuleNotFoundError|ImportError|No module named', 'python_import',
     '检查 PYTHONPATH / 安装包版本；虚拟环境是否激活。'),
    (r'CMake Error|ninja:\s*error|undefined reference|ld\.lld', 'build',
     '看编译器、交叉工具链、缺失库；社区任务注意 hidevlab / 架构宏。'),
    (r'FAILED|AssertionError|Traceback \(most recent call last\)', 'test_fail',
     '定位最后一个 FAILED 用例与断言；缩小复现命令。'),
    (r'OOM|out of memory|内存不足|Allocate.*failed', 'oom',
     '减小 batch / workspace；检查泄漏与未释放的 NPU 内存。'),
    (r'permission denied|PermissionDenied|403|401 Unauthorized', 'auth',
     '检查 Token / 镜像拉取权限 / 私有仓访问。'),
    (r'timeout|Timeout|killed|Signal 9', 'timeout',
     '拉长超时或拆分用例；排查死锁与同步等待。'),
]


def _clip(text: str, n: int = 220) -> str:
    t = re.sub(r'\s+', ' ', (text or '').strip())
    return t if len(t) <= n else t[: n - 1] + '…'


def analyze_ci_log(text: str, max_findings: int = 8) -> Dict:
    raw = text or ''
    lines = raw.splitlines()
    findings = []
    seen = set()
    for pattern, kind, hint in RULES:
        if kind in seen:
            continue
        rx = re.compile(pattern, re.I)
        for i, line in enumerate(lines):
            if rx.search(line):
                ctx = '\n'.join(lines[max(0, i - 1): min(len(lines), i + 2)])
                findings.append({
                    'kind': kind,
                    'line': i + 1,
                    'snippet': _clip(line),
                    'hint': hint,
                    'context': _clip(ctx, 320),
                })
                seen.add(kind)
                break
        if len(findings) >= max_findings:
            break

    # Extract error-like lines even if no rule matched
    error_lines = []
    for i, line in enumerate(lines):
        if re.search(r'(?i)\berror\b|FAILED|Traceback|Exception', line):
            error_lines.append({'line': i + 1, 'text': _clip(line)})
        if len(error_lines) >= 12:
            break

    summary_parts = [f['kind'] for f in findings] or ['unknown']
    return {
        'ok': True,
        'lines': len(lines),
        'chars': len(raw),
        'kinds': summary_parts,
        'findings': findings,
        'error_lines': error_lines[:8],
        'next_steps': _next_steps(findings),
    }


def _next_steps(findings: List[Dict]) -> List[str]:
    steps = [
        '把失败段前后各 30 行保留完整，便于对照官方文档。',
        '记下 CANN / torch_npu / 驱动版本与芯片型号（910B/A2/A3 等）。',
    ]
    kinds = {f['kind'] for f in findings}
    if 'precision' in kinds:
        steps.append('用固定 seed 复现，并对比 CPU golden。')
    if 'hccl' in kinds:
        steps.append('单卡能否过？再开多卡；检查 HCCL_BUFFSIZE。')
    if 'codecheck' in kinds:
        steps.append('按报错文件:行号改完再跑本地 codecheck。')
    if 'build' in kinds:
        steps.append('清理 build 目录后全量重编，确认工具链版本。')
    return steps


def format_ci_report(result: Dict) -> str:
    if not result or not result.get('ok'):
        return '未能解析 CI 日志。'
    lines = [
        '## CI 日志快析',
        '',
        f"- 规模: {result.get('lines')} 行 / {result.get('chars')} 字符",
        f"- 命中类型: {', '.join(result.get('kinds') or [])}",
        '',
    ]
    findings = result.get('findings') or []
    if findings:
        lines.append('### 命中规则')
        lines.append('')
        for f in findings:
            lines.append(f"- **{f['kind']}** (L{f['line']}): `{f['snippet']}`")
            lines.append(f"  - 建议: {f['hint']}")
        lines.append('')
    else:
        lines.append('未命中专用规则，请看下方错误行。')
        lines.append('')
    errs = result.get('error_lines') or []
    if errs:
        lines.append('### 错误行摘录')
        lines.append('')
        for e in errs:
            lines.append(f"- L{e['line']}: `{e['text']}`")
        lines.append('')
    lines.append('### 下一步')
    lines.append('')
    for s in result.get('next_steps') or []:
        lines.append(f'- {s}')
    lines.append('')
    lines.append('可用 `/export` 带走本会话；需要补丁可先贴仓库改动再 `/fix`。')
    return '\n'.join(lines)
