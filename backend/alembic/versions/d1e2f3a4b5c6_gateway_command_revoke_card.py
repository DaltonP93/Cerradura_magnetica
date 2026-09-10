"""gatewaycommandtype: add REVOKE_CARD (auto card revocation to the outbox)

Revision ID: d1e2f3a4b5c6
Revises: e0f1a2b3c4d5
Create Date: 2026-09-07 14:00:00.000000

On PostgreSQL ``gateway_commands.type`` is a native ENUM, so a new member has to
be added to the type with ALTER TYPE (done in an autocommit block, since adding
an enum value cannot run inside a transaction on older servers). On SQLite the
column is a plain VARCHAR (SQLAlchemy's Enum emits no CHECK constraint by
default), so there is nothing to migrate there.
"""
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE gatewaycommandtype ADD VALUE IF NOT EXISTS 'REVOKE_CARD'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it;
    # leaving the unused label in place is harmless, so the downgrade is a no-op.
    pass
