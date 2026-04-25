"""Add generated primary key for knowledge_base.

Revision ID: 20260425_0006
Revises: 20260424_0005
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op

revision = "20260425_0006"
down_revision = "20260424_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS knowledge_base_id VARCHAR(64)")
    op.execute(
        """
        UPDATE knowledge_base
        SET knowledge_base_id = 'kb-' || substr(md5(tenant_id || ':' || knowledge_base_code), 1, 12)
        WHERE knowledge_base_id IS NULL OR knowledge_base_id = ''
        """
    )
    op.execute("ALTER TABLE knowledge_base ALTER COLUMN knowledge_base_id SET NOT NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'knowledge_base_pkey'
                  AND conrelid = 'knowledge_base'::regclass
            ) THEN
                ALTER TABLE knowledge_base DROP CONSTRAINT knowledge_base_pkey;
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TABLE knowledge_base ADD CONSTRAINT knowledge_base_pkey PRIMARY KEY (knowledge_base_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_base_code ON knowledge_base (knowledge_base_code)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_knowledge_base_code")
    op.execute("ALTER TABLE knowledge_base DROP CONSTRAINT IF EXISTS knowledge_base_pkey")
    op.execute("ALTER TABLE knowledge_base ADD CONSTRAINT knowledge_base_pkey PRIMARY KEY (knowledge_base_code)")
    op.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS knowledge_base_id")
