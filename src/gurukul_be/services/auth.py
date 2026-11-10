import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gurukul_be.core.config import get_settings
from gurukul_be.models.identity import RefreshToken, StudentProfile, User
from gurukul_be.schemas.auth import LoginRequest, RegisterRequest, UpdateProfileRequest

password_hash = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-user-password")
ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=30)


def _session_secret() -> str:
    settings = get_settings()
    if (
        "replace-me" in settings.SESSION_SECRET.lower()
        or len(settings.SESSION_SECRET) < 32
    ):
        raise RuntimeError("SESSION_SECRET must be set to at least 32 characters")
    return settings.SESSION_SECRET


def _create_access_token(
    user_id: str, token_version: int = 0, expires_in: timedelta = ACCESS_TOKEN_TTL
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "ver": token_version,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, _session_secret(), algorithm="HS256")


def _student_response(user: User) -> dict[str, Any]:
    profile = user.profile
    return {
        "id": user.id,
        "roll_number": user.roll_number,
        "display_name": user.display_name,
        "email": user.email,
        "date_of_birth": profile.date_of_birth if profile else None,
        "grade_level": profile.grade_level if profile else None,
        "phone_number": profile.phone_number if profile else None,
        "liked_subjects": profile.liked_subjects if profile else [],
    }


def _refresh_token_digest(token: str) -> str:
    secret = _session_secret().encode()
    return hmac.new(
        secret, f"refresh-token:{token}".encode(), hashlib.sha256
    ).hexdigest()


def _auth_response(session: AsyncSession, user: User) -> dict[str, Any]:
    refresh_token = secrets.token_urlsafe(48)
    refresh_expires_at = datetime.now(UTC) + REFRESH_TOKEN_TTL
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_refresh_token_digest(refresh_token),
            auth_token_version=user.auth_token_version,
            expires_at=refresh_expires_at,
        )
    )
    return {
        "access_token": _create_access_token(
            str(user.id), user.auth_token_version, ACCESS_TOKEN_TTL
        ),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "student": _student_response(user),
    }


async def register_student(
    session: AsyncSession, request: RegisterRequest
) -> dict[str, Any]:
    _session_secret()
    email = str(request.email).strip()
    normalized_email = email.casefold()
    existing_user = await session.scalar(
        select(User.id).where(User.email_normalized == normalized_email)
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    sequence_value = await session.scalar(
        text("SELECT nextval('student_roll_number_seq')")
    )
    if sequence_value is None:
        raise RuntimeError("Could not allocate a student roll number")
    roll_number = f"GUR-{datetime.now(UTC):%y}-{int(sequence_value):06d}"

    user = User(
        id=uuid.uuid4(),
        email=email,
        email_normalized=normalized_email,
        roll_number=roll_number,
        password_hash=password_hash.hash(request.password),
        display_name=request.display_name,
        status="active",
        auth_token_version=0,
    )
    user.profile = StudentProfile(
        grade_level=str(request.grade_level),
        date_of_birth=request.date_of_birth,
        phone_number=request.phone_number,
        liked_subjects=request.liked_subjects,
    )
    session.add(user)
    auth_data = _auth_response(session, user)

    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        original_error = error.orig
        constraint = getattr(
            getattr(original_error, "diag", None), "constraint_name", ""
        )
        if constraint in {"users_email_normalized_key", "uq_users_email_normalized"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from error
        if constraint == "uq_users_roll_number":
            raise RuntimeError(
                "Could not allocate a unique student roll number"
            ) from error
        raise

    return auth_data


async def login_student(session: AsyncSession, request: LoginRequest) -> dict[str, Any]:
    _session_secret()
    identifier = request.identifier.strip()
    normalized_identifier = identifier.casefold()
    normalized_name = " ".join(identifier.split()).casefold()
    user = await session.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(
            or_(
                User.roll_number == identifier.upper(),
                User.email_normalized == normalized_identifier,
            )
        )
    )
    if user is None:
        name_matches = await session.scalars(
            select(User)
            .options(selectinload(User.profile))
            .where(func.lower(User.display_name) == normalized_name)
            .limit(2)
        )
        matches = name_matches.all()
        if len(matches) == 1:
            user = matches[0]
        elif len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Name is not unique; sign in using roll number or email",
                headers={"WWW-Authenticate": "Bearer"},
            )

    encoded_password = (
        user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
    )
    password_matches = password_hash.verify(request.password, encoded_password)
    if user is None or not password_matches or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid roll number, name, or email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    auth_data = _auth_response(session, user)
    await session.commit()
    return auth_data


async def refresh_student_tokens(
    session: AsyncSession, presented_token: str
) -> dict[str, Any]:
    _session_secret()
    now = datetime.now(UTC)
    token_hash = _refresh_token_digest(presented_token)
    stored_token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await session.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == stored_token.user_id)
        .with_for_update()
    )
    if stored_token.revoked_at is not None:
        if user is not None:
            user.auth_token_version += 1
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if (
        user is None
        or user.status != "active"
        or stored_token.auth_token_version != user.auth_token_version
        or stored_token.expires_at <= now
    ):
        stored_token.revoked_at = now
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stored_token.revoked_at = now
    auth_data = _auth_response(session, user)
    await session.commit()
    return auth_data


async def logout_student(session: AsyncSession, presented_token: str) -> None:
    _session_secret()
    stored_token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == _refresh_token_digest(presented_token))
        .with_for_update()
    )
    if stored_token is not None and stored_token.revoked_at is None:
        stored_token.revoked_at = datetime.now(UTC)
        await session.commit()


async def get_student_by_id(
    session: AsyncSession, user_id: UUID, token_version: int
) -> User:
    user = await session.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == user_id, User.status == "active")
    )
    if user is None or user.auth_token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def update_student_profile(
    session: AsyncSession, user: User, request: UpdateProfileRequest
) -> dict[str, Any]:
    changes = request.model_dump(exclude_unset=True)
    if "display_name" in changes:
        user.display_name = changes["display_name"]

    if user.profile is None:
        user.profile = StudentProfile(liked_subjects=[])
    if "date_of_birth" in changes:
        user.profile.date_of_birth = changes["date_of_birth"]
    if "grade_level" in changes:
        grade_level = changes["grade_level"]
        user.profile.grade_level = str(grade_level) if grade_level is not None else None
    if "liked_subjects" in changes:
        user.profile.liked_subjects = changes["liked_subjects"]
    if "phone_number" in changes:
        user.profile.phone_number = changes["phone_number"]

    await session.commit()
    return _student_response(user)
