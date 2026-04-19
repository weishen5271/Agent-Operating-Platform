-- Migration: Add tenant_id column to llm_runtime_config table
-- Date: 2026-04-19
-- Description: Support per-tenant LLM runtime configuration

ALTER TABLE llm_runtime_config
ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

-- Create index for tenant-based lookups
CREATE INDEX IF NOT EXISTS idx_llm_runtime_config_tenant_id
ON llm_runtime_config(tenant_id);

-- Set existing default config's tenant_id to NULL (global config)
UPDATE llm_runtime_config
SET tenant_id = NULL
WHERE config_key = 'default';

-- Add foreign key constraint (optional, depends on your needs)
-- ALTER TABLE llm_runtime_config
-- ADD CONSTRAINT fk_llm_runtime_config_tenant
-- FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id)
-- ON DELETE CASCADE;
