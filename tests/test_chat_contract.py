import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from gurukul_be.core.config import Settings
from gurukul_be.integrations.ai_client import AIServiceError, run_ai_chat
from gurukul_be.main import app
from gurukul_be.models.chat import Conversation, Message
from gurukul_be.models.identity import User
from gurukul_be.schemas.conversations import ChatTurnResponse, MessageCreateRequest
from gurukul_be.schemas.internal_ai import (
    AIChatLimits,
    AIChatRunRequest,
    AIChatRunResponse,
    AIStudentContext,
)
from gurukul_be.services.conversations import submit_chat_message


def valid_ai_request(**overrides: object) -> AIChatRunRequest:
    data: dict[str, object] = {
        "request_id": "req_test_001",
        "idempotency_key": "conversation-1:message-1",
        "operation": "lesson_turn",
        "user_ref": "opaque-user",
        "conversation_ref": "opaque-conversation",
        "teacher_bot_id": "teacher_math",
        "subject_id": "subject_math",
        "student_context": {
            "grade_level": "8",
            "language": "en",
            "learning_preferences": [],
        },
        "messages": [
            {
                "role": "user",
                "content": "Explain fractions.",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ],
        "lesson_state": {
            "topic": "Fractions",
            "phase": "checking_understanding",
            "understanding": "not_assessed",
            "next_action": "ask_question",
        },
        "limits": {"max_output_tokens": 700, "deadline_ms": 20_000},
        "policy_versions": {
            "safety": "1",
            "teacher": "math-3",
            "retrieval": "2",
        },
    }
    data.update(overrides)
    return AIChatRunRequest.model_validate(data)


def valid_ai_response(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "contract_version": "2026-01",
        "run_id": "run_test_001",
        "status": "completed",
        "content": {"text": "A fraction is part of a whole.", "format": "markdown"},
        "citations": [],
        "safety": {"status": "allowed", "flags": []},
        "usage": {"input_tokens": 10, "output_tokens": 12, "estimated_cost": 0.001},
        "model": {"logical_route": "tutoring_standard"},
        "lesson_progress": {
            "topic": "Fractions",
            "phase": "checking_understanding",
            "understanding": "not_assessed",
            "next_action": "ask_question",
        },
        "policy_versions": {
            "safety": "1",
            "teacher": "math-3",
            "retrieval": "2",
        },
    }
    data.update(overrides)
    return data


def test_ai_contract_accepts_grade_string_and_bounded_math_request() -> None:
    request = valid_ai_request()

    assert request.contract_version == "2026-01"
    assert request.student_context.grade_level == "8"
    assert request.limits.max_output_tokens == 700


def test_ai_lesson_start_requires_no_prior_messages_or_lesson_state() -> None:
    request = valid_ai_request(
        operation="lesson_start",
        messages=[],
        lesson_state=None,
    )
    assert request.operation == "lesson_start"

    with pytest.raises(ValidationError):
        valid_ai_request(operation="lesson_start")


def test_ai_lesson_turn_requires_current_student_reply() -> None:
    with pytest.raises(ValidationError):
        valid_ai_request(
            messages=[
                {
                    "role": "assistant",
                    "content": "Let's continue.",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ]
        )
    with pytest.raises(ValidationError):
        valid_ai_request(lesson_state=None)


@pytest.mark.parametrize("grade_level", ["0", "11", "grade-8"])
def test_ai_contract_rejects_invalid_grade(grade_level: str) -> None:
    with pytest.raises(ValidationError):
        AIStudentContext(grade_level=grade_level, language="en")


def test_ai_contract_rejects_output_budget_over_the_shared_limit() -> None:
    with pytest.raises(ValidationError):
        AIChatLimits(max_output_tokens=701, deadline_ms=20_000)


def test_ai_contract_rejects_unbounded_assistant_response() -> None:
    with pytest.raises(ValidationError):
        AIChatRunResponse.model_validate(
            valid_ai_response(content={"text": "x" * 4001, "format": "markdown"})
        )


@pytest.mark.asyncio
async def test_ai_client_sends_shared_contract_and_auth_headers() -> None:
    request = valid_ai_request()
    observed: dict[str, object] = {}

    def handle_request(http_request: httpx.Request) -> httpx.Response:
        observed["authorization"] = http_request.headers["Authorization"]
        observed["request_id"] = http_request.headers["X-Request-ID"]
        observed["idempotency_key"] = http_request.headers["Idempotency-Key"]
        observed["url"] = str(http_request.url)
        observed["body"] = json.loads(http_request.content)
        return httpx.Response(200, json=valid_ai_response(), request=http_request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await run_ai_chat(
            request,
            client,
            Settings.model_validate(
                {
                    "AI_SERVICE_URL": "http://ai.test",
                    "AI_SERVICE_AUTH_KEY": "local-test-key",
                    "AI_SERVICE_TIMEOUT_SECONDS": 3,
                }
            ),
        )

    assert result.run_id == "run_test_001"
    assert observed["authorization"] == "Bearer local-test-key"
    assert observed["request_id"] == request.request_id
    assert observed["idempotency_key"] == request.idempotency_key
    assert observed["url"] == "http://ai.test/internal/v1/chat/runs"
    assert isinstance(observed["body"], dict)
    assert observed["body"]["contract_version"] == "2026-01"


@pytest.mark.asyncio
async def test_ai_client_converts_provider_timeout_to_stable_error() -> None:
    def timeout_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(timeout_request)
    ) as client:
        with pytest.raises(AIServiceError) as error:
            await run_ai_chat(
                valid_ai_request(),
                client,
                Settings.model_validate({"AI_SERVICE_TIMEOUT_SECONDS": 1}),
            )

    assert error.value.code == "AI_PROVIDER_TIMEOUT"
    assert error.value.status_code == 504


@pytest.mark.asyncio
async def test_ai_client_maps_provider_error_envelope() -> None:
    def policy_blocked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "AI_POLICY_BLOCKED",
                    "message": "Policy blocked this request.",
                    "retryable": False,
                    "request_id": "req_test_001",
                }
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(policy_blocked)
    ) as client:
        with pytest.raises(AIServiceError) as error:
            await run_ai_chat(
                valid_ai_request(),
                client,
                Settings.model_validate({"AI_SERVICE_TIMEOUT_SECONDS": 1}),
            )

    assert error.value.code == "AI_POLICY_BLOCKED"
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_message_returns_saved_turn_without_another_ai_call() -> None:
    now = datetime.now(UTC)
    student_id = uuid4()
    conversation_id = uuid4()
    user_message_id = uuid4()
    client_message_id = uuid4()
    student = User(
        id=student_id,
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    conversation = Conversation(
        id=conversation_id,
        student_id=student_id,
        teacher_bot_id="teacher_math",
        status="open",
        created_at=now,
        updated_at=now,
    )
    user_message = Message(
        id=user_message_id,
        conversation_id=conversation_id,
        role="user",
        content="Explain fractions.",
        content_format="text",
        status="completed",
        client_message_id=str(client_message_id),
        created_at=now,
        completed_at=now,
    )
    assistant_message = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content="A fraction is part of a whole.",
        content_format="markdown",
        status="completed",
        reply_to_message_id=user_message_id,
        created_at=now,
        completed_at=now,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [
        conversation,
        user_message,
        assistant_message,
        None,
    ]
    ai_client = AsyncMock(spec=httpx.AsyncClient)

    result = await submit_chat_message(
        session,
        student,
        conversation_id,
        MessageCreateRequest(
            client_message_id=client_message_id,
            content="Explain fractions.",
        ),
        ai_client,
    )

    assert result.status_code == 200
    assert isinstance(result.response, ChatTurnResponse)
    assert result.response.assistant_message.content == "A fraction is part of a whole."
    ai_client.post.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_cannot_submit_to_another_students_conversation() -> None:
    student = User(
        id=uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None

    with pytest.raises(HTTPException) as error:
        await submit_chat_message(
            session,
            student,
            uuid4(),
            MessageCreateRequest(
                client_message_id=uuid4(),
                content="Explain fractions.",
            ),
            AsyncMock(spec=httpx.AsyncClient),
        )

    assert error.value.status_code == 404


def test_chat_endpoints_are_in_openapi() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/subjects" in paths
    assert "/api/v1/conversations" in paths
    assert "/api/v1/conversations/{conversation_id}/messages" in paths
    assert (
        "teacher"
        in app.openapi()["components"]["schemas"]["SubjectResponse"]["properties"]
    )
    message_statuses = paths["/api/v1/conversations/{conversation_id}/messages"][
        "post"
    ]["responses"]
    assert "201" in message_statuses
    assert "202" in message_statuses
