"""Data models for the benchmark evaluation system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Config models (loaded from YAML)
# ---------------------------------------------------------------------------


@dataclass
class PromptConfig:
    """Single benchmark prompt loaded from the config YAML."""

    id: str
    type: str  # "file_retrieval", "qa", "comparative"
    query: str
    category: str = "simple"
    file_type: str = "text"
    folder_size: str = "small"

    # file_retrieval fields
    expected_file: Optional[str] = None
    expected_rank: int = 1

    # qa / comparative fields
    expected_files: Optional[List[str]] = None
    expected_answer_keywords: Optional[List[str]] = None
    expected_citation_file: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PromptConfig":
        return cls(
            id=d["id"],
            type=d["type"],
            query=d["query"],
            category=d.get("category", "simple"),
            file_type=d.get("file_type", "text"),
            folder_size=d.get("folder_size", "small"),
            expected_file=d.get("expected_file"),
            expected_rank=d.get("expected_rank", 1),
            expected_files=d.get("expected_files"),
            expected_answer_keywords=d.get("expected_answer_keywords"),
            expected_citation_file=d.get("expected_citation_file"),
        )


@dataclass
class DatasetSuiteConfig:
    """Per-dataset benchmark suite definition loaded from YAML."""

    id: str
    path: str
    levels: Dict[str, int] = field(
        default_factory=lambda: {"easy": 2, "medium": 2, "hard": 1}
    )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetSuiteConfig":
        raw_levels = d.get("levels") if isinstance(d.get("levels"), dict) else {}
        levels = {
            "easy": int(raw_levels.get("easy", 2)),
            "medium": int(raw_levels.get("medium", 2)),
            "hard": int(raw_levels.get("hard", 1)),
        }
        return cls(
            id=str(d.get("id") or d.get("path") or "dataset"),
            path=str(d.get("path") or "").strip(),
            levels=levels,
        )


@dataclass
class BenchmarkConfig:
    """Top-level benchmark configuration."""

    name: str = "RAG Pipeline Benchmark"
    version: str = "1.0.0"
    dataset_path: str = "benchmarks/datasets/"
    runs_per_query: int = 3
    top_k: int = 5
    prompts: List[PromptConfig] = field(default_factory=list)
    dataset_suites: List[DatasetSuiteConfig] = field(default_factory=list)
    no_graphs: bool = False
    output_dir: str = "benchmarks/results/"
    skip_indexing: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BenchmarkConfig":
        bench = d.get("benchmark", {})
        raw_prompts = d.get("prompts", [])
        raw_suites = bench.get("dataset_suites", [])
        return cls(
            name=bench.get("name", "RAG Pipeline Benchmark"),
            version=bench.get("version", "1.0.0"),
            dataset_path=bench.get("dataset_path", "benchmarks/datasets/"),
            runs_per_query=bench.get("runs_per_query", 3),
            top_k=bench.get("top_k", 5),
            prompts=[PromptConfig.from_dict(p) for p in raw_prompts],
            dataset_suites=[
                DatasetSuiteConfig.from_dict(s)
                for s in raw_suites
                if isinstance(s, dict)
            ],
        )


# ---------------------------------------------------------------------------
# Latency profiling
# ---------------------------------------------------------------------------


@dataclass
class LatencyProfile:
    """Timing measurements for a single query execution."""

    query_id: str = ""
    indexing_latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    rerank_latency_ms: float = 0.0
    inference_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    chunk_count: int = 0
    token_count_prompt: int = 0
    token_count_response: int = 0


# ---------------------------------------------------------------------------
# Scoring results
# ---------------------------------------------------------------------------


@dataclass
class RetrievalScore:
    """Retrieval accuracy for a single query."""

    hit_at_1: int = 0
    hit_at_k: int = 0
    mrr: float = 0.0
    retrieved_files: List[str] = field(default_factory=list)
    expected_file: str = ""


@dataclass
class ResponseScore:
    """Response quality for a single query."""

    keyword_score: float = 0.0
    llm_judge_score: float = 0.0
    llm_judge_breakdown: Dict[str, float] = field(default_factory=dict)
    semantic_similarity: float = 0.0
    composite_score: float = 0.0


@dataclass
class CitationScore:
    """Citation accuracy for a single query."""

    citation_present: int = 0
    citation_correct: int = 0
    hallucinated_citations: List[str] = field(default_factory=list)
    hallucination_rate: float = 0.0


@dataclass
class RunScore:
    """All scores for a single run of a single query."""

    retrieval: RetrievalScore = field(default_factory=RetrievalScore)
    response: ResponseScore = field(default_factory=ResponseScore)
    citation: CitationScore = field(default_factory=CitationScore)
    latency: LatencyProfile = field(default_factory=LatencyProfile)


@dataclass
class QueryResult:
    """Aggregated results for one prompt across all runs."""

    prompt_id: str = ""
    query_type: str = ""
    category: str = ""
    file_type: str = ""
    folder_size: str = ""
    dataset_id: str = ""
    scores: RunScore = field(default_factory=RunScore)
    raw_runs: List[RunScore] = field(default_factory=list)

    def to_csv_row(self) -> Dict[str, Any]:
        """Flatten to a dict suitable for CSV export."""
        return {
            "prompt_id": self.prompt_id,
            "query_type": self.query_type,
            "category": self.category,
            "file_type": self.file_type,
            "folder_size": self.folder_size,
            "dataset_id": self.dataset_id,
            "hit_at_1": self.scores.retrieval.hit_at_1,
            "hit_at_k": self.scores.retrieval.hit_at_k,
            "mrr": self.scores.retrieval.mrr,
            "keyword_score": self.scores.response.keyword_score,
            "llm_judge_score": self.scores.response.llm_judge_score,
            "semantic_similarity": self.scores.response.semantic_similarity,
            "composite_score": self.scores.response.composite_score,
            "citation_present": self.scores.citation.citation_present,
            "citation_correct": self.scores.citation.citation_correct,
            "hallucination_rate": self.scores.citation.hallucination_rate,
            "retrieval_latency_ms": self.scores.latency.retrieval_latency_ms,
            "inference_latency_ms": self.scores.latency.inference_latency_ms,
            "total_latency_ms": self.scores.latency.total_latency_ms,
            "chunk_count": self.scores.latency.chunk_count,
            "token_count_prompt": self.scores.latency.token_count_prompt,
            "token_count_response": self.scores.latency.token_count_response,
        }


# ---------------------------------------------------------------------------
# Indexing results
# ---------------------------------------------------------------------------


@dataclass
class IndexingResult:
    """Performance metrics from indexing the evaluation corpus."""

    total_time_s: float = 0.0
    doc_count: int = 0
    chunk_count: int = 0
    embedding_count: int = 0


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkReport:
    """Complete benchmark report with overall and subgroup metrics."""

    overall: Dict[str, Any] = field(default_factory=dict)
    subgroups: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    raw_results: List[QueryResult] = field(default_factory=list)
    indexing: IndexingResult = field(default_factory=IndexingResult)
    output_dir: str = ""
