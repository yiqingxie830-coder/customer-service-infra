from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from langgraph_sdk.client import LangGraphClient
from app_backend.main import app, get_langgraph_client


def build_mock_client(return_state=None, exception=None) -> LangGraphClient:
    mock_client = MagicMock(spec=LangGraphClient)
    mock_runs = AsyncMock()
    
    if exception:
        mock_runs.wait.side_effect = exception
    else:
        mock_runs.wait.return_value = return_state or {"final_response": "Happy to help."}
        
    mock_client.runs = mock_runs
    return mock_client


@pytest.mark.asyncio
async def test_chat_forwards_full_history_and_returns_response() -> None:
    mock_client = build_mock_client()
    app.dependency_overrides[get_langgraph_client] = lambda: mock_client
    
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/chat",
                json={
                    "user_id": "u_001",
                    "session_id": "session-123",
                    "messages": [
                        {"role": "user", "content": "Hi"},
                        {"role": "assistant", "content": "Hello"},
                        {"role": "user", "content": "Can you help?"},
                    ],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"session_id": "session-123", "response": "Happy to help."}
    
    # Verify the mock was called with correct args
    mock_client.runs.wait.assert_called_once()
    call_kwargs = mock_client.runs.wait.call_args.kwargs
    assert call_kwargs["assistant_id"] == "chat_agent"
    assert call_kwargs["input"]["user_id"] == "u_001"
    assert len(call_kwargs["input"]["messages"]) == 3
    assert call_kwargs["input"]["messages"][-1]["content"] == "Can you help?\n\n[Client Type: unknown]"
    assert call_kwargs["metadata"]["client_type"] == "unknown"


@pytest.mark.asyncio
async def test_chat_requires_session_user_and_history() -> None:
    mock_client = build_mock_client()
    app.dependency_overrides[get_langgraph_client] = lambda: mock_client
    
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/chat", json={"user_id": "", "session_id": "", "messages": []})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_maps_langgraph_errors() -> None:
    # Let's simulate a LangGraph SDK exception
    mock_client = build_mock_client(exception=Exception("assistant not found"))
    app.dependency_overrides[get_langgraph_client] = lambda: mock_client
    
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/chat",
                json={
                    "user_id": "u_001",
                    "session_id": "session-123",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {"detail": "assistant not found"}


@pytest.mark.asyncio
async def test_chat_maps_malformed_langgraph_success_to_bad_gateway() -> None:
    mock_client = build_mock_client(return_state="not a dict")
    app.dependency_overrides[get_langgraph_client] = lambda: mock_client
    
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/chat",
                json={
                    "user_id": "u_001",
                    "session_id": "session-123",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {"detail": "LangGraph response was not a dictionary"}


@pytest.mark.asyncio
async def test_chat_with_client_type_appends_message_and_metadata() -> None:
    mock_client = build_mock_client()
    app.dependency_overrides[get_langgraph_client] = lambda: mock_client
    
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/chat",
                json={
                    "user_id": "u_001",
                    "session_id": "session-123",
                    "messages": [
                        {"role": "user", "content": "Hello agent"},
                    ],
                    "client_type": "mobile",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    mock_client.runs.wait.assert_called_once()
    call_kwargs = mock_client.runs.wait.call_args.kwargs
    assert call_kwargs["input"]["messages"][-1]["content"] == "Hello agent\n\n[Client Type: mobile]"
    assert call_kwargs["metadata"]["client_type"] == "mobile"
    assert call_kwargs["config"]["metadata"]["client_type"] == "mobile"
