"""Scoring functions for file retrieval, response relevance, citation accuracy."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from benchmarks.models import CitationScore, ResponseScore, RetrievalScore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------


def normalize_path(p: str) -> str:
    """Normalize a file path for comparison (lowercase, forward slash, strip leading ./)."""
    p = p.replace("\\", "/").strip().lower()
    while p.startswith("./"):
        p = p[2:]
    return p


# ---------------------------------------------------------------------------
# Metric 1 — File Retrieval Hit Rate
# ---------------------------------------------------------------------------


def score_file_retrieval(
    retrieved_files: List[str],
    expected_file: str,
    top_k: int = 5,
) -> RetrievalScore:
    """Score a file-retrieval query (binary hit/miss + MRR)."""
    retrieved_norm = [normalize_path(f) for f in retrieved_files]
    expected_norm = normalize_path(expected_file)

    hit_at_1 = int(bool(retrieved_norm) and retrieved_norm[0] == expected_norm)
    hit_at_k = int(expected_norm in retrieved_norm[:top_k])

    mrr = 0.0
    for rank, path in enumerate(retrieved_norm, start=1):
        if path == expected_norm:
            mrr = 1.0 / rank
            break

    return RetrievalScore(
        hit_at_1=hit_at_1,
        hit_at_k=hit_at_k,
        mrr=mrr,
        retrieved_files=retrieved_norm,
        expected_file=expected_norm,
    )


def score_comparative_retrieval(
    retrieved_files: List[str],
    expected_files: List[str],
    top_k: int = 5,
) -> RetrievalScore:
    """Score a comparative query needing multiple files."""
    retrieved_norm = [normalize_path(f) for f in retrieved_files]
    expected_norm = [normalize_path(f) for f in expected_files]

    found = [e for e in expected_norm if e in retrieved_norm[:top_k]]
    recall = len(found) / len(expected_norm) if expected_norm else 0.0
    hit_at_1 = int(recall == 1.0)
    hit_at_k = int(len(found) > 0)

    # Average MRR across expected files
    mrr_sum = 0.0
    for exp in expected_norm:
        for rank, path in enumerate(retrieved_norm, start=1):
            if path == exp:
                mrr_sum += 1.0 / rank
                break
    mrr = mrr_sum / len(expected_norm) if expected_norm else 0.0

    return RetrievalScore(
        hit_at_1=hit_at_1,
        hit_at_k=hit_at_k,
        mrr=mrr,
        retrieved_files=retrieved_norm,
        expected_file=", ".join(expected_norm),
    )


# ---------------------------------------------------------------------------
# Metric 2 — Response Relevance Score
# ---------------------------------------------------------------------------


async def score_response_relevance(
    query: str,
    response: str,
    expected_keywords: Optional[List[str]],
    context_chunks: List[Dict[str, Any]],
    *,
    judge_client: Optional[Any] = None,
    embedding_client: Optional[Any] = None,
) -> ResponseScore:
    """Score response quality with keyword coverage, optional LLM judge, optional embedding similarity."""
    keywords = expected_keywords or []

    # Layer 1: Keyword coverage (fast, deterministic)
    if keywords:
        found = [kw for kw in keywords if kw.lower() in response.lower()]
        keyword_score = len(found) / len(keywords)
    else:
        keyword_score = 0.0

    # Layer 2: LLM-as-a-judge (optional)
    llm_judge_score = 0.0
    llm_breakdown: Dict[str, float] = {}
    if judge_client is not None:
        try:
            llm_judge_score, llm_breakdown = await _call_judge(
                judge_client, query, response
            )
        except Exception as e:
            logger.warning("LLM judge failed: %s", e)

    # Layer 3: Semantic similarity (optional)
    semantic_sim = 0.0
    if embedding_client is not None:
        try:
            semantic_sim = await _compute_semantic_similarity(
                embedding_client, query, response
            )
        except Exception as e:
            logger.warning("Semantic similarity failed: %s", e)

    # Weighted composite — weights shift depending on available layers
    if judge_client and embedding_client:
        composite = 0.25 * keyword_score + 0.50 * llm_judge_score + 0.25 * semantic_sim
    elif judge_client:
        composite = 0.35 * keyword_score + 0.65 * llm_judge_score
    elif embedding_client:
        composite = 0.50 * keyword_score + 0.50 * semantic_sim
    else:
        composite = keyword_score

    return ResponseScore(
        keyword_score=keyword_score,
        llm_judge_score=llm_judge_score,
        llm_judge_breakdown=llm_breakdown,
        semantic_similarity=semantic_sim,
        composite_score=composite,
    )


async def _call_judge(
    client: Any, query: str, response: str
) -> tuple[float, Dict[str, float]]:
    """Ask an LLM to rate the response on a 0–1 scale."""
    import json

    prompt = (
        "You are an impartial judge evaluating a RAG system response.\n\n"
        f"QUERY: {query}\n\n"
        f"RESPONSE: {response}\n\n"
        "Rate this response from 0.0 to 1.0 on each dimension:\n"
        "1. relevance — Does it answer what was asked?\n"
        "2. grounding — Does it stay within provided context?\n"
        "3. completeness — Does it cover the key aspects?\n\n"
        'Return ONLY valid JSON: {"relevance": float, "grounding": float, '
        '"completeness": float, "overall": float}'
    )
    raw = await asyncio.to_thread(client.generate, prompt)
    # Extract JSON from response
    match = re.search(r"\{[^}]+\}", raw)
    if not match:
        return 0.0, {}
    data = json.loads(match.group())
    overall = float(data.get("overall", 0.0))
    return overall, {k: float(v) for k, v in data.items()}


async def _compute_semantic_similarity(
    embedding_client: Any, query: str, response: str
) -> float:
    """Cosine similarity between embedded query and response."""
    import numpy as np

    vecs = await asyncio.to_thread(embedding_client.embed_text, [query, response])
    if len(vecs) < 2:
        return 0.0
    a, b = np.array(vecs[0], dtype=np.float32), np.array(vecs[1], dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ---------------------------------------------------------------------------
# Metric 3 — Citation Accuracy
# ---------------------------------------------------------------------------

_CITATION_RE = re.compile(
    r"\(?\s*[Ss]ource\s*:\s*([^)\n]+)\)?",
)


def extract_citations_from_response(response: str) -> List[str]:
    """Parse (Source: path) markers from an LLM response."""
    return [m.strip() for m in _CITATION_RE.findall(response)]


def score_citations(
    response: str,
    expected_citation_file: Optional[str],
    corpus_files: Optional[set[str]] = None,
) -> CitationScore:
    """Score citation accuracy in a generated response."""
    cited = extract_citations_from_response(response)
    cited_norm = [normalize_path(c) for c in cited]

    citation_present = int(len(cited_norm) > 0)
    citation_correct = 0
    if expected_citation_file:
        expected_norm = normalize_path(expected_citation_file)
        citation_correct = int(expected_norm in cited_norm)

    hallucinated: List[str] = []
    if corpus_files is not None:
        corpus_norm = {normalize_path(f) for f in corpus_files}
        hallucinated = [c for c in cited_norm if c not in corpus_norm]

    hallucination_rate = len(hallucinated) / max(len(cited_norm), 1)

    return CitationScore(
        citation_present=citation_present,
        citation_correct=citation_correct,
        hallucinated_citations=hallucinated,
        hallucination_rate=hallucination_rate,
    )


# ---------------------------------------------------------------------------
# Helpers: averaging across runs
# ---------------------------------------------------------------------------


def average_run_scores(runs: list) -> Any:
    """Average scoring results across multiple runs of the same query."""
    from benchmarks.models import RunScore

    if not runs:
        return RunScore()
    _ = len(runs)

    def _avg(vals: List[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _avg_int(vals: List[int]) -> int:
        return round(sum(vals) / len(vals)) if vals else 0

    return RunScore(
        retrieval=RetrievalScore(
            hit_at_1=_avg_int([r.retrieval.hit_at_1 for r in runs]),
            hit_at_k=_avg_int([r.retrieval.hit_at_k for r in runs]),
            mrr=_avg([r.retrieval.mrr for r in runs]),
            retrieved_files=runs[-1].retrieval.retrieved_files,
            expected_file=runs[0].retrieval.expected_file,
        ),
        response=ResponseScore(
            keyword_score=_avg([r.response.keyword_score for r in runs]),
            llm_judge_score=_avg([r.response.llm_judge_score for r in runs]),
            llm_judge_breakdown=runs[-1].response.llm_judge_breakdown,
            semantic_similarity=_avg([r.response.semantic_similarity for r in runs]),
            composite_score=_avg([r.response.composite_score for r in runs]),
        ),
        citation=CitationScore(
            citation_present=_avg_int([r.citation.citation_present for r in runs]),
            citation_correct=_avg_int([r.citation.citation_correct for r in runs]),
            hallucinated_citations=runs[-1].citation.hallucinated_citations,
            hallucination_rate=_avg([r.citation.hallucination_rate for r in runs]),
        ),
        latency=LatencyProfile(
            query_id=runs[0].latency.query_id,
            retrieval_latency_ms=_avg([r.latency.retrieval_latency_ms for r in runs]),
            inference_latency_ms=_avg([r.latency.inference_latency_ms for r in runs]),
            total_latency_ms=_avg([r.latency.total_latency_ms for r in runs]),
            chunk_count=_avg_int([r.latency.chunk_count for r in runs]),
            token_count_prompt=_avg_int([r.latency.token_count_prompt for r in runs]),
            token_count_response=_avg_int(
                [r.latency.token_count_response for r in runs]
            ),
        ),
    )


# Needed by average_run_scores
from benchmarks.models import LatencyProfile  # noqa: E402
