"""fix users is_admin compatibility

Revision ID: 20260423_0004
Revises: 20260423_0003
Create Date: 2026-04-23 16:35:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "20260423_0004"
down_revision: Union[str, Sequence[str], None] = "20260423_0003"
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
        op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=True))

    bind.execute(
        text(
            """
            UPDATE users
            SET is_admin = COALESCE(is_admin, false)
            WHERE is_admin IS NULL
            """
        )
    )


def downgrade() -> None:
    pass

