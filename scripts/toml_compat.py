"""TOML loader compatible with Python 3.10+ (tomllib is 3.11+).

Supports the Codex agent files in this repo:
  name = "..."
  description = "..."
  developer_instructions = '''...'''
"""
from __future__ import annotations

import re
from typing import Any, Dict


def loads(text: str) -> Dict[str, Any]:
    try:
        import tomllib  # type: ignore
        return tomllib.loads(text)
    except ModuleNotFoundError:
        pass
    try:
        import tomli  # type: ignore
        return tomli.loads(text)
    except ModuleNotFoundError:
        pass
    return _loads_simple(text)


_KEY_RE = re.compile(
    r'^(?P<key>[A-Za-z_][\w-]*)\s*=\s*(?P<rest>.+)$',
    re.M,
)


def _loads_simple(text: str) -> Dict[str, Any]:
    """Minimal parser for flat string / triple-quoted fields used by Codex agents."""
    result: Dict[str, Any] = {}
    i = 0
    lines = text.splitlines()
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            i += 1
            continue
        match = _KEY_RE.match(stripped)
        if not match:
            raise ValueError(f'TOML parse error near line {i + 1}: {line!r}')
        key = match.group('key')
        rest = match.group('rest').strip()
        if rest.startswith("'''") or rest.startswith('"""'):
            quote = rest[:3]
            body = rest[3:]
            if body.endswith(quote) and len(rest) > 6:
                result[key] = body[:-3]
                i += 1
                continue
            chunks = [body]
            i += 1
            while i < len(lines):
                if lines[i].rstrip().endswith(quote):
                    chunks.append(lines[i].rstrip()[:-3])
                    i += 1
                    break
                chunks.append(lines[i])
                i += 1
            else:
                raise ValueError(f'Unterminated multiline string for {key}')
            # TOML multiline: leading newline after opening quotes is stripped
            value = '\n'.join(chunks)
            if value.startswith('\n'):
                value = value[1:]
            result[key] = value
            continue
        if (rest.startswith('"') and rest.endswith('"')) or (
            rest.startswith("'") and rest.endswith("'")
        ):
            result[key] = rest[1:-1]
            i += 1
            continue
        raise ValueError(f'Unsupported TOML value for {key}: {rest!r}')
    return result
