#!/bin/bash
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$RESPONSE" != "200" ]; then
    echo "CRITICAL: API health check failed (HTTP $RESPONSE)"
    exit 2
fi
echo "OK: API healthy"
exit 0
