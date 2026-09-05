"""dual approval for critical doors

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-03 12:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("doors", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "requires_dual_approval",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.create_table(
        "door_open_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("door_id", sa.Integer(), nullable=False),
        sa.Column("controller_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "EXECUTED", "REJECTED", "EXPIRED", "FAILED",
                name="dooropenrequeststatus",
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["door_id"], ["doors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controller_id"], ["controllers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("door_open_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_door_open_requests_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_door_open_requests_door_id"), ["door_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_door_open_requests_status"), ["status"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("door_open_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_door_open_requests_status"))
        batch_op.drop_index(batch_op.f("ix_door_open_requests_door_id"))
        batch_op.drop_index(batch_op.f("ix_door_open_requests_organization_id"))
    op.drop_table("door_open_requests")

    with op.batch_alter_table("doors", schema=None) as batch_op:
        batch_op.drop_column("requires_dual_approval")

    sa.Enum(name="dooropenrequeststatus").drop(op.get_bind(), checkfirst=True)
