"""Add knowledge wiki tables.

Revision ID: 20260423_0003
Revises: 20260422_0002
Create Date: 2026-04-23
"""

from __future__ import annotations

from alembic import op

revision = "20260423_0003"
down_revision = "20260422_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_compile_run (
            compile_run_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            trigger_type VARCHAR(32) NOT NULL DEFAULT 'manual',
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            scope_type VARCHAR(32) NOT NULL DEFAULT 'source',
            scope_value VARCHAR(64) NOT NULL DEFAULT '',
            input_source_ids JSON NOT NULL DEFAULT '[]',
            input_chunk_ids JSON NOT NULL DEFAULT '[]',
            affected_page_ids JSON NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            token_usage INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMP WITH TIME ZONE NULL,
            finished_at TIMESTAMP WITH TIME ZONE NULL,
            created_by VARCHAR(64) NOT NULL DEFAULT 'system',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_compile_run_tenant_id ON knowledge_wiki_compile_run (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_compile_run_status ON knowledge_wiki_compile_run (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_page (
            page_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            space_code VARCHAR(64) NOT NULL DEFAULT 'knowledge',
            page_type VARCHAR(32) NOT NULL DEFAULT 'overview',
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(255) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            content_markdown TEXT NOT NULL DEFAULT '',
            metadata_json JSON NOT NULL DEFAULT '{}',
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            confidence VARCHAR(16) NOT NULL DEFAULT 'medium',
            freshness_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            source_count INTEGER NOT NULL DEFAULT 0,
            citation_count INTEGER NOT NULL DEFAULT 0,
            revision_no INTEGER NOT NULL DEFAULT 0,
            created_by VARCHAR(64) NOT NULL DEFAULT 'system',
            updated_by VARCHAR(64) NOT NULL DEFAULT 'system',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_page_tenant_id ON knowledge_wiki_page (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_page_slug ON knowledge_wiki_page (slug)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_page_status ON knowledge_wiki_page (status)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_wiki_page_tenant_status_type
        ON knowledge_wiki_page (tenant_id, status, page_type)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_page_revision (
            revision_id VARCHAR(64) PRIMARY KEY,
            page_id VARCHAR(64) NOT NULL REFERENCES knowledge_wiki_page(page_id),
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            revision_no INTEGER NOT NULL,
            compile_run_id VARCHAR(64) NULL REFERENCES knowledge_wiki_compile_run(compile_run_id),
            change_type VARCHAR(32) NOT NULL DEFAULT 'update',
            content_markdown TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            change_summary TEXT NOT NULL DEFAULT '',
            quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            metadata_json JSON NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            created_by VARCHAR(64) NOT NULL DEFAULT 'system'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_page_revision_page_id ON knowledge_wiki_page_revision (page_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_page_revision_compile_run_id
        ON knowledge_wiki_page_revision (compile_run_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_citation (
            citation_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            page_id VARCHAR(64) NOT NULL REFERENCES knowledge_wiki_page(page_id),
            revision_id VARCHAR(64) NOT NULL REFERENCES knowledge_wiki_page_revision(revision_id),
            section_key VARCHAR(128) NOT NULL,
            claim_text TEXT NOT NULL,
            source_id VARCHAR(64) NOT NULL REFERENCES knowledge_document(source_id),
            chunk_id VARCHAR(64) NOT NULL REFERENCES knowledge_chunk(chunk_id),
            evidence_snippet TEXT NOT NULL DEFAULT '',
            support_type VARCHAR(16) NOT NULL DEFAULT 'direct',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_citation_page_id ON knowledge_wiki_citation (page_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_citation_revision_id ON knowledge_wiki_citation (revision_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_citation_source_id ON knowledge_wiki_citation (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_citation_chunk_id ON knowledge_wiki_citation (chunk_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_link (
            link_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            from_page_id VARCHAR(64) NOT NULL REFERENCES knowledge_wiki_page(page_id),
            to_page_id VARCHAR(64) NOT NULL REFERENCES knowledge_wiki_page(page_id),
            link_type VARCHAR(32) NOT NULL DEFAULT 'related',
            weight DOUBLE PRECISION NOT NULL DEFAULT 1,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_link_from_page_id ON knowledge_wiki_link (from_page_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_link_to_page_id ON knowledge_wiki_link (to_page_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_wiki_feedback (
            feedback_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            query TEXT NOT NULL,
            page_ids JSON NOT NULL DEFAULT '[]',
            result_status VARCHAR(32) NOT NULL DEFAULT 'partial',
            feedback_note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_wiki_feedback_tenant_id ON knowledge_wiki_feedback (tenant_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_feedback")
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_link")
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_citation")
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_page_revision")
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_page")
    op.execute("DROP TABLE IF EXISTS knowledge_wiki_compile_run")
