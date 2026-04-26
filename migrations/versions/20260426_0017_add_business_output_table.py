"""Add business_output table.

Revision ID: 20260426_0017
Revises: 20260426_0016
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260426_0017"
down_revision = "20260426_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_output",
        sa.Column("output_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenant.tenant_id"), nullable=False, index=True),
        sa.Column("package_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("linked_draft_group_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("business_output")
