"""Provider-agnostic LLM client.

All pipeline code depends on `LLMClient.complete()` only. Concrete providers are
selected per-role in config/config.yaml. The mock provider enables offline tests and
dry runs (no network in tests — see CLAUDE.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass(frozen=True)
class RoleConfig:
    provider: str  # "anthropic" | "openai" | "mock"
    model: str
    temperature: float
    max_tokens: int


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, *, seed: int | None = None) -> str:
        """Return the assistant text for a single-turn request."""
        ...


class AnthropicClient:
    def __init__(self, cfg: RoleConfig):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._cfg = cfg
        self.model = cfg.model

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=2, max=30))
    def complete(self, system: str, user: str, *, seed: int | None = None) -> str:
        # The Anthropic API has no seed parameter; the seed is still recorded in the
        # run manifest as the run key (see CLAUDE.md provenance rule).
        resp = self._client.messages.create(
            model=self._cfg.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=self._cfg.temperature,
            max_tokens=self._cfg.max_tokens,
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class OpenAIClient:
    def __init__(self, cfg: RoleConfig):
        from openai import OpenAI

        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._cfg = cfg
        self.model = cfg.model

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=2, max=30))
    def complete(self, system: str, user: str, *, seed: int | None = None) -> str:
        resp = self._client.chat.completions.create(
            model=self._cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self._cfg.temperature,
            max_tokens=self._cfg.max_tokens,
            seed=seed,
        )
        return resp.choices[0].message.content or ""


class OpenRouterClient:
    """OpenAI-compatible client pointed at OpenRouter (https://openrouter.ai).

    Gives access to many model families (including free-tier ':free' variants) through
    one API key — useful for dev/pilot testing before spending on pinned paid models.
    Model id format: 'vendor/model', e.g. 'meta-llama/llama-3.3-70b-instruct:free'.
    """

    def __init__(self, cfg: RoleConfig):
        from openai import OpenAI

        self._client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )
        self._cfg = cfg
        self.model = cfg.model

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=2, max=30))
    def complete(self, system: str, user: str, *, seed: int | None = None) -> str:
        resp = self._client.chat.completions.create(
            model=self._cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self._cfg.temperature,
            max_tokens=self._cfg.max_tokens,
            seed=seed,
            extra_headers={
                # Optional per OpenRouter docs; harmless if the values are generic.
                "HTTP-Referer": "https://github.com/PhongCT1105/Hack-Research",
                "X-Title": "outreach-eval",
            },
        )
        return resp.choices[0].message.content or ""


class MockClient:
    """Deterministic offline client for tests and --dry-run.

    Returns canned JSON/text keyed on markers in the prompt so the full pipeline
    (generate -> verify -> extract) round-trips without network access.
    """

    def __init__(self, cfg: RoleConfig):
        self._cfg = cfg
        self.model = f"mock-{cfg.model}"

    def complete(self, system: str, user: str, *, seed: int | None = None) -> str:
        if "verification editor" in system:
            return (
                '{"claims": [{"claim_id": "c1", "atomic_claim": "Professor studies '
                'calibration in medical imaging.", "claim_type": "research_topic", '
                '"verdict": "supported", "evidence_excerpt": "calibration ... medical imaging"}], '
                '"edits": [{"claim_id": "c1", "action": "keep", "original_span": "", '
                '"revised_span": "", "reason": "supported"}], '
                '"revised_email": "Subject: Interest in your lab\\n\\n[mock verified email]"}'
            )
        if "decompose emails" in system:
            return (
                '{"claims": [{"claim_id": "c1", "atomic_claim": "Professor studies '
                'calibration in medical imaging.", "claim_type": "research_topic", '
                '"source_sentence": "[mock sentence]"}]}'
            )
        return (
            f"Subject: Interest in your research (seed={seed})\n\n"
            "Dear Professor,\n\n[mock email body generated offline]\n\nSincerely,\nA Student"
        )


_PROVIDERS = {
    "anthropic": AnthropicClient,
    "openai": OpenAIClient,
    "openrouter": OpenRouterClient,
    "mock": MockClient,
}


def get_client(cfg: RoleConfig) -> LLMClient:
    try:
        return _PROVIDERS[cfg.provider](cfg)
    except KeyError:
        raise ValueError(
            f"Unknown provider {cfg.provider!r}; expected one of {sorted(_PROVIDERS)}"
        ) from None


def role_config_from_dict(d: dict) -> RoleConfig:
    return RoleConfig(
        provider=d["provider"],
        model=d["model"],
        temperature=float(d["temperature"]),
        max_tokens=int(d["max_tokens"]),
    )
