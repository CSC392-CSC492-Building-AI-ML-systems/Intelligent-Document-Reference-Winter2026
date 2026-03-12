#!/bin/bash
set -euo pipefail
cd /opt/docsearch
source venv/bin/activate
python -m db.migrations.apply --confirm
echo "Migration completed"
