"""
Plot summary figures for the observable capacity experiments.

The figures are intended for the report rather than for debugging. They use
only the aggregate CSV files written by observable_capacity_experiments.py.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "delay-monitoring" / "results" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


METHOD_LABELS = {
    "distribution_change": "First distribution change",
    "tvd_rate_change": "TVD rate change",
    "traffic_loss": "Endpoint traffic loss",
    "probe_loss": "Probe loss",
}

METHOD_COLOURS = {
    "distribution_change": "#1f77b4",
    "tvd_rate_change": "#d62728",
    "traffic_loss": "#2ca02c",
    "probe_loss": "#4d4d4d",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def number(row: dict[str, str], key: str) -> float:
    try:
        value = float(row.get(key, "nan"))
    except ValueError:
        return math.nan
    return value


def finite(value: float) -> bool:
    return math.isfinite(value)


def plot_single_methods(single_dir: Path, out_dir: Path) -> None:
    rows = read_csv(single_dir / "summary_by_method.csv")
    by_method = {row["method"]: row for row in rows}
    methods = ["distribution_change", "tvd_rate_change", "traffic_loss", "probe_loss"]

    xs = list(range(len(methods)))
    values = []
    lower = []
    upper = []
    colours = []
    for method in methods:
        row = by_method[method]
        median = number(row, "median_detection_load_ratio")
        q25 = number(row, "q25_detection_load_ratio")
        q75 = number(row, "q75_detection_load_ratio")
        values.append(median if finite(median) else 0.0)
        lower.append(median - q25 if finite(median) and finite(q25) else 0.0)
        upper.append(q75 - median if finite(median) and finite(q75) else 0.0)
        colours.append(METHOD_COLOURS[method])

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    ax.bar(xs, values, yerr=[lower, upper], capsize=4, color=colours, alpha=0.88)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured link capacity")
    ax.set_xticks(xs)
    ax.set_xticklabels([METHOD_LABELS[m] for m in methods], rotation=15, ha="right")
    ax.set_ylabel("Detection load divided by configured link capacity")
    ax.set_title("Single-hop endpoint-observable capacity signals")
    ax.set_ylim(0, 1.08)
    ax.grid(axis="y", alpha=0.25)
    ax.text(xs[-1], 0.045, "not observed", ha="center", va="bottom", fontsize=9, color="#4d4d4d")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_dir / "observable_capacity_single_methods.png", dpi=220)
    plt.close(fig)


def plot_multi_methods(multi_dir: Path, out_dir: Path) -> None:
    rows = read_csv(multi_dir / "summary_by_method.csv")
    methods = ["distribution_change", "tvd_rate_change", "traffic_loss"]

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    for method in methods:
        selected = [row for row in rows if row["method"] == method]
        selected.sort(key=lambda row: int(float(row["hop_count"])))
        xs = [int(float(row["hop_count"])) for row in selected]
        med = [number(row, "median_detection_load_ratio") for row in selected]
        q25 = [number(row, "q25_detection_load_ratio") for row in selected]
        q75 = [number(row, "q75_detection_load_ratio") for row in selected]
        err_low = [m - lo for m, lo in zip(med, q25)]
        err_high = [hi - m for m, hi in zip(med, q75)]
        ax.errorbar(
            xs,
            med,
            yerr=[err_low, err_high],
            marker="o",
            linewidth=2.0,
            capsize=3,
            label=METHOD_LABELS[method],
            color=METHOD_COLOURS[method],
        )

    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured link capacity")
    ax.set_xlabel("Hop count")
    ax.set_ylabel("Detection load divided by configured link capacity")
    ax.set_title("Multi-hop endpoint-observable capacity signals")
    ax.set_ylim(0, 1.08)
    ax.set_xticks(range(2, 11))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="center right")
    fig.tight_layout()
    fig.savefig(out_dir / "observable_capacity_multi_methods.png", dpi=220)
    plt.close(fig)


def plot_multi_tvd_loss(multi_dir: Path, out_dir: Path, hop: int) -> None:
    rows = [
        row
        for row in read_csv(multi_dir / "summary_by_load.csv")
        if int(float(row["hop_count"])) == hop
    ]
    rows.sort(key=lambda row: number(row, "load_ratio"))
    xs = [number(row, "load_ratio") for row in rows]
    tvd = [number(row, "median_tvd_from_baseline") for row in rows]
    losses = [number(row, "median_traffic_loss_count") for row in rows]
    probe_losses = [number(row, "median_probe_loss_count") for row in rows]

    fig, ax1 = plt.subplots(figsize=(10.5, 5.8))
    ax1.plot(xs, tvd, marker="o", color="#1f77b4", linewidth=2.0, label="TVD from low-load baseline")
    ax1.axhline(0.05, color="#1f77b4", linestyle=":", linewidth=1.5, label="Distribution-change threshold")
    ax1.axvline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax1.set_xlabel("Offered load divided by configured link capacity")
    ax1.set_ylabel("TVD")
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(xs, losses, marker="^", color="#2ca02c", linewidth=2.0, label="Endpoint traffic losses")
    ax2.plot(xs, probe_losses, marker="s", color="#4d4d4d", linewidth=1.6, label="Probe losses")
    ax2.set_ylabel("Median lost packets")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
    ax1.set_title(f"TVD and endpoint loss in a {hop}-hop path")
    fig.tight_layout()
    fig.savefig(out_dir / "observable_capacity_multi_tvd_loss.png", dpi=220)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot observable capacity summary figures.")
    parser.add_argument("--single-dir", required=True)
    parser.add_argument("--multi-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--plot-hop", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_single_methods(Path(args.single_dir), out_dir)
    plot_multi_methods(Path(args.multi_dir), out_dir)
    plot_multi_tvd_loss(Path(args.multi_dir), out_dir, args.plot_hop)


if __name__ == "__main__":
    main()
