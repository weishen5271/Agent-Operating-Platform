"""Add knowledge base isolation.

Revision ID: 20260424_0004
Revises: 20260423_0003
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op

revision = "20260424_0004"
down_revision = "20260423_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_base (
            knowledge_base_code VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            created_by VARCHAR(64) NOT NULL DEFAULT 'system',
            updated_by VARCHAR(64) NOT NULL DEFAULT 'system',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_base_tenant_id ON knowledge_base (tenant_id)"
    )
    op.execute(
        "ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS knowledge_base_code VARCHAR(64) NOT NULL DEFAULT 'knowledge'"
    )
    op.execute(
        """
        UPDATE knowledge_document
        SET knowledge_base_code = 'knowledge'
        WHERE knowledge_base_code IS NULL OR knowledge_base_code = ''
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_document_knowledge_base_code ON knowledge_document (knowledge_base_code)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_document_knowledge_base_code")
    op.execute("ALTER TABLE knowledge_document DROP COLUMN IF EXISTS knowledge_base_code")
    op.execute("DROP TABLE IF EXISTS knowledge_base")
