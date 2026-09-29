from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"].startswith("req-")
    assert "x-response-time-ms" in response.headers

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True
    assert response_event["correlation_id"] == response.headers["x-request-id"]
    assert "user_id_hash" in response_event
    assert response_event["session_id"] == "session-01"
    assert response_event["feature"] == "qa"
    assert response_event["model"] == "claude-sonnet-4-5"


def test_chat_scrubs_pii_in_logs(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Call 0987654321, email a@b.com, card 4111 2222 3333 4444",
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200
    log_content = log_path.read_text(encoding="utf-8")
    assert "0987654321" not in log_content
    assert "a@b.com" not in log_content
    assert "4111 2222 3333 4444" not in log_content
    assert "REDACTED_PHONE_VN" in log_content
    assert "REDACTED_EMAIL" in log_content
    assert "REDACTED_CREDIT_CARD" in log_content
