"""add student admission and auth fields

Revision ID: 93bf2e4a6701
Revises: e1d8bfabc727
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "93bf2e4a6701"
down_revision: str | Sequence[str] | None = "e1d8bfabc727"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE student_roll_number_seq START WITH 1")
    op.add_column(
        "users", sa.Column("roll_number", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "student_profiles", sa.Column("date_of_birth", sa.Date(), nullable=True)
    )
    op.add_column(
        "student_profiles",
        sa.Column("phone_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "student_profiles",
        sa.Column(
            "liked_subjects",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )

    op.execute(
        "UPDATE users SET roll_number = "
        "'GUR-' || to_char(created_at, 'YY') || '-' || "
        "lpad(nextval('student_roll_number_seq')::text, 6, '0') "
        "WHERE roll_number IS NULL"
    )
    op.alter_column("users", "roll_number", nullable=False)
    op.create_unique_constraint("uq_users_roll_number", "users", ["roll_number"])


def downgrade() -> None:
    op.drop_constraint("uq_users_roll_number", "users", type_="unique")
    op.drop_column("student_profiles", "liked_subjects")
    op.drop_column("student_profiles", "phone_number")
    op.drop_column("student_profiles", "date_of_birth")
    op.drop_column("users", "roll_number")
    op.execute("DROP SEQUENCE student_roll_number_seq")
