"""add conference_rooms.price_per_day

Revision ID: 20260511_0007
Revises: 20260507_0006
Create Date: 2026-05-11 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260511_0007"
down_revision: Union[str, Sequence[str], None] = "20260507_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "conference_rooms" not in existing_tables:
        return

    columns = {column["name"] for column in inspector.get_columns("conference_rooms")}
    if "price_per_day" not in columns:
        op.add_column(
            "conference_rooms",
            sa.Column(
                "price_per_day",
                sa.DECIMAL(14, 2),
                nullable=False,
                server_default=sa.text("0.00"),
            ),
        )
        op.alter_column("conference_rooms", "price_per_day", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "conference_rooms" not in existing_tables:
        return

    columns = {column["name"] for column in inspector.get_columns("conference_rooms")}
    if "price_per_day" in columns:
        op.drop_column("conference_rooms", "price_per_day")

