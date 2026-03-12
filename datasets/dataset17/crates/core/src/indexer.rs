//! Document indexing module
use super::Config;

pub struct Index {
    config: Config,
    documents: Vec<IndexedDocument>,
}

struct IndexedDocument {
    id: String,
    chunks: Vec<String>,
    embeddings: Vec<Vec<f32>>,
}

impl Index {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            documents: Vec::new(),
        }
    }

    pub fn document_count(&self) -> usize {
        self.documents.len()
    }

    pub fn total_chunks(&self) -> usize {
        self.documents.iter().map(|d| d.chunks.len()).sum()
    }
}
