"""event external_id for bridge inbox idempotency

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-04 21:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("external_id", sa.String(length=120), nullable=True))
        batch_op.create_unique_constraint(
            "uq_event_org_external", ["organization_id", "external_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("uq_event_org_external", type_="unique")
        batch_op.drop_column("external_id")
