from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "2026-01"
MAX_CONTEXT_MESSAGES = 12
MAX_MESSAGE_LENGTH = 4000
MAX_OUTPUT_TOKENS = 700
MAX_DEADLINE_MS = 20_000


class AIChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    created_at: datetime


class AIStudentContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade_level: str = Field(pattern=r"^(?:[1-9]|10)$")
    language: str = Field(min_length=2, max_length=10)
    learning_preferences: list[str] = Field(default_factory=list, max_length=20)


class AIChatLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_output_tokens: int = Field(
        default=MAX_OUTPUT_TOKENS, ge=1, le=MAX_OUTPUT_TOKENS
    )
    deadline_ms: int = Field(default=MAX_DEADLINE_MS, ge=1, le=MAX_DEADLINE_MS)


class AIChatRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2026-01"] = CONTRACT_VERSION
    request_id: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=100)
    operation: Literal["lesson_start", "lesson_turn"] = "lesson_turn"
    user_ref: str = Field(min_length=1, max_length=80)
    conversation_ref: str = Field(min_length=1, max_length=80)
    teacher_bot_id: Literal["teacher_math"]
    subject_id: Literal["subject_math"]
    student_context: AIStudentContext
    messages: list[AIChatMessage] = Field(max_length=MAX_CONTEXT_MESSAGES)
    lesson_state: dict[str, object] | None = None
    limits: AIChatLimits = Field(default_factory=AIChatLimits)
    policy_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "safety": "1",
            "teacher": "math-3",
            "retrieval": "2",
        }
    )

    @model_validator(mode="after")
    def validate_operation_messages(self) -> Self:
        if self.operation == "lesson_start" and self.messages:
            raise ValueError("A new lesson must start without prior messages")
        if self.operation == "lesson_turn" and (
            not self.messages or self.messages[-1].role != "user"
        ):
            raise ValueError("A lesson turn must end with the student's message")
        if self.operation == "lesson_turn" and self.lesson_state is None:
            raise ValueError("A lesson turn must include the saved lesson state")
        if self.operation == "lesson_start" and self.lesson_state is not None:
            raise ValueError("A new lesson cannot have prior lesson state")
        return self


class LessonProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=120)
    phase: Literal["teaching", "checking_understanding", "completed"]
    understanding: Literal["not_assessed", "correct", "partial", "incorrect", "unclear"]
    next_action: Literal["ask_question", "continue", "reteach", "clarify", "complete"]


class AIChatContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=MAX_MESSAGE_LENGTH)
    format: Literal["markdown", "text"] = "markdown"


class AISafetyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["allowed", "blocked"]
    flags: list[str] = Field(default_factory=list)


class AIUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: Decimal | None = Field(default=None, ge=0)


class AIModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_route: str


class AIChatRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2026-01"]
    run_id: str = Field(min_length=1, max_length=80)
    status: Literal["completed", "blocked"]
    content: AIChatContent
    citations: list[dict[str, object]] = Field(default_factory=list)
    safety: AISafetyResult
    usage: AIUsage
    model: AIModelInfo
    lesson_progress: LessonProgress
    policy_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_terminal_result(self) -> "AIChatRunResponse":
        if self.status == "completed" and not self.content.text.strip():
            raise ValueError("Completed AI runs must include a non-empty answer")
        if self.status == "blocked" and self.safety.status != "blocked":
            raise ValueError("Blocked AI runs must include a blocked safety result")
        return self


class AIErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "AI_PROVIDER_TIMEOUT",
        "AI_PROVIDER_UNAVAILABLE",
        "AI_POLICY_BLOCKED",
        "AI_INVALID_REQUEST",
        "AI_INTERNAL_ERROR",
    ]
    message: str
    retryable: bool
    request_id: str


class AIErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: AIErrorDetail
