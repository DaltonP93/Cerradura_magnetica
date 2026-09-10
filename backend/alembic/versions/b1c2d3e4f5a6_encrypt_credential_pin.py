"""encrypt credential pin (widen column for ciphertext)

Revision ID: b1c2d3e4f5a6
Revises: ae2f708080f5
Create Date: 2026-09-02 19:05:00.000000

The PIN is now stored encrypted at rest (Fernet ciphertext), which is longer
than the previous 20-char plaintext column, so the column is widened. Any PINs
already stored as plaintext become undecryptable and must be re-entered.
"""
import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "ae2f708080f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("credentials", schema=None) as batch_op:
        batch_op.alter_column(
            "pin",
            existing_type=sa.String(length=20),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("credentials", schema=None) as batch_op:
        batch_op.alter_column(
            "pin",
            existing_type=sa.String(length=255),
            type_=sa.String(length=20),
            existing_nullable=True,
        )
