from datetime import date
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


def _normalize_display_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("Student name cannot be blank")
    return normalized


def _validate_date_of_birth(value: date) -> date:
    if value >= date.today():
        raise ValueError("Date of birth must be in the past")
    return value


def _normalize_phone_number(value: str) -> str:
    normalized = "".join(
        character for character in value if character.isdigit() or character == "+"
    )
    digits = normalized.removeprefix("+")
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise ValueError("Enter a phone number containing 7 to 15 digits")
    return normalized


def _validate_liked_subjects(value: list[str]) -> list[str]:
    subjects = [" ".join(subject.split()) for subject in value]
    if any(not subject or len(subject) > 50 for subject in subjects):
        raise ValueError("Subjects must contain between 1 and 50 characters")
    if len({subject.casefold() for subject in subjects}) != len(subjects):
        raise ValueError("Subjects must not be duplicated")
    return subjects


class RegisterRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    grade_level: int = Field(ge=1, le=10)
    liked_subjects: list[str] = Field(min_length=1, max_length=20)
    phone_number: str = Field(min_length=7, max_length=20)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return _normalize_display_name(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date) -> date:
        return _validate_date_of_birth(value)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        return _normalize_phone_number(value)

    @field_validator("liked_subjects")
    @classmethod
    def validate_liked_subjects(cls, value: list[str]) -> list[str]:
        return _validate_liked_subjects(value)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)


class PasswordResetVerifyRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    code: str = Field(pattern=r"^\d{6}$")


class PasswordResetConfirmRequest(BaseModel):
    reset_token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerificationRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    code: str = Field(pattern=r"^\d{6}$")


class EmailVerificationResendRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    roll_number: str
    display_name: str
    email: EmailStr
    date_of_birth: date | None
    grade_level: str | None
    phone_number: str | None
    liked_subjects: list[str]


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    date_of_birth: date | None = None
    grade_level: int | None = Field(default=None, ge=1, le=10)
    liked_subjects: list[str] | None = Field(default=None, min_length=1, max_length=20)
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one profile field to update")
        return self

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Student name cannot be blank")
        return _normalize_display_name(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        return _validate_date_of_birth(value) if value is not None else None

    @field_validator("liked_subjects")
    @classmethod
    def validate_liked_subjects(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            raise ValueError("At least one liked subject is required")
        return _validate_liked_subjects(value)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        return _normalize_phone_number(value) if value is not None else None


class AuthData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    student: StudentResponse


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=128)


class MessageData(BaseModel):
    message: str


class RegistrationPendingData(MessageData):
    email: EmailStr
    roll_number: str
    verification_code: str | None = None


class EmailVerificationResendData(MessageData):
    verification_code: str | None = None


class PasswordResetRequestData(MessageData):
    otp_code: str | None = None


class PasswordResetTokenData(BaseModel):
    reset_token: str
    expires_in_seconds: int
