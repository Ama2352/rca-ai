"""Coordinate the frozen RCA stages without adding semantic behavior.

History and Knowledge retrieval precede selection because the frozen runner
measures the complete Generator request, including retrieved context. This
operational detail preserves the original input-budget decision while keeping
Fact construction and selection deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from rca_ai.domain.models import Fact, IncidentInput, RCAResult, ValidationResult
from rca_ai.facts.builder import build_fact_view, verify_fact_view
from rca_ai.facts.selector import SelectionResult, request_bytes, select_facts
from rca_ai.pipeline.assembler import assemble_result
from rca_ai.reasoning.generator import (
    GenerationResult,
    HypothesisGenerator,
    build_generator_request,
)
from rca_ai.reasoning.validator import HypothesisValidator, ValidationExecution
from rca_ai.retrieval.history import HistoryRetrievalResult, retrieve_history
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult, retrieve_knowledge


@dataclass(frozen=True)
class PipelineRunResult:
    """Operational stage outputs for audit/persistence outside the core run.

    The object intentionally keeps F, H, K, generated hypotheses, and
    validations in their own types. A later runner may persist these outputs;
    this core class performs no filesystem writes.
    """

    incident_id: str
    facts: tuple[Fact, ...]
    fact_integrity: bool
    selection: SelectionResult
    history: HistoryRetrievalResult
    knowledge: KnowledgeRetrievalResult
    generation: GenerationResult
    validations: tuple[ValidationExecution, ...]
    rca_result: RCAResult


class RCAPipeline:
    """Run the frozen deterministic/reasoning stages in their validated order.

    Coordination adds no inference, ranking, repair, or text transformation.
    Provider and contract errors propagate unchanged: execution failure is not
    semantic abstention, and an empty hypothesis tuple remains a valid result.
    """

    def __init__(
        self,
        *,
        generator: HypothesisGenerator,
        validator: HypothesisValidator,
    ) -> None:
        self._generator = generator
        self._validator = validator

    def run(self, incident: IncidentInput) -> PipelineRunResult:
        """Build fresh F/H/K context, generate once, validate each H, assemble.

        One independent Validator call is made per generated hypothesis, in
        Generator order. The returned operational artifacts are left for an
        outer runner to save; keeping writes out of this method makes repeated
        runs reproducible and easy to test.
        """
        if incident.retrieval_input is None:
            raise ValueError("IncidentInput.retrieval_input is required by the frozen retrieval flow")

        facts = build_fact_view(incident)
        fact_integrity = verify_fact_view(facts, incident)
        if not fact_integrity:
            raise ValueError("Fresh Fact View failed deterministic integrity verification")

        history = retrieve_history(incident.retrieval_input)
        knowledge = retrieve_knowledge(incident.retrieval_input)

        def exact_request_size(candidate_facts: tuple[Fact, ...]) -> int:
            request = build_generator_request(candidate_facts, history, knowledge)
            return request_bytes(request)

        selection = select_facts(facts, request_size_for=exact_request_size)
        generation = self._generator.generate(selection.facts, history, knowledge)

        validations: list[ValidationExecution] = []
        for hypothesis in generation.hypotheses:
            validations.append(
                self._validator.validate(hypothesis, selection.facts, history, knowledge)
            )

        validation_results: tuple[ValidationResult, ...] = tuple(
            execution.result for execution in validations
        )
        final_result = assemble_result(
            incident.incident_id,
            generation.hypotheses,
            validation_results,
            selection.facts,
            history,
            knowledge,
        )
        return PipelineRunResult(
            incident_id=incident.incident_id,
            facts=facts,
            fact_integrity=fact_integrity,
            selection=selection,
            history=history,
            knowledge=knowledge,
            generation=generation,
            validations=tuple(validations),
            rca_result=final_result,
        )
