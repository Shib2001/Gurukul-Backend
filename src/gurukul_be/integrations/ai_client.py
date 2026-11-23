import asyncio

import httpx
from fastapi import Request
from pydantic import ValidationError

from gurukul_be.core.config import Settings, get_settings
from gurukul_be.schemas.internal_ai import (
    AIChatRunRequest,
    AIChatRunResponse,
    AIErrorResponse,
)


def get_ai_http_client(request: Request) -> httpx.AsyncClient:
    client = getattr(request.app.state, "ai_http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise TypeError("The AI HTTP client has not been initialized")
    return client


_ERROR_MESSAGES = {
    "AI_PROVIDER_TIMEOUT": "The AI teacher timed out. Your question was saved.",
    "AI_PROVIDER_UNAVAILABLE": (
        "The AI teacher is temporarily unavailable. Your question was saved."
    ),
    "AI_POLICY_BLOCKED": "The AI teacher could not answer this request.",
    "AI_INVALID_REQUEST": "The AI service rejected the chat request.",
    "AI_INTERNAL_ERROR": "The AI service could not complete this request.",
}
_ERROR_STATUS_CODES = {
    "AI_PROVIDER_TIMEOUT": 504,
    "AI_PROVIDER_UNAVAILABLE": 503,
    "AI_POLICY_BLOCKED": 422,
    "AI_INVALID_REQUEST": 502,
    "AI_INTERNAL_ERROR": 502,
}


class AIServiceError(Exception):
    def __init__(self, code: str, request_id: str) -> None:
        self.code = code
        self.request_id = request_id
        self.status_code = _ERROR_STATUS_CODES[code]
        self.public_message = _ERROR_MESSAGES[code]
        super().__init__(self.public_message)


def _error_code(response: httpx.Response) -> str:
    try:
        body = AIErrorResponse.model_validate(response.json())
    except (ValueError, ValidationError):
        return "AI_PROVIDER_UNAVAILABLE"
    return body.error.code


async def run_ai_chat(
    payload: AIChatRunRequest,
    client: httpx.AsyncClient,
    settings: Settings | None = None,
) -> AIChatRunResponse:
    settings = settings or get_settings()
    request_id = payload.request_id
    timeout_seconds = settings.AI_SERVICE_TIMEOUT_SECONDS
    timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=min(timeout_seconds, 3),
        read=timeout_seconds,
        write=min(timeout_seconds, 3),
        pool=min(timeout_seconds, 3),
    )
    headers = {
        "Authorization": f"Bearer {settings.AI_SERVICE_AUTH_KEY}",
        "X-Request-ID": payload.request_id,
        "Idempotency-Key": payload.idempotency_key,
    }

    try:
        async with asyncio.timeout(timeout_seconds + 1):
            response = await client.post(
                f"{settings.AI_SERVICE_URL.rstrip('/')}/internal/v1/chat/runs",
                headers=headers,
                json=payload.model_dump(mode="json"),
                timeout=timeout,
            )
    except (TimeoutError, httpx.TimeoutException) as error:
        raise AIServiceError("AI_PROVIDER_TIMEOUT", request_id) from error
    except httpx.RequestError as error:
        raise AIServiceError("AI_PROVIDER_UNAVAILABLE", request_id) from error

    if response.is_error:
        raise AIServiceError(_error_code(response), request_id)

    try:
        result = AIChatRunResponse.model_validate(response.json())
    except (ValueError, ValidationError) as error:
        raise AIServiceError("AI_INTERNAL_ERROR", request_id) from error

    if result.status == "blocked" or result.safety.status == "blocked":
        raise AIServiceError("AI_POLICY_BLOCKED", request_id)

    return result
