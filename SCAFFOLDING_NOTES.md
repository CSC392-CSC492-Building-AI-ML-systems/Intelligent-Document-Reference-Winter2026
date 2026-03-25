# Scaffolding notes
- This scaffold creates the architecture and stubs only.
- Implementations should avoid cross-layer imports (follow the dependency directions).
- Implement model clients under model_clients/ and route them via embeddings/router.py and inference/router.py.
- Persist runtime backend choices in db/settings_store.py and expose via backend/api/routes_settings.py.
- Fill DB schema at db/schema.sql and add migrations.

