"""Citation formatting helpers."""

import os
import re
from typing import Any, Dict, List

NOISE_QUERY_TERMS = {
    "random",
    "rubbish",
    "nonsense",
    "garbage",
    "asdf",
    "qwerty",
    "blah",
    "test",
    "unknown",
    "irrelevant",
    "nothing",
}


def _query_terms(query: str) -> set[str]:
    terms = re.findall(r"[a-z0-9_\-.]+", (query or "").lower())
    return {t for t in terms if len(t) > 1}


def _path_terms(path: str) -> set[str]:
    lowered = path.lower().replace("\\", "/")
    components = [c for c in lowered.split("/") if c]
    out: set[str] = set()
    for comp in components:
        stem, ext = os.path.splitext(comp)
        out.update(re.findall(r"[a-z0-9_]+", stem))
        if ext:
            out.add(ext)
            out.add(ext.lstrip("."))

    base = os.path.basename(lowered)
    stem, ext = os.path.splitext(base)
    if ext:
        out.add(ext)
        out.add(ext.lstrip("."))
    return out


def _path_match_score(path: str, query: str, q_terms: set[str]) -> float:
    """Return score in [0, 1] for how clearly query targets this path."""
    if not query:
        return 0.0

    lowered_query = query.lower()
    basename = os.path.basename(path).lower()
    score = 0.0

    if basename and basename in lowered_query:
        score += 1.0

    p_terms = _path_terms(path)
    overlap = len(q_terms & p_terms)
    if overlap > 0:
        score += min(1.0, 0.25 * overlap)

    return min(score, 1.0)


def _semantic_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    dist = max(0.0, min(2.0, float(distance)))
    # Non-linear mapping so mediocre matches do not look too confident.
    # dist=0.0 -> 1.0, dist=0.5 -> 0.5, dist=1.0 -> 0.0
    score = (1.0 - dist) if dist < 1.0 else 0.0
    return max(0.0, score)


def _hybrid_score(raw_hybrid: float) -> float:
    # hybrid scores from RRF are usually small; squash to [0,1] conservatively.
    return max(0.0, min(1.0, raw_hybrid * 6.0))


def _content_overlap_score(query_terms: set[str], text: str) -> float:
    """Token overlap score in [0,1] between query and chunk content."""
    if not query_terms or not text:
        return 0.0
    text_terms = set(re.findall(r"[a-z0-9_]+", text.lower()))
    if not text_terms:
        return 0.0
    overlap = len(query_terms & text_terms)
    if overlap <= 0:
        return 0.0
    return min(1.0, overlap / max(3, len(query_terms)))


def _query_looks_noisy(query_terms: set[str], query: str) -> bool:
    if not query:
        return False
    lowered_query = query.lower()
    if any(term in query_terms for term in NOISE_QUERY_TERMS):
        return True

    # Very short and generic prompts tend to be poor evidence anchors.
    if len(query_terms) <= 2 and len(lowered_query.strip()) < 16:
        return True

    return False


def _confidence_for_display(score: float, noisy_query: bool) -> float:
    """Convert internal score to user-facing confidence in [0,1]."""
    # Piecewise calibration: weak evidence remains low, strong evidence rises quickly.
    if score < 0.10:
        conf = score * 0.20
    elif score < 0.30:
        conf = 0.02 + (score - 0.10) * 1.10
    elif score < 0.50:
        conf = 0.24 + (score - 0.30) * 1.75
    elif score < 0.70:
        conf = 0.59 + (score - 0.50) * 1.50
    else:
        conf = 0.89 + (score - 0.70) * 0.30

    if noisy_query:
        conf *= 0.40

    return max(0.01, min(0.95, conf))


def format_citations(
    chunks: List[Dict[str, Any]], max_items: int = 3, query: str = ""
) -> List[Dict[str, Any]]:
    """Extract unique citations from retrieved chunks.

    Args:
        chunks: List of chunk dicts returned by retrieval.
        max_items: Max citation cards to return.
        query: User query for intent-sensitive citation filtering.

    Returns:
        Deduplicated and ranked list of citation dicts matching frontend interface.
    """
    q_terms = _query_terms(query)
    noisy_query = _query_looks_noisy(q_terms, query)

    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        path = chunk.get("file_path", "unknown")
        distance = chunk.get("distance")
        lexical = float(chunk.get("lexical_score", 0.0))
        hybrid = float(chunk.get("hybrid_score", 0.0))
        snippet = chunk.get("text_content", "")

        sem = _semantic_score(distance)
        hyb = _hybrid_score(hybrid)
        lex = min(1.0, lexical * 0.08)
        path_match = _path_match_score(path, query, q_terms)
        content_overlap = _content_overlap_score(q_terms, snippet)

        # Weighted evidence score [0,1]
        score = (
            0.58 * sem
            + 0.16 * hyb
            + 0.08 * lex
            + 0.06 * path_match
            + 0.12 * content_overlap
        )

        if sem >= 0.75 and content_overlap >= 0.25:
            score += 0.12
        elif sem >= 0.65 and content_overlap >= 0.20:
            score += 0.08

        if sem >= 0.85 and (lex > 0.10 or path_match > 0.0):
            score += 0.06

        score = min(1.0, score)

        # Penalize semantically-only matches with no lexical/path/content evidence.
        if lex == 0.0 and path_match == 0.0 and content_overlap == 0.0:
            if sem < 0.45:
                score *= 0.45
            elif sem < 0.70:
                score *= 0.70
            else:
                score *= 0.90
        elif lex == 0.0 and path_match == 0.0 and content_overlap < 0.20:
            if sem < 0.50:
                score *= 0.75
            elif sem < 0.75:
                score *= 0.90

        existing = grouped.get(path)
        if existing is None or score > existing["_score"]:
            grouped[path] = {
                "file_path": path,
                "file_name": os.path.basename(path),
                "snippet": snippet[:300] if snippet else "",
                "relevance_score": round(
                    _confidence_for_display(score, noisy_query), 4
                ),
                "chunk_index": chunk.get("chunk_index", 0),
                "_score": score,
                "_path_match": path_match,
                "_content_overlap": content_overlap,
                "_semantic": sem,
                "_lexical": lex,
            }

    ranked = sorted(grouped.values(), key=lambda c: c["_score"], reverse=True)
    if ranked:
        best = ranked[0]["_score"]
        lowered_query = (query or "").lower()
        path_intent = any(
            marker in lowered_query
            for marker in ("file", "directory", "folder", "path", "/", "\\")
        )

        if path_intent and any(c.get("_path_match", 0.0) > 0.0 for c in ranked):
            ranked = [c for c in ranked if c.get("_path_match", 0.0) > 0.0]
        else:
            threshold = max(0.12, best * 0.80)
            ranked = [c for c in ranked if c["_score"] >= threshold]

    trimmed = ranked[:max_items]

    low_evidence_query = False
    if trimmed and q_terms:
        max_overlap = max(float(c.get("_content_overlap", 0.0)) for c in trimmed)
        has_path_match = any(float(c.get("_path_match", 0.0)) > 0.0 for c in trimmed)
        max_semantic = max(float(c.get("_semantic", 0.0)) for c in trimmed)
        max_lexical = max(float(c.get("_lexical", 0.0)) for c in trimmed)
        low_evidence_query = (
            (max_overlap < 0.20)
            and (not has_path_match)
            and (max_semantic < 0.55)
            and (max_lexical < 0.08)
        )

    if low_evidence_query:
        for citation in trimmed:
            citation["relevance_score"] = round(
                max(0.01, min(0.95, float(citation["relevance_score"]) * 0.45)),
                4,
            )

    for citation in trimmed:
        citation.pop("_score", None)
        citation.pop("_path_match", None)
        citation.pop("_content_overlap", None)
        citation.pop("_semantic", None)
        citation.pop("_lexical", None)
    return trimmed
