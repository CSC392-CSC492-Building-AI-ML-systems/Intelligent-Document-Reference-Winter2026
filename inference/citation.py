"""Citation formatting helpers with confidence-calibrated scoring."""

import os
from typing import Any, Dict, List


STOP_WORDS = {
    "the",
    "is",
    "at",
    "which",
    "on",
    "in",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "it",
    "by",
    "be",
    "as",
    "do",
    "has",
    "had",
    "was",
    "are",
    "been",
    "with",
    "this",
    "that",
    "from",
    "can",
    "will",
    "but",
    "not",
    "all",
    "any",
    "about",
    "into",
    "its",
    "what",
    "how",
    "when",
    "where",
    "who",
    "why",
    "file",
    "files",
    "document",
    "documents",
    "page",
    "pages",
    "find",
    "show",
    "tell",
    "me",
    "give",
    "get",
    "see",
    "look",
    "search",
    "there",
    "here",
    "some",
    "more",
    "most",
    "other",
    "than",
    "then",
    "also",
    "just",
    "only",
    "very",
    "too",
    "so",
    "no",
    "yes",
    "up",
    "down",
    "out",
    "over",
    "under",
}


def _query_terms(query: str) -> set[str]:
    terms = re.findall(r"[a-z0-9_\-.]+", (query or "").lower())
    return {t for t in terms if len(t) > 1 and t not in STOP_WORDS}


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
    if dist >= 1.0:
        return 0.0
    raw = 1.0 - dist
    return raw**0.7


def _hybrid_score(raw_hybrid: float) -> float:
    return max(0.0, min(1.0, raw_hybrid * 8.0))


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
    if any(term in query_terms for term in NOISE_QUERY_TERMS):
        return True
    if len(query_terms) <= 2 and len(query.strip()) < 16:
        return True
    return False


def _confidence_for_display(score: float, noisy_query: bool) -> float:
    """Convert internal score to user-facing confidence in [0,1].

    Designed so that:
    - Strong matches (score > 0.55) display as 70-95%
    - Moderate matches (0.30-0.55) display as 35-70%
    - Weak matches (< 0.30) display as 5-35%
    """
    if score < 0.10:
        conf = score * 0.50
    elif score < 0.25:
        conf = 0.05 + (score - 0.10) * 1.33
    elif score < 0.40:
        conf = 0.25 + (score - 0.25) * 2.00
    elif score < 0.55:
        conf = 0.55 + (score - 0.40) * 1.67
    elif score < 0.75:
        conf = 0.80 + (score - 0.55) * 0.75
    else:
        conf = 0.95

    if noisy_query:
        conf *= 0.40

    return max(0.01, min(0.95, conf))


def format_citations(
    chunks: List[Dict[str, Any]], max_items: int = 3, query: str = ""
) -> List[Dict[str, Any]]:
    """Extract unique citations from retrieved chunks.

    Args:
        chunks: List of chunk dicts returned by search_with_metadata,
                each containing at least 'file_path' and optionally 'distance',
                'text_content', and 'chunk_index'.

    Returns:
        Deduplicated list of citation dicts matching the frontend Citation interface.
    """
    seen = set()
    citations: List[Dict[str, Any]] = []
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

        score = (
            0.52 * sem
            + 0.14 * hyb
            + 0.06 * lex
            + 0.06 * path_match
            + 0.22 * content_overlap
        )

        if sem >= 0.75 and content_overlap >= 0.25:
            score += 0.15
        elif sem >= 0.65 and content_overlap >= 0.20:
            score += 0.10
        elif sem >= 0.55 and content_overlap >= 0.15:
            score += 0.05

        if sem >= 0.85 and (lex > 0.10 or path_match > 0.0):
            score += 0.08

        score = min(1.0, score)

        if lex == 0.0 and path_match == 0.0 and content_overlap == 0.0:
            if sem < 0.40:
                score *= 0.25
            elif sem < 0.55:
                score *= 0.45
            elif sem < 0.70:
                score *= 0.60
            else:
                score *= 0.80
        elif lex == 0.0 and path_match == 0.0 and content_overlap < 0.15:
            if sem < 0.50:
                score *= 0.55
            elif sem < 0.70:
                score *= 0.75

        existing = grouped.get(path)
        if existing is None or score > existing["_score"]:
            entry: Dict[str, Any] = {
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
            page = chunk.get("page_number")
            section = chunk.get("section")
            if page is not None:
                entry["page_number"] = page
            if section:
                entry["section"] = section
            grouped[path] = entry

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
            threshold = max(0.15, best * 0.60)
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
            and (max_semantic < 0.75)
            and (max_lexical < 0.08)
        )

    if low_evidence_query:
        for citation in trimmed:
            citation["relevance_score"] = round(
                max(0.01, min(0.95, float(citation["relevance_score"]) * 0.45)),
                4,
            )
    return citations
