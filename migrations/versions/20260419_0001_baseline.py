"""Baseline PostgreSQL schema.

Revision ID: 20260419_0001
Revises:
Create Date: 2026-04-19
"""

from __future__ import annotations

from alembic import op

revision = "20260419_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant (
            tenant_id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            package VARCHAR(255) NOT NULL,
            environment VARCHAR(64) NOT NULL,
            budget VARCHAR(64) NOT NULL,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_account (
            user_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(64) NOT NULL,
            scopes JSON NOT NULL DEFAULT '[]',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_account_tenant_id ON user_account (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation (
            conversation_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            title VARCHAR(255) NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversation_tenant_id ON conversation (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_message (
            message_id SERIAL PRIMARY KEY,
            conversation_id VARCHAR(64) NOT NULL REFERENCES conversation(conversation_id),
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_message_conversation_id "
        "ON conversation_message (conversation_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS request_trace (
            trace_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            user_id VARCHAR(64) NOT NULL,
            intent VARCHAR(64) NOT NULL,
            strategy VARCHAR(64) NOT NULL,
            message TEXT NOT NULL,
            answer TEXT NOT NULL DEFAULT '',
            sources JSON NOT NULL DEFAULT '[]',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_request_trace_tenant_id ON request_trace (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_request_trace_user_id ON request_trace (user_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_step (
            step_id SERIAL PRIMARY KEY,
            trace_id VARCHAR(64) NOT NULL REFERENCES request_trace(trace_id),
            name VARCHAR(64) NOT NULL,
            status VARCHAR(64) NOT NULL,
            summary TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_step_trace_id ON trace_step (trace_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_request (
            draft_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            user_id VARCHAR(64) NOT NULL,
            capability_name VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            risk_level VARCHAR(32) NOT NULL,
            status VARCHAR(64) NOT NULL,
            payload JSON NOT NULL,
            summary TEXT NOT NULL,
            approval_hint TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            confirmed_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_request_tenant_id ON approval_request (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS security_event (
            event_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            category VARCHAR(64) NOT NULL,
            severity VARCHAR(32) NOT NULL,
            title VARCHAR(255) NOT NULL,
            status VARCHAR(64) NOT NULL,
            owner VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_security_event_tenant_id ON security_event (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_document (
            source_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL REFERENCES tenant(tenant_id),
            name VARCHAR(255) NOT NULL,
            source_type VARCHAR(64) NOT NULL,
            owner VARCHAR(255) NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(64) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_document_tenant_id ON knowledge_document (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_runtime_config (
            config_key VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) REFERENCES tenant(tenant_id),
            provider VARCHAR(64) NOT NULL,
            base_url VARCHAR(1024) NOT NULL DEFAULT '',
            model VARCHAR(255) NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            temperature DOUBLE PRECISION NOT NULL DEFAULT 0.2,
            system_prompt TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT false,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_llm_runtime_config_tenant_id ON llm_runtime_config (tenant_id)")

    op.execute("ALTER TABLE user_account ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    op.execute("ALTER TABLE user_account ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
    op.execute(
        """
        UPDATE user_account
        SET email = user_id || '@example.com'
        WHERE email IS NULL OR email = ''
        """
    )
    op.execute(
        """
        UPDATE user_account
        SET password_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4grwcuhVHhphnetC'
        WHERE password_hash IS NULL OR password_hash = ''
        """
    )
    op.execute("ALTER TABLE user_account ALTER COLUMN email SET NOT NULL")
    op.execute("ALTER TABLE user_account ALTER COLUMN password_hash SET NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_account_email ON user_account (email)")

    op.execute("ALTER TABLE llm_runtime_config ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_runtime_config_tenant_id ON llm_runtime_config (tenant_id)")
    op.execute("UPDATE llm_runtime_config SET tenant_id = NULL WHERE config_key = 'default'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_runtime_config")
    op.execute("DROP TABLE IF EXISTS knowledge_document")
    op.execute("DROP TABLE IF EXISTS security_event")
    op.execute("DROP TABLE IF EXISTS approval_request")
    op.execute("DROP TABLE IF EXISTS trace_step")
    op.execute("DROP TABLE IF EXISTS request_trace")
    op.execute("DROP TABLE IF EXISTS conversation_message")
    op.execute("DROP TABLE IF EXISTS conversation")
    op.execute("DROP TABLE IF EXISTS user_account")
    op.execute("DROP TABLE IF EXISTS tenant")
