import uuid
from datetime import UTC, date, datetime
from http import HTTPStatus
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from gurukul_be.core.config import Settings
from gurukul_be.integrations.email import EmailNotConfiguredError
from gurukul_be.main import app, http_error_handler
from gurukul_be.models.identity import PasswordResetChallenge, StudentProfile, User
from gurukul_be.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    UpdateProfileRequest,
)
from gurukul_be.services import auth, password_reset

client = TestClient(app)


def valid_registration(**overrides: object) -> RegisterRequest:
    data: dict[str, object] = {
        "display_name": "A Student",
        "date_of_birth": date(2010, 5, 12),
        "grade_level": 10,
        "liked_subjects": ["Mathematics", "Science"],
        "phone_number": "+91 9876543210",
        "email": "student@example.com",
        "password": "a-strong-password",
    }
    data.update(overrides)
    return RegisterRequest.model_validate(data)


def test_registration_schema_normalizes_fields() -> None:
    registration = valid_registration(
        display_name="  A   Student ", phone_number="+91 9876543210"
    )

    assert registration.display_name == "A Student"
    assert registration.phone_number == "+919876543210"
    assert registration.grade_level == 10


@pytest.mark.parametrize("grade", [0, 11])
def test_registration_schema_rejects_grade_outside_range(grade: int) -> None:
    with pytest.raises(ValidationError):
        valid_registration(grade_level=grade)


def test_registration_schema_rejects_duplicate_subjects() -> None:
    with pytest.raises(ValidationError):
        valid_registration(liked_subjects=["Science", " science "])


def test_profile_update_schema_accepts_partial_fields_and_normalizes_values() -> None:
    request = UpdateProfileRequest.model_validate(
        {"display_name": "  A   Student ", "phone_number": "+91 9876543210"}
    )

    assert request.model_dump(exclude_unset=True) == {
        "display_name": "A Student",
        "phone_number": "+919876543210",
    }


@pytest.mark.parametrize("payload", [{}, {"grade_level": 11}, {"liked_subjects": []}])
def test_profile_update_schema_rejects_empty_or_invalid_updates(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        UpdateProfileRequest.model_validate(payload)


def test_auth_routes_are_registered() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/me" in paths
    assert "patch" in paths["/api/v1/auth/me"]
    assert "/api/v1/auth/password-reset/request" in paths
    assert "/api/v1/auth/password-reset/verify" in paths
    assert "/api/v1/auth/password-reset/confirm" in paths
    response_schema = paths["/api/v1/auth/register"]["post"]["responses"]["201"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("ApiResponse_AuthData_")
    auth_data_schema = response.json()["components"]["schemas"]["AuthData"][
        "properties"
    ]
    assert "access_expires_in_seconds" not in auth_data_schema
    assert "refresh_expires_in_seconds" not in auth_data_schema
    assert (
        paths["/api/v1/auth/password-reset/request"]["post"]["responses"]["202"][
            "description"
        ]
        == "Successful Response"
    )


@pytest.mark.asyncio
async def test_profile_update_changes_only_submitted_fields() -> None:
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    profile = StudentProfile(
        date_of_birth=date(2010, 5, 12),
        grade_level="10",
        phone_number="+919876543210",
        liked_subjects=["Mathematics"],
    )
    user.profile = profile
    session = AsyncMock(spec=AsyncSession)
    request = UpdateProfileRequest(display_name="Updated Student", grade_level=9)

    result = await auth.update_student_profile(session, user, request)

    assert user.display_name == "Updated Student"
    assert profile.grade_level == "9"
    assert profile.date_of_birth == date(2010, 5, 12)
    assert profile.phone_number == "+919876543210"
    assert profile.liked_subjects == ["Mathematics"]
    assert result["display_name"] == "Updated Student"
    assert result["grade_level"] == "9"
    session.commit.assert_awaited_once()


def test_short_password_returns_clear_validation_error_without_echoing_password() -> (
    None
):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "A Student",
            "date_of_birth": "2010-05-12",
            "grade_level": 10,
            "liked_subjects": ["Mathematics"],
            "phone_number": "+919876543210",
            "email": "student@example.com",
            "password": "Test123",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["status_code"] == 422
    assert body["message"] == HTTPStatus.UNPROCESSABLE_ENTITY.phrase
    assert body["detail"] == "Request validation failed"
    assert body["errors"] == [
        {
            "field": "password",
            "message": "String should have at least 8 characters",
            "code": "string_too_short",
        }
    ]
    assert "Test123" not in response.text


@pytest.mark.asyncio
async def test_http_errors_include_standard_status_and_reason_phrase() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/missing"})

    response = await http_error_handler(
        request,
        StarletteHTTPException(
            status_code=404, detail="Student was not found", headers={"X-Test": "yes"}
        ),
    )

    assert response.status_code == 404
    assert response.headers["x-test"] == "yes"
    assert response.body == (
        b'{"status_code":404,"message":"Not Found",'
        b'"detail":"Student was not found","errors":[]}'
    )


@pytest.mark.asyncio
async def test_registration_assigns_roll_number_and_persists_admission_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_session_secret", lambda: "s" * 32)
    monkeypatch.setattr(auth, "_create_access_token", lambda *args: "signed-token")
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [None, 42]
    session.add = Mock()

    result = await auth.register_student(session, valid_registration())

    user = session.add.call_args_list[0].args[0]
    assert user.roll_number == "GUR-26-000042"
    assert user.password_hash != "a-strong-password"
    assert auth.password_hash.verify("a-strong-password", user.password_hash)
    assert user.profile.date_of_birth == date(2010, 5, 12)
    assert user.profile.grade_level == "10"
    assert user.profile.phone_number == "+919876543210"
    assert user.profile.liked_subjects == ["Mathematics", "Science"]
    assert result["access_token"] == "signed-token"
    assert len(result["refresh_token"]) >= 64
    assert "access_expires_in_seconds" not in result
    assert "refresh_expires_in_seconds" not in result
    assert result["student"]["roll_number"] == "GUR-26-000042"
    session.commit.assert_awaited_once()
    refresh_record = session.add.call_args_list[-1].args[0]
    assert refresh_record.token_hash != result["refresh_token"]
    assert refresh_record.auth_token_version == user.auth_token_version


@pytest.mark.parametrize(
    "identifier",
    [
        "gur-26-000042",
        "student@example.com",
        "STUDENT@EXAMPLE.COM",
        "a student",
    ],
)
@pytest.mark.asyncio
async def test_login_accepts_roll_number_and_returns_token(
    monkeypatch: pytest.MonkeyPatch, identifier: str
) -> None:
    monkeypatch.setattr(auth, "_session_secret", lambda: "s" * 32)
    monkeypatch.setattr(auth, "_create_access_token", lambda *args: "signed-token")
    student = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        password_hash=auth.password_hash.hash("a-strong-password"),
        display_name="A Student",
        status="active",
    )
    student.profile = StudentProfile(
        date_of_birth=date(2010, 5, 12),
        grade_level="10",
        phone_number="+919876543210",
        liked_subjects=["Mathematics"],
    )
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()
    if identifier.casefold() == "a student":
        session.scalar.return_value = None
        name_matches = Mock()
        name_matches.all.return_value = [student]
        session.scalars.return_value = name_matches
    else:
        session.scalar.return_value = student

    result = await auth.login_student(
        session,
        LoginRequest(identifier=identifier, password="a-strong-password"),
    )

    assert result["access_token"] == "signed-token"
    assert len(result["refresh_token"]) >= 64
    assert result["student"]["email"] == "student@example.com"


@pytest.mark.asyncio
async def test_login_rejects_duplicate_name_and_requests_unique_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_session_secret", lambda: "s" * 32)
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    name_matches = Mock()
    name_matches.all.return_value = [User(), User()]
    session.scalars.return_value = name_matches

    with pytest.raises(HTTPException) as error:
        await auth.login_student(
            session, LoginRequest(identifier="A Student", password="a-strong-password")
        )
    assert error.value.status_code == 401
    assert "Name is not unique" in str(error.value.detail)


def test_password_reset_schemas_validate_code_and_password() -> None:
    assert PasswordResetRequest(identifier="student@example.com").identifier
    assert (
        PasswordResetVerifyRequest(identifier="GUR-26-000042", code="123456").code
        == "123456"
    )
    assert (
        PasswordResetConfirmRequest(
            reset_token="r" * 43, new_password="new-password-123"
        ).new_password
        == "new-password-123"
    )

    with pytest.raises(ValidationError):
        PasswordResetVerifyRequest(identifier="student@example.com", code="12345")
    with pytest.raises(ValidationError):
        PasswordResetConfirmRequest(reset_token="r" * 43, new_password="short")
    assert RefreshRequest(refresh_token="r" * 64).refresh_token


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_session_secret", lambda: "s" * 32)
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
        auth_token_version=2,
    )
    user.profile = StudentProfile(grade_level="10", liked_subjects=["Mathematics"])
    old_token_value = "old-refresh-token"
    old_token = auth.RefreshToken(
        user_id=user.id,
        token_hash=auth._refresh_token_digest(old_token_value),
        auth_token_version=2,
        expires_at=datetime.now(UTC) + auth.REFRESH_TOKEN_TTL,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [old_token, user]
    session.add = Mock()

    result = await auth.refresh_student_tokens(session, old_token_value)

    assert old_token.revoked_at is not None
    new_token = session.add.call_args.args[0]
    assert new_token.token_hash == auth._refresh_token_digest(result["refresh_token"])
    assert result["refresh_token"] != old_token_value
    assert "access_expires_in_seconds" not in result
    assert "refresh_expires_in_seconds" not in result
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_all_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_session_secret", lambda: "s" * 32)
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
        auth_token_version=2,
    )
    reused_token = auth.RefreshToken(
        user_id=user.id,
        token_hash=auth._refresh_token_digest("reused-refresh-token"),
        auth_token_version=2,
        expires_at=datetime.now(UTC) + auth.REFRESH_TOKEN_TTL,
        revoked_at=datetime.now(UTC),
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [reused_token, user]

    with pytest.raises(HTTPException) as error:
        await auth.refresh_student_tokens(session, "reused-refresh-token")

    assert error.value.status_code == 401
    assert user.auth_token_version == 3
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_logout_revokes_only_the_submitted_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_session_secret", lambda: "s" * 32)
    refresh_token = "logout-refresh-token"
    stored_token = auth.RefreshToken(
        user_id=uuid.uuid4(),
        token_hash=auth._refresh_token_digest(refresh_token),
        auth_token_version=0,
        expires_at=datetime.now(UTC) + auth.REFRESH_TOKEN_TTL,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = stored_token

    await auth.logout_student(session, refresh_token)

    assert stored_token.revoked_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_reset_request_is_generic_for_unknown_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_FROM_EMAIL = "no-reply@example.com"
    monkeypatch.setattr(password_reset, "get_settings", lambda: settings)
    monkeypatch.setattr(
        password_reset, "validate_email_configuration", lambda settings: None
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None

    result = await password_reset.request_password_reset_code(
        session, "unknown@example.com", BackgroundTasks()
    )

    assert result["message"] == password_reset.GENERIC_REQUEST_MESSAGE
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_reset_code_is_returned_only_when_dev_override_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(password_reset, "_session_secret", lambda: "s" * 32)
    settings = Settings(PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=True)
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [user, None]
    session.add = Mock()
    background_tasks = BackgroundTasks()
    monkeypatch.setattr(password_reset, "get_settings", lambda: settings)

    result = await password_reset.request_password_reset_code(
        session, user.email, background_tasks
    )

    assert result["message"] == password_reset.GENERIC_REQUEST_MESSAGE
    code = result["otp_code"]
    assert code.isdigit() and len(code) == 6
    assert background_tasks.tasks == []
    challenge = session.add.call_args.args[0]
    assert challenge.code_hash == password_reset._digest(
        str(user.id), "reset-code", code
    )


@pytest.mark.asyncio
async def test_password_reset_code_override_is_ignored_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        APP_ENV="production",
        PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=True,
    )
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_FROM_EMAIL = "no-reply@example.com"
    monkeypatch.setattr(password_reset, "get_settings", lambda: settings)
    monkeypatch.setattr(
        password_reset, "validate_email_configuration", lambda settings: None
    )
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [user, None]
    session.add = Mock()
    background_tasks = BackgroundTasks()

    result = await password_reset.request_password_reset_code(
        session, user.email, background_tasks
    )

    assert result == {"message": password_reset.GENERIC_REQUEST_MESSAGE}
    assert len(background_tasks.tasks) == 1


@pytest.mark.asyncio
async def test_password_reset_unconfigured_email_fails_before_account_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=False)
    monkeypatch.setattr(password_reset, "get_settings", lambda: settings)

    def reject_email_configuration(settings: Settings) -> None:
        raise EmailNotConfiguredError("Email is disabled")

    monkeypatch.setattr(
        password_reset, "validate_email_configuration", reject_email_configuration
    )
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as error:
        await password_reset.request_password_reset_code(
            session, "student@example.com", BackgroundTasks()
        )

    assert error.value.status_code == 503
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_reset_request_schedules_email_and_stores_only_code_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(password_reset, "_session_secret", lambda: "s" * 32)
    settings = Settings(PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=False)
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_FROM_EMAIL = "no-reply@example.com"
    monkeypatch.setattr(password_reset, "get_settings", lambda: settings)
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [user, None]
    session.add = Mock()
    background_tasks = BackgroundTasks()

    result = await password_reset.request_password_reset_code(
        session, user.email, background_tasks
    )

    challenge = session.add.call_args.args[0]
    scheduled_code = background_tasks.tasks[0].args[1]
    assert result["message"] == password_reset.GENERIC_REQUEST_MESSAGE
    assert isinstance(scheduled_code, str)
    assert scheduled_code.isdigit() and len(scheduled_code) == 6
    assert challenge.code_hash == password_reset._digest(
        str(user.id), "reset-code", scheduled_code
    )
    assert len(challenge.code_hash) == 64
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_fifth_incorrect_code_expires_challenge_and_is_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(password_reset, "_session_secret", lambda: "s" * 32)
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    challenge = PasswordResetChallenge(
        user_id=user.id,
        code_hash=password_reset._digest(str(user.id), "reset-code", "123456"),
        expires_at=datetime.now(UTC) + password_reset.CODE_TTL,
        failed_attempts=4,
        last_sent_at=datetime.now(UTC),
        request_window_started_at=datetime.now(UTC),
        requests_in_window=1,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [user, challenge]

    with pytest.raises(HTTPException) as error:
        await password_reset.verify_password_reset_code(session, user.email, "000000")

    assert error.value.status_code == 400
    assert error.value.detail == password_reset.INVALID_CODE_MESSAGE
    assert challenge.failed_attempts == password_reset.MAX_CODE_ATTEMPTS
    assert challenge.expires_at <= datetime.now(UTC)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_reset_verification_returns_single_use_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(password_reset, "_session_secret", lambda: "s" * 32)
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        display_name="A Student",
        status="active",
    )
    challenge = PasswordResetChallenge(
        user_id=user.id,
        code_hash=password_reset._digest(str(user.id), "reset-code", "123456"),
        expires_at=datetime.now(UTC) + password_reset.CODE_TTL,
        failed_attempts=0,
        last_sent_at=datetime.now(UTC),
        request_window_started_at=datetime.now(UTC),
        requests_in_window=1,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [user, challenge]

    result = await password_reset.verify_password_reset_code(
        session, user.email, "123456"
    )

    assert len(result["reset_token"]) >= 32
    assert result["expires_in_seconds"] == 900
    assert challenge.verified_at is not None
    assert challenge.reset_token_hash != result["reset_token"]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_reset_changes_password_and_invalidates_access_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(password_reset, "_session_secret", lambda: "s" * 32)
    reset_token = "one-time-reset-token"
    user = User(
        id=uuid.uuid4(),
        email="student@example.com",
        email_normalized="student@example.com",
        roll_number="GUR-26-000042",
        password_hash=auth.password_hash.hash("old-password-123"),
        display_name="A Student",
        status="active",
        auth_token_version=4,
    )
    challenge = PasswordResetChallenge(
        user_id=user.id,
        code_hash="code-hash",
        expires_at=datetime.now(UTC),
        failed_attempts=0,
        last_sent_at=datetime.now(UTC),
        request_window_started_at=datetime.now(UTC),
        requests_in_window=1,
        verified_at=datetime.now(UTC),
        reset_token_hash=password_reset._digest("", "reset-token", reset_token),
        reset_token_expires_at=datetime.now(UTC) + password_reset.RESET_TOKEN_TTL,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [challenge, user, challenge]

    result = await password_reset.reset_student_password(
        session, reset_token, "new-password-123"
    )

    assert result["message"].startswith("Your password has been reset")
    assert user.password_hash is not None
    assert auth.password_hash.verify("new-password-123", user.password_hash)
    assert not auth.password_hash.verify("old-password-123", user.password_hash)
    assert user.auth_token_version == 5
    assert challenge.consumed_at is not None
    assert challenge.reset_token_hash is None
    session.commit.assert_awaited_once()
