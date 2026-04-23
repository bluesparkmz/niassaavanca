"""add company social tables

Revision ID: 20260423_0003
Revises: 20260423_0002
Create Date: 2026-04-23 16:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "20260423_0003"
down_revision: Union[str, Sequence[str], None] = "20260423_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "company_likes" not in existing_tables:
        op.create_table(
            "company_likes",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "company_id", name="uq_company_like_user_company"),
        )
        op.create_index("ix_company_likes_id", "company_likes", ["id"], unique=False)
        op.create_index("ix_company_likes_user_id", "company_likes", ["user_id"], unique=False)
        op.create_index("ix_company_likes_company_id", "company_likes", ["company_id"], unique=False)

    if "company_follows" not in existing_tables:
        op.create_table(
            "company_follows",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "company_id", name="uq_company_follow_user_company"),
        )
        op.create_index("ix_company_follows_id", "company_follows", ["id"], unique=False)
        op.create_index("ix_company_follows_user_id", "company_follows", ["user_id"], unique=False)
        op.create_index("ix_company_follows_company_id", "company_follows", ["company_id"], unique=False)

    if "company_comments" not in existing_tables:
        op.create_table(
            "company_comments",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_company_comments_id", "company_comments", ["id"], unique=False)
        op.create_index("ix_company_comments_user_id", "company_comments", ["user_id"], unique=False)
        op.create_index("ix_company_comments_company_id", "company_comments", ["company_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "company_comments" in existing_tables:
        op.drop_index("ix_company_comments_company_id", table_name="company_comments")
        op.drop_index("ix_company_comments_user_id", table_name="company_comments")
        op.drop_index("ix_company_comments_id", table_name="company_comments")
        op.drop_table("company_comments")

    if "company_follows" in existing_tables:
        op.drop_index("ix_company_follows_company_id", table_name="company_follows")
        op.drop_index("ix_company_follows_user_id", table_name="company_follows")
        op.drop_index("ix_company_follows_id", table_name="company_follows")
        op.drop_table("company_follows")

    if "company_likes" in existing_tables:
        op.drop_index("ix_company_likes_company_id", table_name="company_likes")
        op.drop_index("ix_company_likes_user_id", table_name="company_likes")
        op.drop_index("ix_company_likes_id", table_name="company_likes")
        op.drop_table("company_likes")

