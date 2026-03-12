"""Information density filtering: remove low-signal chunks without harming recall."""

from collections import Counter
from typing import List, Set

from ingestion.chunking.structural import StructuralChunk
from ingestion.models import estimate_tokens

_STOPWORDS: Set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "been",
    "be",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "they",
    "them",
    "their",
    "i",
    "you",
    "he",
    "she",
    "we",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
}


def _content_word_ratio(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.0
    content = sum(1 for w in words if w not in _STOPWORDS)
    return content / len(words)


def _tfidf_novelty(chunk: StructuralChunk, all_chunks: List[StructuralChunk]) -> float:
    if not all_chunks:
        return 1.0
    doc_terms: Counter = Counter()
    for c in all_chunks:
        for w in c.text.lower().split():
            if w not in _STOPWORDS and len(w) > 2:
                doc_terms[w] += 1
    chunk_terms = [
        w for w in chunk.text.lower().split() if w not in _STOPWORDS and len(w) > 2
    ]
    if not chunk_terms:
        return 0.0
    novelty = sum(1.0 / (1 + doc_terms.get(w, 0)) for w in chunk_terms) / len(
        chunk_terms
    )
    return min(1.0, novelty)


def filter_by_density(
    chunks: List[StructuralChunk],
    *,
    min_tokens: int = 50,
    min_content_word_ratio: float = 0.35,
    tfidf_threshold: float = 0.0,
    use_tfidf: bool = False,
) -> List[StructuralChunk]:
    """Remove low-information chunks by density heuristics."""
    out: List[StructuralChunk] = []
    for c in chunks:
        if estimate_tokens(c.text) < min_tokens:
            continue
        if _content_word_ratio(c.text) < min_content_word_ratio:
            continue
        if use_tfidf and tfidf_threshold > 0:
            nov = _tfidf_novelty(c, chunks)
            if nov < tfidf_threshold:
                continue
        out.append(c)
    return out
