"""add lesson start idempotency and progression state

Revision ID: 2a7f1c90d4b3
Revises: 71cd83f2a901
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2a7f1c90d4b3"
down_revision: str | Sequence[str] | None = "71cd83f2a901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("client_conversation_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("lesson_state", sa.JSON(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE conversations SET client_conversation_id = gen_random_uuid()::text "
            "WHERE client_conversation_id IS NULL"
        )
    )
    op.alter_column(
        "conversations",
        "client_conversation_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_conversations_student_client_id",
        "conversations",
        ["student_id", "client_conversation_id"],
    )
    op.create_unique_constraint(
        "uq_teacher_bots_subject_id",
        "teacher_bots",
        ["subject_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_teacher_bots_subject_id", "teacher_bots", type_="unique")
    op.drop_constraint(
        "uq_conversations_student_client_id", "conversations", type_="unique"
    )
    op.drop_column("conversations", "lesson_state")
    op.drop_column("conversations", "client_conversation_id")
