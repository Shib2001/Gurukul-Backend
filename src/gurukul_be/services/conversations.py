from datetime import UTC, datetime
from typing import Literal, NoReturn
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gurukul_be.integrations.ai_client import AIServiceError, run_ai_chat
from gurukul_be.models.chat import (
    AIJobRun,
    Conversation,
    Message,
    Subject,
    TeacherBot,
)
from gurukul_be.models.identity import User
from gurukul_be.schemas.catalog import (
    SubjectResponse,
    SubjectSummary,
    TeacherResponse,
    TeacherSummary,
)
from gurukul_be.schemas.conversations import (
    ChatTurnResponse,
    ConversationCreateRequest,
    ConversationResponse,
    LessonStartResponse,
    MessageCreateRequest,
    MessagePageResponse,
    MessageResponse,
)
from gurukul_be.schemas.internal_ai import (
    CONTRACT_VERSION,
    MAX_CONTEXT_MESSAGES,
    AIChatLimits,
    AIChatMessage,
    AIChatRunRequest,
    AIChatRunResponse,
    AIStudentContext,
)


class ChatSubmissionResult:
    def __init__(
        self, response: ChatTurnResponse | LessonStartResponse, status_code: int
    ) -> None:
        self.response = response
        self.status_code = status_code


def _conversation_response(
    conversation: Conversation, teacher: TeacherBot, subject: Subject
) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        subject=SubjectSummary(id=subject.id, name=subject.name),
        teacher=TeacherSummary(
            id=teacher.id,
            subject_id=teacher.subject_id,
            display_name=teacher.display_name,
        ),
        title=conversation.title,
        status=conversation.status,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        content_format=message.content_format,
        status=message.status,
        client_message_id=(
            UUID(message.client_message_id) if message.client_message_id else None
        ),
        reply_to_message_id=message.reply_to_message_id,
        failure_code=message.failure_code,
        citations=message.citations or [],
        created_at=message.created_at,
        completed_at=message.completed_at,
    )


def _chat_turn_response(
    conversation_id: UUID, user_message: Message, assistant_message: Message
) -> ChatTurnResponse:
    return ChatTurnResponse(
        conversation_id=conversation_id,
        user_message=_message_response(user_message),
        assistant_message=_message_response(assistant_message),
    )


def _raise_saved_failure(
    failure_code: str | None,
    request_id: str,
    assistant_message: Message,
    conversation_id: UUID,
    user_message: Message | None = None,
) -> NoReturn:
    known_errors = {
        "AI_PROVIDER_TIMEOUT": (
            status.HTTP_504_GATEWAY_TIMEOUT,
            "The AI teacher timed out. Your question was saved.",
        ),
        "AI_PROVIDER_UNAVAILABLE": (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI teacher is temporarily unavailable. Your question was saved.",
        ),
        "AI_POLICY_BLOCKED": (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The AI teacher could not answer this request.",
        ),
    }
    status_code, message = known_errors.get(
        failure_code or "",
        (
            status.HTTP_502_BAD_GATEWAY,
            "The AI service could not complete this request.",
        ),
    )
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": failure_code or "AI_INTERNAL_ERROR",
            "message": message,
            "request_id": request_id,
            "conversation_id": str(conversation_id),
            "user_message_id": str(user_message.id) if user_message else None,
            "assistant_message_id": str(assistant_message.id),
        },
    )


def _teacher_response(teacher: TeacherBot) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        display_name=teacher.display_name,
        description=teacher.description,
        min_grade=teacher.min_grade,
        max_grade=teacher.max_grade,
        supported_languages=teacher.supported_languages,
        capabilities=teacher.capabilities,
    )


async def list_subjects(session: AsyncSession) -> list[SubjectResponse]:
    result = await session.execute(
        select(Subject, TeacherBot)
        .join(TeacherBot, TeacherBot.subject_id == Subject.id)
        .where(
            Subject.status == "published",
            TeacherBot.status == "enabled",
        )
        .order_by(Subject.display_order, Subject.name)
    )
    return [
        SubjectResponse(
            id=subject.id,
            slug=subject.slug,
            name=subject.name,
            description=subject.description,
            teacher=_teacher_response(teacher),
        )
        for subject, teacher in result.all()
    ]


async def create_conversation(
    session: AsyncSession,
    student: User,
    request: ConversationCreateRequest,
    ai_client: httpx.AsyncClient,
) -> ChatSubmissionResult:
    existing_conversation = await session.scalar(
        select(Conversation).where(
            Conversation.student_id == student.id,
            Conversation.client_conversation_id == str(request.client_conversation_id),
        )
    )
    if existing_conversation is not None:
        return await _existing_lesson_start(session, existing_conversation, request)

    teacher = await session.scalar(
        select(TeacherBot)
        .join(Subject, TeacherBot.subject_id == Subject.id)
        .where(
            TeacherBot.subject_id == request.subject_id,
            TeacherBot.status == "enabled",
            Subject.status == "published",
        )
    )
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected subject is not available",
        )
    subject = await session.get(Subject, teacher.subject_id)
    if subject is None or subject.status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected subject is not available",
        )
    if teacher.id != "teacher_math" or subject.id != "subject_math":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The first lesson slice currently supports Mathematics only",
        )
    grade = _student_grade(student)
    if not teacher.min_grade <= grade <= teacher.max_grade:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected teacher does not support your grade",
        )
    language = student.profile.preferred_language if student.profile else "en"
    if language not in teacher.supported_languages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected teacher does not support your preferred language",
        )

    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        student_id=student.id,
        client_conversation_id=str(request.client_conversation_id),
        teacher_bot_id=teacher.id,
        status="open",
        last_message_at=now,
    )
    assistant_message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="",
        content_format="markdown",
        status="pending",
        created_at=now,
    )
    request_id = f"req_{uuid4().hex}"
    idempotency_key = f"{conversation.id}:lesson-start"
    run = AIJobRun(
        conversation_id=conversation.id,
        request_id=request_id,
        message_id=assistant_message.id,
        teacher_bot_id=teacher.id,
        operation="lesson_start",
        status="pending",
        contract_version=CONTRACT_VERSION,
        policy_versions=_teacher_policy_versions(teacher),
    )
    session.add_all([conversation, assistant_message, run])
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_conversation = await session.scalar(
            select(Conversation).where(
                Conversation.student_id == student.id,
                Conversation.client_conversation_id
                == str(request.client_conversation_id),
            )
        )
        if existing_conversation is None:
            raise
        return await _existing_lesson_start(session, existing_conversation, request)
    await session.refresh(assistant_message)

    await _execute_lesson_run(
        session=session,
        student=student,
        conversation=conversation,
        teacher=teacher,
        subject=subject,
        messages=[],
        operation="lesson_start",
        idempotency_key=idempotency_key,
        request_id=request_id,
        assistant_message=assistant_message,
        run=run,
        ai_client=ai_client,
    )
    return ChatSubmissionResult(
        LessonStartResponse(
            conversation=_conversation_response(conversation, teacher, subject),
            opening_message=_message_response(assistant_message),
        ),
        status.HTTP_201_CREATED,
    )


async def _existing_lesson_start(
    session: AsyncSession,
    conversation: Conversation,
    request: ConversationCreateRequest,
) -> ChatSubmissionResult:
    teacher = await session.scalar(
        select(TeacherBot).where(TeacherBot.id == conversation.teacher_bot_id)
    )
    subject = await session.get(Subject, request.subject_id)
    if teacher is None or subject is None:
        raise RuntimeError("Persisted conversation catalog records are missing")
    if teacher.subject_id != request.subject_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="client_conversation_id was already used for a different subject",
        )
    assistant_message = await session.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "assistant",
            Message.reply_to_message_id.is_(None),
        )
        .order_by(Message.created_at, Message.id)
    )
    if assistant_message is None:
        raise RuntimeError("Persisted lesson start has no opening message")
    run = await session.scalar(
        select(AIJobRun).where(AIJobRun.message_id == assistant_message.id)
    )
    if assistant_message.status in {"failed", "blocked"}:
        _raise_saved_failure(
            assistant_message.failure_code,
            run.request_id if run else "unknown",
            assistant_message,
            conversation.id,
        )
    return ChatSubmissionResult(
        LessonStartResponse(
            conversation=_conversation_response(conversation, teacher, subject),
            opening_message=_message_response(assistant_message),
        ),
        status.HTTP_202_ACCEPTED
        if assistant_message.status == "pending"
        else status.HTTP_200_OK,
    )


def _teacher_policy_versions(teacher: TeacherBot) -> dict[str, str]:
    return {
        "safety": "1",
        "teacher": teacher.prompt_policy_version,
        "retrieval": teacher.retrieval_policy_version,
    }


async def _execute_lesson_run(
    *,
    session: AsyncSession,
    student: User,
    conversation: Conversation,
    teacher: TeacherBot,
    subject: Subject,
    messages: list[AIChatMessage],
    operation: Literal["lesson_start", "lesson_turn"],
    idempotency_key: str,
    request_id: str,
    assistant_message: Message,
    run: AIJobRun,
    ai_client: httpx.AsyncClient,
) -> AIChatRunResponse:
    grade = _student_grade(student)
    language = student.profile.preferred_language if student.profile else "en"
    ai_request = AIChatRunRequest(
        request_id=request_id,
        idempotency_key=idempotency_key,
        operation=operation,
        user_ref=str(student.id),
        conversation_ref=str(conversation.id),
        teacher_bot_id="teacher_math",
        subject_id="subject_math",
        student_context=AIStudentContext(
            grade_level=str(grade),
            language=language,
        ),
        messages=messages,
        lesson_state=conversation.lesson_state,
        limits=AIChatLimits(),
        policy_versions=_teacher_policy_versions(teacher),
    )
    started_at = datetime.now(UTC)
    try:
        ai_result = await run_ai_chat(ai_request, ai_client)
    except AIServiceError as error:
        finished_at = datetime.now(UTC)
        assistant_message.status = (
            "blocked" if error.code == "AI_POLICY_BLOCKED" else "failed"
        )
        assistant_message.failure_code = error.code
        assistant_message.completed_at = finished_at
        run.status = assistant_message.status
        run.failure_code = error.code
        run.latency_ms = int((finished_at - started_at).total_seconds() * 1000)
        run.completed_at = finished_at
        await session.commit()
        _raise_saved_failure(
            error.code,
            request_id,
            assistant_message,
            conversation.id,
        )

    finished_at = datetime.now(UTC)
    assistant_message.content = ai_result.content.text
    assistant_message.content_format = ai_result.content.format
    assistant_message.citations = ai_result.citations
    assistant_message.status = "completed"
    assistant_message.completed_at = finished_at
    run.status = "completed"
    run.provider_run_id = ai_result.run_id
    run.model_route = ai_result.model.logical_route
    run.input_tokens = ai_result.usage.input_tokens
    run.output_tokens = ai_result.usage.output_tokens
    run.estimated_cost = ai_result.usage.estimated_cost
    run.safety_status = ai_result.safety.status
    run.policy_versions = ai_result.policy_versions or run.policy_versions
    run.latency_ms = int((finished_at - started_at).total_seconds() * 1000)
    run.completed_at = finished_at
    conversation.lesson_state = ai_result.lesson_progress.model_dump()
    conversation.last_message_at = finished_at
    await session.commit()
    await session.refresh(assistant_message)
    return ai_result


async def list_conversations(
    session: AsyncSession, student_id: UUID, limit: int, offset: int
) -> list[ConversationResponse]:
    result = await session.execute(
        select(Conversation, TeacherBot, Subject)
        .join(TeacherBot, Conversation.teacher_bot_id == TeacherBot.id)
        .join(Subject, TeacherBot.subject_id == Subject.id)
        .where(Conversation.student_id == student_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        _conversation_response(conversation, teacher, subject)
        for conversation, teacher, subject in result.all()
    ]


async def list_conversation_messages(
    session: AsyncSession,
    student_id: UUID,
    conversation_id: UUID,
    limit: int,
    offset: int,
) -> MessagePageResponse:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.student_id == student_id,
        )
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    result = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .limit(limit + 1)
        .offset(offset)
    )
    rows = result.all()
    return MessagePageResponse(
        messages=[_message_response(message) for message in rows[:limit]],
        limit=limit,
        offset=offset,
        has_more=len(rows) > limit,
    )


def _student_grade(student: User) -> int:
    grade_value = student.profile.grade_level if student.profile else None
    try:
        grade = int(grade_value) if grade_value is not None else 0
    except ValueError:
        grade = 0
    if not 1 <= grade <= 10:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Set a valid grade from 1 to 10 in your student profile first",
        )
    return grade


def _message_to_ai(message: Message) -> AIChatMessage:
    if message.created_at is None:
        raise RuntimeError("Persisted chat messages must have a creation timestamp")
    return AIChatMessage(
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


async def submit_chat_message(
    session: AsyncSession,
    student: User,
    conversation_id: UUID,
    request: MessageCreateRequest,
    ai_client: httpx.AsyncClient,
) -> ChatSubmissionResult:
    conversation = await session.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.student_id == student.id,
        )
        .with_for_update()
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if conversation.status != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This conversation is not open",
        )

    existing_user_message = await session.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.client_message_id == str(request.client_message_id),
            Message.role == "user",
        )
    )
    if existing_user_message is not None:
        if existing_user_message.content != request.content:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="client_message_id was already used for a different message",
            )
        assistant_message = await session.scalar(
            select(Message).where(
                Message.reply_to_message_id == existing_user_message.id,
                Message.role == "assistant",
            )
        )
        if assistant_message is None:
            raise RuntimeError("A persisted user turn is missing its assistant record")
        run = await session.scalar(
            select(AIJobRun).where(AIJobRun.message_id == assistant_message.id)
        )
        if assistant_message.status in {"failed", "blocked"}:
            _raise_saved_failure(
                assistant_message.failure_code,
                run.request_id if run else "unknown",
                assistant_message,
                conversation_id,
                existing_user_message,
            )
        result = _chat_turn_response(
            conversation_id, existing_user_message, assistant_message
        )
        return ChatSubmissionResult(
            result,
            status.HTTP_202_ACCEPTED
            if assistant_message.status == "pending"
            else status.HTTP_200_OK,
        )

    pending_assistant = await session.scalar(
        select(Message)
        .join(
            Conversation,
            Message.conversation_id == Conversation.id,
        )
        .where(
            Conversation.id == conversation_id,
            Message.role == "assistant",
            Message.status == "pending",
        )
    )
    if pending_assistant is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for the current teacher response before sending another message",
        )

    teacher = await session.scalar(
        select(TeacherBot).where(
            TeacherBot.id == conversation.teacher_bot_id,
            TeacherBot.status == "enabled",
        )
    )
    subject = (
        await session.get(Subject, teacher.subject_id) if teacher is not None else None
    )
    if teacher is None or subject is None or subject.status != "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The teacher for this conversation is no longer available",
        )
    if teacher.id != "teacher_math" or subject.id != "subject_math":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This chat slice currently supports the Mathematics teacher only",
        )

    grade = _student_grade(student)
    if not teacher.min_grade <= grade <= teacher.max_grade:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected teacher does not support your grade",
        )
    language = student.profile.preferred_language if student.profile else "en"
    if language not in teacher.supported_languages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected teacher does not support your preferred language",
        )

    now = datetime.now(UTC)
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    user_message = Message(
        id=user_message_id,
        conversation_id=conversation_id,
        role="user",
        content=request.content,
        content_format="text",
        status="completed",
        client_message_id=str(request.client_message_id),
        created_at=now,
        completed_at=now,
    )
    assistant_message = Message(
        id=assistant_message_id,
        conversation_id=conversation_id,
        role="assistant",
        content="",
        content_format="markdown",
        status="pending",
        reply_to_message_id=user_message_id,
        created_at=now,
    )
    request_id = f"req_{uuid4().hex}"
    idempotency_key = f"{conversation_id}:{request.client_message_id}"
    run = AIJobRun(
        conversation_id=conversation_id,
        request_id=request_id,
        message_id=assistant_message_id,
        teacher_bot_id=teacher.id,
        operation="lesson_turn",
        status="pending",
        contract_version=CONTRACT_VERSION,
        policy_versions=_teacher_policy_versions(teacher),
    )
    conversation.last_message_at = now
    session.add_all([user_message, assistant_message, run])
    await session.commit()
    await session.refresh(user_message)

    previous_result = await session.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.status == "completed",
            Message.role.in_(("user", "assistant")),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(MAX_CONTEXT_MESSAGES)
    )
    context_messages = list(reversed(previous_result.all()))
    await _execute_lesson_run(
        session=session,
        student=student,
        conversation=conversation,
        teacher=teacher,
        subject=subject,
        messages=[_message_to_ai(message) for message in context_messages],
        operation="lesson_turn",
        idempotency_key=idempotency_key,
        request_id=request_id,
        assistant_message=assistant_message,
        run=run,
        ai_client=ai_client,
    )

    return ChatSubmissionResult(
        _chat_turn_response(conversation_id, user_message, assistant_message),
        status.HTTP_201_CREATED,
    )
