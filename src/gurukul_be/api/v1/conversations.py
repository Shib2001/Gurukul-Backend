from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from gurukul_be.api.responses import success_response
from gurukul_be.api.v1.auth import get_current_student
from gurukul_be.db.session import get_db
from gurukul_be.integrations.ai_client import get_ai_http_client
from gurukul_be.models.identity import User
from gurukul_be.schemas.catalog import SubjectResponse
from gurukul_be.schemas.common import ApiResponse
from gurukul_be.schemas.conversations import (
    ChatTurnResponse,
    ConversationCreateRequest,
    ConversationResponse,
    LessonStartResponse,
    MessageCreateRequest,
    MessagePageResponse,
)
from gurukul_be.services.conversations import (
    create_conversation,
    list_conversation_messages,
    list_conversations,
    list_subjects,
    submit_chat_message,
)

router = APIRouter(tags=["learning"])


@router.get(
    "/subjects",
    response_model=ApiResponse[list[SubjectResponse]],
    dependencies=[Depends(get_current_student)],
)
async def get_subjects(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    subjects = await list_subjects(session)
    return success_response(subjects, status.HTTP_200_OK)


@router.post(
    "/conversations",
    response_model=ApiResponse[LessonStartResponse],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"description": "Previously saved idempotent lesson start"},
        status.HTTP_202_ACCEPTED: {"description": "The original lesson is pending"},
        status.HTTP_404_NOT_FOUND: {"description": "Subject is not available"},
        status.HTTP_409_CONFLICT: {
            "description": "Idempotency key was used for a different subject"
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "The AI service is unavailable; failed state was saved"
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "description": "The AI provider timed out; failed state was saved"
        },
    },
)
async def post_conversation(
    request: ConversationCreateRequest,
    response: Response,
    ai_client: Annotated[httpx.AsyncClient, Depends(get_ai_http_client)],
    student: Annotated[User, Depends(get_current_student)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await create_conversation(session, student, request, ai_client)
    response.status_code = result.status_code
    return success_response(result.response, result.status_code)


@router.get(
    "/conversations",
    response_model=ApiResponse[list[ConversationResponse]],
)
async def get_conversations(
    student: Annotated[User, Depends(get_current_student)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    conversations = await list_conversations(session, student.id, limit, offset)
    return success_response(conversations, status.HTTP_200_OK)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[MessagePageResponse],
)
async def get_messages(
    conversation_id: UUID,
    student: Annotated[User, Depends(get_current_student)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    messages = await list_conversation_messages(
        session, student.id, conversation_id, limit, offset
    )
    return success_response(messages, status.HTTP_200_OK)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[ChatTurnResponse],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"description": "Previously saved idempotent turn"},
        status.HTTP_202_ACCEPTED: {"description": "The original turn is pending"},
        status.HTTP_409_CONFLICT: {
            "description": "Idempotency conflict or another turn is in progress"
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The teacher or safety policy rejected the request"
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "The AI service is unavailable; failed state was saved"
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "description": "The AI provider timed out; failed state was saved"
        },
    },
)
async def post_message(
    conversation_id: UUID,
    request: MessageCreateRequest,
    response: Response,
    ai_client: Annotated[httpx.AsyncClient, Depends(get_ai_http_client)],
    student: Annotated[User, Depends(get_current_student)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await submit_chat_message(
        session, student, conversation_id, request, ai_client
    )
    response.status_code = result.status_code
    return success_response(result.response, result.status_code)
