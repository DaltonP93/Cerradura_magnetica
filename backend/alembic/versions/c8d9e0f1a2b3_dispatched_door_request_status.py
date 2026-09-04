"""add DISPATCHED to dooropenrequeststatus (dual approval via bridge)

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-04 20:00:00.000000
"""
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Native enum type: add the new value (PG 12+ allows this in a tx as long
        # as the value is not used in the same transaction).
        op.execute("ALTER TYPE dooropenrequeststatus ADD VALUE IF NOT EXISTS 'DISPATCHED'")
    # SQLite/others: the Enum column is stored as a plain VARCHAR without a CHECK
    # constraint, so the new value needs no schema change.


def downgrade() -> None:
    # Removing a value from a PostgreSQL enum requires recreating the type and
    # rewriting the column; the unused value is harmless, so this is a no-op.
    pass
