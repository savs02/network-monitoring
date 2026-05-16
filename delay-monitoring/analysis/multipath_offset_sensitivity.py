"""
Offset sensitivity for the bimodal multipath capacity analysis.

The main multipath experiment uses a 30 ms separation between the lower-delay and
upper-delay path components. This script reruns the modal split over a range of
offsets and records when the upper-mode capacity association remains valid.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "delay-monitoring" / "results" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

import multipath_bimodal_capacity as mp


def numeric(value: object, default: float = math.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], q: float) -> float:
    vals = sorted(value for value in values if math.isfinite(value))
    if not vals:
        return math.nan
    return float(np.percentile(vals, q))


def make_args(args: argparse.Namespace, offset: float) -> argparse.Namespace:
    return argparse.Namespace(
        single_results=args.single_results,
        results_dir=args.results_dir,
        dists=args.dists,
        seed_start=args.seed_start,
        seed_end=args.seed_end,
        upper_shares=args.upper_shares,
        upper_path_offset_ms=offset,
        max_valley_ratio=args.max_valley_ratio,
        change_threshold=args.change_threshold,
        min_history_slopes=args.min_history_slopes,
        rate_multiplier=args.rate_multiplier,
        min_score_jump=args.min_score_jump,
        min_baseline_rate=args.min_baseline_rate,
    )


def summarise_offset(
    offset: float,
    response_rows: list[dict],
    method_rows: list[dict],
    args: argparse.Namespace,
) -> dict:
    baseline_ratio = min(numeric(row["load_ratio"]) for row in response_rows)
    baseline = [row for row in response_rows if numeric(row["load_ratio"]) == baseline_ratio]
    split_valid = [
        row
        for row in baseline
        if str(row["baseline_split_valid"]).lower() in {"true", "1"}
        or row["baseline_split_valid"] is True
    ]
    upper_rows = [row for row in method_rows if row["method"] == "upper_component_rate"]
    upper_detected = [
        numeric(row["detection_load_ratio"])
        for row in upper_rows
        if math.isfinite(numeric(row["detection_load_ratio"]))
    ]
    mixture_rows = [row for row in method_rows if row["method"] == "overall_rate_change"]
    mixture_detected = [
        numeric(row["detection_load_ratio"])
        for row in mixture_rows
        if math.isfinite(numeric(row["detection_load_ratio"]))
    ]
    return {
        "upper_offset_ms": offset,
        "cases": len(baseline),
        "valid_split_rate": len(split_valid) / len(baseline) if baseline else math.nan,
        "median_valley_ratio": statistics.median(numeric(row["baseline_valley_ratio"]) for row in split_valid) if split_valid else math.nan,
        "upper_detection_rate": len(upper_detected) / len(upper_rows) if upper_rows else math.nan,
        "upper_median_detection_ratio": statistics.median(upper_detected) if upper_detected else math.nan,
        "upper_q25_detection_ratio": percentile(upper_detected, 25),
        "upper_q75_detection_ratio": percentile(upper_detected, 75),
        "upper_early_rate_below_0p9": sum(value < 0.9 for value in upper_detected) / len(upper_rows) if upper_rows else math.nan,
        "upper_late_rate_above_0p925": sum(value > 0.925 for value in upper_detected) / len(upper_rows) if upper_rows else math.nan,
        "mixture_detection_rate": len(mixture_detected) / len(mixture_rows) if mixture_rows else math.nan,
        "mixture_median_detection_ratio": statistics.median(mixture_detected) if mixture_detected else math.nan,
    }


def plot_summary(rows: list[dict], results_dir: Path) -> Path:
    offsets = [numeric(row["upper_offset_ms"]) for row in rows]
    split_rates = [numeric(row["valid_split_rate"]) for row in rows]
    upper_rates = [numeric(row["upper_detection_rate"]) for row in rows]
    medians = [numeric(row["upper_median_detection_ratio"]) for row in rows]
    q25 = [numeric(row["upper_q25_detection_ratio"]) for row in rows]
    q75 = [numeric(row["upper_q75_detection_ratio"]) for row in rows]

    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.2), sharex=True)
    axes[0].plot(offsets, split_rates, marker="o", linewidth=2, label="Valid bimodal split")
    axes[0].plot(offsets, upper_rates, marker="o", linewidth=2, label="Upper-mode detection")
    axes[0].set_ylabel("Rate")
    axes[0].set_ylim(-0.02, 1.05)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=8)

    lows = [m - l if math.isfinite(m) and math.isfinite(l) else 0 for m, l in zip(medians, q25)]
    highs = [h - m if math.isfinite(m) and math.isfinite(h) else 0 for m, h in zip(medians, q75)]
    axes[1].errorbar(offsets, medians, yerr=[lows, highs], marker="o", linewidth=2, capsize=3, color="#2ca02c")
    axes[1].axhline(0.925, color="black", linestyle="--", linewidth=1.2, label="Single-path grid point")
    axes[1].set_xlabel("Upper-path delay offset in milliseconds")
    axes[1].set_ylabel("Detected load ratio")
    axes[1].set_ylim(0.0, 1.05)
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(fontsize=8)

    fig.suptitle("Sensitivity of modal capacity association to path-delay separation")
    out = results_dir / "multipath_offset_sensitivity.png"
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multipath modal offset sensitivity.")
    parser.add_argument("--single-results", default=str(mp.REPO_ROOT / "delay-monitoring" / "results" / "observable-capacity-single-100-seed"))
    parser.add_argument("--results-dir", default=str(mp.REPO_ROOT / "delay-monitoring" / "results" / "multipath-offset-sensitivity"))
    parser.add_argument("--dists", nargs="+", choices=list(mp.base.DISTRIBUTIONS), default=list(mp.base.DISTRIBUTIONS))
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=100)
    parser.add_argument("--upper-shares", nargs="+", type=float, default=[0.1, 0.25, 0.5, 0.75])
    parser.add_argument("--offsets-ms", nargs="+", type=float, default=[10.0, 20.0, 30.0, 40.0, 50.0])
    parser.add_argument("--max-valley-ratio", type=float, default=0.8)
    parser.add_argument("--change-threshold", type=float, default=mp.base.DELTA)
    parser.add_argument("--min-history-slopes", type=int, default=2)
    parser.add_argument("--rate-multiplier", type=float, default=5.0)
    parser.add_argument("--min-score-jump", type=float, default=0.05)
    parser.add_argument("--min-baseline-rate", type=float, default=1.0e-4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for offset in args.offsets_ms:
        local_args = make_args(args, offset)
        response_rows, method_rows = mp.run_analysis(local_args)
        summary_rows.append(summarise_offset(offset, response_rows, method_rows, args))
    write_csv(results_dir / "multipath_offset_sensitivity.csv", summary_rows)
    plot_path = plot_summary(summary_rows, results_dir)
    print(plot_path)
    print(f"Wrote multipath offset sensitivity to {results_dir}")


if __name__ == "__main__":
    main()
