-- Migration: V004_CreateUsers.sql
-- Auto-generated schema migration

CREATE TABLE IF NOT EXISTS createusers (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name        VARCHAR(255) NOT NULL,
    data        JSON,
    status      ENUM('active', 'archived', 'deleted') DEFAULT 'active',
    INDEX idx_createusers_status (status),
    INDEX idx_createusers_created (created_at)
);
