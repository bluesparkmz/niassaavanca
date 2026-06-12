"""remove unique constraints on lodging_rooms and conference_rooms names

Revision ID: 20260612_0010
Revises: 20260611_0009
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260612_0010"
down_revision: Union[str, Sequence[str], None] = "20260611_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique constraints
    try:
        op.drop_constraint("uq_lodging_room_name", "lodging_rooms", type_="unique")
    except Exception:
        pass  # Ignore if constraint doesn't exist
    try:
        op.drop_constraint("uq_conference_room_name", "conference_rooms", type_="unique")
    except Exception:
        pass  # Ignore if constraint doesn't exist


def downgrade() -> None:
    # Recreate the unique constraints if needed
    try:
        op.create_unique_constraint(
            "uq_lodging_room_name", "lodging_rooms", ["lodging_profile_id", "name"]
        )
    except Exception:
        pass
    try:
        op.create_unique_constraint(
            "uq_conference_room_name", "conference_rooms", ["lodging_profile_id", "name"]
        )
    except Exception:
        pass