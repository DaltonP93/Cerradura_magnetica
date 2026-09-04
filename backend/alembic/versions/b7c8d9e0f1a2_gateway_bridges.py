"""gateway bridges (mTLS-identified local daemons)

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-09-04 16:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_bridges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cert_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cert_fingerprint", name="uq_gateway_bridge_fp"),
    )
    with op.batch_alter_table("gateway_bridges", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_gateway_bridges_organization_id"), ["organization_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("gateway_bridges", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gateway_bridges_organization_id"))
    op.drop_table("gateway_bridges")
