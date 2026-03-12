# Architecture Overview

## Components

### Core Engine
The processing engine provides a pipeline-based architecture where
documents flow through configurable processing stages.

### Models
- **Document**: Core data model representing an ingested document
- **EmbeddingRecord**: Stores vector embeddings linked to document chunks

### Services
- **IndexerService**: Handles document chunking and embedding storage
- **RetrieverService**: Performs similarity search across indexed documents

## Data Flow
1. Document ingested via API
2. Text extracted and cleaned
3. Content chunked with overlap
4. Embeddings generated for each chunk
5. Vectors stored in database
6. Queries embedded and compared via cosine similarity
