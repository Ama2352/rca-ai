"""Explicit provider wiring for the offline/controlled prepared-demo benchmark.

Nothing here is imported by the default API or release runner. Each route uses
the same PreparedDemoPipeline request builders, budget guards, and reasoning
stages; only provider objects differ. Configurations A/B/C respectively use
Groq/Groq, Groq/Cerebras, and Groq/Gemini. There is no proactive pacing here.
"""

from __future__ import annotations

from typing import Literal

from rca_ai.pipeline.prepared_demo import PreparedDemoPipeline
from rca_ai.pipeline.request_budget import DEFAULT_MAX_ESTIMATED_TOKENS
from rca_ai.reasoning.generator import JsonCompletionProvider


BenchmarkConfiguration = Literal["A", "B", "C"]


def build_benchmark_pipeline(
    configuration: BenchmarkConfiguration,
    *,
    groq_provider: JsonCompletionProvider,
    cerebras_provider: JsonCompletionProvider,
    gemini_provider: JsonCompletionProvider,
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
) -> PreparedDemoPipeline:
    """Compose the three benchmark routings without changing default providers."""

    if configuration not in {"A", "B", "C"}:
        raise ValueError(f"Unknown benchmark configuration: {configuration}")

    generator_provider = groq_provider
    validator_provider = {
        "A": groq_provider,
        "B": cerebras_provider,
        "C": gemini_provider,
    }[configuration]
    return PreparedDemoPipeline(
        generator_provider=generator_provider,
        validator_provider=validator_provider,
        max_estimated_tokens=max_estimated_tokens,
        provider_pacer=None,
    )
