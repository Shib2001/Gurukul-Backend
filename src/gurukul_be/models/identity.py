from __future__ import annotations #it is a python in-built module which is used to postpone evaluating type annotations.

import uuid
from datetime import datetime

# SQLAlchemy database column types and helpers.
from sqlalchemy import DateTime, ForeignKey, String, Uuid, func

# Mapped describes a model attribute's Python type; mapped_column defines its
# database column; relationship connects two model objects without adding a column.
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gurukul_be.db.base import Base


class User(Base):
    # Each instance of this class is a row in the PostgreSQL "users" table.
    # Base connects this class to SQLAlchemy's shared model metadata.
    __tablename__ = "users"

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

    # Store a password hash, never the original password.
    # None is allowed for accounts that use an external identity provider instead.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The display name is required and limited to 120 characters.
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # SQLAlchemy supplies "active" when application code does not set a status.
    # A later migration can add a database check/enum if allowed statuses need
    # stronger enforcement by PostgreSQL.
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

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

    # SQLAlchemy supplies "en" if application code does not set a language.
    preferred_language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False
    )

    # The other side of User.profile. This lets code access profile.user.
    # back_populates makes both sides refer to the same relationship.
    user: Mapped[User] = relationship(back_populates="profile")