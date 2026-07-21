"""exchange confirmations and in_process/processed statuses

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("owner_confirmed", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "claims",
        sa.Column("finder_confirmed", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("claims", sa.Column("owner_confirm_token", sa.String(), nullable=True))
    op.add_column("claims", sa.Column("finder_confirm_token", sa.String(), nullable=True))

    # Map legacy statuses onto the new exchange lifecycle.
    op.execute("UPDATE found_items SET status = 'in_process' WHERE status = 'claimed'")
    op.execute("UPDATE lost_items SET status = 'in_process' WHERE status = 'claimed'")
    op.execute("UPDATE claims SET status = 'in_process' WHERE status IN ('pending', 'confirmed')")


def downgrade() -> None:
    op.execute("UPDATE found_items SET status = 'claimed' WHERE status = 'in_process'")
    op.execute("UPDATE lost_items SET status = 'claimed' WHERE status = 'in_process'")
    op.execute("UPDATE claims SET status = 'pending' WHERE status = 'in_process'")
    op.execute("UPDATE found_items SET status = 'claimed' WHERE status = 'processed'")
    op.execute("UPDATE lost_items SET status = 'claimed' WHERE status = 'processed'")
    op.execute("UPDATE claims SET status = 'confirmed' WHERE status = 'processed'")

    op.drop_column("claims", "finder_confirm_token")
    op.drop_column("claims", "owner_confirm_token")
    op.drop_column("claims", "finder_confirmed")
    op.drop_column("claims", "owner_confirmed")
