"""Reset tenant/user data and switch to generated primary keys.

Revision ID: 20260425_0007
Revises: 20260425_0006
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op

revision = "20260425_0007"
down_revision = "20260425_0006"
branch_labels = None
depends_on = None


TENANT_FK_TABLES = [
    ("user_account", "tenant_id"),
    ("conversation", "tenant_id"),
    ("request_trace", "tenant_id"),
    ("approval_request", "tenant_id"),
    ("security_event", "tenant_id"),
    ("knowledge_document", "tenant_id"),
    ("knowledge_chunk", "tenant_id"),
    ("knowledge_wiki_page", "tenant_id"),
    ("knowledge_wiki_page_revision", "tenant_id"),
    ("knowledge_wiki_citation", "tenant_id"),
    ("knowledge_wiki_link", "tenant_id"),
    ("knowledge_wiki_compile_run", "tenant_id"),
    ("knowledge_wiki_feedback", "tenant_id"),
    ("knowledge_base", "tenant_id"),
    ("llm_runtime_config", "tenant_id"),
]


def _drop_fk(table_name: str, constraint_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
                  AND conrelid = '{table_name}'::regclass
            ) THEN
                ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name};
            END IF;
        END
        $$;
        """
    )


def _add_fk(table_name: str, constraint_name: str, column_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
                  AND conrelid = '{table_name}'::regclass
            ) THEN
                ALTER TABLE {table_name}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY ({column_name}) REFERENCES tenant(tenant_id);
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    op.execute(
        """
        TRUNCATE TABLE
            conversation_message,
            trace_step,
            knowledge_wiki_citation,
            knowledge_wiki_link,
            knowledge_wiki_page_revision,
            knowledge_wiki_compile_run,
            knowledge_wiki_feedback,
            knowledge_wiki_page,
            knowledge_chunk,
            knowledge_document,
            knowledge_base,
            approval_request,
            security_event,
            request_trace,
            conversation,
            llm_runtime_config,
            user_account,
            tenant
        RESTART IDENTITY CASCADE
        """
    )

    for table_name, column_name in TENANT_FK_TABLES:
        _drop_fk(table_name, f"{table_name}_{column_name}_fkey")

    op.execute("ALTER TABLE tenant ADD COLUMN IF NOT EXISTS tenant_record_id VARCHAR(64)")
    op.execute("ALTER TABLE user_account ADD COLUMN IF NOT EXISTS user_account_id VARCHAR(64)")

    op.execute(
        """
        UPDATE tenant
        SET tenant_record_id = 'tn-' || substr(md5(tenant_id), 1, 12)
        WHERE tenant_record_id IS NULL OR tenant_record_id = ''
        """
    )
    op.execute(
        """
        UPDATE user_account
        SET user_account_id = 'usr-' || substr(md5(user_id), 1, 12)
        WHERE user_account_id IS NULL OR user_account_id = ''
        """
    )

    op.execute("ALTER TABLE tenant ALTER COLUMN tenant_record_id SET NOT NULL")
    op.execute("ALTER TABLE user_account ALTER COLUMN user_account_id SET NOT NULL")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_tenant_tenant_id'
                  AND conrelid = 'tenant'::regclass
            ) THEN
                ALTER TABLE tenant ADD CONSTRAINT uq_tenant_tenant_id UNIQUE (tenant_id);
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_user_account_user_id'
                  AND conrelid = 'user_account'::regclass
            ) THEN
                ALTER TABLE user_account ADD CONSTRAINT uq_user_account_user_id UNIQUE (user_id);
            END IF;
        END
        $$;
        """
    )

    op.execute("ALTER TABLE tenant DROP CONSTRAINT IF EXISTS tenant_pkey")
    op.execute("ALTER TABLE user_account DROP CONSTRAINT IF EXISTS user_account_pkey")

    op.execute("ALTER TABLE tenant ADD CONSTRAINT tenant_pkey PRIMARY KEY (tenant_record_id)")
    op.execute("ALTER TABLE user_account ADD CONSTRAINT user_account_pkey PRIMARY KEY (user_account_id)")

    for table_name, column_name in TENANT_FK_TABLES:
        _add_fk(table_name, f"{table_name}_{column_name}_fkey", column_name)


def downgrade() -> None:
    for table_name, column_name in TENANT_FK_TABLES:
        _drop_fk(table_name, f"{table_name}_{column_name}_fkey")

    op.execute("ALTER TABLE tenant DROP CONSTRAINT IF EXISTS tenant_pkey")
    op.execute("ALTER TABLE user_account DROP CONSTRAINT IF EXISTS user_account_pkey")
    op.execute("ALTER TABLE tenant ADD CONSTRAINT tenant_pkey PRIMARY KEY (tenant_id)")
    op.execute("ALTER TABLE user_account ADD CONSTRAINT user_account_pkey PRIMARY KEY (user_id)")
    op.execute("ALTER TABLE tenant DROP CONSTRAINT IF EXISTS uq_tenant_tenant_id")
    op.execute("ALTER TABLE user_account DROP CONSTRAINT IF EXISTS uq_user_account_user_id")
    op.execute("ALTER TABLE tenant DROP COLUMN IF EXISTS tenant_record_id")
    op.execute("ALTER TABLE user_account DROP COLUMN IF EXISTS user_account_id")

    for table_name, column_name in TENANT_FK_TABLES:
        _add_fk(table_name, f"{table_name}_{column_name}_fkey", column_name)
