"""gateway command outbox (Fase 3 scaffolding)

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-04 15:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_commands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("controller_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column(
            "type",
            sa.Enum("PING", "OPEN_DOOR", "SYNC_TIME", "SYNC_PERMISSIONS", name="gatewaycommandtype"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "LEASED", "SUCCEEDED", "FAILED", name="gatewaycommandstatus"),
            nullable=False,
        ),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controller_id"], ["controllers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_gateway_command_idem"),
    )
    with op.batch_alter_table("gateway_commands", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_gateway_commands_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_gateway_commands_controller_id"), ["controller_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_gateway_commands_status"), ["status"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("gateway_commands", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_gateway_commands_status"))
        batch_op.drop_index(batch_op.f("ix_gateway_commands_controller_id"))
        batch_op.drop_index(batch_op.f("ix_gateway_commands_organization_id"))
    op.drop_table("gateway_commands")
    sa.Enum(name="gatewaycommandstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="gatewaycommandtype").drop(op.get_bind(), checkfirst=True)
