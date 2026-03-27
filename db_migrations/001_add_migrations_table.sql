-- 001_add_migrations_table.sql
-- Bootstrap: create the _migrations tracking table itself.
-- This migration is recorded automatically by the migration runner.

CREATE TABLE IF NOT EXISTS _migrations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    filename  TEXT    NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
