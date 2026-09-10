"""composite index on events (organization_id, occurred_at)

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-03 13:10:00.000000
"""
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_events_org_occurred", "events", ["organization_id", "occurred_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_events_org_occurred", table_name="events")
