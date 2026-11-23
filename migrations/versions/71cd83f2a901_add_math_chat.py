"""add mathematics chat and conversation records

Revision ID: 71cd83f2a901
Revises: 6bc7e9354f21
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "71cd83f2a901"
down_revision: str | Sequence[str] | None = "6bc7e9354f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="published",
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'disabled')",
            name="ck_subjects_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_subjects_slug"),
    )
    op.create_table(
        "teacher_bots",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("subject_id", sa.String(length=50), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("min_grade", sa.Integer(), nullable=False),
        sa.Column("max_grade", sa.Integer(), nullable=False),
        sa.Column("supported_languages", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("prompt_policy_version", sa.String(length=40), nullable=False),
        sa.Column("retrieval_policy_version", sa.String(length=40), nullable=False),
        sa.Column("model_policy_version", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="enabled",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "min_grade >= 1 AND max_grade <= 10 AND min_grade <= max_grade",
            name="ck_teacher_bots_grade_range",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'enabled', 'disabled')",
            name="ck_teacher_bots_status",
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_teacher_bots_slug"),
    )
    op.create_index("ix_teacher_bots_subject_id", "teacher_bots", ["subject_id"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_bot_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="open", nullable=False
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'archived', 'closed')",
            name="ck_conversations_status",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["teacher_bot_id"], ["teacher_bots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_student_id", "conversations", ["student_id"])
    op.create_index(
        "ix_conversations_teacher_bot_id", "conversations", ["teacher_bot_id"]
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_format",
            sa.String(length=20),
            server_default="text",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="completed",
            nullable=False,
        ),
        sa.Column("client_message_id", sa.String(length=36), nullable=True),
        sa.Column("reply_to_message_id", sa.Uuid(), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'blocked')",
            name="ck_messages_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_message_id"], ["messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="uq_messages_conversation_client_message",
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("teacher_bot_id", sa.String(length=50), nullable=True),
        sa.Column(
            "operation",
            sa.String(length=40),
            server_default="tutor_chat",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("contract_version", sa.String(length=20), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("provider_run_id", sa.String(length=80), nullable=True),
        sa.Column("model_route", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("safety_status", sa.String(length=30), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'blocked')",
            name="ck_ai_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["teacher_bot_id"], ["teacher_bots.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_ai_runs_request_id"),
    )
    op.create_index("ix_ai_runs_conversation_id", "ai_runs", ["conversation_id"])
    op.bulk_insert(
        sa.table(
            "subjects",
            sa.column("id", sa.String()),
            sa.column("slug", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("status", sa.String()),
            sa.column("display_order", sa.Integer()),
        ),
        [
            {
                "id": "subject_math",
                "slug": "mathematics",
                "name": "Mathematics",
                "description": "A step-by-step Mathematics tutor for grades 1-10.",
                "status": "published",
                "display_order": 1,
            }
        ],
    )
    op.execute(
        sa.text(
            "INSERT INTO teacher_bots (id, subject_id, slug, display_name, "
            "description, min_grade, max_grade, supported_languages, capabilities, "
            "prompt_policy_version, retrieval_policy_version, model_policy_version, "
            "status) VALUES ('teacher_math', 'subject_math', 'mathematics-tutor', "
            "'Mathematics Teacher', 'A patient, step-by-step Mathematics teacher.', "
            "1, 10, CAST('[\"en\"]' AS JSON), CAST('[\"text_chat\"]' AS JSON), "
            "'math-3', '2', 'tutoring_standard', 'enabled')"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_ai_runs_conversation_id", table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_teacher_bot_id", table_name="conversations")
    op.drop_index("ix_conversations_student_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_teacher_bots_subject_id", table_name="teacher_bots")
    op.drop_table("teacher_bots")
    op.drop_table("subjects")
