"""desk custody statuses and serial / high-value item fields

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("found_items", "lost_items"):
        op.add_column(
            table,
            sa.Column("is_high_value", sa.Boolean(), server_default="false", nullable=False),
        )
        op.add_column(table, sa.Column("serial_number", sa.String(), nullable=True))
        op.add_column(table, sa.Column("distinctive_marks", sa.String(), nullable=True))

    op.add_column(
        "claims",
        sa.Column("desk_received", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "claims",
        sa.Column("desk_released", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("claims", "desk_released")
    op.drop_column("claims", "desk_received")
    for table in ("lost_items", "found_items"):
        op.drop_column(table, "distinctive_marks")
        op.drop_column(table, "serial_number")
        op.drop_column(table, "is_high_value")
