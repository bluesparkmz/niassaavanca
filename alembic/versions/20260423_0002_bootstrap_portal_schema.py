"""bootstrap portal schema on top of legacy database

Revision ID: 20260423_0002
Revises: 20260304_0001
Create Date: 2026-04-23 15:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

import models


# revision identifiers, used by Alembic.
revision: str = "20260423_0002"
down_revision: Union[str, Sequence[str], None] = "20260304_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(inspector: sa.Inspector, table_name: str, column: sa.Column) -> None:
    if table_name not in _table_names(inspector):
        return
    if column.name in _column_names(inspector, table_name):
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = _table_names(inspector)

    target_table_names = [
        "companies",
        "lodging_profiles",
        "experience_profiles",
        "restaurant_profiles",
        "producer_profiles",
        "producer_products",
        "company_services",
        "favorites",
        "partner_leads",
        "selo_niassa_requests",
        "notifications",
    ]
    missing_tables = [
        models.Base.metadata.tables[name]
        for name in target_table_names
        if name in models.Base.metadata.tables and name not in existing_tables
    ]
    if missing_tables:
        models.Base.metadata.create_all(bind=bind, tables=missing_tables)
        inspector = inspect(bind)

    if "users" in _table_names(inspector):
        _add_column_if_missing(inspector, "users", sa.Column("full_name", sa.String(length=140), nullable=True))
        inspector = inspect(bind)
        columns = _column_names(inspector, "users")
        if "full_name" in columns:
            if "name" in columns:
                bind.execute(
                    text(
                        """
                        UPDATE users
                        SET full_name = COALESCE(NULLIF(name, ''), split_part(email, '@', 1), 'Utilizador')
                        WHERE full_name IS NULL OR full_name = ''
                        """
                    )
                )
            else:
                bind.execute(
                    text(
                        """
                        UPDATE users
                        SET full_name = COALESCE(split_part(email, '@', 1), 'Utilizador')
                        WHERE full_name IS NULL OR full_name = ''
                        """
                    )
                )
            op.alter_column("users", "full_name", existing_type=sa.String(length=140), nullable=False)

        _add_column_if_missing(inspector, "users", sa.Column("phone", sa.String(length=30), nullable=True))
        _add_column_if_missing(inspector, "users", sa.Column("avatar_url", sa.String(length=255), nullable=True))
        _add_column_if_missing(inspector, "users", sa.Column("password_hash", sa.String(length=255), nullable=True))
        _add_column_if_missing(
            inspector,
            "users",
            sa.Column("role", sa.String(length=20), nullable=False, server_default=sa.text("'customer'")),
        )
        _add_column_if_missing(
            inspector,
            "users",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        _add_column_if_missing(
            inspector,
            "users",
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        _add_column_if_missing(
            inspector,
            "users",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )


def downgrade() -> None:
    pass

