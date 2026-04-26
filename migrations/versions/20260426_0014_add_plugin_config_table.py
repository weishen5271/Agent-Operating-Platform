"""Add tenant plugin config table.

Revision ID: 20260426_0014
Revises: 20260426_0013
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0014"
down_revision = "20260426_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_config (
            config_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            plugin_name VARCHAR(255) NOT NULL,
            config JSON NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, plugin_name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_plugin_config_tenant_id ON plugin_config (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_plugin_config_plugin_name ON plugin_config (plugin_name)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_config")
