from __future__ import (
    annotations,
)  # it is a python in-built module which is used to postpone evaluating type annotations.

import uuid
from datetime import date, datetime

# SQLAlchemy database column types and helpers.
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)

# Mapped describes a model attribute's Python type; mapped_column defines its
# database column; relationship connects two model objects without adding a column.
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gurukul_be.db.base import Base


class User(Base):
    # Each instance of this class is a row in the PostgreSQL "users" table.
    # Base connects this class to SQLAlchemy's shared model metadata.
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("roll_number", name="uq_users_roll_number"),)

    # Mapped[uuid.UUID] is the Python type of this attribute.
    # Uuid(...) is the corresponding database type.
    # primary_key=True makes it the row's unique identifier.
    # default=uuid.uuid4 asks Python to make a new UUID when a User is created.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Keep the email the user entered. nullable=False means the database
    # rejects a user row without an email. String(320) sets its maximum length.
    email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Store a normalized copy for reliable account lookup and uniqueness.
    # For example, " Alex@Example.com " can be normalized to "alex@example.com".
    # This model defines the column but does NOT normalize the value; the code
    # that registers/logs in a user must set it consistently (trim and lowercase).
    # A unique constraint prevents two users from having the same normalized email.
    email_normalized: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False
    )

    roll_number: Mapped[str] = mapped_column(String(20), nullable=False)

    # Store a password hash, never the original password.
    # None is allowed for accounts that use an external identity provider instead.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The display name is required and limited to 120 characters.
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # SQLAlchemy supplies "active" when application code does not set a status.
    # A later migration can add a database check/enum if allowed statuses need
    # stronger enforcement by PostgreSQL.
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    auth_token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # datetime is the Python type returned for this value.
    # DateTime(timezone=True) stores a timezone-aware timestamp.
    # server_default=func.now() tells PostgreSQL to fill in the current time.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # This is an ORM relationship, not a database column.
    # It lets Python code access user.profile. The StudentProfile class is
    # declared below; the future-annotations import lets us refer to it here.
    # uselist=False tells SQLAlchemy this relationship is one-to-one.
    # The database enforces that with unique=True on StudentProfile.user_id.
    # back_populates links this property to StudentProfile.user below.
    profile: Mapped[StudentProfile | None] = relationship(
        back_populates="user", uselist=False
    )


class StudentProfile(Base):
    # Student-only learning details are stored separately from account/login data.
    __tablename__ = "student_profiles"

    # Every profile row has its own primary key, just like a user row.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # This column points to the id of a row in the users table.
    # ForeignKey makes PostgreSQL reject a profile linked to a nonexistent user.
    # ondelete="CASCADE" means deleting a user also deletes that user's profile.
    # unique=True means a user can have only one profile.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # These are optional student details. nullable=True means they may be empty.
    grade_level: Mapped[str | None] = mapped_column(String(40), nullable=True)

    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)

    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    liked_subjects: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )

    # SQLAlchemy supplies "en" if application code does not set a language.
    preferred_language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False
    )

    # The other side of User.profile. This lets code access profile.user.
    # back_populates makes both sides refer to the same relationship.
    user: Mapped[User] = relationship(back_populates="profile")


class PasswordResetChallenge(Base):
    __tablename__ = "password_reset_challenges"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_password_reset_challenges_user_id"),
        UniqueConstraint(
            "reset_token_hash",
            name="uq_password_reset_challenges_reset_token_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failed_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    request_window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requests_in_window: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_token_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
