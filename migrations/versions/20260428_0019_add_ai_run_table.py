"""Add ai_run table and output action links.

Revision ID: 20260428_0019
Revises: 20260427_0018
Create Date: 2026-04-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260428_0019"
down_revision = "20260427_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_run",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenant.tenant_id"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=255), nullable=False),
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=255), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("data_input_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("output_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("draft_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        # 新增时间类字段统一使用 Unix timestamp 毫秒，数据库层用 BigInteger。
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_ai_run_tenant_id", "ai_run", ["tenant_id"])
    op.create_index("ix_ai_run_user_id", "ai_run", ["user_id"])
    op.create_index("ix_ai_run_package_id", "ai_run", ["package_id"])
    op.create_index("ix_ai_run_action_id", "ai_run", ["action_id"])
    op.create_index("ix_ai_run_status", "ai_run", ["status"])
    op.create_index("ix_ai_run_trace_id", "ai_run", ["trace_id"])
    op.create_index("ix_ai_run_object_type", "ai_run", ["object_type"])
    op.create_index("ix_ai_run_object_id", "ai_run", ["object_id"])

    op.add_column("business_output", sa.Column("run_id", sa.String(length=64), nullable=True))
    op.add_column("business_output", sa.Column("action_id", sa.String(length=128), nullable=True))
    op.add_column("business_output", sa.Column("object_type", sa.String(length=64), nullable=True))
    op.add_column("business_output", sa.Column("object_id", sa.String(length=255), nullable=True))
    op.create_index("ix_business_output_run_id", "business_output", ["run_id"])
    op.create_index("ix_business_output_action_id", "business_output", ["action_id"])


def downgrade() -> None:
    op.drop_index("ix_business_output_action_id", table_name="business_output")
    op.drop_index("ix_business_output_run_id", table_name="business_output")
    op.drop_column("business_output", "object_id")
    op.drop_column("business_output", "object_type")
    op.drop_column("business_output", "action_id")
    op.drop_column("business_output", "run_id")
    op.drop_table("ai_run")
