"""Generate graphs from a partial or complete benchmark_run.log.

This script parses per-prompt sections from the benchmark log and writes:
- parsed_per_query.csv
- parsed_dataset_summary.csv
- parsed_overall_summary.json
- graphs/*.png (dataset and overall charts)

Usage:
    python scripts/graph_benchmark_log.py \
        --log benchmarks/results/benchmark_run.log \
        --out benchmarks/results/parsed_from_log
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ENTRY_RE = re.compile(r"--- \[(\d+)/(\d+)\] ([^\s]+) \(([^\)]+)\) ---")
SUITE_RE = re.compile(r"=== Suite ([^:]+): dataset=([^,]+), prompts=(\d+) ===")
RETRIEVAL_RE = re.compile(r"hit@1=(\d+)\s+hit@k=(\d+)\s+mrr=([0-9.]+)")
RESPONSE_RE = re.compile(r"composite=([0-9.]+)\s+keyword=([0-9.]+)\s+judge=([0-9.]+)")
CITATION_RE = re.compile(r"present=(\d+)\s+correct=(\d+)\s+halluc_rate=([0-9.]+)")
LATENCY_RE = re.compile(r"retrieval=(\d+)ms\s+inference=(\d+)ms\s+total=(\d+)ms")
CHUNK_RE = re.compile(r"Chunks=(\d+)\s+prompt_tokens=(\d+)\s+response_tokens=(\d+)")
KV_META_RE = re.compile(
    r"category=([^\s]+)\s+file_type=([^\s]+)\s+folder_size=([^\s]+)"
)


def _safe_literal_list(text: str) -> list[str]:
    t = text.strip()
    if not (t.startswith("[") and t.endswith("]")):
        return []
    try:
        # Use json after normalizing single quotes.
        candidate = t.replace("'", '"')
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass

    # Fallback parser for malformed entries.
    parts = []
    current = ""
    in_quote = False
    quote = ""
    for ch in t[1:-1]:
        if ch in {"'", '"'}:
            if not in_quote:
                in_quote = True
                quote = ch
                continue
            if quote == ch:
                in_quote = False
                continue
        if ch == "," and not in_quote:
            if current.strip():
                parts.append(current.strip())
            current = ""
            continue
        current += ch
    if current.strip():
        parts.append(current.strip())
    return [p.strip("'\"") for p in parts if p.strip()]


def parse_benchmark_log(log_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current_suite_id = ""
    current_dataset_path = ""
    current: dict[str, Any] | None = None

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for raw in lines:
        line = raw.strip()

        suite_match = SUITE_RE.search(line)
        if suite_match:
            current_suite_id = suite_match.group(1).strip()
            current_dataset_path = suite_match.group(2).strip()
            continue

        entry_match = ENTRY_RE.search(line)
        if entry_match:
            if current:
                records.append(current)
            current = {
                "suite_id": current_suite_id,
                "dataset_path": current_dataset_path,
                "prompt_id": entry_match.group(3),
                "query_type": entry_match.group(4),
                "category": "",
                "file_type": "",
                "folder_size": "",
                "hit_at_1": 0,
                "hit_at_k": 0,
                "mrr": 0.0,
                "composite": 0.0,
                "keyword": 0.0,
                "judge": 0.0,
                "citation_present": 0,
                "citation_correct": 0,
                "halluc_rate": 0.0,
                "retrieval_ms": 0,
                "inference_ms": 0,
                "total_ms": 0,
                "chunks": 0,
                "prompt_tokens": 0,
                "response_tokens": 0,
                "expected_file": "",
                "retrieved_files": [],
            }
            continue

        if not current:
            continue

        if line.startswith("category="):
            m = KV_META_RE.search(line)
            if m:
                current["category"] = m.group(1)
                current["file_type"] = m.group(2)
                current["folder_size"] = m.group(3)
            continue

        if line.startswith("Retrieval"):
            m = RETRIEVAL_RE.search(line)
            if m:
                current["hit_at_1"] = int(m.group(1))
                current["hit_at_k"] = int(m.group(2))
                current["mrr"] = float(m.group(3))
            continue

        if line.startswith("Response"):
            m = RESPONSE_RE.search(line)
            if m:
                current["composite"] = float(m.group(1))
                current["keyword"] = float(m.group(2))
                current["judge"] = float(m.group(3))
            continue

        if line.startswith("Citation"):
            m = CITATION_RE.search(line)
            if m:
                current["citation_present"] = int(m.group(1))
                current["citation_correct"] = int(m.group(2))
                current["halluc_rate"] = float(m.group(3))
            continue

        if line.startswith("Latency"):
            m = LATENCY_RE.search(line)
            if m:
                current["retrieval_ms"] = int(m.group(1))
                current["inference_ms"] = int(m.group(2))
                current["total_ms"] = int(m.group(3))
            continue

        if line.startswith("Chunks="):
            m = CHUNK_RE.search(line)
            if m:
                current["chunks"] = int(m.group(1))
                current["prompt_tokens"] = int(m.group(2))
                current["response_tokens"] = int(m.group(3))
            continue

        if line.startswith("expected_file="):
            current["expected_file"] = line.split("=", 1)[1].strip()
            continue

        if line.startswith("retrieved"):
            rhs = line.split("=", 1)[1].strip()
            current["retrieved_files"] = _safe_literal_list(rhs)
            continue

    if current:
        records.append(current)

    return records


def summarize_by_dataset(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["suite_id"]].append(row)

    out: list[dict[str, Any]] = []
    for suite_id in sorted(grouped.keys()):
        rows = grouped[suite_id]
        n = len(rows)
        if n == 0:
            continue
        total_time_s = sum(float(r["total_ms"]) for r in rows) / 1000.0
        out.append(
            {
                "suite_id": suite_id,
                "dataset_path": rows[0]["dataset_path"],
                "count": n,
                "hit_rate_at_1": sum(int(r["hit_at_1"]) for r in rows) / n,
                "hit_rate_at_k": sum(int(r["hit_at_k"]) for r in rows) / n,
                "mrr": sum(float(r["mrr"]) for r in rows) / n,
                "avg_composite": sum(float(r["composite"]) for r in rows) / n,
                "avg_keyword": sum(float(r["keyword"]) for r in rows) / n,
                "avg_judge": sum(float(r["judge"]) for r in rows) / n,
                "avg_total_ms": sum(float(r["total_ms"]) for r in rows) / n,
                "throughput_qps": (n / total_time_s) if total_time_s > 0 else 0.0,
            }
        )
    return out


def summarize_overall(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    if n == 0:
        return {}
    latencies = sorted(float(r["total_ms"]) for r in records)
    total_time_s = sum(latencies) / 1000.0

    def _pct(values: list[float], p: float) -> float:
        idx = min(len(values) - 1, int(len(values) * p / 100))
        return values[idx]

    return {
        "count": n,
        "hit_rate_at_1": sum(int(r["hit_at_1"]) for r in records) / n,
        "hit_rate_at_k": sum(int(r["hit_at_k"]) for r in records) / n,
        "mrr": sum(float(r["mrr"]) for r in records) / n,
        "avg_composite": sum(float(r["composite"]) for r in records) / n,
        "avg_keyword": sum(float(r["keyword"]) for r in records) / n,
        "avg_judge": sum(float(r["judge"]) for r in records) / n,
        "latency_mean_ms": sum(latencies) / n,
        "latency_p50_ms": _pct(latencies, 50),
        "latency_p90_ms": _pct(latencies, 90),
        "latency_p99_ms": _pct(latencies, 99),
        "throughput_qps": (n / total_time_s) if total_time_s > 0 else 0.0,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate_graphs(
    dataset_rows: list[dict[str, Any]],
    overall: dict[str, Any],
    out_dir: Path,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    graphs = out_dir / "graphs"
    graphs.mkdir(parents=True, exist_ok=True)

    if dataset_rows:
        labels = [r["suite_id"] for r in dataset_rows]

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(
            labels,
            [r["hit_rate_at_1"] for r in dataset_rows],
            marker="o",
            label="Hit@1",
        )
        ax.plot(
            labels,
            [r["hit_rate_at_k"] for r in dataset_rows],
            marker="o",
            label="Hit@K",
        )
        ax.set_ylim(0, 1.05)
        ax.set_title("Dataset Retrieval Accuracy (Recovered from benchmark_run.log)")
        ax.set_ylabel("Rate")
        ax.set_xlabel("Dataset Suite")
        ax.tick_params(axis="x", rotation=60)
        ax.legend()
        fig.tight_layout()
        fig.savefig(graphs / "dataset_retrieval_accuracy.png", dpi=150)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.bar(
            labels,
            [r["avg_composite"] for r in dataset_rows],
            label="Composite",
            alpha=0.9,
        )
        ax.plot(
            labels, [r["avg_judge"] for r in dataset_rows], marker="o", label="Judge"
        )
        ax.set_ylim(0, 1.05)
        ax.set_title("Dataset Response Scores")
        ax.set_ylabel("Score")
        ax.set_xlabel("Dataset Suite")
        ax.tick_params(axis="x", rotation=60)
        ax.legend()
        fig.tight_layout()
        fig.savefig(graphs / "dataset_response_scores.png", dpi=150)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.bar(
            labels,
            [r["avg_total_ms"] for r in dataset_rows],
            color="steelblue",
            label="Avg total latency (ms)",
        )
        ax2 = ax.twinx()
        ax2.plot(
            labels,
            [r["throughput_qps"] for r in dataset_rows],
            marker="o",
            color="darkorange",
            label="QPS",
        )
        ax.set_title("Dataset Latency and Throughput")
        ax.set_ylabel("Milliseconds")
        ax2.set_ylabel("QPS")
        ax.tick_params(axis="x", rotation=60)
        fig.tight_layout()
        fig.savefig(graphs / "dataset_latency_throughput.png", dpi=150)
        plt.close(fig)

    if overall:
        keys = [
            "hit_rate_at_1",
            "hit_rate_at_k",
            "mrr",
            "avg_composite",
            "avg_keyword",
            "avg_judge",
        ]
        vals = [float(overall.get(k, 0.0)) for k in keys]
        labels = [
            "Hit@1",
            "Hit@K",
            "MRR",
            "Composite",
            "Keyword",
            "Judge",
        ]

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(labels, vals, color="seagreen")
        ax.set_ylim(0, 1.05)
        ax.set_title("Overall Quality Metrics (Recovered Log Data)")
        ax.set_ylabel("Score")
        fig.tight_layout()
        fig.savefig(graphs / "overall_quality_metrics.png", dpi=150)
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse benchmark_run.log and graph partial results"
    )
    parser.add_argument("--log", required=True, help="Path to benchmark_run.log")
    parser.add_argument(
        "--out", required=True, help="Output directory for parsed files and graphs"
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = parse_benchmark_log(log_path)
    dataset_summary = summarize_by_dataset(records)
    overall = summarize_overall(records)

    write_csv(out_dir / "parsed_per_query.csv", records)
    write_csv(out_dir / "parsed_dataset_summary.csv", dataset_summary)
    (out_dir / "parsed_overall_summary.json").write_text(
        json.dumps(overall, indent=2), encoding="utf-8"
    )

    generate_graphs(dataset_summary, overall, out_dir)

    print(f"Parsed records: {len(records)}")
    print(f"Datasets with completed prompt entries: {len(dataset_summary)}")
    print(f"Wrote: {out_dir / 'parsed_per_query.csv'}")
    print(f"Wrote: {out_dir / 'parsed_dataset_summary.csv'}")
    print(f"Wrote: {out_dir / 'parsed_overall_summary.json'}")
    print(f"Graphs: {out_dir / 'graphs'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
