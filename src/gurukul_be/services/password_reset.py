import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gurukul_be.core.config import Settings, get_settings
from gurukul_be.integrations.email import (
    EmailNotConfiguredError,
    send_password_reset_code,
    validate_email_configuration,
)
from gurukul_be.models.identity import PasswordResetChallenge, User
from gurukul_be.services.auth import _session_secret, password_hash

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
RESET_TOKEN_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
REQUEST_WINDOW = timedelta(hours=1)
MAX_REQUESTS_PER_WINDOW = 3
MAX_CODE_ATTEMPTS = 5
GENERIC_REQUEST_MESSAGE = (
    "If an account exists, a password reset code will be sent to its registered email. "
    "If it does not arrive, wait 60 seconds before requesting another."
)
INVALID_CODE_MESSAGE = (
    "The reset code is invalid or expired. Request a new code and try again."
)
INVALID_TOKEN_MESSAGE = (
    "The reset token is invalid or expired. Request a new code and try again."
)


def _digest(user_id: str, purpose: str, value: str) -> str:
    secret = _session_secret().encode("utf-8")
    message = f"{purpose}:{user_id}:{value}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _invalid_code_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=INVALID_CODE_MESSAGE,
    )


def _invalid_token_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=INVALID_TOKEN_MESSAGE,
    )


async def request_password_reset_code(
    session: AsyncSession, identifier: str, background_tasks: BackgroundTasks
) -> dict[str, str]:
    settings = get_settings()
    return_code = (
        settings.APP_ENV.casefold() == "development"
        and settings.PASSWORD_RESET_RETURN_CODE_IN_RESPONSE
    )
    if not return_code:
        try:
            validate_email_configuration(settings)
        except EmailNotConfiguredError as error:
            logger.error("Password-reset email is not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password reset is temporarily unavailable",
            ) from error

    normalized_identifier = identifier.strip()
    user = await session.scalar(
        select(User)
        .where(
            or_(
                User.email_normalized == normalized_identifier.casefold(),
                User.roll_number == normalized_identifier.upper(),
            )
        )
        .with_for_update()
    )
    if user is None or user.status != "active":
        return {"message": GENERIC_REQUEST_MESSAGE}

    now = datetime.now(UTC)
    challenge = await session.scalar(
        select(PasswordResetChallenge)
        .where(PasswordResetChallenge.user_id == user.id)
        .with_for_update()
    )
    if challenge is not None and now - challenge.last_sent_at < RESEND_COOLDOWN:
        return {"message": GENERIC_REQUEST_MESSAGE}

    if (
        challenge is not None
        and now - challenge.request_window_started_at < REQUEST_WINDOW
    ):
        if challenge.requests_in_window >= MAX_REQUESTS_PER_WINDOW:
            return {"message": GENERIC_REQUEST_MESSAGE}
        challenge.requests_in_window += 1
    else:
        request_count = 1
        if challenge is None:
            challenge = PasswordResetChallenge(
                user_id=user.id,
                code_hash="",
                expires_at=now,
                last_sent_at=now,
                request_window_started_at=now,
                requests_in_window=request_count,
            )
            session.add(challenge)
        else:
            challenge.request_window_started_at = now
            challenge.requests_in_window = request_count

    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge.code_hash = _digest(str(user.id), "reset-code", code)
    challenge.expires_at = now + CODE_TTL
    challenge.failed_attempts = 0
    challenge.last_sent_at = now
    challenge.verified_at = None
    challenge.reset_token_hash = None
    challenge.reset_token_expires_at = None
    challenge.consumed_at = None
    await session.commit()

    if return_code:
        return {"message": GENERIC_REQUEST_MESSAGE, "otp_code": code}

    background_tasks.add_task(_deliver_password_reset_code, user.email, code, settings)
    return {"message": GENERIC_REQUEST_MESSAGE}


def _deliver_password_reset_code(recipient: str, code: str, settings: Settings) -> None:
    try:
        send_password_reset_code(recipient, code, settings)
    except (EmailNotConfiguredError, OSError, smtplib.SMTPException, ValueError):
        logger.exception("Could not deliver a password-reset email")


async def verify_password_reset_code(
    session: AsyncSession, identifier: str, code: str
) -> dict[str, Any]:
    normalized_identifier = identifier.strip()
    user = await session.scalar(
        select(User)
        .where(
            or_(
                User.email_normalized == normalized_identifier.casefold(),
                User.roll_number == normalized_identifier.upper(),
            ),
            User.status == "active",
        )
        .with_for_update()
    )
    if user is None:
        raise _invalid_code_error()

    challenge = await session.scalar(
        select(PasswordResetChallenge)
        .where(PasswordResetChallenge.user_id == user.id)
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.consumed_at is not None
        or challenge.verified_at is not None
        or challenge.expires_at <= now
        or challenge.failed_attempts >= MAX_CODE_ATTEMPTS
    ):
        raise _invalid_code_error()

    submitted_hash = _digest(str(user.id), "reset-code", code)
    if not hmac.compare_digest(challenge.code_hash, submitted_hash):
        challenge.failed_attempts += 1
        if challenge.failed_attempts >= MAX_CODE_ATTEMPTS:
            challenge.expires_at = now
        await session.commit()
        raise _invalid_code_error()

    reset_token = secrets.token_urlsafe(32)
    challenge.verified_at = now
    challenge.reset_token_hash = _digest("", "reset-token", reset_token)
    challenge.reset_token_expires_at = now + RESET_TOKEN_TTL
    await session.commit()
    return {
        "reset_token": reset_token,
        "expires_in_seconds": int(RESET_TOKEN_TTL.total_seconds()),
    }


async def reset_student_password(
    session: AsyncSession, reset_token: str, new_password: str
) -> dict[str, str]:
    token_hash = _digest("", "reset-token", reset_token)
    challenge = await session.scalar(
        select(PasswordResetChallenge).where(
            PasswordResetChallenge.reset_token_hash == token_hash
        )
    )
    if challenge is None:
        raise _invalid_token_error()

    user = await session.scalar(
        select(User)
        .where(User.id == challenge.user_id, User.status == "active")
        .with_for_update()
    )
    locked_challenge = await session.scalar(
        select(PasswordResetChallenge)
        .where(PasswordResetChallenge.id == challenge.id)
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        user is None
        or locked_challenge is None
        or locked_challenge.consumed_at is not None
        or locked_challenge.verified_at is None
        or locked_challenge.reset_token_hash is None
        or not hmac.compare_digest(locked_challenge.reset_token_hash, token_hash)
        or locked_challenge.reset_token_expires_at is None
        or locked_challenge.reset_token_expires_at <= now
    ):
        raise _invalid_token_error()

    user.password_hash = password_hash.hash(new_password)
    user.auth_token_version += 1
    locked_challenge.consumed_at = now
    locked_challenge.reset_token_hash = None
    await session.commit()
    return {
        "message": "Your password has been reset. Please sign in with your new password."
    }
