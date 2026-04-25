"""Add user ownership to conversations.

Revision ID: 20260425_0010
Revises: 20260425_0009
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op


revision = "20260425_0010"
down_revision = "20260425_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversation
            ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT 'admin'
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversation_user_id ON conversation (user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_conversation_user_id")
    op.execute(
        """
        ALTER TABLE conversation
            DROP COLUMN IF EXISTS user_id
        """
    )
