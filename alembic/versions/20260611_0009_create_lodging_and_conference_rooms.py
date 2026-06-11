"""create lodging_rooms and conference_rooms tables if missing

Revision ID: 20260611_0009
Revises: 20260517_0008
Create Date: 2026-06-11 15:00:00
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

import models


revision: str = "20260611_0009"
down_revision: Union[str, Sequence[str], None] = "20260517_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    target_table_names = ["lodging_rooms", "conference_rooms"]
    missing_tables = [
        models.Base.metadata.tables[name]
        for name in target_table_names
        if name in models.Base.metadata.tables and name not in existing_tables
    ]
    if missing_tables:
        models.Base.metadata.create_all(bind=bind, tables=missing_tables)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table_name in ("conference_rooms", "lodging_rooms"):
        if table_name in existing_tables:
            op.drop_table(table_name)
