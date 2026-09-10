"""audit_logs.request_id (request correlation)

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-05 10:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("request_id", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_audit_logs_request_id"), ["request_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_request_id"))
        batch_op.drop_column("request_id")
