"""Minimal MCP stdio client (tools only) for ReviewAgent.

Default built-in server: ascend-doc (npx -y ascend-doc-mcp@latest),
matching Ascend agent-skills docs/doc-mcp/README.md.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.agent_home import ensure_home, home_dir
from scripts.knowledge_search import PROJECT_ROOT

BUILTIN_SERVERS = {
    'ascend-doc': {
        'command': 'npx',
        'args': ['-y', 'ascend-doc-mcp@latest'],
        'description': '昇腾官方只读文档 MCP（ascend-doc-mcp）',
    },
}


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    disabled: bool = False
    description: str = ''

    def as_dict(self) -> Dict:
        return {
            'name': self.name,
            'command': self.command,
            'args': self.args,
            'disabled': self.disabled,
            'description': self.description,
            'builtin': self.name in BUILTIN_SERVERS,
        }


def _parse_servers_block(raw: Dict) -> Dict[str, Dict]:
    if not isinstance(raw, dict):
        return {}
    return raw.get('mcpServers') or raw.get('mcp') or raw.get('servers') or {}


def _load_json_file(path: Path) -> Dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding='utf-8')
    # Allow JSONC-ish line comments
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith('//'):
            continue
        lines.append(line)
    try:
        data = json.loads('\n'.join(lines))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def config_paths() -> List[Path]:
    ensure_home()
    return [
        PROJECT_ROOT / '.mcp.json',
        PROJECT_ROOT / 'mcp.json',
        Path(home_dir()) / 'mcp.json',
    ]


def load_mcp_config(extra: Optional[Dict] = None) -> Dict[str, McpServerConfig]:
    """Merge project → user → builtin defaults (project/user override builtin)."""
    merged: Dict[str, Dict] = {k: dict(v) for k, v in BUILTIN_SERVERS.items()}
    for path in reversed(config_paths()):
        block = _parse_servers_block(_load_json_file(path))
        for name, cfg in block.items():
            if not isinstance(cfg, dict):
                continue
            merged[name] = {**merged.get(name, {}), **cfg}
    if extra:
        for name, cfg in _parse_servers_block(extra).items():
            if isinstance(cfg, dict):
                merged[name] = {**merged.get(name, {}), **cfg}

    out: Dict[str, McpServerConfig] = {}
    for name, cfg in merged.items():
        command = cfg.get('command')
        args = cfg.get('args') or []
        # OpenCode-style: command as list
        if isinstance(command, list) and command:
            args = list(command[1:]) + list(args)
            command = command[0]
        if not command:
            continue
        if not isinstance(args, list):
            args = [str(args)]
        env = cfg.get('env') if isinstance(cfg.get('env'), dict) else {}
        out[name] = McpServerConfig(
            name=name,
            command=str(command),
            args=[str(a) for a in args],
            env={str(k): str(v) for k, v in env.items()},
            disabled=bool(cfg.get('disabled') or cfg.get('enabled') is False),
            description=str(cfg.get('description') or BUILTIN_SERVERS.get(name, {}).get('description') or ''),
        )
    return out


def ensure_default_user_mcp() -> Path:
    """Write ~/.reviewagent/mcp.json with ascend-doc if missing."""
    ensure_home()
    path = Path(home_dir()) / 'mcp.json'
    if path.is_file():
        return path
    payload = {
        'mcpServers': {
            'ascend-doc': {
                'command': 'npx',
                'args': ['-y', 'ascend-doc-mcp@latest'],
                'description': '昇腾官方只读文档 MCP',
            }
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


class McpSession:
    """One stdio MCP server process (JSON-RPC 2.0, Content-Length framing preferred)."""

    def __init__(self, config: McpServerConfig):
        self.config = config
        self.proc: Optional[subprocess.Popen] = None
        self._id = 0
        self._lock = threading.Lock()
        self._reader_buf = b''
        self.tools: List[Dict] = []
        self.last_error: Optional[str] = None

    def start(self, timeout: float = 45.0) -> bool:
        if self.config.disabled:
            self.last_error = 'server disabled'
            return False
        cmd = [self.config.command, *self.config.args]
        if self.config.command == 'npx' and not shutil.which('npx'):
            self.last_error = '未找到 npx（需 Node.js ≥ 22 以运行 ascend-doc-mcp）'
            return False
        env = os.environ.copy()
        env.update(self.config.env)
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
        except OSError as exc:
            self.last_error = f'启动失败: {exc}'
            return False
        try:
            self._request('initialize', {
                'protocolVersion': '2024-11-05',
                'capabilities': {},
                'clientInfo': {'name': 'reviewagent', 'version': '1.8.0'},
            }, timeout=timeout)
            # notifications/initialized (no id)
            self._notify('notifications/initialized', {})
            listed = self._request('tools/list', {}, timeout=timeout)
            tools = (listed or {}).get('tools') if isinstance(listed, dict) else None
            self.tools = tools if isinstance(tools, list) else []
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.close()
            return False

    def close(self) -> None:
        self._stdout_alive = False
        if self.proc is None:
            return
        try:
            if self.proc.stdin:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            if self.proc.poll() is None:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            for stream in (self.proc.stdout, self.proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
        finally:
            self.proc = None

    def call_tool(self, name: str, arguments: Optional[Dict] = None,
                  timeout: float = 60.0) -> Dict[str, Any]:
        if not self.proc:
            return {'error': self.last_error or 'MCP 未启动'}
        try:
            result = self._request('tools/call', {
                'name': name,
                'arguments': arguments or {},
            }, timeout=timeout)
            return {'ok': True, 'result': result}
        except Exception as exc:
            return {'error': str(exc)}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _notify(self, method: str, params: Dict) -> None:
        msg = {'jsonrpc': '2.0', 'method': method, 'params': params}
        self._write(msg)

    def _request(self, method: str, params: Dict, timeout: float = 30.0) -> Any:
        with self._lock:
            req_id = self._next_id()
            msg = {'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params}
            self._write(msg)
            deadline = time.time() + timeout
            while time.time() < deadline:
                resp = self._read_message(timeout=max(0.1, deadline - time.time()))
                if resp is None:
                    continue
                if resp.get('id') != req_id:
                    # ignore unrelated notifications
                    continue
                if 'error' in resp:
                    err = resp['error']
                    raise RuntimeError(err.get('message') if isinstance(err, dict) else str(err))
                return resp.get('result')
            raise TimeoutError(f'MCP {method} 超时')

    def _write(self, msg: Dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError('MCP stdin 不可用')
        body = json.dumps(msg, ensure_ascii=False).encode('utf-8')
        header = f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii')
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    def _read_message(self, timeout: float = 5.0) -> Optional[Dict]:
        if not self.proc or not self.proc.stdout:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Try Content-Length framing first
            if b'\r\n\r\n' in self._reader_buf or b'\n\n' in self._reader_buf:
                sep = b'\r\n\r\n' if b'\r\n\r\n' in self._reader_buf else b'\n\n'
                header, rest = self._reader_buf.split(sep, 1)
                length = None
                for line in header.decode('ascii', errors='ignore').splitlines():
                    if line.lower().startswith('content-length:'):
                        try:
                            length = int(line.split(':', 1)[1].strip())
                        except ValueError:
                            length = None
                if length is not None:
                    if len(rest) < length:
                        self._reader_buf = header + sep + rest
                    else:
                        body, self._reader_buf = rest[:length], rest[length:]
                        return json.loads(body.decode('utf-8'))
            # Fallback: newline-delimited JSON
            if b'\n' in self._reader_buf and b'Content-Length' not in self._reader_buf.split(b'\n', 1)[0]:
                line, self._reader_buf = self._reader_buf.split(b'\n', 1)
                line = line.strip()
                if line.startswith(b'{'):
                    try:
                        return json.loads(line.decode('utf-8'))
                    except json.JSONDecodeError:
                        pass
            chunk = self._read_available()
            if chunk:
                self._reader_buf += chunk
            else:
                time.sleep(0.05)
                if self.proc.poll() is not None:
                    err = ''
                    if self.proc.stderr:
                        try:
                            err = self.proc.stderr.read().decode('utf-8', errors='replace')[:500]
                        except Exception:
                            pass
                    raise RuntimeError(f'MCP 进程退出 code={self.proc.returncode} {err}')
        return None

    def _read_available(self) -> bytes:
        """Non-blocking-ish read of stdout."""
        assert self.proc and self.proc.stdout
        import select
        try:
            if os.name == 'nt':
                # Windows: short blocking read via peek-less small reads
                # Use a worker with timeout via communicating buffer growth
                if not hasattr(self, '_stdout_thread'):
                    self._q: List[bytes] = []
                    self._stdout_alive = True

                    def _pump():
                        while self._stdout_alive and self.proc and self.proc.stdout:
                            try:
                                data = self.proc.stdout.read(1)
                            except Exception:
                                break
                            if not data:
                                break
                            self._q.append(data)

                    self._stdout_thread = threading.Thread(target=_pump, daemon=True)
                    self._stdout_thread.start()
                if self._q:
                    data = b''.join(self._q)
                    self._q.clear()
                    # read a bit more greedily
                    time.sleep(0.01)
                    if self._q:
                        data += b''.join(self._q)
                        self._q.clear()
                    return data
                return b''
            r, _, _ = select.select([self.proc.stdout], [], [], 0.05)
            if not r:
                return b''
            return self.proc.stdout.read(4096) or b''
        except Exception:
            return b''


class McpRegistry:
    """Lazy cache of MCP sessions keyed by server name."""

    def __init__(self):
        self.configs = load_mcp_config()
        self._sessions: Dict[str, McpSession] = {}

    def reload(self) -> None:
        for s in self._sessions.values():
            s.close()
        self._sessions.clear()
        self.configs = load_mcp_config()

    def list_servers(self) -> List[Dict]:
        return [c.as_dict() for c in self.configs.values()]

    def get_session(self, name: str, start: bool = True) -> Optional[McpSession]:
        cfg = self.configs.get(name)
        if not cfg:
            return None
        sess = self._sessions.get(name)
        if sess and sess.proc and sess.proc.poll() is None:
            return sess
        if not start:
            return None
        sess = McpSession(cfg)
        if sess.start():
            self._sessions[name] = sess
            return sess
        return sess  # caller reads last_error

    def list_tools(self, name: str) -> Dict[str, Any]:
        sess = self.get_session(name)
        if not sess:
            return {'error': f'未知 MCP server: {name}'}
        if sess.last_error and not sess.tools:
            return {'error': sess.last_error, 'server': name}
        return {
            'server': name,
            'tools': [
                {'name': t.get('name'), 'description': (t.get('description') or '')[:200]}
                for t in sess.tools if isinstance(t, dict)
            ],
        }

    def call(self, server: str, tool: str, arguments: Optional[Dict] = None) -> Dict[str, Any]:
        sess = self.get_session(server)
        if not sess:
            return {'error': f'未知 MCP server: {server}'}
        if sess.last_error and (not sess.proc or sess.proc.poll() is not None):
            return {'error': sess.last_error, 'server': server}
        return sess.call_tool(tool, arguments or {})


_REGISTRY: Optional[McpRegistry] = None


def get_registry() -> McpRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        ensure_default_user_mcp()
        _REGISTRY = McpRegistry()
    return _REGISTRY
