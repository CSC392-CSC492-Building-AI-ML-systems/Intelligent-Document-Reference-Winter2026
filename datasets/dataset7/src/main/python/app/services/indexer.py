"""Document indexing service."""


class IndexerService:
    def __init__(self, db, embedder):
        self.db = db
        self.embedder = embedder

    def index_document(self, doc):
        chunks = self._chunk(doc.content)
        embeddings = self.embedder.embed_batch(chunks)
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            self.db.store(doc.id, i, chunk, emb)

    def _chunk(self, text, size=512, overlap=64):
        chunks = []
        for i in range(0, len(text), size - overlap):
            chunks.append(text[i : i + size])
        return chunks
