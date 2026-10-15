"""Load cann-op-checker / cann-inference-advisor context for CLI reviews."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.knowledge_search import PROJECT_ROOT

OPERATOR_PATH_HINTS = (
    'ops-', 'asc-devkit', 'design.md', 'op_kernel', 'op_host', 'basic_api',
)
OPERATOR_CODE_HINTS = (
    'ascendc', '__simt', '__gm__', '__ubuf__', 'tiling', 'tilingkey',
    'asc-devkit', 'getunderlyingptr',
)
INFERENCE_PATH_HINTS = (
    'vllm', 'torch_npu', 'torch-npu', 'ascendcl', 'om/', 'inference',
)
INFERENCE_CODE_HINTS = (
    'torch_npu', 'torch.npu', '.npu()', 'aclrt', 'aclinit', 'vllm_ascend',
    'vllm-ascend', 'ascendcl',
)
# Too generic alone — never decide scenario by themselves.
GENERIC_ONLY = {'cann', 'api', 'om', 'npu', 'ascend'}

MAX_CHARS = 16000
MAX_BYTES = 32 * 1024


@dataclass
class SpecialistLoad:
    scenario: Optional[str] = None
    status: str = 'none'  # none | ready | needs_context | missing_agent
    reason: str = ''
    question: str = ''
    files: List[Dict] = field(default_factory=list)
    omitted: List[str] = field(default_factory=list)
    text: str = ''
    budget: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            'scenario': self.scenario,
            'status': self.status,
            'reason': self.reason,
            'question': self.question,
            'files': self.files,
            'omitted': self.omitted,
            'budget': self.budget,
            'chars': len(self.text),
            'utf8_bytes': len(self.text.encode('utf-8')),
        }


def _roots() -> List[Path]:
    return [
        PROJECT_ROOT / '.cursor',
        PROJECT_ROOT / '.agents',
        Path.home() / '.cursor',
    ]


def _find(rel: str) -> Optional[Path]:
    for root in _roots():
        path = root / rel
        if path.is_file():
            return path
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_blob(diff_or_text: str, paths: Sequence[str]) -> str:
    return f"{' '.join(paths)}\n{diff_or_text}".lower()


def _count_hits(blob: str, path_hints: Iterable[str], code_hints: Iterable[str],
                paths: Sequence[str]) -> Tuple[int, List[str]]:
    hits: List[str] = []
    lower_paths = ' '.join(paths).lower()
    for hint in path_hints:
        if hint in lower_paths:
            hits.append(f'path:{hint}')
    for hint in code_hints:
        if hint in blob and hint not in GENERIC_ONLY:
            hits.append(f'code:{hint}')
    # dedupe preserving order
    seen = set()
    uniq = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return len(uniq), uniq


def detect_scenario(
    content: str,
    paths: Optional[Sequence[str]] = None,
    explicit: Optional[str] = None,
) -> SpecialistLoad:
    """Decide operator vs inference. Ambiguous → needs_context (do not guess)."""
    if explicit in ('operator', 'inference'):
        return SpecialistLoad(
            scenario=explicit,
            status='ready',
            reason=f'explicit --scenario {explicit}',
        )
    if explicit not in (None, ''):
        return SpecialistLoad(
            status='needs_context',
            reason=f'未知 --scenario={explicit!r}',
            question='这是算子社区任务，还是推理部署？',
        )

    paths = list(paths or [])
    # Prefer added lines only when content looks like a repo prompt with a diff block
    blob = _evidence_blob(content, paths)
    op_n, op_hits = _count_hits(blob, OPERATOR_PATH_HINTS, OPERATOR_CODE_HINTS, paths)
    inf_n, inf_hits = _count_hits(blob, INFERENCE_PATH_HINTS, INFERENCE_CODE_HINTS, paths)

    if op_n and not inf_n:
        return SpecialistLoad(
            scenario='operator',
            status='ready',
            reason='auto: ' + ', '.join(op_hits[:6]),
        )
    if inf_n and not op_n:
        return SpecialistLoad(
            scenario='inference',
            status='ready',
            reason='auto: ' + ', '.join(inf_hits[:6]),
        )
    if op_n and inf_n:
        return SpecialistLoad(
            status='needs_context',
            reason=f'混合证据 op={op_hits[:4]} inference={inf_hits[:4]}',
            question='这是算子社区任务，还是推理部署？',
        )
    return SpecialistLoad(
        status='needs_context',
        reason='无明确算子/推理证据',
        question='这是算子社区任务，还是推理部署？',
    )


def _extract_sections(text: str, section_ids: Sequence[str]) -> str:
    """Keep headings that match § markers or markdown ## titles containing tokens."""
    if not section_ids:
        return text
    # Keep whole file if short enough; otherwise keep matching ## blocks + red-line sections
    blocks = re.split(r'(?=^##\s)', text, flags=re.M)
    if len(blocks) <= 1:
        return text
    kept = [blocks[0]]  # title / intro
    tokens = [s.lower() for s in section_ids]
    for block in blocks[1:]:
        head = block.splitlines()[0].lower() if block else ''
        if any(tok in head or tok in block[:200].lower() for tok in tokens):
            kept.append(block)
        elif any(k in head for k in ('红线', '分流', '角色', '内置', '严重级别', '报告')):
            kept.append(block)
    return ''.join(kept) if len(kept) > 1 else text


def _append_budgeted(parts: List[str], piece: str, omitted: List[str], label: str) -> None:
    candidate = ''.join(parts) + piece
    if len(candidate) > MAX_CHARS or len(candidate.encode('utf-8')) > MAX_BYTES:
        omitted.append(label)
        return
    parts.append(piece)


def load_specialist_context(scenario: str) -> SpecialistLoad:
    """Load agent + required skills for a decided scenario."""
    if scenario == 'operator':
        agent_rel = 'agents/cann-op-checker.md'
        skill_specs = [
            ('skills/cann-ascendc-op-dev/SKILL.md', ['任务分型', '端到端', 'Agent 执行', '0.', '1.', '5.']),
            ('skills/cann-ascendc-op-dev/pitfalls.md', ['SIMT', 'CI', 'hidevlab', 'Basic API']),
        ]
    elif scenario == 'inference':
        agent_rel = 'agents/cann-inference-advisor.md'
        skill_specs = [
            ('skills/common-issues-patterns/SKILL.md', ['常见', '诊断', 'pattern']),
            ('skills/model-migration/SKILL.md', ['迁移', '精度']),
            ('skills/inference-optimization/SKILL.md', ['性能', 'profiling']),
        ]
    else:
        return SpecialistLoad(status='needs_context', reason=f'未知场景 {scenario}',
                              question='这是算子社区任务，还是推理部署？')

    agent_path = _find(agent_rel)
    if not agent_path:
        return SpecialistLoad(
            scenario=scenario,
            status='missing_agent',
            reason=f'未找到 {agent_rel}',
        )

    omitted: List[str] = []
    files_meta: List[Dict] = []
    parts: List[str] = []

    agent_text = agent_path.read_text(encoding='utf-8')
    files_meta.append({
        'path': str(agent_path.relative_to(PROJECT_ROOT)).replace('\\', '/'),
        'sha256': _sha256(agent_path),
        'role': 'agent',
        'status': 'loaded',
    })
    _append_budgeted(parts, f'# Specialist Agent\n{agent_text}\n', omitted, agent_rel)

    for rel, section_ids in skill_specs:
        path = _find(rel)
        if not path:
            files_meta.append({'path': rel, 'role': 'skill', 'status': 'missing'})
            omitted.append(f'missing:{rel}')
            continue
        body = _extract_sections(path.read_text(encoding='utf-8'), section_ids)
        label = str(path.relative_to(PROJECT_ROOT)).replace('\\', '/')
        before = len(parts)
        _append_budgeted(parts, f'\n# Skill: {label}\n{body}\n', omitted, label)
        files_meta.append({
            'path': label,
            'sha256': _sha256(path),
            'role': 'skill',
            'status': 'loaded' if len(parts) > before else 'omitted_budget',
        })

    text = ''.join(parts)
    return SpecialistLoad(
        scenario=scenario,
        status='ready',
        reason='loaded',
        files=files_meta,
        omitted=omitted,
        text=text,
        budget={'max_chars': MAX_CHARS, 'max_bytes': MAX_BYTES,
                'method': 'unicode_chars_and_utf8_bytes'},
    )


def resolve_specialist(
    content: str,
    paths: Optional[Sequence[str]] = None,
    explicit: Optional[str] = None,
) -> SpecialistLoad:
    decided = detect_scenario(content, paths=paths, explicit=explicit)
    if decided.status != 'ready' or not decided.scenario:
        return decided
    loaded = load_specialist_context(decided.scenario)
    loaded.reason = decided.reason
    return loaded
