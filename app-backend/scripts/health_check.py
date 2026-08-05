"""Validate the app-backend -> LangGraph chat chain through a running app backend.

Posts a real `POST /chat` request to the app backend and asserts the response
shape. A passing run means the app backend accepted the request, reached
LangGraph, and returned a non-empty chat response with the expected session id.

Run with:
    uv run python scripts/health_check.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import httpx


DEFAULT_USER_ID = "smoke-test-user"
DEFAULT_SESSION_ID = "smoke-test-session"
DEFAULT_MESSAGE = "Reply with a short confirmation that the chat chain is healthy."
DEFAULT_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class CliArgs:
    base_url: str
    user_id: str
    session_id: str
    message: str
    timeout_seconds: float


def main() -> int:
    parser = _build_parser()
    try:
        args = _parse_cli_args(parser.parse_args())
    except ValueError as error:
        parser.error(str(error))

    return asyncio.run(
        _run_chat_health_check(
            base_url=args.base_url,
            user_id=args.user_id,
            session_id=args.session_id,
            message=args.message,
            timeout_seconds=args.timeout_seconds,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the app-backend -> LangGraph chat chain through the running app backend.",
    )
    _ = parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL for the running app backend, for example http://localhost:8000.",
    )
    _ = parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="User id to send in the chat request.")
    _ = parser.add_argument("--session-id", default=DEFAULT_SESSION_ID, help="Session id to expect in the response.")
    _ = parser.add_argument("--message", default=DEFAULT_MESSAGE, help="User message to send through the chat chain.")
    _ = parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout for the app backend request.",
    )
    return parser


def _parse_cli_args(namespace: argparse.Namespace) -> CliArgs:
    raw_args = cast("Mapping[str, object]", vars(namespace))
    return CliArgs(
        base_url=_required_str(raw_args["base_url"], "--base-url"),
        user_id=_required_str(raw_args["user_id"], "--user-id"),
        session_id=_required_str(raw_args["session_id"], "--session-id"),
        message=_required_str(raw_args["message"], "--message"),
        timeout_seconds=_positive_float(raw_args["timeout_seconds"], "--timeout-seconds"),
    )


def _required_str(value: object, flag: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{flag} must be a non-empty string")
    return value


def _positive_float(value: object, flag: str) -> float:
    if not isinstance(value, float) or value <= 0:
        raise ValueError(f"{flag} must be a positive number")
    return value


async def _run_chat_health_check(
    *,
    base_url: str,
    user_id: str,
    session_id: str,
    message: str,
    timeout_seconds: float,
) -> int:
    request_body = {
        "user_id": user_id,
        "session_id": session_id,
        "messages": [{"role": "user", "content": message}],
    }

    endpoint = f"{base_url.rstrip('/')}/chat"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
            response = await client.post(endpoint, json=request_body)
    except httpx.TimeoutException:
        _write_failure(f"Timed out after {timeout_seconds:g}s while calling {endpoint}")
        return 1
    except httpx.TransportError as error:
        _write_failure(f"Could not reach app backend at {endpoint}: {error}")
        return 1

    if response.status_code != 200:
        _write_failure(f"App backend returned HTTP {response.status_code}: {_response_error_detail(response)}")
        return 1

    try:
        data = cast(object, response.json())
    except ValueError:
        _write_failure(f"App backend returned non-JSON success response: {response.text}")
        return 1

    if not _is_valid_chat_response(data, expected_session_id=session_id):
        _write_failure(f"App backend returned unexpected chat response: {json.dumps(data, sort_keys=True)}")
        return 1

    print(json.dumps({"status": "ok", "chat_response": data}, indent=2, sort_keys=True))
    return 0


def _is_valid_chat_response(data: object, *, expected_session_id: str) -> bool:
    if not isinstance(data, Mapping):
        return False

    response_data = cast("Mapping[str, object]", data)
    session_id = response_data.get("session_id")
    response = response_data.get("response")
    return session_id == expected_session_id and isinstance(response, str) and bool(response)


def _response_error_detail(response: httpx.Response) -> str:
    try:
        data = cast(object, response.json())
    except ValueError:
        return response.text or "<empty response body>"

    if isinstance(data, Mapping):
        response_data = cast("Mapping[str, object]", data)
        detail = response_data.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        if detail is not None:
            return json.dumps(detail, sort_keys=True)

    return response.text or "<empty response body>"


def _write_failure(messages: str | Sequence[str]) -> None:
    if isinstance(messages, str):
        messages = [messages]
    for message in messages:
        print(f"ERROR: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
