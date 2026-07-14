"""enable pgvector and evolve item tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-14 08:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False))

    op.add_column("found_items", sa.Column("finder_user_id", sa.Integer(), nullable=True))
    op.add_column("found_items", sa.Column("status", sa.String(), server_default="available", nullable=False))
    op.add_column("found_items", sa.Column("claimed_by_lost_id", sa.String(), nullable=True))
    op.create_foreign_key("fk_found_finder_user", "found_items", "users", ["finder_user_id"], ["id"])

    op.add_column("lost_items", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.add_column("lost_items", sa.Column("status", sa.String(), server_default="open", nullable=False))
    op.create_foreign_key("fk_lost_owner_user", "lost_items", "users", ["owner_user_id"], ["id"])

    # Replace JSON embeddings with pgvector columns
    op.drop_column("found_items", "image_embedding")
    op.drop_column("found_items", "text_embedding")
    op.add_column("found_items", sa.Column("image_embedding", Vector(512), nullable=True))
    op.add_column("found_items", sa.Column("text_embedding", Vector(512), nullable=True))

    op.drop_column("lost_items", "image_embedding")
    op.drop_column("lost_items", "text_embedding")
    op.add_column("lost_items", sa.Column("image_embedding", Vector(512), nullable=True))
    op.add_column("lost_items", sa.Column("text_embedding", Vector(512), nullable=True))

    op.create_table(
        "claims",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("found_item_id", sa.String(), nullable=False),
        sa.Column("lost_item_id", sa.String(), nullable=False),
        sa.Column("claimed_by_email", sa.String(), nullable=True),
        sa.Column("claimed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("notify_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["found_item_id"], ["found_items.id"]),
        sa.ForeignKeyConstraint(["lost_item_id"], ["lost_items.id"]),
        sa.ForeignKeyConstraint(["claimed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("claims")

    op.drop_column("lost_items", "text_embedding")
    op.drop_column("lost_items", "image_embedding")
    op.add_column("lost_items", sa.Column("text_embedding", sa.JSON(), nullable=True))
    op.add_column("lost_items", sa.Column("image_embedding", sa.JSON(), nullable=True))
    op.drop_constraint("fk_lost_owner_user", "lost_items", type_="foreignkey")
    op.drop_column("lost_items", "status")
    op.drop_column("lost_items", "owner_user_id")

    op.drop_column("found_items", "text_embedding")
    op.drop_column("found_items", "image_embedding")
    op.add_column("found_items", sa.Column("text_embedding", sa.JSON(), nullable=True))
    op.add_column("found_items", sa.Column("image_embedding", sa.JSON(), nullable=True))
    op.drop_constraint("fk_found_finder_user", "found_items", type_="foreignkey")
    op.drop_column("found_items", "claimed_by_lost_id")
    op.drop_column("found_items", "status")
    op.drop_column("found_items", "finder_user_id")

    op.drop_column("users", "is_admin")
