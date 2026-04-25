"""Add embedding runtime fields to LLM config and chunk tables.

Revision ID: 20260425_0009
Revises: 20260425_0008
Create Date: 2026-04-25

Background
----------
P1 阶段引入真实 embedding 模型（OpenAI 兼容）替代历史哈希向量。
为保持线上数据可控：
1. 在 llm_runtime_config 表上新增 embedding_* 字段，与 LLM 主配置共存。
2. knowledge_chunk 与 knowledge_wiki_source_chunk 增加 embedding_status / embedding_model，
   既有数据全部标记为 pending，以便管理端按需 reindex；未 reindex 前，向量路径自动跳过。
本次迁移不删除既有 embedding_vector 列：维度由 JSON 字段在应用层兼容，pgvector 列保留为可空，未来再单独治理。
"""

from __future__ import annotations

from alembic import op


revision = "20260425_0009"
down_revision = "20260425_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE llm_runtime_config
            ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(64) NOT NULL DEFAULT 'openai-compatible',
            ADD COLUMN IF NOT EXISTS embedding_base_url VARCHAR(1024) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(255) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS embedding_api_key TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER NOT NULL DEFAULT 1536,
            ADD COLUMN IF NOT EXISTS embedding_enabled BOOLEAN NOT NULL DEFAULT FALSE
        """
    )

    for table in ("knowledge_chunk", "knowledge_wiki_source_chunk"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS embedding_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(255) NOT NULL DEFAULT ''
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding_status ON {table} (embedding_status)"
        )
        # 既有数据使用旧的哈希向量，统一标记 pending 等待 reindex
        op.execute(
            f"UPDATE {table} SET embedding_status = 'pending' WHERE embedding_status IS NULL OR embedding_status = ''"
        )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE llm_runtime_config
            DROP COLUMN IF EXISTS embedding_provider,
            DROP COLUMN IF EXISTS embedding_base_url,
            DROP COLUMN IF EXISTS embedding_model,
            DROP COLUMN IF EXISTS embedding_api_key,
            DROP COLUMN IF EXISTS embedding_dimensions,
            DROP COLUMN IF EXISTS embedding_enabled
        """
    )
    for table in ("knowledge_chunk", "knowledge_wiki_source_chunk"):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_embedding_status")
        op.execute(
            f"""
            ALTER TABLE {table}
                DROP COLUMN IF EXISTS embedding_status,
                DROP COLUMN IF EXISTS embedding_model
            """
        )
