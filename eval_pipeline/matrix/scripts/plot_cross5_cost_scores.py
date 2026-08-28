#!/usr/bin/env python3
"""Render the frozen agent-cost vs score views for the cross-5 pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_points(summary: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    points = []
    for cell in summary["cells"]:
        metrics = cell.get("metrics") or cell.get("latest_metrics") or {}
        value = (metrics.get(metric) or {}).get("score")
        cost = cell["agent_cost"].get("cny")
        if cell.get("evaluation_status") != "scored" or value is None or cost is None:
            continue
        points.append(
            {
                "cell_id": cell["cell_id"],
                "harness_id": cell["harness_id"],
                "model_id": cell["model_id"],
                "requested_model": cell["requested_model"],
                "cost_cny": float(cost),
                "score": float(value),
            }
        )
    return points


def pareto_frontier(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep non-dominated points for lower cost and higher score."""
    frontier = []
    best_score = float("-inf")
    for row in sorted(points, key=lambda item: (item["cost_cny"], -item["score"])):
        if row["score"] > best_score:
            frontier.append(row)
            best_score = row["score"]
    return frontier


def short_model(value: str) -> str:
    return {
        "gpt-5-6-sol": "GPT-5.6-Sol",
        "gemini-3-1-pro-preview": "Gemini 3.1 Pro",
        "claude-opus-5": "Claude Opus 5",
    }.get(value, value)


def draw_panel(ax: Any, points: list[dict[str, Any]], metric: str) -> None:
    from matplotlib.ticker import PercentFormatter

    colors = {
        "gpt-5-6-sol": "#2563eb",
        "gemini-3-1-pro-preview": "#16a34a",
        "claude-opus-5": "#dc2626",
    }
    markers = {"deerflow": "o", "opencode": "s", "claude-code": "^"}
    for row in points:
        ax.scatter(
            row["cost_cny"],
            row["score"],
            s=78,
            color=colors.get(row["model_id"], "#6b7280"),
            marker=markers.get(row["harness_id"], "D"),
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        ax.annotate(
            f"{row['harness_id']} / {short_model(row['model_id'])}",
            (row["cost_cny"], row["score"]),
            xytext=(6, 8),
            textcoords="offset points",
            fontsize=8.5,
        )
    frontier = pareto_frontier(points)
    if frontier:
        ax.plot(
            [row["cost_cny"] for row in frontier],
            [row["score"] for row in frontier],
            color="#111827",
            linewidth=1.0,
            linestyle="--",
            alpha=0.75,
            label="Pareto frontier",
            zorder=2,
        )
    if points:
        values = [row["cost_cny"] for row in points]
        low, high = min(values), max(values)
        pad = max((high - low) * 0.18, high * 0.05, 0.05)
        ax.set_xlim(max(0, low - pad), high + pad)
    ax.set_ylim(-0.06, 1.04)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Official-equivalent agent LLM cost (CNY)")
    ax.set_ylabel(metric.upper())
    ax.set_title(f"Agent Cost vs {metric.upper()}")
    ax.grid(True, linewidth=0.5, alpha=0.25)
    if frontier:
        ax.legend(loc="upper right", frameon=False, fontsize=8.5)


def save_single(output_dir: Path, points: list[dict[str, Any]], metric: str) -> list[Path]:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.4, 5.0), constrained_layout=False)
    fig.subplots_adjust(left=0.11, right=0.97, bottom=0.19, top=0.80)
    draw_panel(ax, points, metric)
    fig.suptitle("Biodiversity Q1-v2 Cross-5 (Shadow Experimental)", fontsize=12, y=0.96)
    fig.text(
        0.5,
        0.025,
        "Price axis: agent LLM only. Judge/diagnostics excluded. Failed and withheld cells omitted.",
        ha="center",
        fontsize=8,
        color="#4b5563",
    )
    outputs = [output_dir / f"cost_{metric}.png", output_dir / f"cost_{metric}.pdf"]
    fig.savefig(outputs[0], dpi=220, bbox_inches="tight")
    fig.savefig(outputs[1], bbox_inches="tight")
    plt.close(fig)
    return outputs


def save_combined(
    output_dir: Path, points_by_metric: dict[str, list[dict[str, Any]]]
) -> list[Path]:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), constrained_layout=False)
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.18, top=0.82, wspace=0.28)
    for ax, metric in zip(axes, ("gcp", "grr")):
        draw_panel(ax, points_by_metric[metric], metric)
    fig.suptitle("Biodiversity Q1-v2 Cross-5: Official-equivalent Cost and Grounding", fontsize=13, y=0.96)
    fig.text(
        0.5,
        0.025,
        "Agent LLM cost only; Judge and diagnostic ledgers are separate. Missing/withheld scores are not plotted as zero.",
        ha="center",
        fontsize=8.5,
        color="#4b5563",
    )
    outputs = [output_dir / "cost_score_frontier.png", output_dir / "cost_score_frontier.pdf"]
    fig.savefig(outputs[0], dpi=220, bbox_inches="tight")
    fig.savefig(outputs[1], bbox_inches="tight")
    plt.close(fig)
    return outputs


def write_delivery_seal(output_dir: Path) -> Path:
    seal_path = output_dir / "DELIVERY_SHA256SUMS.json"
    files = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path != seal_path:
            files.append(
                {
                    "path": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    seal_path.write_text(
        json.dumps(
            {"schema_version": "cross5_delivery_seal_v1", "files": files},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return seal_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    points = {metric: load_points(summary, metric) for metric in ("gcp", "grr")}
    outputs = []
    for metric in ("gcp", "grr"):
        outputs.extend(save_single(output_dir, points[metric], metric))
    outputs.extend(save_combined(output_dir, points))
    receipt = {
        "schema_version": "q1_v2_cross5_cost_score_plot_receipt_v1",
        "scope": summary.get("scope"),
        "summary_path": str(args.summary.resolve()),
        "summary_sha256": sha256_file(args.summary),
        "price_axis": "agent_llm_official_equivalent_cny",
        "excluded_cost_ledgers": ["judge_llm", "diagnostic_canary"],
        "missing_score_policy": "omit_not_zero",
        "unpriced_exact_model_policy": "omit_from_cost_axis_and_keep_NA_in_tables",
        "plotted_cells": {
            metric: [row["cell_id"] for row in points[metric]]
            for metric in ("gcp", "grr")
        },
        "pareto_cells": {
            metric: [row["cell_id"] for row in pareto_frontier(points[metric])]
            for metric in ("gcp", "grr")
        },
        "artifacts": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in outputs
        ],
    }
    (output_dir / "plot_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    seal = write_delivery_seal(output_dir)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "plotted_gcp_cells": len(points["gcp"]),
                "plotted_grr_cells": len(points["grr"]),
                "delivery_seal": str(seal),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
