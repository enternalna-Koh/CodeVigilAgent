"""与界面无关的网关密钥作用域绑定。"""
from __future__ import annotations


class GatewayKey:
    """密钥只能随原服务商和原地址恢复，不跨作用域回填。"""

    def __init__(self, provider: str, base_url: str, key: str):
        self.original = self.identity(provider, base_url)
        self.current = self.original
        self.saved_key = key

    @staticmethod
    def identity(provider: str, base_url: str) -> tuple[str, str]:
        return provider.strip().lower(), base_url.strip().rstrip('/')

    def update(self, provider: str, base_url: str, key: str) -> str:
        target = self.identity(provider, base_url)
        if target != self.current:
            self.current = target
            return self.saved_key if target == self.original else ''
        return key

    @property
    def changed(self) -> bool:
        return self.current != self.original
