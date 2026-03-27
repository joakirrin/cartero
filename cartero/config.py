from __future__ import annotations

from dataclasses import dataclass


_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class CarteroConfig:
    llm_provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 8192
    max_retries: int = 3
    max_diff_tokens: int = 30_000
    clean_after_publish_days: int = 7

    @property
    def max_diff_chars(self) -> int:
        return self.max_diff_tokens * _CHARS_PER_TOKEN


default_config = CarteroConfig()
