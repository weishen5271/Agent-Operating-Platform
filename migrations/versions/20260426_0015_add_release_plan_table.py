"""Add release plan table.

Revision ID: 20260426_0015
Revises: 20260426_0014
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0015"
down_revision = "20260426_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS release_plan (
            release_id VARCHAR(64) PRIMARY KEY,
            package_id VARCHAR(255) NOT NULL,
            package_name VARCHAR(255) NOT NULL,
            skill VARCHAR(255) NOT NULL,
            version VARCHAR(64) NOT NULL,
            status VARCHAR(64) NOT NULL,
            rollout_percent INTEGER NOT NULL DEFAULT 0,
            metric_delta VARCHAR(255) NOT NULL DEFAULT '',
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_release_plan_package_id ON release_plan (package_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_release_plan_skill ON release_plan (skill)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_release_plan_status ON release_plan (status)")
    op.execute(
        """
        INSERT INTO release_plan (
            release_id,
            package_id,
            package_name,
            skill,
            version,
            status,
            rollout_percent,
            metric_delta,
            started_at
        )
        VALUES
            (
                'rel-kb-grounded-qa-001',
                'industry.mfg',
                '工业设备运维助手',
                'kb_grounded_qa',
                '1.2.0',
                '灰度中',
                25,
                '引用命中 +3.2%',
                '2026-04-26 09:30:00+08'
            ),
            (
                'rel-report-compose-001',
                '_common/report_gen',
                '报告生成',
                'report_compose',
                '1.0.4',
                '已完成',
                100,
                '导出耗时 -8ms',
                '2026-04-25 16:10:00+08'
            )
        ON CONFLICT (release_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS release_plan")
