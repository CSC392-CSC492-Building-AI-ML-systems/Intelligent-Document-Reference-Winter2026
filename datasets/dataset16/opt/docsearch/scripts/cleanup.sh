#!/bin/bash
set -euo pipefail
find /var/log/docsearch -name "*.log" -mtime +30 -delete
find /tmp/docsearch -type f -mtime +7 -delete
echo "Cleanup completed"
