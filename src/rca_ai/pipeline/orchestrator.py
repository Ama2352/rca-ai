"""Canonical RCA orchestration over source-linked Facts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import time
from typing import Callable, Iterator
from typing import Any

from rca_ai.domain.models import (
    CanonicalIncidentEvidence,
    Fact,
    IncidentInput,
    RCAResult,
    ValidationResult,
)
from rca_ai.facts.builder import build_fact_view, verify_fact_view
from rca_ai.pipeline.assembler import assemble_result
from rca_ai.pipeline.provider_observation import ObservedProvider
from rca_ai.pipeline.request_budget import (
    DEFAULT_MAX_ESTIMATED_TOKENS,
    BudgetGuardProvider,
)
from rca_ai.reasoning.generator import (
    GenerationResult,
    HypothesisGenerator,
    JsonCompletionProvider,
)
from rca_ai.reasoning.validator import HypothesisValidator, ValidationExecution
from rca_ai.retrieval.history import HistoryRetrievalResult, retrieve_history
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult, retrieve_knowledge
from rca_ai.retrieval.projection import RetrievalProjection, project_retrieval


@dataclass(frozen=True)
class PipelineRunResult:
    """Typed outputs from the official RCA pipeline stages."""

    incident_id: str
    evidence: CanonicalIncidentEvidence
    facts: tuple[Fact, ...]
    fact_integrity: bool
    retrieval_projection: RetrievalProjection
    history: HistoryRetrievalResult
    knowledge: KnowledgeRetrievalResult
    generation: GenerationResult
    validations: tuple[ValidationExecution, ...]
    rca_result: RCAResult


@dataclass(frozen=True)
class DemoEvent:
    """Optional, content-free event for official RCA progress and timing."""

    kind: str
    stage: str
    timestamp: float
    candidate_id: str | None = None
    attempts: int | None = None
    http_429s: int | None = None
    retry_after_seconds: float | None = None


class RCAPipeline:
    """Execute the official RCA stages over canonical Facts.

    Every Fact built from canonical evidence is passed unchanged to the
    Generator and each candidate-specific Validator request. Provider guards
    reject complete requests over budget before transport.
    """

    def __init__(
        self,
        *,
        generator_provider: JsonCompletionProvider,
        validator_provider: JsonCompletionProvider,
        max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
    ) -> None:
        self._observer: Callable[[DemoEvent], None] | None = None
        self._active_stage = ""
        self._active_candidate: str | None = None
        generator_provider = ObservedProvider(generator_provider, self._provider_event)
        validator_provider = ObservedProvider(validator_provider, self._provider_event)
        self._generator = HypothesisGenerator(BudgetGuardProvider(
            generator_provider,
            max_estimated_tokens=max_estimated_tokens,
        ))
        guarded_validator = BudgetGuardProvider(
            validator_provider,
            max_estimated_tokens=max_estimated_tokens,
        )
        self._validator = HypothesisValidator(guarded_validator)

    def _provider_event(self, kind: str, outcome: Any | None = None) -> None:
        self._emit(kind, self._active_stage, self._active_candidate, outcome)

    def _emit(self, kind: str, stage: str, candidate_id: str | None = None,
              outcome: Any | None = None) -> None:
        if self._observer is not None:
            attempts = getattr(outcome, "attempts", None)
            log = getattr(outcome, "attempt_log", ()) if outcome is not None else ()
            retries_429 = sum(getattr(item, "http_status", None) == 429 for item in log)
            retry_after = [getattr(item, "retry_after_seconds", None) for item in log]
            self._observer(DemoEvent(
                kind, stage, time.perf_counter(), candidate_id,
                attempts=attempts if isinstance(attempts, int) else None,
                http_429s=retries_429 if log else None,
                retry_after_seconds=max((item for item in retry_after if isinstance(item, (int, float))), default=None),
            ))

    @contextmanager
    def _stage(self, stage: str, candidate_id: str | None = None) -> Iterator[None]:
        self._active_stage, self._active_candidate = stage, candidate_id
        self._emit("stage_started", stage, candidate_id)
        try:
            yield
        except Exception:
            self._emit("stage_failed", stage, candidate_id)
            raise
        else:
            self._emit("stage_completed", stage, candidate_id)

    def run(self, incident: IncidentInput,
            *, observer: Callable[[DemoEvent], None] | None = None) -> PipelineRunResult:
        """Build F/H/K, send every Fact to reasoning, then assemble deterministically."""
        self._observer = observer
        try:
            with self._stage("evidence"):
                facts = build_fact_view(incident)
                fact_integrity = verify_fact_view(facts, incident)
                if not fact_integrity:
                    raise ValueError("Fresh Fact View failed deterministic integrity verification")

            with self._stage("retrieval"):
                retrieval_projection = project_retrieval(incident.evidence)
                history = retrieve_history(retrieval_projection.payload)
                knowledge = retrieve_knowledge(retrieval_projection.payload)

            with self._stage("generation"):
                generation = self._generator.generate(facts, history, knowledge)
            validations: list[ValidationExecution] = []
            for hypothesis in generation.hypotheses:
                with self._stage("validation", hypothesis.id):
                    validations.append(self._validator.validate(hypothesis, facts, history, knowledge))

            with self._stage("assembly"):
                validation_results: tuple[ValidationResult, ...] = tuple(
                    execution.result for execution in validations
                )
                final_result = assemble_result(
                    incident.incident_id,
                    generation.hypotheses,
                    validation_results,
                    facts,
                    history,
                    knowledge,
                )
            return PipelineRunResult(
                incident_id=incident.incident_id,
                evidence=incident.evidence,
                facts=facts,
                fact_integrity=fact_integrity,
                retrieval_projection=retrieval_projection,
                history=history,
                knowledge=knowledge,
                generation=generation,
                validations=tuple(validations),
                rca_result=final_result,
            )
        finally:
            self._observer = None
            self._active_stage = ""
            self._active_candidate = None
