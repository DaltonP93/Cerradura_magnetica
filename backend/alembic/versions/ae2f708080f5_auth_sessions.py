"""auth sessions and refresh-token generations

Revision ID: ae2f708080f5
Revises: 995243b73005
Create Date: 2026-09-02 13:23:36.018127

"""
import sqlalchemy as sa

from alembic import op

revision = "ae2f708080f5"
down_revision = "995243b73005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("auth_sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_auth_sessions_session_id"), ["session_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_auth_sessions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auth_session_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auth_session_id"], ["auth_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["auth_refresh_tokens.id"],
            name="fk_refresh_replaced_by", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_session_id", "generation", name="uq_refresh_session_generation"),
    )
    with op.batch_alter_table("auth_refresh_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_auth_refresh_tokens_auth_session_id"), ["auth_session_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_auth_refresh_tokens_token_hash"), ["token_hash"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_refresh_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_auth_refresh_tokens_token_hash"))
        batch_op.drop_index(batch_op.f("ix_auth_refresh_tokens_auth_session_id"))
    op.drop_table("auth_refresh_tokens")

    with op.batch_alter_table("auth_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_auth_sessions_user_id"))
        batch_op.drop_index(batch_op.f("ix_auth_sessions_session_id"))
    op.drop_table("auth_sessions")
