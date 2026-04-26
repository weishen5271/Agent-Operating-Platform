"""Add output guard rule table.

Revision ID: 20260426_0013
Revises: 20260426_0012
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0013"
down_revision = "20260426_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS output_guard_rule (
            rule_id VARCHAR(128) PRIMARY KEY,
            package_id VARCHAR(255) NOT NULL,
            pattern TEXT NOT NULL,
            action VARCHAR(128) NOT NULL,
            source VARCHAR(128) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_output_guard_rule_package_id ON output_guard_rule (package_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_output_guard_rule_source ON output_guard_rule (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_output_guard_rule_enabled ON output_guard_rule (enabled)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS output_guard_rule")
