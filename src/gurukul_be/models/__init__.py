"""Domain models package."""

from gurukul_be.models.chat import (
    AIJobRun,
    Conversation,
    Message,
    Subject,
    TeacherBot,
)

# This imports those model classes from identity.py and makes them available through the package.
from gurukul_be.models.identity import (
    EmailVerificationChallenge,
    PasswordResetChallenge,
    RefreshToken,
    StudentProfile,
    User,
)

# This import also loads the model definitions. That matters when a tool such as Alembic needs to discover the tables registered with SQLAlchemy.
__all__ = [
    "AIJobRun",
    "Conversation",
    "EmailVerificationChallenge",
    "Message",
    "PasswordResetChallenge",
    "RefreshToken",
    "StudentProfile",
    "Subject",
    "TeacherBot",
    "User",
]
