# Deployment Guide

## Production Checklist
- [ ] Set `APP_SECRET_KEY` environment variable
- [ ] Configure embedding API keys
- [ ] Set up monitoring and alerting
- [ ] Configure backup strategy for SQLite database
- [ ] Review resource limits (CPU, memory)
- [ ] Enable HTTPS/TLS

## Docker Deployment
```bash
docker build -t doc-search:latest .
docker run -d -p 8000:8000 \
  -v /data/doc-search:/app/data \
  -e APP_SECRET_KEY=$(openssl rand -hex 32) \
  doc-search:latest
```

## Scaling Considerations
- **Vertical**: Increase memory for larger embedding caches
- **Horizontal**: Run multiple API instances behind a load balancer
- **Embedding**: Use batch processing to optimize GPU utilization
- **Database**: Consider PostgreSQL + pgvector for > 1M documents

## Monitoring
Key metrics to track:
- Query latency (p50, p95, p99)
- Embedding generation time
- Index size and growth rate
- Error rate by endpoint
- Cache hit ratio
