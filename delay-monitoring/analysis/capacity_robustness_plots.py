"""
Summarise robustness experiments for the dissertation figures.

The script reads observable-capacity result directories produced by
observable_capacity_experiments.py and writes compact figures into the report
figure directory. It does not rerun Network Simulator 3.
"""

from __future__ import annotations

import argparse
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

import distributional_capacity_response as base
from observable_capacity_experiments import METHOD_COLOURS, METHOD_LABELS


REPORT_FIGURES = REPO_ROOT / "report" / "figures" / "evaluation"
SUMMARY_DIR = REPO_ROOT / "delay-monitoring" / "results" / "capacity-robustness-summary"

PLOT_METHODS = ["distribution_change", "tvd_rate_change", "traffic_loss"]
POSITION_ORDER = ["start", "middle", "end"]


def finite(value: float) -> bool:
    return np.isfinite(float(value))


def numeric(row: dict, key: str, default: float = math.nan) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def median(values) -> float:
    usable = [float(value) for value in values if finite(value)]
    return statistics.median(usable) if usable else math.nan


def percentile(values, pct: float) -> float:
    usable = [float(value) for value in values if finite(value)]
    return float(np.percentile(usable, pct)) if usable else math.nan


def group_by(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault(tuple(row.get(key, "") for key in keys), []).append(row)
    return grouped


def read_rows(results_dir: Path, filename: str) -> list[dict]:
    path = results_dir / filename
    if not path.exists():
        raise FileNotFoundError(path)
    return base.read_csv(path)


def method_summary(rows: list[dict], experiment: str) -> list[dict]:
    summary = []
    for (scenario, method), sub in sorted(group_by(rows, ("scenario", "method")).items()):
        vals = [
            numeric(row, "detection_load_ratio")
            for row in sub
            if str(row.get("detected", "")).lower() == "true"
        ]
        summary.append({
            "experiment": experiment,
            "scenario": scenario,
            "method": method,
            "runs": len(sub),
            "detected_rate": len(vals) / len(sub) if sub else math.nan,
            "median_detection_load_ratio": median(vals),
            "q25_detection_load_ratio": percentile(vals, 25),
            "q75_detection_load_ratio": percentile(vals, 75),
            "early_rate_below_0_900": sum(1 for value in vals if value < 0.9) / len(sub) if sub else math.nan,
            "late_rate_above_0_925": sum(1 for value in vals if value > 0.925) / len(sub) if sub else math.nan,
        })
    return summary


def by_distribution_summary(rows: list[dict], experiment: str) -> list[dict]:
    summary = []
    for (scenario, dist, method), sub in sorted(group_by(rows, ("scenario", "dist", "method")).items()):
        vals = [
            numeric(row, "detection_load_ratio")
            for row in sub
            if str(row.get("detected", "")).lower() == "true"
        ]
        summary.append({
            "experiment": experiment,
            "scenario": scenario,
            "dist": dist,
            "method": method,
            "runs": len(sub),
            "detected_rate": len(vals) / len(sub) if sub else math.nan,
            "median_detection_load_ratio": median(vals),
            "q25_detection_load_ratio": percentile(vals, 25),
            "q75_detection_load_ratio": percentile(vals, 75),
        })
    return summary


def plot_bursty_methods(rows: list[dict], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 6.0))
    xs = np.arange(len(PLOT_METHODS))
    medians, lower, upper, labels = [], [], [], []
    for method in PLOT_METHODS:
        vals = [
            numeric(row, "detection_load_ratio")
            for row in rows
            if row.get("method") == method and str(row.get("detected", "")).lower() == "true"
        ]
        med = median(vals)
        medians.append(med)
        lower.append(med - percentile(vals, 25) if finite(med) else 0.0)
        upper.append(percentile(vals, 75) - med if finite(med) else 0.0)
        labels.append(METHOD_LABELS.get(method, method))
    colours = [METHOD_COLOURS.get(method, "#4d4d4d") for method in PLOT_METHODS]
    ax.bar(xs, medians, color=colours, alpha=0.82)
    ax.errorbar(xs, medians, yerr=[lower, upper], fmt="none", ecolor="black", capsize=4)
    ax.axhline(0.5, color="#4d4d4d", linestyle=":", linewidth=1.6, label="Peak on-rate equals link rate")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.4, label="Configured link rate")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=12, ha="right")
    ax.set_ylabel("Detection load divided by configured link rate")
    ax.set_title("Single-link bursty cross-traffic stress test")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=240)
    plt.close(fig)


def plot_bursty_curve(details: list[dict], methods: list[dict], out_path: Path, dist: str = "weibull") -> None:
    selected = [row for row in details if row.get("dist") == dist]
    grouped = group_by(selected, ("load_ratio",))
    xs, tvd, loss = [], [], []
    for (ratio,), rows in sorted(grouped.items(), key=lambda item: float(item[0][0])):
        xs.append(float(ratio))
        tvd.append(median(numeric(row, "tvd_from_baseline") for row in rows))
        loss.append(median(numeric(row, "cross_traffic_loss_count") for row in rows))

    fig, ax1 = plt.subplots(figsize=(10.8, 6.2))
    ax1.plot(xs, tvd, color="#1f77b4", linewidth=2.0, marker="o", markersize=3.5, label="TVD from low-load state")
    ax1.set_xlabel("Average offered load divided by configured link rate")
    ax1.set_ylabel("Median TVD", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.axhline(0.05, color="#1f77b4", linestyle=":", linewidth=1.3, label="TVD 0.05")
    ax1.axvline(0.5, color="#4d4d4d", linestyle=":", linewidth=1.4, label="Peak on-rate equals link rate")

    ax2 = ax1.twinx()
    ax2.plot(xs, loss, color="#2ca02c", linewidth=1.8, marker="s", markersize=3.5, label="Endpoint traffic loss")
    ax2.set_ylabel("Median cross-traffic packet loss", color="#2ca02c")
    ax2.tick_params(axis="y", labelcolor="#2ca02c")

    for method, colour in (("tvd_rate_change", "#d62728"), ("traffic_loss", "#2ca02c")):
        vals = [
            numeric(row, "detection_load_ratio")
            for row in methods
            if row.get("dist") == dist
            and row.get("method") == method
            and str(row.get("detected", "")).lower() == "true"
        ]
        med = median(vals)
        if finite(med):
            ax1.axvline(med, color=colour, linestyle="--", linewidth=1.3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
    ax1.grid(True, alpha=0.25)
    ax1.set_title(f"Bursty {base.DIST_LABELS.get(dist, dist)} response")
    fig.tight_layout()
    fig.savefig(out_path, dpi=240)
    plt.close(fig)


def parse_hetero_input(values: list[str]) -> list[tuple[str, Path]]:
    parsed = []
    for value in values:
        if "=" not in value:
            raise ValueError("--hetero-dir values must be label=path")
        label, path = value.split("=", 1)
        parsed.append((label, Path(path).resolve()))
    return parsed


def plot_hetero_methods(labelled_rows: list[tuple[str, list[dict]]], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.8, 6.2))
    x_lookup = {label: index for index, label in enumerate(POSITION_ORDER)}
    for method in PLOT_METHODS:
        xs, medians, lower, upper = [], [], [], []
        for label, rows in labelled_rows:
            vals = [
                numeric(row, "detection_load_ratio")
                for row in rows
                if row.get("method") == method and str(row.get("detected", "")).lower() == "true"
            ]
            med = median(vals)
            xs.append(x_lookup.get(label, len(xs)))
            medians.append(med)
            lower.append(med - percentile(vals, 25) if finite(med) else 0.0)
            upper.append(percentile(vals, 75) - med if finite(med) else 0.0)
        ax.errorbar(xs,
                    medians,
                    yerr=[lower, upper],
                    marker="o",
                    linewidth=2.0,
                    capsize=4,
                    color=METHOD_COLOURS.get(method, "#4d4d4d"),
                    label=METHOD_LABELS.get(method, method))
    ax.axhline(0.925, color="#d62728", linestyle=":", linewidth=1.3, label="Uniform-link response grid point")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.3, label="Slow-link configured rate")
    ax.set_xticks(range(len(POSITION_ORDER)))
    ax.set_xticklabels(["Slow first link", "Slow middle link", "Slow final link"])
    ax.set_ylabel("Detection load divided by slow-link rate")
    ax.set_title("Heterogeneous five-hop bottleneck-position stress test")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=240)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot robustness summaries for the capacity chapters.")
    parser.add_argument("--bursty-dir", type=Path)
    parser.add_argument("--hetero-dir", action="append", default=[], help="Position-labelled directory, e.g. start=path")
    parser.add_argument("--report-figures", type=Path, default=REPORT_FIGURES)
    parser.add_argument("--summary-dir", type=Path, default=SUMMARY_DIR)
    args = parser.parse_args()

    args.report_figures.mkdir(parents=True, exist_ok=True)
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    all_summaries: list[dict] = []
    all_by_dist: list[dict] = []

    if args.bursty_dir:
        bursty_dir = args.bursty_dir.resolve()
        bursty_methods = read_rows(bursty_dir, "method_results.csv")
        bursty_details = read_rows(bursty_dir, "load_results.csv")
        all_summaries.extend(method_summary(bursty_methods, "single_bursty_pareto"))
        all_by_dist.extend(by_distribution_summary(bursty_methods, "single_bursty_pareto"))
        plot_bursty_methods(bursty_methods, args.report_figures / "observable_capacity_bursty_methods.png")
        plot_bursty_curve(bursty_details,
                          bursty_methods,
                          args.report_figures / "observable_capacity_bursty_tvd_loss_weibull.png",
                          dist="weibull")

    hetero_inputs = parse_hetero_input(args.hetero_dir)
    if hetero_inputs:
        labelled_rows = []
        for label, results_dir in hetero_inputs:
            rows = read_rows(results_dir, "method_results.csv")
            details = read_rows(results_dir, "load_results.csv")
            for row in rows:
                row["bottleneck_position"] = label
            for row in details:
                row["bottleneck_position"] = label
            labelled_rows.append((label, rows))
            all_summaries.extend(method_summary(rows, f"heterogeneous_{label}"))
            all_by_dist.extend(by_distribution_summary(rows, f"heterogeneous_{label}"))
        plot_hetero_methods(labelled_rows, args.report_figures / "observable_capacity_heterogeneous_methods.png")

    if all_summaries:
        base.write_csv(args.summary_dir / "robust_capacity_summary.csv", all_summaries)
    if all_by_dist:
        base.write_csv(args.summary_dir / "robust_capacity_by_distribution.csv", all_by_dist)

    print(f"Wrote robustness summaries to {base.rel(args.summary_dir)}")
    print(f"Wrote robustness figures to {base.rel(args.report_figures)}")


if __name__ == "__main__":
    main()
