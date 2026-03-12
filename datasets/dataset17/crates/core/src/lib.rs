//! Core library for document processing
pub mod parser;
pub mod embedder;
pub mod indexer;

/// Configuration for the core library
#[derive(Debug, Clone)]
pub struct Config {
    pub max_document_size: usize,
    pub chunk_size: usize,
    pub overlap: usize,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            max_document_size: 10_000_000,
            chunk_size: 512,
            overlap: 64,
        }
    }
}
