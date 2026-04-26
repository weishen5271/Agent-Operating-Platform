"""Add tenant tool overrides.

Revision ID: 20260426_0012
Revises: 20260426_0011
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0012"
down_revision = "20260426_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_override (
            override_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            tool_name VARCHAR(128) NOT NULL,
            quota INTEGER,
            timeout INTEGER,
            disabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, tool_name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tool_override_tenant_id ON tool_override (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tool_override_tool_name ON tool_override (tool_name)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tool_override")
