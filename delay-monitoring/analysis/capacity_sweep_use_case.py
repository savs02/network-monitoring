"""
Capacity sensitivity sweep for the adaptive capacity use case.

Each configured capacity is evaluated with the same adaptive stopping and
distribution-change search used by adaptive_capacity_use_case.py. The sweep is
intended to check whether the method scales with the link capacity, rather than
only working at the original 10 Mbps setting.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
USE_CASE_SCRIPT = SCRIPT_DIR / "adaptive_capacity_use_case.py"

os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "delay-monitoring" / "results" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


DEFAULT_CAPACITIES_MBPS = (
    2.0,
    3.0,
    4.0,
    5.0,
    6.0,
    7.0,
    8.0,
    9.0,
    11.0,
    12.0,
    14.0,
    16.0,
    18.0,
    20.0,
    24.0,
    28.0,
    32.0,
    40.0,
    50.0,
    64.0,
)

DISTRIBUTIONS = ("normal", "lognormal", "weibull")
DIST_LABELS = {
    "normal": "Normal",
    "lognormal": "Lognormal",
    "weibull": "Weibull",
}
DIST_COLOURS = {
    "normal": "#2874a6",
    "lognormal": "#c0392b",
    "weibull": "#d68910",
}
DIST_MARKERS = {
    "normal": "o",
    "lognormal": "s",
    "weibull": "^",
}
DIST_LINESTYLES = {
    "normal": "-",
    "lognormal": "--",
    "weibull": ":",
}


def fmt_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def capacity_label(capacity_mbps: float) -> str:
    return f"cap_{fmt_float(capacity_mbps).replace('.', 'p')}Mbps"


def read_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def numeric(row: dict, key: str) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return math.nan
    try:
        return float(value)
    except ValueError:
        return math.nan


def command_for_capacity(args: argparse.Namespace, capacity_mbps: float, build: bool) -> list[str]:
    start_load = max(args.min_start_load_mbps, capacity_mbps * args.start_load_fraction)
    max_load = capacity_mbps * args.max_load_factor
    binary_width = max(args.min_binary_width_mbps, capacity_mbps * args.binary_width_fraction)
    result_dir = Path(args.results_dir) / capacity_label(capacity_mbps)

    command = [
        sys.executable,
        str(USE_CASE_SCRIPT),
        "--results-dir",
        str(result_dir),
        "--dists",
        *args.dists,
        "--seed-start",
        str(args.seed_start),
        "--seed-end",
        str(args.seed_end),
        "--workers",
        str(args.workers),
        "--start-load-mbps",
        fmt_float(start_load),
        "--load-multiplier",
        fmt_float(args.load_multiplier),
        "--max-load-mbps",
        fmt_float(max_load),
        "--binary-iterations",
        str(args.binary_iterations),
        "--binary-min-width-mbps",
        fmt_float(binary_width),
        "--configured-capacity-mbps",
        fmt_float(capacity_mbps),
        "--link-data-rate",
        f"{fmt_float(capacity_mbps)}Mbps",
        "--link-delay",
        args.link_delay,
        "--queue-size",
        str(args.queue_size),
        "--probe-packet-size",
        str(args.probe_packet_size),
        "--probe-interval-mean-ms",
        fmt_float(args.probe_interval_mean_ms),
        "--max-packets-per-load",
        str(args.max_packets_per_load),
    ]
    if args.force:
        command.append("--force")
    if args.skip_ns3_build or not build:
        command.append("--skip-ns3-build")
    return command


def run_capacity(args: argparse.Namespace, capacity_mbps: float, build: bool) -> None:
    result_dir = Path(args.results_dir) / capacity_label(capacity_mbps)
    if args.collect_only:
        return
    if args.skip_complete and (result_dir / "aggregate_summary.json").exists():
        print(f"Skipping {capacity_mbps:g} Mbps, summary already exists", flush=True)
        return

    print(f"Running configured capacity {capacity_mbps:g} Mbps", flush=True)
    completed = subprocess.run(command_for_capacity(args, capacity_mbps, build), cwd=REPO_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"Capacity sweep failed at {capacity_mbps:g} Mbps")


def collect_results(args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    aggregate_rows: list[dict] = []
    distribution_rows: list[dict] = []
    stopping_rows: list[dict] = []
    detection_rows: list[dict] = []

    for capacity_mbps in args.capacities_mbps:
        result_dir = Path(args.results_dir) / capacity_label(capacity_mbps)
        aggregate_path = result_dir / "aggregate_summary.json"
        if not aggregate_path.exists():
            print(f"Missing summary for {capacity_mbps:g} Mbps", flush=True)
            continue

        aggregate = read_json(aggregate_path)
        aggregate_rows.append(
            {
                "configured_capacity_mbps": capacity_mbps,
                "capacity_label": capacity_label(capacity_mbps),
                **aggregate,
                "threshold_ratio": numeric(aggregate, "median_threshold_mbps") / capacity_mbps,
            }
        )

        for row in read_csv(result_dir / "summary_by_distribution.csv"):
            threshold = numeric(row, "median_threshold_mbps")
            row = {
                "configured_capacity_mbps": capacity_mbps,
                "capacity_label": capacity_label(capacity_mbps),
                **row,
                "median_threshold_ratio": threshold / capacity_mbps,
                "q25_threshold_ratio": numeric(row, "q25_threshold_mbps") / capacity_mbps,
                "q75_threshold_ratio": numeric(row, "q75_threshold_mbps") / capacity_mbps,
            }
            distribution_rows.append(row)

        for row in read_csv(result_dir / "stopping_summary_by_distribution.csv"):
            stopping_rows.append(
                {
                    "configured_capacity_mbps": capacity_mbps,
                    "capacity_label": capacity_label(capacity_mbps),
                    **row,
                }
            )

        for row in read_csv(result_dir / "detection_summary_by_distribution.csv"):
            first = numeric(row, "median_first_detection_mbps")
            detection_rows.append(
                {
                    "configured_capacity_mbps": capacity_mbps,
                    "capacity_label": capacity_label(capacity_mbps),
                    **row,
                    "median_first_detection_ratio": first / capacity_mbps,
                }
            )

    return aggregate_rows, distribution_rows, stopping_rows, detection_rows


def sorted_dist_rows(rows: list[dict], dist: str) -> list[dict]:
    sub = [row for row in rows if row.get("dist") == dist]
    return sorted(sub, key=lambda row: numeric(row, "configured_capacity_mbps"))


def plot_threshold_ratio(rows: list[dict], plots_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    for dist in DISTRIBUTIONS:
        sub = sorted_dist_rows(rows, dist)
        if not sub:
            continue
        x = [numeric(row, "configured_capacity_mbps") for row in sub]
        med = [numeric(row, "median_threshold_ratio") for row in sub]
        q25 = [numeric(row, "q25_threshold_ratio") for row in sub]
        q75 = [numeric(row, "q75_threshold_ratio") for row in sub]
        ax.plot(
            x,
            med,
            marker=DIST_MARKERS[dist],
            linestyle=DIST_LINESTYLES[dist],
            linewidth=2.2,
            markersize=6,
            color=DIST_COLOURS[dist],
            label=DIST_LABELS[dist],
        )
        ax.fill_between(x, q25, q75, color=DIST_COLOURS[dist], alpha=0.16)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xlabel("Configured link capacity in Mbps")
    ax.set_ylabel("Estimated threshold divided by configured capacity")
    ax.set_title("Capacity sweep threshold scaling")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    out = plots_dir / "capacity_sweep_threshold_ratio.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_aggregate_threshold_ratio(rows: list[dict], plots_dir: Path) -> Path:
    ordered = sorted(rows, key=lambda row: numeric(row, "configured_capacity_mbps"))
    x = [numeric(row, "configured_capacity_mbps") for row in ordered]
    y = [numeric(row, "threshold_ratio") for row in ordered]

    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    ax.plot(x, y, marker="o", linewidth=2.4, markersize=6, color="#34495e")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.axhline(0.975, color="#7f8c8d", linestyle=":", linewidth=1.2, label="Stable 0.975 ratio")
    ax.set_xlabel("Configured link capacity in Mbps")
    ax.set_ylabel("Median estimated threshold divided by configured capacity")
    ax.set_title("Aggregate capacity sweep threshold scaling")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    out = plots_dir / "capacity_sweep_aggregate_threshold_ratio.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_relative_error(rows: list[dict], plots_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    for dist in DISTRIBUTIONS:
        sub = sorted_dist_rows(rows, dist)
        if not sub:
            continue
        x = [numeric(row, "configured_capacity_mbps") for row in sub]
        y = [100.0 * numeric(row, "median_relative_threshold_error") for row in sub]
        ax.plot(
            x,
            y,
            marker=DIST_MARKERS[dist],
            linestyle=DIST_LINESTYLES[dist],
            linewidth=2.2,
            markersize=6,
            color=DIST_COLOURS[dist],
            label=DIST_LABELS[dist],
        )
    ax.axhline(0.0, color="black", linestyle="--", linewidth=1.2)
    ax.set_xlabel("Configured link capacity in Mbps")
    ax.set_ylabel("Median threshold error as percentage")
    ax.set_title("Capacity sweep relative error")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    out = plots_dir / "capacity_sweep_relative_error.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_detection_ratio(rows: list[dict], plots_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    for dist in DISTRIBUTIONS:
        sub = sorted_dist_rows(rows, dist)
        if not sub:
            continue
        x = [numeric(row, "configured_capacity_mbps") for row in sub]
        y = [numeric(row, "median_first_detection_ratio") for row in sub]
        ax.plot(
            x,
            y,
            marker=DIST_MARKERS[dist],
            linestyle=DIST_LINESTYLES[dist],
            linewidth=2.2,
            markersize=6,
            color=DIST_COLOURS[dist],
            label=DIST_LABELS[dist],
        )
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xlabel("Configured link capacity in Mbps")
    ax.set_ylabel("First significant load divided by configured capacity")
    ax.set_title("Capacity sweep exponential detection point")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    out = plots_dir / "capacity_sweep_detection_ratio.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_stopping_counts(rows: list[dict], plots_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    for dist in DISTRIBUTIONS:
        sub = sorted_dist_rows(rows, dist)
        if not sub:
            continue
        x = [numeric(row, "configured_capacity_mbps") for row in sub]
        y = [numeric(row, "median_n_stop") for row in sub]
        ax.plot(
            x,
            y,
            marker=DIST_MARKERS[dist],
            linestyle=DIST_LINESTYLES[dist],
            linewidth=2.2,
            markersize=6,
            color=DIST_COLOURS[dist],
            label=DIST_LABELS[dist],
        )
    ax.set_xlabel("Configured link capacity in Mbps")
    ax.set_ylabel("Median stopped sample count")
    ax.set_title("Adaptive stopping cost across capacities")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    out = plots_dir / "capacity_sweep_stopping_counts.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def generate_plots(
    aggregate_rows: list[dict],
    distribution_rows: list[dict],
    stopping_rows: list[dict],
    detection_rows: list[dict],
    plots_dir: Path,
) -> list[Path]:
    plots_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if aggregate_rows:
        paths.append(plot_aggregate_threshold_ratio(aggregate_rows, plots_dir))
    if distribution_rows:
        paths.append(plot_threshold_ratio(distribution_rows, plots_dir))
        paths.append(plot_relative_error(distribution_rows, plots_dir))
    if detection_rows:
        paths.append(plot_detection_ratio(detection_rows, plots_dir))
    if stopping_rows:
        paths.append(plot_stopping_counts(stopping_rows, plots_dir))
    return paths


def make_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run configured-capacity sensitivity experiments.")
    parser.add_argument("--results-dir", default=str(REPO_ROOT / "delay-monitoring" / "results" / "use-case-capacity-sweep"))
    parser.add_argument("--capacities-mbps", nargs="+", type=float, default=list(DEFAULT_CAPACITIES_MBPS))
    parser.add_argument("--dists", nargs="+", default=list(DISTRIBUTIONS), choices=list(DISTRIBUTIONS))
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-complete", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--skip-ns3-build", action="store_true")
    parser.add_argument("--start-load-fraction", type=float, default=0.05)
    parser.add_argument("--min-start-load-mbps", type=float, default=0.1)
    parser.add_argument("--load-multiplier", type=float, default=2.0)
    parser.add_argument("--max-load-factor", type=float, default=3.2)
    parser.add_argument("--binary-iterations", type=int, default=6)
    parser.add_argument("--binary-width-fraction", type=float, default=0.025)
    parser.add_argument("--min-binary-width-mbps", type=float, default=0.05)
    parser.add_argument("--link-delay", default="2ms")
    parser.add_argument("--queue-size", type=int, default=50)
    parser.add_argument("--probe-packet-size", type=int, default=64)
    parser.add_argument("--probe-interval-mean-ms", type=float, default=10.0)
    parser.add_argument("--max-packets-per-load", type=int, default=4000)
    return parser.parse_args()


def save_config(args: argparse.Namespace, results_dir: Path) -> None:
    config = vars(args).copy()
    config["capacities_mbps"] = list(args.capacities_mbps)
    config["note"] = "Each capacity is run as a separate adaptive capacity use-case experiment."
    with (results_dir / "capacity_sweep_config.json").open("w") as f:
        json.dump(config, f, indent=2)


def main() -> int:
    args = make_args()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    save_config(args, results_dir)

    for index, capacity_mbps in enumerate(args.capacities_mbps):
        run_capacity(args, capacity_mbps, build=index == 0)

    aggregate_rows, distribution_rows, stopping_rows, detection_rows = collect_results(args)
    write_csv(results_dir / "capacity_sweep_aggregate.csv", aggregate_rows)
    write_csv(results_dir / "capacity_sweep_by_distribution.csv", distribution_rows)
    write_csv(results_dir / "capacity_sweep_stopping.csv", stopping_rows)
    write_csv(results_dir / "capacity_sweep_detection.csv", detection_rows)

    plot_paths = generate_plots(aggregate_rows, distribution_rows, stopping_rows, detection_rows, results_dir / "plots")
    print(f"Wrote {len(aggregate_rows)} capacity summaries to {results_dir}", flush=True)
    print(f"Generated {len(plot_paths)} sweep plots in {results_dir / 'plots'}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
