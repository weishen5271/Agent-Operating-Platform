"""Add MCP server registry table.

Revision ID: 20260427_0018
Revises: 20260426_0017
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op


revision = "20260427_0018"
down_revision = "20260426_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_server (
            server_id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            transport VARCHAR(64) NOT NULL,
            endpoint VARCHAR(1024) NOT NULL,
            auth_ref VARCHAR(255) NOT NULL DEFAULT '',
            headers JSON NOT NULL DEFAULT '{}',
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mcp_server_name ON mcp_server (name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mcp_server_status ON mcp_server (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mcp_server")
