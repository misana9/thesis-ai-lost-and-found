"""add found_items and lost_items tables

Revision ID: a1b2c3d4e5f6
Revises: 706b2e252e68
Create Date: 2026-07-12 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "706b2e252e68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "found_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("date_found", sa.String(), nullable=True),
        sa.Column("time_found", sa.String(), nullable=True),
        sa.Column("reported_by", sa.String(), nullable=True),
        sa.Column("finder_email", sa.String(), nullable=True),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("image_embedding", sa.JSON(), nullable=True),
        sa.Column("text_embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "lost_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("date_lost", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("image_embedding", sa.JSON(), nullable=True),
        sa.Column("text_embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("lost_items")
    op.drop_table("found_items")
