"""Graph generation for benchmark reports.

All graph logic is wrapped in try/except so missing matplotlib does not crash
the benchmark run.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from benchmarks.models import BenchmarkReport

logger = logging.getLogger(__name__)


def generate_graphs(report: "BenchmarkReport", output_dir: str) -> int:
    """Generate all benchmark charts. Returns the count of charts created."""
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless backend
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — skipping graph generation")
        return 0

    try:
        import seaborn as sns

        sns.set_theme(style="darkgrid", palette="muted")
    except ImportError:
        pass  # seaborn is optional

    graphs_dir = Path(output_dir) / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    chart_funcs = [
        _chart_hit_rate_by_file_type,
        _chart_hit_rate_by_category,
        _chart_response_score_distribution,
        _chart_latency_cdf,
        _chart_latency_by_stage,
        _chart_throughput_over_time,
        _chart_subgroup_heatmap,
        _chart_indexing_performance,
    ]
    for fn in chart_funcs:
        try:
            fn(report, str(graphs_dir))
            generated += 1
            plt.close("all")
        except Exception as e:
            logger.warning("Graph %s failed: %s", fn.__name__, e)
            plt.close("all")

    return generated


# ---------------------------------------------------------------------------
# Individual chart generators
# ---------------------------------------------------------------------------


def _chart_hit_rate_by_file_type(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    ft_data = report.subgroups.get("file_type", {})
    if not ft_data:
        return
    labels = sorted(ft_data.keys())
    hit_vals = [ft_data[label]["hit_rate_at_1"] for label in labels]
    resp_vals = [ft_data[label]["avg_response_score"] for label in labels]

    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w / 2, hit_vals, w, label="Hit@1")
    ax.bar(x + w / 2, resp_vals, w, label="Avg Response Score", alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.05)
    ax.set_title("Retrieval & Response Accuracy by File Type")
    ax.set_ylabel("Score")
    ax.legend()
    fig.tight_layout()
    fig.savefig(f"{out}/hit_rate_by_file_type.png", dpi=150)


def _chart_hit_rate_by_category(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt

    cat_data = report.subgroups.get("category", {})
    if not cat_data:
        return
    labels = sorted(cat_data.keys())
    vals = [cat_data[label]["hit_rate_at_1"] for label in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(labels, vals, color="steelblue")
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Hit@1 Rate")
    ax.set_title("Retrieval Accuracy by Query Category")
    fig.tight_layout()
    fig.savefig(f"{out}/hit_rate_by_query_category.png", dpi=150)


def _chart_response_score_distribution(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt

    scores_by_type: Dict[str, List[float]] = defaultdict(list)
    for r in report.raw_results:
        scores_by_type[r.query_type].append(r.scores.response.composite_score)

    if not scores_by_type:
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    labels = sorted(scores_by_type.keys())
    data = [scores_by_type[label] for label in labels]
    ax.violinplot(data, showmeans=True, showmedians=True)
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Composite Score")
    ax.set_title("Response Score Distribution by Query Type")
    ax.set_ylim(-0.05, 1.05)
    fig.tight_layout()
    fig.savefig(f"{out}/response_score_distribution.png", dpi=150)


def _chart_latency_cdf(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt

    latencies = sorted(r.scores.latency.total_latency_ms for r in report.raw_results)
    if not latencies:
        return
    cdf = [(i + 1) / len(latencies) for i in range(len(latencies))]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(latencies, cdf, linewidth=2)

    p90 = _percentile(latencies, 90)
    p99 = _percentile(latencies, 99)
    ax.axvline(p90, color="orange", linestyle="--", label=f"p90 = {p90:.0f} ms")
    ax.axvline(p99, color="red", linestyle="--", label=f"p99 = {p99:.0f} ms")
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Cumulative Probability")
    ax.set_title("End-to-End Query Latency CDF")
    ax.legend()
    fig.tight_layout()
    fig.savefig(f"{out}/latency_cdf.png", dpi=150)


def _chart_latency_by_stage(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    cat_data = report.subgroups.get("category", {})
    if not cat_data:
        return

    # Collect per-category average latency by stage from raw results
    stages_by_cat: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in report.raw_results:
        stages_by_cat[r.category]["retrieval"].append(
            r.scores.latency.retrieval_latency_ms
        )
        stages_by_cat[r.category]["inference"].append(
            r.scores.latency.inference_latency_ms
        )

    categories = sorted(stages_by_cat.keys())
    ret_means = [_mean(stages_by_cat[c]["retrieval"]) for c in categories]
    inf_means = [_mean(stages_by_cat[c]["inference"]) for c in categories]

    x = np.arange(len(categories))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x, ret_means, label="Retrieval", width=0.6)
    ax.bar(x, inf_means, bottom=ret_means, label="Inference", width=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Average Latency by Stage and Query Category")
    ax.legend()
    fig.tight_layout()
    fig.savefig(f"{out}/latency_by_stage.png", dpi=150)


def _chart_throughput_over_time(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt

    latencies = [r.scores.latency.total_latency_ms for r in report.raw_results]
    if not latencies:
        return

    # Compute cumulative throughput as queries progress
    cum_time_s = 0.0
    throughput: List[float] = []
    for i, lat in enumerate(latencies, 1):
        cum_time_s += lat / 1000.0
        throughput.append(i / cum_time_s if cum_time_s > 0 else 0.0)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range(1, len(throughput) + 1), throughput, linewidth=1.5)
    ax.set_xlabel("Query Index")
    ax.set_ylabel("Queries / sec (cumulative)")
    ax.set_title("Throughput Over Time")
    fig.tight_layout()
    fig.savefig(f"{out}/throughput_over_time.png", dpi=150)


def _chart_subgroup_heatmap(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt

    # Build pivot: file_type (rows) × category (cols), value = avg response score
    pivot: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for r in report.raw_results:
        pivot[r.file_type][r.category].append(r.scores.response.composite_score)

    if not pivot:
        return

    rows = sorted(pivot.keys())
    cols = sorted({c for ft in pivot.values() for c in ft})
    data = [[_mean(pivot[r].get(c, [0.0])) for c in cols] for r in rows]

    try:
        import seaborn as sns

        fig, ax = plt.subplots(figsize=(10, 6))
        sns.heatmap(
            data,
            annot=True,
            fmt=".2f",
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
            ax=ax,
            xticklabels=cols,
            yticklabels=rows,
        )
        ax.set_title("Response Score Heatmap: File Type × Query Complexity")
        fig.tight_layout()
        fig.savefig(f"{out}/subgroup_heatmap.png", dpi=150)
    except ImportError:
        # Fallback without seaborn
        fig, ax = plt.subplots(figsize=(10, 6))
        im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels(cols)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(rows)
        for i in range(len(rows)):
            for j in range(len(cols)):
                ax.text(j, i, f"{data[i][j]:.2f}", ha="center", va="center")
        fig.colorbar(im)
        ax.set_title("Response Score Heatmap: File Type × Query Complexity")
        fig.tight_layout()
        fig.savefig(f"{out}/subgroup_heatmap.png", dpi=150)


def _chart_indexing_performance(report: "BenchmarkReport", out: str) -> None:
    import matplotlib.pyplot as plt

    idx = report.indexing
    if idx.total_time_s <= 0:
        return

    labels = ["Docs Indexed", "Chunks Created"]
    values = [idx.doc_count, idx.chunk_count]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].bar(labels, values, color=["steelblue", "coral"])
    axes[0].set_title("Indexing Volume")
    axes[0].set_ylabel("Count")

    throughput = idx.doc_count / idx.total_time_s
    chunk_tp = idx.chunk_count / idx.total_time_s
    axes[1].bar(
        ["Docs/sec", "Chunks/sec"],
        [throughput, chunk_tp],
        color=["steelblue", "coral"],
    )
    axes[1].set_title("Indexing Throughput")
    axes[1].set_ylabel("Per second")

    fig.suptitle(f"Indexing Performance (total: {idx.total_time_s:.1f}s)")
    fig.tight_layout()
    fig.savefig(f"{out}/indexing_performance.png", dpi=150)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * pct / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]
