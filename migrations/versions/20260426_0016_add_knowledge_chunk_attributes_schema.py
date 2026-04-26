"""Add knowledge source chunk attributes schema.

Revision ID: 20260426_0016
Revises: 20260426_0015
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0016"
down_revision = "20260426_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS chunk_attributes_schema JSON NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE knowledge_wiki_source ADD COLUMN IF NOT EXISTS chunk_attributes_schema JSON NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_wiki_source DROP COLUMN IF EXISTS chunk_attributes_schema")
    op.execute("ALTER TABLE knowledge_document DROP COLUMN IF EXISTS chunk_attributes_schema")
