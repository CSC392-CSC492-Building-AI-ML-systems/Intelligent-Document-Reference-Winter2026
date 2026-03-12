#!/bin/bash
set -euo pipefail
BACKUP_DIR="/var/backups/docsearch/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"
cp /var/lib/docsearch/data/index.db "$BACKUP_DIR/"
echo "Backup completed: $BACKUP_DIR"
