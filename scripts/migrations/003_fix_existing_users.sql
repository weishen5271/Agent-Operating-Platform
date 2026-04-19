-- Migration: Fix existing users with missing email/password_hash
-- Date: 2026-04-19
-- Description: Update existing users with email and password_hash fields

-- Default password is "password123" - bcrypt hash
UPDATE user_account
SET email = user_id || '@example.com',
    password_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4grwcuhVHhphnetC'
WHERE email = '' OR email IS NULL;
