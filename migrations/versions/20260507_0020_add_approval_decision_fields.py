"""Add approval decision fields.

Revision ID: 20260507_0020
Revises: 20260428_0019
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260507_0020"
down_revision = "20260428_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_request", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "approval_request",
        sa.Column("decision_comment", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "decision_comment")
    op.drop_column("approval_request", "decided_at")
