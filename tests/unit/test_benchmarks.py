"""Unit tests for the benchmark evaluation system.

Covers: models, scoring, config loading, aggregation, CSV export, runner helpers.
"""

import csv
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Stub sqlite_vec if not available
if "sqlite_vec" not in sys.modules:
    _sv = MagicMock()
    _sv.serialize_float32 = lambda v: b"\x00"
    sys.modules["sqlite_vec"] = _sv

from benchmarks.models import (
    BenchmarkConfig,
    BenchmarkReport,
    CitationScore,
    IndexingResult,
    LatencyProfile,
    PromptConfig,
    QueryResult,
    ResponseScore,
    RetrievalScore,
    RunScore,
)
from benchmarks.scoring import (
    average_run_scores,
    extract_citations_from_response,
    normalize_path,
    score_citations,
    score_comparative_retrieval,
    score_file_retrieval,
    score_response_relevance,
)

# ======================================================================
# normalize_path
# ======================================================================


class TestNormalizePath:
    def test_forward_slash(self):
        assert normalize_path("foo\\bar\\baz.txt") == "foo/bar/baz.txt"

    def test_lowercase(self):
        assert normalize_path("Foo/BAR.TXT") == "foo/bar.txt"

    def test_strip_leading_dot_slash(self):
        assert normalize_path("./a/b.txt") == "a/b.txt"

    def test_double_dot_slash(self):
        assert normalize_path("././c.txt") == "c.txt"

    def test_whitespace_strip(self):
        assert normalize_path("  x.txt  ") == "x.txt"


# ======================================================================
# score_file_retrieval
# ======================================================================


class TestScoreFileRetrieval:
    def test_hit_at_1(self):
        score = score_file_retrieval(["a.txt", "b.txt"], "a.txt")
        assert score.hit_at_1 == 1
        assert score.hit_at_k == 1
        assert score.mrr == 1.0

    def test_hit_at_k_not_1(self):
        score = score_file_retrieval(["b.txt", "c.txt", "a.txt"], "a.txt", top_k=5)
        assert score.hit_at_1 == 0
        assert score.hit_at_k == 1
        assert score.mrr == pytest.approx(1 / 3)

    def test_miss(self):
        score = score_file_retrieval(["b.txt", "c.txt"], "a.txt")
        assert score.hit_at_1 == 0
        assert score.hit_at_k == 0
        assert score.mrr == 0.0

    def test_empty_retrieved(self):
        score = score_file_retrieval([], "a.txt")
        assert score.hit_at_1 == 0
        assert score.mrr == 0.0

    def test_path_normalization(self):
        score = score_file_retrieval(["./Foo/Bar.TXT"], "foo/bar.txt")
        assert score.hit_at_1 == 1


# ======================================================================
# score_comparative_retrieval
# ======================================================================


class TestScoreComparativeRetrieval:
    def test_all_found(self):
        score = score_comparative_retrieval(
            ["a.txt", "b.txt", "c.txt"], ["a.txt", "b.txt"], top_k=5
        )
        assert score.hit_at_1 == 1  # recall == 1.0
        assert score.hit_at_k == 1

    def test_partial_found(self):
        score = score_comparative_retrieval(
            ["a.txt", "c.txt"], ["a.txt", "b.txt"], top_k=5
        )
        assert score.hit_at_1 == 0  # recall < 1.0
        assert score.hit_at_k == 1  # at least one found

    def test_none_found(self):
        score = score_comparative_retrieval(
            ["x.txt", "y.txt"], ["a.txt", "b.txt"], top_k=5
        )
        assert score.hit_at_1 == 0
        assert score.hit_at_k == 0
        assert score.mrr == 0.0

    def test_empty_expected(self):
        score = score_comparative_retrieval(["a.txt"], [], top_k=5)
        assert score.mrr == 0.0


# ======================================================================
# score_response_relevance
# ======================================================================


class TestScoreResponseRelevance:
    def test_keyword_only(self):
        import asyncio

        score = asyncio.run(
            score_response_relevance(
                query="What is Python?",
                response="Python is a programming language with dynamic typing.",
                expected_keywords=["Python", "programming", "dynamic"],
                context_chunks=[],
            )
        )
        assert score.keyword_score == pytest.approx(1.0)
        assert score.composite_score == pytest.approx(1.0)  # only keyword layer

    def test_partial_keywords(self):
        import asyncio

        score = asyncio.run(
            score_response_relevance(
                query="What is Python?",
                response="Python is a language.",
                expected_keywords=["Python", "programming", "dynamic", "typing"],
                context_chunks=[],
            )
        )
        assert score.keyword_score == pytest.approx(0.25)  # 1/4

    def test_no_keywords(self):
        import asyncio

        score = asyncio.run(
            score_response_relevance(
                query="Hello",
                response="World",
                expected_keywords=None,
                context_chunks=[],
            )
        )
        assert score.keyword_score == 0.0
        assert score.composite_score == 0.0


# ======================================================================
# extract_citations_from_response & score_citations
# ======================================================================


class TestCitations:
    def test_extract_simple(self):
        text = "The answer is 42 (Source: data/answer.txt)."
        citations = extract_citations_from_response(text)
        assert len(citations) == 1
        assert "data/answer.txt" in citations[0]

    def test_extract_multiple(self):
        text = "First (Source: a.txt) and second (Source: b.txt) references."
        citations = extract_citations_from_response(text)
        assert len(citations) == 2

    def test_extract_none(self):
        citations = extract_citations_from_response("No citations here.")
        assert len(citations) == 0

    def test_score_correct_citation(self):
        response = "Answer (Source: docs/file.txt)"
        score = score_citations(response, "docs/file.txt")
        assert score.citation_present == 1
        assert score.citation_correct == 1

    def test_score_wrong_citation(self):
        response = "Answer (Source: docs/wrong.txt)"
        score = score_citations(response, "docs/file.txt")
        assert score.citation_present == 1
        assert score.citation_correct == 0

    def test_score_hallucinated(self):
        response = "Answer (Source: ghost.txt)"
        corpus = {"real.txt", "other.txt"}
        score = score_citations(response, "real.txt", corpus_files=corpus)
        assert len(score.hallucinated_citations) == 1
        assert score.hallucination_rate == pytest.approx(1.0)

    def test_no_citation_in_response(self):
        score = score_citations("No source here.", "docs/file.txt")
        assert score.citation_present == 0
        assert score.citation_correct == 0


# ======================================================================
# average_run_scores
# ======================================================================


class TestAverageRunScores:
    def test_single_run(self):
        run = RunScore(
            retrieval=RetrievalScore(hit_at_1=1, hit_at_k=1, mrr=1.0),
            response=ResponseScore(composite_score=0.8),
            citation=CitationScore(citation_present=1, citation_correct=1),
            latency=LatencyProfile(total_latency_ms=100),
        )
        avg = average_run_scores([run])
        assert avg.retrieval.hit_at_1 == 1
        assert avg.response.composite_score == pytest.approx(0.8)
        assert avg.latency.total_latency_ms == pytest.approx(100)

    def test_multiple_runs(self):
        runs = [
            RunScore(
                retrieval=RetrievalScore(hit_at_1=1, mrr=1.0),
                response=ResponseScore(composite_score=0.9),
                latency=LatencyProfile(total_latency_ms=100),
            ),
            RunScore(
                retrieval=RetrievalScore(hit_at_1=0, mrr=0.5),
                response=ResponseScore(composite_score=0.7),
                latency=LatencyProfile(total_latency_ms=200),
            ),
        ]
        avg = average_run_scores(runs)
        assert (
            avg.retrieval.hit_at_1 == 0
        )  # round(0.5) = 0 in Python 3 (banker's rounding)
        assert avg.retrieval.mrr == pytest.approx(0.75)
        assert avg.response.composite_score == pytest.approx(0.8)
        assert avg.latency.total_latency_ms == pytest.approx(150)

    def test_empty(self):
        avg = average_run_scores([])
        assert avg.retrieval.hit_at_1 == 0
        assert avg.response.composite_score == 0.0


# ======================================================================
# PromptConfig.from_dict
# ======================================================================


class TestPromptConfig:
    def test_minimal(self):
        d = {"id": "q1", "type": "qa", "query": "hello?"}
        p = PromptConfig.from_dict(d)
        assert p.id == "q1"
        assert p.type == "qa"
        assert p.query == "hello?"
        assert p.category == "simple"

    def test_full(self):
        d = {
            "id": "q2",
            "type": "file_retrieval",
            "query": "find the file",
            "category": "file_retrieval",
            "file_type": "code",
            "folder_size": "large",
            "expected_file": "a/b.py",
            "expected_rank": 2,
            "expected_answer_keywords": ["python"],
        }
        p = PromptConfig.from_dict(d)
        assert p.expected_file == "a/b.py"
        assert p.expected_rank == 2
        assert p.file_type == "code"


# ======================================================================
# BenchmarkConfig.from_dict
# ======================================================================


class TestBenchmarkConfig:
    def test_defaults(self):
        raw = {"benchmark": {}, "prompts": []}
        cfg = BenchmarkConfig.from_dict(raw)
        assert cfg.name == "RAG Pipeline Benchmark"
        assert cfg.runs_per_query == 3
        assert cfg.prompts == []

    def test_with_prompts(self):
        raw = {
            "benchmark": {"name": "Test", "top_k": 10},
            "prompts": [
                {"id": "p1", "type": "qa", "query": "what?"},
                {"id": "p2", "type": "file_retrieval", "query": "find x"},
            ],
        }
        cfg = BenchmarkConfig.from_dict(raw)
        assert cfg.name == "Test"
        assert cfg.top_k == 10
        assert len(cfg.prompts) == 2

    def test_yaml_load(self):
        """Verify the default_benchmark.yaml can be loaded."""
        import yaml

        yaml_path = (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "default_benchmark.yaml"
        )
        if not yaml_path.exists():
            pytest.skip("default_benchmark.yaml not found")
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cfg = BenchmarkConfig.from_dict(raw)
        assert len(cfg.prompts) >= 90
        assert cfg.version == "1.0.0"


# ======================================================================
# QueryResult.to_csv_row
# ======================================================================


class TestQueryResultCSV:
    def test_csv_row_keys(self):
        qr = QueryResult(
            prompt_id="q1",
            query_type="qa",
            category="simple",
            file_type="text",
            folder_size="small",
            scores=RunScore(
                retrieval=RetrievalScore(hit_at_1=1, hit_at_k=1, mrr=1.0),
                response=ResponseScore(composite_score=0.9),
                citation=CitationScore(citation_present=1),
                latency=LatencyProfile(total_latency_ms=42),
            ),
        )
        row = qr.to_csv_row()
        assert row["prompt_id"] == "q1"
        assert row["hit_at_1"] == 1
        assert row["total_latency_ms"] == 42
        assert "composite_score" in row

    def test_csv_roundtrip(self):
        """CSV write + read should preserve data."""
        qr = QueryResult(
            prompt_id="rt",
            query_type="qa",
            category="simple",
            file_type="text",
            folder_size="small",
            scores=RunScore(
                retrieval=RetrievalScore(hit_at_1=1, mrr=0.5),
                response=ResponseScore(composite_score=0.75),
                latency=LatencyProfile(total_latency_ms=123.4),
            ),
        )
        row = qr.to_csv_row()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
        buf.seek(0)
        reader = csv.DictReader(buf)
        loaded = next(reader)
        assert loaded["prompt_id"] == "rt"
        assert float(loaded["mrr"]) == pytest.approx(0.5)


# ======================================================================
# BenchmarkRunner._compute_group_stats
# ======================================================================


class TestAggregation:
    def test_group_stats(self):
        from benchmarks.runner import BenchmarkRunner

        results = [
            QueryResult(
                prompt_id="a",
                query_type="qa",
                category="simple",
                file_type="text",
                folder_size="small",
                scores=RunScore(
                    retrieval=RetrievalScore(hit_at_1=1, hit_at_k=1, mrr=1.0),
                    response=ResponseScore(composite_score=0.8, keyword_score=0.6),
                    citation=CitationScore(citation_present=1, citation_correct=1),
                    latency=LatencyProfile(total_latency_ms=100),
                ),
            ),
            QueryResult(
                prompt_id="b",
                query_type="qa",
                category="simple",
                file_type="text",
                folder_size="small",
                scores=RunScore(
                    retrieval=RetrievalScore(hit_at_1=0, hit_at_k=1, mrr=0.5),
                    response=ResponseScore(composite_score=0.6, keyword_score=0.4),
                    citation=CitationScore(citation_present=1, citation_correct=0),
                    latency=LatencyProfile(total_latency_ms=200),
                ),
            ),
        ]
        stats = BenchmarkRunner._compute_group_stats(results)

        assert stats["count"] == 2
        assert stats["hit_rate_at_1"] == pytest.approx(0.5)
        assert stats["hit_rate_at_k"] == pytest.approx(1.0)
        assert stats["mrr"] == pytest.approx(0.75)
        assert stats["avg_response_score"] == pytest.approx(0.7)
        assert stats["citation_correctness_rate"] == pytest.approx(0.5)
        assert stats["latency_mean_ms"] == pytest.approx(150.0)
        assert stats["throughput_qps"] > 0

    def test_empty_group(self):
        from benchmarks.runner import BenchmarkRunner

        stats = BenchmarkRunner._compute_group_stats([])
        assert stats == {}


# ======================================================================
# BenchmarkRunner._write_results (output files)
# ======================================================================


class TestWriteResults:
    def test_summary_json(self, tmp_path):
        from benchmarks.runner import BenchmarkRunner

        config = BenchmarkConfig(name="Test Run", output_dir=str(tmp_path))
        ctx = MagicMock()
        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner.config = config
        runner.ctx = ctx

        report = BenchmarkReport(
            overall={"count": 1, "hit_rate_at_1": 1.0},
            subgroups={},
            raw_results=[
                QueryResult(
                    prompt_id="t1",
                    query_type="qa",
                    category="simple",
                    file_type="text",
                    folder_size="small",
                    scores=RunScore(
                        retrieval=RetrievalScore(hit_at_1=1, mrr=1.0),
                        response=ResponseScore(composite_score=0.9),
                        latency=LatencyProfile(total_latency_ms=50),
                    ),
                )
            ],
            indexing=IndexingResult(total_time_s=1.0, doc_count=5),
            output_dir=str(tmp_path),
        )
        runner._write_results(report)

        summary_file = tmp_path / "summary.json"
        assert summary_file.exists()
        data = json.loads(summary_file.read_text(encoding="utf-8"))
        assert data["benchmark_name"] == "Test Run"
        assert data["indexing"]["doc_count"] == 5

        csv_file = tmp_path / "per_query.csv"
        assert csv_file.exists()
        lines = csv_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2  # header + 1 row

    def test_failed_retrievals_written(self, tmp_path):
        from benchmarks.runner import BenchmarkRunner

        config = BenchmarkConfig(output_dir=str(tmp_path))
        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner.config = config
        runner.ctx = MagicMock()

        report = BenchmarkReport(
            overall={},
            subgroups={},
            raw_results=[
                QueryResult(
                    prompt_id="f1",
                    query_type="file_retrieval",
                    scores=RunScore(
                        retrieval=RetrievalScore(
                            hit_at_1=0,
                            hit_at_k=0,
                            expected_file="a.txt",
                            retrieved_files=["b.txt"],
                        ),
                    ),
                ),
            ],
            indexing=IndexingResult(),
            output_dir=str(tmp_path),
        )
        runner._write_results(report)

        failed = tmp_path / "failed_retrievals.json"
        assert failed.exists()
        data = json.loads(failed.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["expected_file"] == "a.txt"

    def test_hallucinated_citations_written(self, tmp_path):
        from benchmarks.runner import BenchmarkRunner

        config = BenchmarkConfig(output_dir=str(tmp_path))
        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner.config = config
        runner.ctx = MagicMock()

        report = BenchmarkReport(
            overall={},
            subgroups={},
            raw_results=[
                QueryResult(
                    prompt_id="h1",
                    scores=RunScore(
                        citation=CitationScore(
                            hallucinated_citations=["ghost.txt"],
                            hallucination_rate=1.0,
                        ),
                    ),
                ),
            ],
            indexing=IndexingResult(),
            output_dir=str(tmp_path),
        )
        runner._write_results(report)

        hfile = tmp_path / "hallucinated_citations.json"
        assert hfile.exists()
        data = json.loads(hfile.read_text(encoding="utf-8"))
        assert data[0]["hallucinated"] == ["ghost.txt"]


# ======================================================================
# timed context manager
# ======================================================================


class TestTimed:
    def test_timed(self):
        import time

        from benchmarks.runner import timed

        with timed() as t:
            time.sleep(0.01)
        assert t["ms"] >= 5  # at least some measurable time
