"""user MFA recovery codes (F-5)

Adds a JSON column holding the SHA-256 hashes of the user's unused one-time
recovery codes. Nullable; NULL/absent means the user has no recovery codes.

Revision ID: c5d6e7f8a9b0
Revises: e0f1a2b3c4d5
Create Date: 2026-09-10 12:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mfa_recovery_hashes", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("mfa_recovery_hashes")
