"""gateway_bridges.secret_hash (F-4: per-bridge shared secret)

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-09-07 00:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing rows have no secret and therefore cannot authenticate
    # (fail-closed) until re-registered/rotated — which is the intended F-4 posture.
    with op.batch_alter_table("gateway_bridges", schema=None) as batch_op:
        batch_op.add_column(sa.Column("secret_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("gateway_bridges", schema=None) as batch_op:
        batch_op.drop_column("secret_hash")
