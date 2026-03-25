"""BenchmarkRunner — orchestrates end-to-end benchmark evaluation."""

from __future__ import annotations

import asyncio
import csv
import datetime
import json
import logging
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from benchmarks.models import (
    BenchmarkConfig,
    BenchmarkReport,
    DatasetSuiteConfig,
    IndexingResult,
    LatencyProfile,
    QueryResult,
    RunScore,
)
from benchmarks.scoring import (
    average_run_scores,
    normalize_path,
    score_citations,
    score_comparative_retrieval,
    score_file_retrieval,
    score_response_relevance,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------


@contextmanager
def timed():
    """Context manager that records elapsed wall-clock time in milliseconds.

    Usage::

        with timed() as t:
            ...
        elapsed_ms = t["ms"]
    """
    result: Dict[str, float] = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["ms"] = (time.perf_counter() - start) * 1000.0


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------


class BenchmarkRunner:
    """Run benchmark queries against the RAG pipeline and collect metrics."""

    def __init__(
        self,
        config: BenchmarkConfig,
        ctx: Any,
        indexing_llm_client: Any | None = None,
    ) -> None:
        self.config = config
        self.ctx = ctx  # AppContext
        self.indexing_llm_client = indexing_llm_client or ctx.inference_client

        # Build the high-level responder from the AppContext components
        from inference.responder import Responder

        self.responder = Responder(
            db=ctx.db,
            embedding_client=ctx.embedding_client,
            inference_client=ctx.inference_client,
        )

        # Build corpus file set for hallucination detection
        self._corpus_files: Optional[Set[str]] = None

        # Per-query log file handle (opened during run)
        self._log_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> BenchmarkReport:
        """Execute the full benchmark: index → query → aggregate → write → graph → print."""
        output_dir = self.config.output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Set up continuous per-query log file
        self._log_path = Path(output_dir) / "benchmark_run.log"
        self._init_log_file()

        suite_mode = bool(self.config.dataset_suites)
        results: List[QueryResult] = []
        indexing_result = IndexingResult()

        if suite_mode:
            self._append_log(
                "Running dataset suite mode with %d datasets"
                % len(self.config.dataset_suites)
            )
            for suite in self.config.dataset_suites:
                suite_results, suite_indexing = await self._run_dataset_suite(
                    suite=suite,
                    output_dir=output_dir,
                )
                results.extend(suite_results)
                indexing_result.total_time_s += suite_indexing.total_time_s
                indexing_result.doc_count += suite_indexing.doc_count
                indexing_result.chunk_count += suite_indexing.chunk_count
                indexing_result.embedding_count += suite_indexing.embedding_count
        else:
            # Legacy single-dataset behavior.
            self._setup_benchmark_db(output_dir)

            if not self.config.skip_indexing:
                logger.info("Indexing dataset at %s …", self.config.dataset_path)
                self._append_log("Indexing dataset at %s …" % self.config.dataset_path)
                indexing_result = await self._run_indexing()
                self._append_log(
                    "Indexing complete: %d docs, %d chunks in %.1fs"
                    % (
                        indexing_result.doc_count,
                        indexing_result.chunk_count,
                        indexing_result.total_time_s,
                    )
                )
            else:
                logger.info("Skipping indexing (--skip-indexing)")
                self._append_log("Skipping indexing (--skip-indexing)")

            self._corpus_files = self._collect_corpus_files()

            total = len(self.config.prompts)
            logger.info(
                "Running %d prompts × %d runs …", total, self.config.runs_per_query
            )
            self._append_log(
                "Running %d prompts × %d runs …" % (total, self.config.runs_per_query)
            )

            for idx, prompt in enumerate(self.config.prompts):
                result = await self._run_query(
                    prompt, None, idx + 1, total, dataset_id=""
                )
                results.append(result)
                self._log_query_result(result, idx + 1, total)

            self._append_log("All %d prompts completed." % total)

        # Step 3 — Aggregate
        report = self._aggregate(results, indexing_result, output_dir)

        # Step 4 — Write output files
        self._write_results(report)

        # Step 5 — Graphs
        if not self.config.no_graphs:
            try:
                from benchmarks.graphs import generate_graphs

                n = generate_graphs(report, output_dir)
                logger.info("Generated %d graphs in %s/graphs/", n, output_dir)
            except Exception as e:
                logger.warning("Graph generation failed: %s", e)

        # Step 6 — Terminal summary
        self._print_summary(report)

        return report

    # ------------------------------------------------------------------
    # Isolated benchmark database
    # ------------------------------------------------------------------

    def _setup_benchmark_db(self, output_dir: str, suffix: str = "") -> None:
        """Create a fresh, isolated DB for this benchmark run.

        This ensures the retriever only finds files from the benchmark
        dataset, not leftover data from previous UI indexing sessions.
        """
        from db.unified import UnifiedDatabase

        safe_suffix = f"_{suffix}" if suffix else ""
        db_path = str(Path(output_dir) / f"benchmark{safe_suffix}.db")
        # Remove stale DB from a previous run so we start clean
        db_file = Path(db_path)
        if db_file.exists():
            db_file.unlink()

        vector_dimension = int(
            (getattr(self.ctx, "runtime_preferences", {}) or {}).get(
                "embedding_dimension",
                getattr(
                    getattr(self.ctx, "settings", None), "embedding_dimension", 3072
                ),
            )
        )
        benchmark_db = UnifiedDatabase(
            db_path=db_path, vector_dimension=vector_dimension
        )
        self.ctx.db = benchmark_db

        # Re-wire the responder so it uses the benchmark DB too
        from inference.responder import Responder

        self.responder = Responder(
            db=benchmark_db,
            embedding_client=self.ctx.embedding_client,
            inference_client=self.ctx.inference_client,
        )

        logger.info(
            "Using isolated benchmark DB: %s (vector dim=%d)",
            db_path,
            vector_dimension,
        )
        self._append_log(
            "Using isolated benchmark DB: %s (vector dim=%d)"
            % (db_path, vector_dimension)
        )

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path.replace("\\", "/").lower().strip()

    def _prompt_expected_paths(self, prompt: Any) -> List[str]:
        paths: List[str] = []
        if getattr(prompt, "expected_file", None):
            paths.append(str(prompt.expected_file))
        if getattr(prompt, "expected_files", None):
            paths.extend(str(p) for p in (prompt.expected_files or []))
        if getattr(prompt, "expected_citation_file", None):
            paths.append(str(prompt.expected_citation_file))
        return paths

    def _prompt_matches_suite(self, prompt: Any, suite_path: str) -> bool:
        normalized_suite = self._normalize_path(suite_path).rstrip("/")
        if not normalized_suite:
            return False
        marker = f"/{normalized_suite}/"
        for raw in self._prompt_expected_paths(prompt):
            normalized = f"/{self._normalize_path(raw).strip('/')}"
            if marker in normalized + "/":
                return True
        return False

    def _difficulty(self, prompt: Any) -> str:
        category = str(getattr(prompt, "category", "")).lower()
        folder_size = str(getattr(prompt, "folder_size", "")).lower()
        if category in {"file_retrieval", "simple"}:
            return "easy"
        if category in {"medium", "comparative"}:
            return "medium"
        if category in {"code_understanding", "image_ocr"}:
            return "hard"
        if folder_size == "small":
            return "easy"
        if folder_size == "medium":
            return "medium"
        return "hard"

    def _select_suite_prompts(self, suite: DatasetSuiteConfig) -> List[Any]:
        matching = [
            p for p in self.config.prompts if self._prompt_matches_suite(p, suite.path)
        ]
        if not matching:
            return []

        buckets: Dict[str, List[Any]] = {"easy": [], "medium": [], "hard": []}
        for prompt in matching:
            buckets[self._difficulty(prompt)].append(prompt)

        selected: List[Any] = []
        selected_ids: Set[str] = set()
        for level in ("easy", "medium", "hard"):
            target = max(0, int((suite.levels or {}).get(level, 0)))
            if target <= 0:
                continue
            for prompt in buckets[level][:target]:
                if prompt.id not in selected_ids:
                    selected.append(prompt)
                    selected_ids.add(prompt.id)

        # If a bucket was short, top up from remaining matching prompts.
        target_total = sum(max(0, int(v)) for v in (suite.levels or {}).values())
        if len(selected) < target_total:
            for prompt in matching:
                if prompt.id in selected_ids:
                    continue
                selected.append(prompt)
                selected_ids.add(prompt.id)
                if len(selected) >= target_total:
                    break

        return selected

    async def _run_dataset_suite(
        self,
        *,
        suite: DatasetSuiteConfig,
        output_dir: str,
    ) -> tuple[List[QueryResult], IndexingResult]:
        suite_id = suite.id or suite.path
        suite_prompts = self._select_suite_prompts(suite)
        if not suite_prompts:
            self._append_log(
                f"Skipping suite {suite_id}: no matching prompts for {suite.path}"
            )
            return [], IndexingResult()

        self._append_log(
            f"=== Suite {suite_id}: dataset={suite.path}, prompts={len(suite_prompts)} ==="
        )
        self._setup_benchmark_db(output_dir, suffix=suite_id)

        previous_dataset_path = self.config.dataset_path
        self.config.dataset_path = suite.path
        indexing_result = IndexingResult()

        try:
            if not self.config.skip_indexing:
                logger.info("Indexing suite %s at %s …", suite_id, suite.path)
                self._append_log(f"Indexing dataset at {suite.path} …")
                indexing_result = await self._run_indexing()
                self._append_log(
                    "Indexing complete: %d docs, %d chunks in %.1fs"
                    % (
                        indexing_result.doc_count,
                        indexing_result.chunk_count,
                        indexing_result.total_time_s,
                    )
                )
            else:
                self._append_log("Skipping indexing (--skip-indexing)")

            self._corpus_files = self._collect_corpus_files()

            suite_results: List[QueryResult] = []
            total = len(suite_prompts)
            self._append_log(
                "Running %d prompts × %d runs for suite %s …"
                % (total, self.config.runs_per_query, suite_id)
            )
            for idx, prompt in enumerate(suite_prompts):
                result = await self._run_query(
                    prompt,
                    None,
                    idx + 1,
                    total,
                    dataset_id=suite_id,
                )
                suite_results.append(result)
                self._log_query_result(result, idx + 1, total)
            return suite_results, indexing_result
        finally:
            self.config.dataset_path = previous_dataset_path

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def _run_indexing(self) -> IndexingResult:
        """Index the dataset directory and return timing/counts."""
        from ingestion.pipeline import PipelineConfig
        from ingestion.pipeline import run as run_ingestion

        dataset_path = Path(self.config.dataset_path).resolve()
        if not dataset_path.exists():
            logger.error("Dataset path does not exist: %s", dataset_path)
            return IndexingResult()

        # Benchmarks should be deterministic and independent from optional OCR tools.
        previous_ocr_enabled = os.environ.get("OCR_ENABLED")
        os.environ["OCR_ENABLED"] = "false"
        try:
            pipeline_cfg = PipelineConfig(
                # Benchmark retrieval requires vectors to exist in vec_items.
                embed_after_chunk=True,
                dedup_enabled=True,
            )
            with timed() as t:
                output = await asyncio.to_thread(
                    run_ingestion,
                    str(dataset_path),
                    config=pipeline_cfg,
                    db=self.ctx.db,
                    embedder=self.ctx.embedding_client.embed_text,
                    llm_client=self.indexing_llm_client,
                )
        finally:
            if previous_ocr_enabled is None:
                os.environ.pop("OCR_ENABLED", None)
            else:
                os.environ["OCR_ENABLED"] = previous_ocr_enabled

        return IndexingResult(
            total_time_s=t["ms"] / 1000.0,
            doc_count=output.files_processed,
            chunk_count=output.chunks_generated,
            embedding_count=len(output.embeddings) if output.embeddings else 0,
        )

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    async def _run_query(
        self,
        prompt: Any,  # PromptConfig
        semaphore: Optional[asyncio.Semaphore],
        idx: int,
        total: int,
        dataset_id: str,
    ) -> QueryResult:
        """Execute a single prompt N times, score each run, and average."""

        async def _inner() -> QueryResult:
            runs: List[RunScore] = []
            for run_idx in range(self.config.runs_per_query):
                run_score = await self._execute_single_run(prompt)
                runs.append(run_score)

            averaged = average_run_scores(runs)
            logger.info(
                "[%d/%d] %s  hit@1=%d  composite=%.2f  latency=%.0fms",
                idx,
                total,
                prompt.id,
                averaged.retrieval.hit_at_1,
                averaged.response.composite_score,
                averaged.latency.total_latency_ms,
            )

            return QueryResult(
                prompt_id=prompt.id,
                query_type=prompt.type,
                category=prompt.category,
                file_type=prompt.file_type,
                folder_size=prompt.folder_size,
                dataset_id=dataset_id,
                scores=averaged,
                raw_runs=runs,
            )

        if semaphore is not None:
            async with semaphore:
                return await _inner()
        return await _inner()

    async def _execute_single_run(self, prompt: Any) -> RunScore:
        """Run one query through the pipeline and score it."""
        top_k = self.config.top_k

        # --- 1. Retrieval (timed) ---
        with timed() as t_ret:
            from inference.retriever import Retriever

            retriever = Retriever(
                db=self.ctx.db, embedding_client=self.ctx.embedding_client
            )
            chunks = await retriever.retrieve(prompt.query, top_k=top_k)

        retrieved_files = [c.get("file_path", c.get("path", "")) for c in chunks]

        # --- 2. Inference (timed) ---
        with timed() as t_inf:
            from inference.rag import RAGProcessor

            rag = RAGProcessor(inference_client=self.ctx.inference_client)
            answer = await rag.generate_response(prompt.query, chunks)

        # --- 3. Scoring ---
        # Retrieval score
        if prompt.type == "comparative" and prompt.expected_files:
            retrieval = score_comparative_retrieval(
                retrieved_files, prompt.expected_files, top_k
            )
        elif prompt.expected_file:
            retrieval = score_file_retrieval(
                retrieved_files, prompt.expected_file, top_k
            )
        else:
            from benchmarks.models import RetrievalScore

            retrieval = RetrievalScore(
                retrieved_files=[normalize_path(f) for f in retrieved_files]
            )

        # Response relevance score
        response_score = await score_response_relevance(
            prompt.query,
            answer,
            prompt.expected_answer_keywords,
            chunks,
            judge_client=self.ctx.inference_client,
            embedding_client=self.ctx.embedding_client,
        )

        # Citation score
        citation = score_citations(
            answer,
            prompt.expected_citation_file,
            corpus_files=self._corpus_files,
        )

        # Latency profile
        total_ms = t_ret["ms"] + t_inf["ms"]
        latency = LatencyProfile(
            query_id=prompt.id,
            retrieval_latency_ms=t_ret["ms"],
            inference_latency_ms=t_inf["ms"],
            total_latency_ms=total_ms,
            chunk_count=len(chunks),
            token_count_prompt=len(prompt.query.split()),
            token_count_response=len(answer.split()),
        )

        return RunScore(
            retrieval=retrieval,
            response=response_score,
            citation=citation,
            latency=latency,
        )

    # ------------------------------------------------------------------
    # Corpus file collection
    # ------------------------------------------------------------------

    def _collect_corpus_files(self) -> Set[str]:
        """Query the DB for all indexed file paths."""
        try:
            conn = self.ctx.db._get_conn()
            try:
                rows = conn.execute("SELECT path FROM files").fetchall()
                return {normalize_path(r["path"]) for r in rows}
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Could not collect corpus files: %s", e)
            return set()

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        results: List[QueryResult],
        indexing: IndexingResult,
        output_dir: str,
    ) -> BenchmarkReport:
        """Compute overall and subgroup metrics from raw results."""
        if not results:
            return BenchmarkReport(
                raw_results=results,
                indexing=indexing,
                output_dir=output_dir,
            )

        overall = self._compute_group_stats(results)

        # Subgroup disaggregation
        subgroups: Dict[str, Dict[str, Any]] = {}
        for dimension in (
            "query_type",
            "category",
            "file_type",
            "folder_size",
            "dataset_id",
        ):
            groups: Dict[str, List[QueryResult]] = defaultdict(list)
            for r in results:
                key = getattr(r, dimension, "unknown")
                groups[key].append(r)
            subgroups[dimension] = {
                k: self._compute_group_stats(v) for k, v in groups.items()
            }

        return BenchmarkReport(
            overall=overall,
            subgroups=subgroups,
            raw_results=results,
            indexing=indexing,
            output_dir=output_dir,
        )

    @staticmethod
    def _compute_group_stats(results: List[QueryResult]) -> Dict[str, Any]:
        """Compute aggregate statistics for a group of results."""
        n = len(results)
        if n == 0:
            return {}

        hit1 = [r.scores.retrieval.hit_at_1 for r in results]
        hitk = [r.scores.retrieval.hit_at_k for r in results]
        mrrs = [r.scores.retrieval.mrr for r in results]
        composites = [r.scores.response.composite_score for r in results]
        keywords = [r.scores.response.keyword_score for r in results]
        judge = [r.scores.response.llm_judge_score for r in results]
        cite_present = [r.scores.citation.citation_present for r in results]
        cite_correct = [r.scores.citation.citation_correct for r in results]
        halluc = [r.scores.citation.hallucination_rate for r in results]
        latencies = [r.scores.latency.total_latency_ms for r in results]

        def _avg(vals: list) -> float:
            return sum(vals) / len(vals) if vals else 0.0

        sorted_lat = sorted(latencies)

        expected_scored = [
            r for r in results if bool((r.scores.retrieval.expected_file or "").strip())
        ]
        expected_total = len(expected_scored)
        correct_at_1_count = sum(r.scores.retrieval.hit_at_1 for r in expected_scored)
        correct_at_k_count = sum(r.scores.retrieval.hit_at_k for r in expected_scored)
        incorrect_at_k_count = max(0, expected_total - correct_at_k_count)

        return {
            "count": n,
            "retrieval_expected_total": expected_total,
            "retrieval_correct_at_1_count": correct_at_1_count,
            "retrieval_correct_at_k_count": correct_at_k_count,
            "retrieval_incorrect_at_k_count": incorrect_at_k_count,
            "retrieval_correct_at_1_rate": (
                correct_at_1_count / expected_total if expected_total > 0 else 0.0
            ),
            "retrieval_correct_at_k_rate": (
                correct_at_k_count / expected_total if expected_total > 0 else 0.0
            ),
            "hit_rate_at_1": _avg(hit1),
            "hit_rate_at_k": _avg(hitk),
            "mrr": _avg(mrrs),
            "avg_response_score": _avg(composites),
            "avg_keyword_score": _avg(keywords),
            "avg_judge_score": _avg(judge),
            "citation_presence_rate": _avg(cite_present),
            "citation_correctness_rate": _avg(cite_correct),
            "avg_hallucination_rate": _avg(halluc),
            "latency_p50_ms": _percentile(sorted_lat, 50),
            "latency_p90_ms": _percentile(sorted_lat, 90),
            "latency_p99_ms": _percentile(sorted_lat, 99),
            "latency_mean_ms": _avg(latencies),
            "throughput_qps": (
                n / (sum(latencies) / 1000.0) if sum(latencies) > 0 else 0.0
            ),
        }

    @staticmethod
    def _paths_match_for_report(actual: str, expected: str) -> bool:
        actual_n = normalize_path(actual).rstrip("/")
        expected_n = normalize_path(expected).rstrip("/")
        if not actual_n or not expected_n:
            return False
        if actual_n == expected_n:
            return True
        return actual_n.endswith("/" + expected_n) or expected_n.endswith(
            "/" + actual_n
        )

    @staticmethod
    def _split_expected_paths(expected: str) -> List[str]:
        return [part.strip() for part in str(expected).split(",") if part.strip()]

    # ------------------------------------------------------------------
    # Output file writing
    # ------------------------------------------------------------------

    def _write_results(self, report: BenchmarkReport) -> None:
        """Write summary.json, per_query.csv, failed_retrievals.json, hallucinated_citations.json."""
        out = Path(report.output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # --- summary.json ---
        summary = {
            "benchmark_name": self.config.name,
            "version": self.config.version,
            "dataset_path": self.config.dataset_path,
            "dataset_suites": [
                {"id": s.id, "path": s.path, "levels": s.levels}
                for s in self.config.dataset_suites
            ],
            "runs_per_query": self.config.runs_per_query,
            "top_k": self.config.top_k,
            "total_prompts": len(report.raw_results),
            "overall": report.overall,
            "subgroups": report.subgroups,
            "indexing": {
                "total_time_s": report.indexing.total_time_s,
                "doc_count": report.indexing.doc_count,
                "chunk_count": report.indexing.chunk_count,
                "embedding_count": report.indexing.embedding_count,
            },
        }
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        logger.info("Wrote %s", out / "summary.json")

        # --- per_query.csv ---
        if report.raw_results:
            fieldnames = list(report.raw_results[0].to_csv_row().keys())
            with open(out / "per_query.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in report.raw_results:
                    writer.writerow(r.to_csv_row())
            logger.info("Wrote %s", out / "per_query.csv")

        # --- failed_retrievals.json ---
        failed = [
            {
                "prompt_id": r.prompt_id,
                "query_type": r.query_type,
                "expected_file": r.scores.retrieval.expected_file,
                "expected_files": self._split_expected_paths(
                    r.scores.retrieval.expected_file
                ),
                "retrieved_files": r.scores.retrieval.retrieved_files,
                "matched_expected_files": [
                    exp
                    for exp in self._split_expected_paths(
                        r.scores.retrieval.expected_file
                    )
                    if any(
                        self._paths_match_for_report(ret, exp)
                        for ret in r.scores.retrieval.retrieved_files
                    )
                ],
                "match_debug": {
                    "matched_expected_count": sum(
                        1
                        for exp in self._split_expected_paths(
                            r.scores.retrieval.expected_file
                        )
                        if any(
                            self._paths_match_for_report(ret, exp)
                            for ret in r.scores.retrieval.retrieved_files
                        )
                    ),
                    "retrieved_count": len(r.scores.retrieval.retrieved_files),
                },
                "hit_at_k": r.scores.retrieval.hit_at_k,
            }
            for r in report.raw_results
            if r.scores.retrieval.expected_file and r.scores.retrieval.hit_at_k == 0
        ]
        (out / "failed_retrievals.json").write_text(
            json.dumps(failed, indent=2, default=str), encoding="utf-8"
        )
        logger.info(
            "Wrote %d failed retrievals to %s",
            len(failed),
            out / "failed_retrievals.json",
        )

        # --- hallucinated_citations.json ---
        hallucinated = [
            {
                "prompt_id": r.prompt_id,
                "hallucinated": r.scores.citation.hallucinated_citations,
                "hallucination_rate": r.scores.citation.hallucination_rate,
            }
            for r in report.raw_results
            if r.scores.citation.hallucinated_citations
        ]
        (out / "hallucinated_citations.json").write_text(
            json.dumps(hallucinated, indent=2, default=str), encoding="utf-8"
        )
        logger.info(
            "Wrote %d hallucination records to %s",
            len(hallucinated),
            out / "hallucinated_citations.json",
        )

    # ------------------------------------------------------------------
    # Terminal summary
    # ------------------------------------------------------------------

    def _print_summary(self, report: BenchmarkReport) -> None:
        """Print a formatted terminal summary using box-drawing characters."""
        o = report.overall
        if not o:
            print("No results to summarise.")
            return

        W = 72
        HL = "─" * W
        print()
        print(f"╔{'═' * W}╗")
        print(f"║{'BENCHMARK RESULTS':^{W}}║")
        print(f"╠{'═' * W}╣")
        print(f"║  {'Name:':<20}{self.config.name:<{W - 23}}║")
        print(f"║  {'Dataset:':<20}{self.config.dataset_path:<{W - 23}}║")
        print(f"║  {'Prompts:':<20}{o.get('count', 0):<{W - 23}}║")
        print(f"║  {'Runs/query:':<20}{self.config.runs_per_query:<{W - 23}}║")
        print(f"╠{'═' * W}╣")

        # Retrieval
        print(f"║{'  RETRIEVAL':─<{W}}║")
        print(
            f"║    Correct@K:    {int(o.get('retrieval_correct_at_k_count', 0)):>4d}/"
            f"{int(o.get('retrieval_expected_total', 0)):<4d}"
            f" ({o.get('retrieval_correct_at_k_rate', 0):>5.1%})"
            f"{'':>{W - 45}}║"
        )
        print(f"║    Hit@1:        {o.get('hit_rate_at_1', 0):>8.1%}{'':>{W - 29}}║")
        print(f"║    Hit@K:        {o.get('hit_rate_at_k', 0):>8.1%}{'':>{W - 29}}║")
        print(f"║    MRR:          {o.get('mrr', 0):>8.3f}{'':>{W - 29}}║")
        print(f"║{HL}║")

        # Response quality
        print(f"║{'  RESPONSE QUALITY':─<{W}}║")
        print(
            f"║    Composite:    {o.get('avg_response_score', 0):>8.3f}{'':>{W - 29}}║"
        )
        print(
            f"║    Keyword:      {o.get('avg_keyword_score', 0):>8.3f}{'':>{W - 29}}║"
        )
        print(f"║    LLM Judge:    {o.get('avg_judge_score', 0):>8.3f}{'':>{W - 29}}║")
        print(f"║{HL}║")

        # Citations
        print(f"║{'  CITATIONS':─<{W}}║")
        print(
            f"║    Presence:     {o.get('citation_presence_rate', 0):>8.1%}{'':>{W - 29}}║"
        )
        print(
            f"║    Correct:      {o.get('citation_correctness_rate', 0):>8.1%}{'':>{W - 29}}║"
        )
        print(
            f"║    Halluc. Rate: {o.get('avg_hallucination_rate', 0):>8.1%}{'':>{W - 29}}║"
        )
        print(f"║{HL}║")

        # Latency
        print(f"║{'  LATENCY':─<{W}}║")
        print(
            f"║    p50:          {o.get('latency_p50_ms', 0):>7.0f} ms{'':>{W - 31}}║"
        )
        print(
            f"║    p90:          {o.get('latency_p90_ms', 0):>7.0f} ms{'':>{W - 31}}║"
        )
        print(
            f"║    p99:          {o.get('latency_p99_ms', 0):>7.0f} ms{'':>{W - 31}}║"
        )
        print(
            f"║    Throughput:   {o.get('throughput_qps', 0):>7.2f} q/s{'':>{W - 32}}║"
        )
        print(f"╠{'═' * W}╣")

        # Indexing
        idx = report.indexing
        if idx.total_time_s > 0:
            print(f"║{'  INDEXING':─<{W}}║")
            print(f"║    Time:         {idx.total_time_s:>7.1f} s{'':>{W - 30}}║")
            print(f"║    Docs:         {idx.doc_count:>7d}{'':>{W - 28}}║")
            print(f"║    Chunks:       {idx.chunk_count:>7d}{'':>{W - 28}}║")
            print(f"║{HL}║")

        # Output location
        print(f"║  Output: {report.output_dir:<{W - 11}}║")
        print(f"╚{'═' * W}╝")
        print()

    # ------------------------------------------------------------------
    # Per-query continuous logging
    # ------------------------------------------------------------------

    def _init_log_file(self) -> None:
        """Create / overwrite the benchmark log file with a header."""
        assert self._log_path is not None
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = (
            f"Benchmark Run Log\n"
            f"Started: {ts}\n"
            f"Config:  {self.config.name} v{self.config.version}\n"
            f"Dataset: {self.config.dataset_path}\n"
            f"Runs/query: {self.config.runs_per_query}  top_k: {self.config.top_k}\n"
            f"{'=' * 80}\n"
        )
        self._log_path.write_text(header, encoding="utf-8")
        logger.info("Benchmark log file: %s", self._log_path)

    def _append_log(self, message: str) -> None:
        """Append a timestamped line to the log file."""
        if self._log_path is None:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")

    def _log_query_result(self, result: QueryResult, idx: int, total: int) -> None:
        """Write a detailed block for one completed query to the log file."""
        s = result.scores
        lines = [
            f"\n--- [{idx}/{total}] {result.prompt_id} ({result.query_type}) ---",
            f"  category={result.category}  file_type={result.file_type}  folder_size={result.folder_size}",
            f"  Retrieval   : hit@1={s.retrieval.hit_at_1}  hit@k={s.retrieval.hit_at_k}  mrr={s.retrieval.mrr:.3f}",
            f"  Response    : composite={s.response.composite_score:.3f}  keyword={s.response.keyword_score:.3f}  judge={s.response.llm_judge_score:.3f}",
            f"  Citation    : present={s.citation.citation_present}  correct={s.citation.citation_correct}  halluc_rate={s.citation.hallucination_rate:.3f}",
            f"  Latency     : retrieval={s.latency.retrieval_latency_ms:.0f}ms  inference={s.latency.inference_latency_ms:.0f}ms  total={s.latency.total_latency_ms:.0f}ms",
            f"  Chunks={s.latency.chunk_count}  prompt_tokens={s.latency.token_count_prompt}  response_tokens={s.latency.token_count_response}",
        ]
        if s.retrieval.expected_file:
            lines.append(f"  expected_file={s.retrieval.expected_file}")
            lines.append(f"  retrieved   ={s.retrieval.retrieved_files[:5]}")
        if s.citation.hallucinated_citations:
            lines.append(f"  hallucinated={s.citation.hallucinated_citations}")
        self._append_log("\n".join(lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * pct / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]
