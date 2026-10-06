"""Prepared-input RCA execution that passes every Fact without selection."""

from __future__ import annotations

from dataclasses import dataclass

from rca_ai.domain.models import (
    CanonicalIncidentEvidence,
    Fact,
    IncidentInput,
    RCAResult,
    ValidationResult,
)
from rca_ai.facts.builder import build_fact_view, verify_fact_view
from rca_ai.pipeline.assembler import assemble_result
from rca_ai.pipeline.prepared_demo_providers import (
    PacingProvider,
    ProviderCallPacer,
    ValidatorSchemaRetryProvider,
)
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
class PreparedDemoRunResult:
    """Actual prepared-demo stage outputs; no Selector result is implied."""

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


class PreparedDemoPipeline:
    """Execute frozen RCA stages over prepared Facts without selection.

    The coordinator contains stage wiring only. A provider decorator checks
    each complete Generator or candidate-specific Validator request at the
    transport boundary, which prevents hidden truncation or Fact dropping.
    """

    def __init__(
        self,
        *,
        generator_provider: JsonCompletionProvider,
        validator_provider: JsonCompletionProvider,
        max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
        provider_pacer: ProviderCallPacer | None = None,
    ) -> None:
        if provider_pacer is not None:
            generator_provider = PacingProvider(generator_provider, provider_pacer)
            validator_provider = PacingProvider(validator_provider, provider_pacer)
        self._generator = HypothesisGenerator(BudgetGuardProvider(
            generator_provider,
            max_estimated_tokens=max_estimated_tokens,
        ))
        guarded_validator = BudgetGuardProvider(
            validator_provider,
            max_estimated_tokens=max_estimated_tokens,
        )
        self._validator = HypothesisValidator(ValidatorSchemaRetryProvider(guarded_validator))

    def run(self, incident: IncidentInput) -> PreparedDemoRunResult:
        """Build F/H/K, send every Fact to reasoning, then assemble deterministically."""

        facts = build_fact_view(incident)
        fact_integrity = verify_fact_view(facts, incident)
        if not fact_integrity:
            raise ValueError("Fresh Fact View failed deterministic integrity verification")

        retrieval_projection = project_retrieval(incident.evidence)
        history = retrieve_history(retrieval_projection.payload)
        knowledge = retrieve_knowledge(retrieval_projection.payload)

        generation = self._generator.generate(facts, history, knowledge)
        validations: list[ValidationExecution] = []
        for hypothesis in generation.hypotheses:
            validations.append(self._validator.validate(hypothesis, facts, history, knowledge))

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
        return PreparedDemoRunResult(
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
