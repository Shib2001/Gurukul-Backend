from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from gurukul_be.api.responses import success_response
from gurukul_be.db.session import get_db
from gurukul_be.models.identity import User
from gurukul_be.schemas.auth import (
    AuthData,
    EmailVerificationRequest,
    EmailVerificationResendData,
    EmailVerificationResendRequest,
    LoginRequest,
    MessageData,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestData,
    PasswordResetTokenData,
    PasswordResetVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    RegistrationPendingData,
    StudentResponse,
    UpdateProfileRequest,
)
from gurukul_be.schemas.common import ApiResponse
from gurukul_be.services.auth import (
    _session_secret,
    _student_response,
    get_student_by_id,
    login_student,
    logout_student,
    refresh_student_tokens,
    register_student,
    resend_email_verification_code,
    update_student_profile,
    verify_student_email,
)
from gurukul_be.services.password_reset import (
    request_password_reset_code,
    reset_student_password,
    verify_password_reset_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer()


@router.post(
    "/register",
    response_model=ApiResponse[RegistrationPendingData],
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def register(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    return success_response(
        await register_student(session, request, background_tasks),
        status.HTTP_202_ACCEPTED,
    )


@router.post("/verify-email", response_model=ApiResponse[AuthData])
async def verify_email(
    request: EmailVerificationRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await verify_student_email(session, request.identifier, request.code)
    return success_response(result, status.HTTP_200_OK)


@router.post(
    "/verify-email/resend",
    response_model=ApiResponse[EmailVerificationResendData],
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_verification_email(
    request: EmailVerificationResendRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await resend_email_verification_code(
        session, request.identifier, background_tasks
    )
    return success_response(result, status.HTTP_202_ACCEPTED)


@router.post("/login", response_model=ApiResponse[AuthData])
async def login(
    request: LoginRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, object]:
    return success_response(await login_student(session, request), status.HTTP_200_OK)


@router.post("/refresh", response_model=ApiResponse[AuthData])
async def refresh(
    request: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await refresh_student_tokens(session, request.refresh_token)
    return success_response(result, status.HTTP_200_OK)


@router.post(
    "/logout",
    response_model=ApiResponse[MessageData],
)
async def logout(
    request: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    await logout_student(session, request.refresh_token)
    return success_response(
        {"message": "You have been signed out."}, status.HTTP_200_OK
    )


async def get_current_student(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    secret = _session_secret()
    try:
        claims = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
        )
        subject = claims.get("sub")
        if not isinstance(subject, str):
            raise TypeError("Token subject must be a UUID")
        user_id = UUID(subject)
        token_version = claims.get("ver", 0)
        if isinstance(token_version, bool) or not isinstance(token_version, int):
            raise TypeError("Token version must be an integer")
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user = await get_student_by_id(session, user_id, token_version)
    return user


@router.get("/me", response_model=ApiResponse[StudentResponse])
async def get_me(
    user: Annotated[User, Depends(get_current_student)],
) -> dict[str, object]:
    return success_response(_student_response(user), status.HTTP_200_OK)


@router.patch("/me", response_model=ApiResponse[StudentResponse])
async def update_me(
    request: UpdateProfileRequest,
    user: Annotated[User, Depends(get_current_student)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    updated_profile = await update_student_profile(session, user, request)
    return success_response(updated_profile, status.HTTP_200_OK)


@router.post(
    "/password-reset/request",
    response_model=ApiResponse[PasswordResetRequestData],
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await request_password_reset_code(
        session, request.identifier, background_tasks
    )
    return success_response(result, status.HTTP_202_ACCEPTED)


@router.post(
    "/password-reset/verify",
    response_model=ApiResponse[PasswordResetTokenData],
)
async def verify_password_reset(
    request: PasswordResetVerifyRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await verify_password_reset_code(session, request.identifier, request.code)
    return success_response(result, status.HTTP_200_OK)


@router.post(
    "/password-reset/confirm",
    response_model=ApiResponse[MessageData],
)
async def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    result = await reset_student_password(
        session, request.reset_token, request.new_password
    )
    return success_response(result, status.HTTP_200_OK)
