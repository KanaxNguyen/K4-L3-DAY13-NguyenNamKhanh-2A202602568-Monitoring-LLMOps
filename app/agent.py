from __future__ import annotations

import os
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, scrub_text, summarize_text
from .prompt_management import resolve_prompt
from .tracing import get_langfuse_client, observe, propagate_attributes, tracing_enabled


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


@contextmanager
def _observation_span(client: Any, name: str, as_type: str = "span", **kwargs: Any):
    if client is not None and hasattr(client, "start_as_current_observation"):
        with client.start_as_current_observation(name=name, as_type=as_type, **kwargs) as obs:
            yield obs
    else:
        yield None


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_active = tracing_enabled()
        langfuse_client = get_langfuse_client() if langfuse_active else None
        safe_session_id = scrub_text(session_id)
        safe_feature = scrub_text(feature)
        safe_correlation_id = scrub_text(correlation_id)
        if langfuse_active:
            attributes_context = propagate_attributes(
                user_id=hash_user_id(user_id),
                session_id=safe_session_id,
                tags=["lab", safe_feature, self.model],
                trace_name="day13-agent-request",
                environment=os.getenv("APP_ENV", "dev"),
                metadata={
                    "feature": safe_feature,
                    "model": self.model,
                    "correlation_id": safe_correlation_id,
                },
            )
        else:
            attributes_context = nullcontext()
        with attributes_context:
            if langfuse_client is not None:
                langfuse_client.update_current_span(input=scrub_text(message))
            started = time.perf_counter()
            with _observation_span(
                langfuse_client,
                name="retrieve",
                as_type="retriever",
                input=scrub_text(message),
            ) as retrieval_observation:
                docs = retrieve(message)
                if retrieval_observation is not None and hasattr(retrieval_observation, "update"):
                    retrieval_observation.update(output=[scrub_text(doc) for doc in docs])

            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=tracing_enabled(),
            )
            if langfuse_client is not None:
                langfuse_client.update_current_span(
                    metadata={
                        "doc_count": len(docs),
                        "query_preview": summarize_text(message),
                        "prompt_name": scrub_text(prompt.name),
                        "prompt_label": scrub_text(prompt.label),
                        "prompt_version": scrub_text(prompt.version),
                        "prompt_source": scrub_text(prompt.source),
                        "prompt_fetch_error": prompt.fetch_error or "",
                    },
                    version=prompt.version,
                )
            prompt_context = (
                propagate_attributes(prompt=prompt.managed_prompt)
                if langfuse_active
                else nullcontext()
            )
            with prompt_context:
                with _observation_span(
                    langfuse_client,
                    name="generate",
                    as_type="generation",
                    model=self.model,
                    input=scrub_text(prompt.text),
                    prompt=prompt.managed_prompt,
                ) as generation:
                    response = self.llm.generate(prompt.text)
                    input_cost_usd = round(response.usage.input_tokens / 1_000_000 * 3, 6)
                    output_cost_usd = round(response.usage.output_tokens / 1_000_000 * 15, 6)
                    cost_usd = self._estimate_cost(
                        response.usage.input_tokens, response.usage.output_tokens
                    )
                    if generation is not None and hasattr(generation, "update"):
                        generation.update(
                            output=scrub_text(response.text),
                            usage_details={
                                "input": response.usage.input_tokens,
                                "output": response.usage.output_tokens,
                            },
                            cost_details={
                                "input": input_cost_usd,
                                "output": output_cost_usd,
                                "total": cost_usd,
                            },
                        )

            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if langfuse_client is not None:
                langfuse_client.update_current_span(output=scrub_text(response.text))

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
