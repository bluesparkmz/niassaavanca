"""ensure users.is_admin is optional in app and safe in db

Revision ID: 20260423_0005
Revises: 20260423_0004
Create Date: 2026-04-23 17:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "20260423_0005"
down_revision: Union[str, Sequence[str], None] = "20260423_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "users" not in existing_tables:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" not in columns:
        return

    bind.execute(
        text(
            """
            UPDATE users
            SET is_admin = false
            WHERE is_admin IS NULL
            """
        )
    )

    op.alter_column(
        "users",
        "is_admin",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "users" not in existing_tables:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" not in columns:
        return

    op.alter_column(
        "users",
        "is_admin",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )
