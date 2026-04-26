"""Add package context and trace step metadata.

Revision ID: 20260426_0011
Revises: 20260425_0010
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0011"
down_revision = "20260425_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenant
            ADD COLUMN IF NOT EXISTS enabled_common_packages JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE trace_step
            ADD COLUMN IF NOT EXISTS node_type VARCHAR(32),
            ADD COLUMN IF NOT EXISTS ref VARCHAR(255),
            ADD COLUMN IF NOT EXISTS ref_source VARCHAR(64),
            ADD COLUMN IF NOT EXISTS ref_version VARCHAR(64),
            ADD COLUMN IF NOT EXISTS duration_ms INTEGER
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE trace_step
            DROP COLUMN IF EXISTS duration_ms,
            DROP COLUMN IF EXISTS ref_version,
            DROP COLUMN IF EXISTS ref_source,
            DROP COLUMN IF EXISTS ref,
            DROP COLUMN IF EXISTS node_type
        """
    )
    op.execute(
        """
        ALTER TABLE tenant
            DROP COLUMN IF EXISTS enabled_common_packages
        """
    )
