# Troubleshooting

## Common Issues

### "Database is locked" Error
**Cause**: Multiple writers attempting concurrent access to SQLite.
**Solution**: Ensure only one writer process at a time, or switch
to WAL mode:
```python
connection.execute("PRAGMA journal_mode=WAL")
```

### Slow Embedding Generation
**Cause**: Large batch sizes or network latency to embedding API.
**Solution**:
1. Reduce batch size in config
2. Enable embedding cache
3. Consider using a local model (e.g., Ollama)

### Out of Memory During Indexing
**Cause**: Loading too many documents into memory simultaneously.
**Solution**: Use streaming ingestion with smaller batch sizes:
```yaml
ingestion:
  batch_size: 16  # reduce from default 64
  max_concurrent: 2
```

### Poor Retrieval Quality
**Cause**: Suboptimal chunking or embedding model.
**Solution**:
1. Switch to semantic chunking
2. Increase chunk overlap
3. Try a different embedding model
4. Enable hybrid (BM25 + vector) retrieval

### File Watcher Not Detecting Changes
**Cause**: OS file event limits reached.
**Solution** (Linux):
```bash
echo 65536 | sudo tee /proc/sys/fs/inotify/max_user_watches
```
