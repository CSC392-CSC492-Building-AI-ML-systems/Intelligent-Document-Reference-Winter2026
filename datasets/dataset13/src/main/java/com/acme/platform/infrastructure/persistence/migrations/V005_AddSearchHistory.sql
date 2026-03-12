-- Migration: V005_AddSearchHistory.sql
-- Auto-generated schema migration

CREATE TABLE IF NOT EXISTS addsearchhistory (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name        VARCHAR(255) NOT NULL,
    data        JSON,
    status      ENUM('active', 'archived', 'deleted') DEFAULT 'active',
    INDEX idx_addsearchhistory_status (status),
    INDEX idx_addsearchhistory_created (created_at)
);
