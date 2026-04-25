"""Split wiki source tables from RAG knowledge tables.

Revision ID: 20260425_0008
Revises: 20260425_0007
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op


revision = "20260425_0008"
down_revision = "20260425_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_source (
            source_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            knowledge_base_code VARCHAR(64) NOT NULL DEFAULT 'knowledge',
            name VARCHAR(255) NOT NULL,
            source_type VARCHAR(64) NOT NULL,
            owner VARCHAR(255) NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(64) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_source_tenant_id ON knowledge_wiki_source (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_source_knowledge_base_code "
        "ON knowledge_wiki_source (knowledge_base_code)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_source_chunk (
            chunk_id VARCHAR(64) PRIMARY KEY,
            source_id VARCHAR(64) NOT NULL REFERENCES knowledge_wiki_source(source_id),
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            chunk_index INTEGER NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            embedding JSON NOT NULL DEFAULT '[]',
            metadata_json JSON NOT NULL DEFAULT '{}',
            token_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(64) NOT NULL DEFAULT 'published',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_source_chunk_source_id "
        "ON knowledge_wiki_source_chunk (source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_source_chunk_tenant_id "
        "ON knowledge_wiki_source_chunk (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_source_chunk_content_hash "
        "ON knowledge_wiki_source_chunk (content_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_source_chunk_status "
        "ON knowledge_wiki_source_chunk (status)"
    )

    # Repoint citation FKs to new wiki tables.
    # User confirmed existing wiki citation/page data can be discarded.
    op.execute("TRUNCATE TABLE knowledge_wiki_citation")
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        DROP CONSTRAINT IF EXISTS knowledge_wiki_citation_source_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        DROP CONSTRAINT IF EXISTS knowledge_wiki_citation_chunk_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        ADD CONSTRAINT knowledge_wiki_citation_source_id_fkey
        FOREIGN KEY (source_id) REFERENCES knowledge_wiki_source(source_id)
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        ADD CONSTRAINT knowledge_wiki_citation_chunk_id_fkey
        FOREIGN KEY (chunk_id) REFERENCES knowledge_wiki_source_chunk(chunk_id)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        DROP CONSTRAINT IF EXISTS knowledge_wiki_citation_source_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        DROP CONSTRAINT IF EXISTS knowledge_wiki_citation_chunk_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        ADD CONSTRAINT knowledge_wiki_citation_source_id_fkey
        FOREIGN KEY (source_id) REFERENCES knowledge_document(source_id)
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_wiki_citation
        ADD CONSTRAINT knowledge_wiki_citation_chunk_id_fkey
        FOREIGN KEY (chunk_id) REFERENCES knowledge_chunk(chunk_id)
        """
    )
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_source_chunk")
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_source")
