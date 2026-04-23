"""Add knowledge chunks for RAG retrieval.

Revision ID: 20260422_0002
Revises: 20260419_0001
Create Date: 2026-04-22
"""

from __future__ import annotations

from alembic import op

revision = "20260422_0002"
down_revision = "20260419_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunk (
            chunk_id VARCHAR(64) PRIMARY KEY,
            source_id VARCHAR(64) NOT NULL REFERENCES knowledge_document(source_id),
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
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_source_id ON knowledge_chunk (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_tenant_id ON knowledge_chunk (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_content_hash ON knowledge_chunk (content_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_status ON knowledge_chunk (status)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_tenant_status_source
        ON knowledge_chunk (tenant_id, status, source_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_content_fts
        ON knowledge_chunk
        USING gin (to_tsvector('simple', content))
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE NOTICE 'pgvector extension is not available, keep JSON embedding fallback';
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
                ALTER TABLE knowledge_chunk
                    ADD COLUMN IF NOT EXISTS embedding_vector vector(64);
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
                CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding_vector_hnsw
                ON knowledge_chunk
                USING hnsw (embedding_vector vector_cosine_ops);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunk")
