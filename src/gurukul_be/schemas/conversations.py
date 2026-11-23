from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gurukul_be.schemas.catalog import SubjectSummary, TeacherSummary


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1, max_length=50)
    client_conversation_id: UUID


class ConversationResponse(BaseModel):
    id: UUID
    subject: SubjectSummary
    teacher: TeacherSummary
    title: str | None
    status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_message_id: UUID
    content: str = Field(min_length=1, max_length=4000)
    content_format: Literal["text"] = "text"

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message cannot be blank")
        return normalized


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    content_format: str
    status: Literal["pending", "completed", "failed", "blocked"]
    client_message_id: UUID | None
    reply_to_message_id: UUID | None
    failure_code: str | None
    citations: list[dict[str, object]]
    created_at: datetime
    completed_at: datetime | None


class ChatTurnResponse(BaseModel):
    conversation_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse


class MessagePageResponse(BaseModel):
    messages: list[MessageResponse]
    limit: int
    offset: int
    has_more: bool


class LessonStartResponse(BaseModel):
    conversation: ConversationResponse
    opening_message: MessageResponse
