#!/usr/bin/env python3
"""Temporary ASGI workload used only by profile_production.py.

This harness is bind-mounted read-only into a disposable profiling container;
it is intentionally not copied into either production image.
"""

from __future__ import annotations

import argparse

from rca_ai.api.demo import create_app
from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.providers.contracts import ProviderResult


class FakeProvider:
    def complete(self, request):
        return ProviderResult(
            content={"hypotheses": []}, raw_content='{"hypotheses":[]}',
            http_status=200, attempts=1, response_id="offline-profile",
            model_returned="offline-fake", finish_reason="stop", usage={},
            latency_seconds=0.0, rate_limit_headers={}, attempt_log=(),
        )


def make_pipeline() -> RCAPipeline:
    return RCAPipeline(generator_provider=FakeProvider(), validator_provider=FakeProvider())


app = create_app(pipeline_factory=make_pipeline, credential_available=lambda: True)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
