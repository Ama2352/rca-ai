from __future__ import annotations

import pytest

import rca_ai.pipeline.prepared_demo_benchmark as benchmark


class CapturePipeline:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.parametrize("configuration,expected", [
    ("A", ("groq", "groq")),
    ("B", ("groq", "cerebras")),
    ("C", ("groq", "gemini")),
])
def test_benchmark_builder_uses_requested_routing_without_cross_provider_pacing(monkeypatch, configuration, expected):
    monkeypatch.setattr(benchmark, "PreparedDemoPipeline", CapturePipeline)
    groq, cerebras, gemini = object(), object(), object()
    pipeline = benchmark.build_benchmark_pipeline(
        configuration, groq_provider=groq, cerebras_provider=cerebras,
        gemini_provider=gemini,
    )
    labels = {id(groq): "groq", id(cerebras): "cerebras", id(gemini): "gemini"}
    actual = tuple(labels[id(pipeline.kwargs[key])]
                   for key in ("generator_provider", "validator_provider"))
    assert actual == expected
    assert pipeline.kwargs["provider_pacer"] is None
    assert pipeline.kwargs["max_estimated_tokens"] == 7000


def test_unknown_benchmark_configuration_is_rejected(monkeypatch):
    monkeypatch.setattr(benchmark, "PreparedDemoPipeline", CapturePipeline)
    with pytest.raises(ValueError, match="configuration"):
        benchmark.build_benchmark_pipeline(
            "D", groq_provider=object(), cerebras_provider=object(), gemini_provider=object(),
        )
