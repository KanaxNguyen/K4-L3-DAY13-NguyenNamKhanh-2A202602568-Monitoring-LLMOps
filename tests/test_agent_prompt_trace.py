from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []
        self.observations: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        observation = {**kwargs, "updates": []}
        self.observations.append(observation)

        class Observation:
            def update(self, **values) -> None:
                observation["updates"].append(values)

        yield Observation()


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    result = agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = next(update for update in client.span_updates if "metadata" in update)
    assert span_update["metadata"] == {
        "doc_count": 1,
        "query_preview": "Explain traces",
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert client.span_updates[0]["input"] == "Explain traces"
    assert client.span_updates[-1]["output"] == result.answer
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert propagated[-1]["prompt"] is client.prompt

    retrieval, generation = client.observations
    assert retrieval["as_type"] == "retriever"
    assert retrieval["input"] == "Explain traces"
    assert retrieval["updates"][0]["output"]
    assert generation["as_type"] == "generation"
    assert generation["model"] == agent.model
    assert generation["input"].endswith("Question=Explain traces")
    generation_update = generation["updates"][0]
    assert generation_update["output"] == result.answer
    assert generation_update["usage_details"] == {
        "input": result.tokens_in,
        "output": result.tokens_out,
    }
    assert generation_update["cost_details"]["total"] == result.cost_usd
