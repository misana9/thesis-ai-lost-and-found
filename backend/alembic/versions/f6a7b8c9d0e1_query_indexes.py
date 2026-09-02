"""indexes for matching, dashboard, and auth lookups

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_users_email_verification_token", "users", ["email_verification_token"])
    op.create_index("ix_found_items_status", "found_items", ["status"])
    op.create_index("ix_found_items_finder_email", "found_items", ["finder_email"])
    op.create_index("ix_found_items_finder_user_id", "found_items", ["finder_user_id"])
    op.create_index("ix_lost_items_status", "lost_items", ["status"])
    op.create_index("ix_lost_items_email", "lost_items", ["email"])
    op.create_index("ix_lost_items_owner_user_id", "lost_items", ["owner_user_id"])
    op.create_index("ix_claims_found_item_id", "claims", ["found_item_id"])
    op.create_index("ix_claims_lost_item_id", "claims", ["lost_item_id"])
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_claimed_by_email", "claims", ["claimed_by_email"])
    op.create_index("ix_claims_owner_confirm_token", "claims", ["owner_confirm_token"])
    op.create_index("ix_claims_finder_confirm_token", "claims", ["finder_confirm_token"])


def downgrade() -> None:
    op.drop_index("ix_claims_finder_confirm_token", table_name="claims")
    op.drop_index("ix_claims_owner_confirm_token", table_name="claims")
    op.drop_index("ix_claims_claimed_by_email", table_name="claims")
    op.drop_index("ix_claims_status", table_name="claims")
    op.drop_index("ix_claims_lost_item_id", table_name="claims")
    op.drop_index("ix_claims_found_item_id", table_name="claims")
    op.drop_index("ix_lost_items_owner_user_id", table_name="lost_items")
    op.drop_index("ix_lost_items_email", table_name="lost_items")
    op.drop_index("ix_lost_items_status", table_name="lost_items")
    op.drop_index("ix_found_items_finder_user_id", table_name="found_items")
    op.drop_index("ix_found_items_finder_email", table_name="found_items")
    op.drop_index("ix_found_items_status", table_name="found_items")
    op.drop_index("ix_users_email_verification_token", table_name="users")
