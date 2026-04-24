"""Remove seeded knowledge demo data.

Revision ID: 20260424_0005
Revises: 20260424_0004
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op

revision = "20260424_0005"
down_revision = "20260424_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM knowledge_wiki_citation
        WHERE source_id IN ('ks-001', 'ks-002')
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_wiki_page_revision
        WHERE page_id IN (
            SELECT page_id FROM knowledge_wiki_page WHERE slug IN ('source-ks-001', 'source-ks-002')
        )
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_wiki_page
        WHERE slug IN ('source-ks-001', 'source-ks-002')
        """
    )
    op.execute(
        """
        UPDATE knowledge_wiki_compile_run
        SET affected_page_ids = '[]', summary = ''
        WHERE scope_value IN ('ks-001', 'ks-002')
           OR input_source_ids::text LIKE '%ks-001%'
           OR input_source_ids::text LIKE '%ks-002%'
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_chunk
        WHERE chunk_id IN ('kc-seed-p0a', 'kc-seed-finance')
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_document
        WHERE source_id IN ('ks-001', 'ks-002')
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_base
        WHERE knowledge_base_code IN ('knowledge', 'finance')
          AND created_by = 'system'
        """
    )


def downgrade() -> None:
    return None
