-- Migration: Add email and password_hash columns to user_account table
-- Date: 2026-04-19
-- Description: Support user authentication (login/register)

ALTER TABLE user_account
ADD COLUMN IF NOT EXISTS email VARCHAR(255) NOT NULL DEFAULT '';

ALTER TABLE user_account
ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NOT NULL DEFAULT '';

-- Create unique index on email
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_account_email
ON user_account(email);

-- Update existing users with default values
UPDATE user_account
SET email = user_id || '@example.com',
    password_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4grwcuhVHhphnetC'
WHERE email = '';
