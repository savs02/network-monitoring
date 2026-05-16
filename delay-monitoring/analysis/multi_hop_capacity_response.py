"""
Multi-hop capacity response experiments.

This extends the one-link capacity use case to paths with two to ten hops. The
path is a chain of point-to-point links. Probe traffic traverses the full path,
while controlled cross traffic is increased across the path rather than being
placed on a single hidden bottleneck. The analysis compares distributional
profiling against packet-loss profiling using the same response-rate criterion
as the one-link experiment.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "delay-monitoring" / "results" / ".matplotlib"))

import matplotlib.pyplot as plt
import numpy as np

import distributional_capacity_response as base


def effective_tracking_hop(hop_count: int, bottleneck_hop: int, cross_traffic_scope: str) -> int:
    if cross_traffic_scope != "single-hop":
        return -1
    if bottleneck_hop < 0:
        return min(hop_count - 1, hop_count // 2)
    return min(hop_count - 1, bottleneck_hop)


def stressed_hop_count(hop_count: int, cross_traffic_scope: str) -> int:
    return hop_count if cross_traffic_scope in {"all-links", "path"} else 1


def add_hop_context(row: dict, hop_count: int, args: argparse.Namespace) -> dict:
    return {
        "hop_count": hop_count,
        "traffic_scope": args.cross_traffic_scope,
        "stressed_hop_count": stressed_hop_count(hop_count, args.cross_traffic_scope),
        "bottleneck_hop": effective_tracking_hop(hop_count, args.bottleneck_hop, args.cross_traffic_scope),
        **row,
    }


def ns3_target(dist: str, seed: int, load_mbps: float, raw_path: Path, drop_path: Path, args: argparse.Namespace) -> str:
    return (
        "scratch/delay-monitoring-multihop/multi-hop-capacity-network "
        f"--delayDist={dist} "
        f"--hopCount={args.hop_count} "
        f"--bottleneckHop={args.bottleneck_hop} "
        f"--crossTrafficScope={args.cross_traffic_scope} "
        f"--crossTrafficDataRate={load_mbps:.6f}Mbps "
        f"--crossTrafficStopTime={getattr(args, 'cross_traffic_stop_time', -1.0):.6f} "
        f"--linkDataRate={args.link_data_rate} "
        f"--linkDelay={args.link_delay} "
        f"--queueSize={args.queue_size} "
        f"--queueDiscType={args.queue_disc_type} "
        f"--useQueueDisc={'true' if getattr(args, 'use_queue_disc', False) else 'false'} "
        f"--packetSize={args.probe_packet_size} "
        f"--intervalMean={args.probe_interval_mean_ms:.6f} "
        f"--numPackets={args.max_packets_per_load} "
        f"--simulationStopTime={args.simulation_stop_time:.6f} "
        f"--RngRun={seed} "
        f"--outputFile={raw_path} "
        f"--dropStatsFile={drop_path}"
    )


base.ns3_target = ns3_target


def build_ns3() -> None:
    base.log("Building NS-3 multi-hop target")
    completed = subprocess.run(
        ["./ns3", "build", "scratch/delay-monitoring-multihop/multi-hop-capacity-network"],
        cwd=base.NS3_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "NS-3 multi-hop build failed\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )


def run_one_case(hop_count: int, dist: str, seed: int, results_dir: Path, args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict]]:
    local_args = argparse.Namespace(**vars(args))
    local_args.hop_count = hop_count
    local_args.configured_capacity_mbps = args.capacity_mbps
    local_args.link_data_rate = f"{base.fmt_float(args.capacity_mbps)}Mbps"

    hop_results_dir = results_dir / f"hop_{hop_count:02d}"
    cache: dict[float, base.LoadState] = {}
    all_response_rows: list[dict] = []
    estimates: list[dict] = []

    for mode in args.modes:
        rows, estimate = base.run_search(mode, dist, seed, args.capacity_mbps, hop_results_dir, local_args, cache)
        all_response_rows.extend(add_hop_context(row, hop_count, local_args) for row in rows)
        estimates.append(add_hop_context(estimate, hop_count, local_args))

    for ratio in args.loss_sweep_ratios:
        if ratio > 0:
            base.evaluate_load(dist, seed, args.capacity_mbps, args.capacity_mbps * ratio, hop_results_dir, local_args, cache)

    load_rows = [
        add_hop_context(base.state_row(state), hop_count, local_args)
        for state in sorted(cache.values(), key=lambda s: s.load_mbps)
    ]
    return load_rows, all_response_rows, estimates


def finite(value: float) -> bool:
    return np.isfinite(float(value))


def ratio_or_nan(row: dict | None, key: str) -> float:
    return base.numeric(row, key) if row else math.nan


def summarise(estimates: list[dict], responses: list[dict], loads: list[dict], results_dir: Path) -> None:
    by_hop_mode_dist = []
    for (hop, mode, dist), rows in sorted(
        base.group_by(estimates, ("hop_count", "mode", "dist")).items(),
        key=lambda item: (int(item[0][0]), item[0][1], item[0][2]),
    ):
        by_hop_mode_dist.append({
            "hop_count": hop,
            "mode": mode,
            "dist": dist,
            "runs": len(rows),
            "detected_rate": sum(1 for row in rows if row["status"] == "detected") / len(rows),
            "median_estimated_capacity_ratio": base.median(base.numeric(row, "estimated_capacity_ratio") for row in rows),
            "q25_estimated_capacity_ratio": base.percentile((base.numeric(row, "estimated_capacity_ratio") for row in rows), 25),
            "q75_estimated_capacity_ratio": base.percentile((base.numeric(row, "estimated_capacity_ratio") for row in rows), 75),
            "median_upper_ratio": base.median(base.numeric(row, "upper_ratio") for row in rows),
            "median_first_accelerated_ratio": base.median(base.numeric(row, "first_accelerated_ratio") for row in rows),
            "median_load_evaluations": base.median(base.numeric(row, "load_evaluations") for row in rows),
            "median_max_qdisc_drops": base.median(base.numeric(row, "max_qdisc_drop_count", 0) for row in rows),
            "median_max_probe_losses": base.median(base.numeric(row, "max_probe_loss_count", 0) for row in rows),
        })

    by_hop_mode = []
    for (hop, mode), rows in sorted(
        base.group_by(estimates, ("hop_count", "mode")).items(),
        key=lambda item: (int(item[0][0]), item[0][1]),
    ):
        by_hop_mode.append({
            "hop_count": hop,
            "mode": mode,
            "runs": len(rows),
            "detected_rate": sum(1 for row in rows if row["status"] == "detected") / len(rows),
            "median_estimated_capacity_ratio": base.median(base.numeric(row, "estimated_capacity_ratio") for row in rows),
            "q25_estimated_capacity_ratio": base.percentile((base.numeric(row, "estimated_capacity_ratio") for row in rows), 25),
            "q75_estimated_capacity_ratio": base.percentile((base.numeric(row, "estimated_capacity_ratio") for row in rows), 75),
            "median_upper_ratio": base.median(base.numeric(row, "upper_ratio") for row in rows),
            "median_first_accelerated_ratio": base.median(base.numeric(row, "first_accelerated_ratio") for row in rows),
            "median_load_evaluations": base.median(base.numeric(row, "load_evaluations") for row in rows),
        })

    drop_rows = []
    for (hop, dist, seed), rows in sorted(
        base.group_by(loads, ("hop_count", "dist", "seed")).items(),
        key=lambda item: (int(item[0][0]), item[0][1], int(item[0][2])),
    ):
        ordered = sorted(rows, key=lambda row: base.numeric(row, "offered_load_mbps"))
        first_queue = next((row for row in ordered if base.numeric(row, "queue_drop_count", 0) > 0), None)
        first_qdisc = next((row for row in ordered if base.numeric(row, "qdisc_drop_count", 0) > 0), None)
        first_bottleneck_qdisc = next((row for row in ordered if base.numeric(row, "bottleneck_qdisc_drop_count", 0) > 0), None)
        first_max_hop_qdisc = next((row for row in ordered if base.numeric(row, "max_hop_qdisc_drop_count", 0) > 0), None)
        first_probe = next((row for row in ordered if base.numeric(row, "probe_loss_count", 0) > 0), None)
        drop_rows.append({
            "hop_count": hop,
            "dist": dist,
            "seed": seed,
            "first_queue_drop_load_mbps": ratio_or_nan(first_queue, "offered_load_mbps"),
            "first_queue_drop_ratio": ratio_or_nan(first_queue, "load_ratio"),
            "first_qdisc_drop_load_mbps": ratio_or_nan(first_qdisc, "offered_load_mbps"),
            "first_qdisc_drop_ratio": ratio_or_nan(first_qdisc, "load_ratio"),
            "first_bottleneck_qdisc_drop_load_mbps": ratio_or_nan(first_bottleneck_qdisc, "offered_load_mbps"),
            "first_bottleneck_qdisc_drop_ratio": ratio_or_nan(first_bottleneck_qdisc, "load_ratio"),
            "first_max_hop_qdisc_drop_load_mbps": ratio_or_nan(first_max_hop_qdisc, "offered_load_mbps"),
            "first_max_hop_qdisc_drop_ratio": ratio_or_nan(first_max_hop_qdisc, "load_ratio"),
            "first_probe_loss_load_mbps": ratio_or_nan(first_probe, "offered_load_mbps"),
            "first_probe_loss_ratio": ratio_or_nan(first_probe, "load_ratio"),
            "max_tested_ratio": max((base.numeric(row, "load_ratio", 0) for row in ordered), default=0),
            "max_queue_drop_count": max((base.numeric(row, "queue_drop_count", 0) for row in ordered), default=0),
            "max_qdisc_drop_count": max((base.numeric(row, "qdisc_drop_count", 0) for row in ordered), default=0),
            "max_bottleneck_qdisc_drop_count": max((base.numeric(row, "bottleneck_qdisc_drop_count", 0) for row in ordered), default=0),
            "max_hop_qdisc_drop_count": max((base.numeric(row, "max_hop_qdisc_drop_count", 0) for row in ordered), default=0),
            "max_probe_loss_count": max((base.numeric(row, "probe_loss_count", 0) for row in ordered), default=0),
            "median_active_cross_traffic_flows": base.median(base.numeric(row, "active_cross_traffic_flows", 0) for row in ordered),
        })

    drop_summary = []
    for (hop, dist), rows in sorted(
        base.group_by(drop_rows, ("hop_count", "dist")).items(),
        key=lambda item: (int(item[0][0]), item[0][1]),
    ):
        drop_summary.append({
            "hop_count": hop,
            "dist": dist,
            "runs": len(rows),
            "qdisc_drop_detected_rate": sum(1 for row in rows if finite(base.numeric(row, "first_qdisc_drop_ratio"))) / len(rows),
            "median_first_qdisc_drop_ratio": base.median(base.numeric(row, "first_qdisc_drop_ratio") for row in rows),
            "bottleneck_qdisc_drop_detected_rate": sum(1 for row in rows if finite(base.numeric(row, "first_bottleneck_qdisc_drop_ratio"))) / len(rows),
            "median_first_bottleneck_qdisc_drop_ratio": base.median(base.numeric(row, "first_bottleneck_qdisc_drop_ratio") for row in rows),
            "max_hop_qdisc_drop_detected_rate": sum(1 for row in rows if finite(base.numeric(row, "first_max_hop_qdisc_drop_ratio"))) / len(rows),
            "median_first_max_hop_qdisc_drop_ratio": base.median(base.numeric(row, "first_max_hop_qdisc_drop_ratio") for row in rows),
            "probe_loss_detected_rate": sum(1 for row in rows if finite(base.numeric(row, "first_probe_loss_ratio"))) / len(rows),
            "median_first_probe_loss_ratio": base.median(base.numeric(row, "first_probe_loss_ratio") for row in rows),
            "median_max_tested_ratio": base.median(base.numeric(row, "max_tested_ratio") for row in rows),
            "median_max_qdisc_drops": base.median(base.numeric(row, "max_qdisc_drop_count", 0) for row in rows),
            "median_max_bottleneck_qdisc_drops": base.median(base.numeric(row, "max_bottleneck_qdisc_drop_count", 0) for row in rows),
            "median_max_hop_qdisc_drops": base.median(base.numeric(row, "max_hop_qdisc_drop_count", 0) for row in rows),
            "median_max_probe_losses": base.median(base.numeric(row, "max_probe_loss_count", 0) for row in rows),
            "median_active_cross_traffic_flows": base.median(base.numeric(row, "median_active_cross_traffic_flows", 0) for row in rows),
        })

    by_run_drop = {
        (str(row["hop_count"]), row["dist"], str(row["seed"])): row
        for row in drop_rows
    }
    comparison_rows = []
    for (hop, mode, dist), rows in sorted(
        base.group_by(estimates, ("hop_count", "mode", "dist")).items(),
        key=lambda item: (int(item[0][0]), item[0][1], item[0][2]),
    ):
        comparisons = []
        for row in rows:
            drop = by_run_drop.get((str(row["hop_count"]), row["dist"], str(row["seed"])))
            distributional = base.numeric(row, "upper_ratio")
            probe = base.numeric(drop, "first_probe_loss_ratio") if drop else math.nan
            qdisc = base.numeric(drop, "first_qdisc_drop_ratio") if drop else math.nan
            comparisons.append((distributional, probe, qdisc))

        def beats(candidate: float, baseline: float) -> bool:
            if not finite(candidate):
                return False
            if not finite(baseline):
                return True
            return candidate < baseline - 1.0e-9

        def ties(candidate: float, baseline: float) -> bool:
            return finite(candidate) and finite(baseline) and abs(candidate - baseline) <= 1.0e-9

        comparison_rows.append({
            "hop_count": hop,
            "mode": mode,
            "dist": dist,
            "runs": len(comparisons),
            "distributional_upper_beats_probe_loss_rate": sum(1 for d, p, _ in comparisons if beats(d, p)) / len(comparisons),
            "distributional_upper_ties_probe_loss_rate": sum(1 for d, p, _ in comparisons if ties(d, p)) / len(comparisons),
            "probe_loss_beats_distributional_upper_rate": sum(1 for d, p, _ in comparisons if beats(p, d)) / len(comparisons),
            "distributional_upper_beats_qdisc_drop_rate": sum(1 for d, _, q in comparisons if beats(d, q)) / len(comparisons),
            "distributional_upper_ties_qdisc_drop_rate": sum(1 for d, _, q in comparisons if ties(d, q)) / len(comparisons),
            "qdisc_drop_beats_distributional_upper_rate": sum(1 for d, _, q in comparisons if beats(q, d)) / len(comparisons),
            "median_distributional_upper_minus_probe_loss_ratio": base.median(d - p for d, p, _ in comparisons if finite(d) and finite(p)),
            "median_distributional_upper_minus_qdisc_ratio": base.median(d - q for d, _, q in comparisons if finite(d) and finite(q)),
        })

    base.write_csv(results_dir / "summary_by_hop_mode_distribution.csv", by_hop_mode_dist)
    base.write_csv(results_dir / "summary_by_hop_mode.csv", by_hop_mode)
    base.write_csv(results_dir / "drop_detection_by_run.csv", drop_rows)
    base.write_csv(results_dir / "drop_detection_summary_by_hop.csv", drop_summary)
    base.write_csv(results_dir / "comparison_summary_by_hop.csv", comparison_rows)


def unique_hops(rows: Iterable[dict]) -> list[int]:
    return sorted({int(float(row["hop_count"])) for row in rows})


def plot_capacity_brackets(estimates: list[dict], plots_dir: Path, mode: str) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    for dist in base.DISTRIBUTIONS:
        rows = [row for row in estimates if row.get("mode") == mode and row.get("dist") == dist and row.get("status") == "detected"]
        if not rows:
            continue
        groups = base.group_by(rows, ("hop_count",))
        xs, lower, upper, lower_lo, lower_hi = [], [], [], [], []
        for (hop,), sub in sorted(groups.items(), key=lambda item: int(item[0][0])):
            vals = [base.numeric(row, "estimated_capacity_ratio") for row in sub]
            upper_vals = [base.numeric(row, "upper_ratio") for row in sub]
            med = base.median(vals)
            q25 = base.percentile(vals, 25)
            q75 = base.percentile(vals, 75)
            xs.append(int(hop))
            lower.append(med)
            upper.append(base.median(upper_vals))
            lower_lo.append(med - q25)
            lower_hi.append(q75 - med)
        colour = base.DIST_COLOURS.get(dist, None)
        ax.errorbar(xs, lower, yerr=[lower_lo, lower_hi], marker="o", linewidth=2.0, capsize=3, color=colour, label=f"{base.DIST_LABELS.get(dist, dist)} lower")
        ax.plot(xs, upper, marker="^", linestyle="--", linewidth=1.7, color=colour, alpha=0.85, label=f"{base.DIST_LABELS.get(dist, dist)} upper")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xlabel("Hop count")
    ax.set_ylabel("Estimated load divided by per-link capacity")
    ax.set_title("Multi-hop distributional capacity bracket")
    ax.set_xticks(unique_hops(estimates))
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2, fontsize=9)
    out = plots_dir / "multi_hop_capacity_brackets.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_distributional_vs_loss(estimates: list[dict], drop_summary: list[dict], plots_dir: Path, mode: str) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    for dist in base.DISTRIBUTIONS:
        rows = [row for row in estimates if row.get("mode") == mode and row.get("dist") == dist and row.get("status") == "detected"]
        if not rows:
            continue
        groups = base.group_by(rows, ("hop_count",))
        xs, ys = [], []
        for (hop,), sub in sorted(groups.items(), key=lambda item: int(item[0][0])):
            xs.append(int(hop))
            ys.append(base.median(base.numeric(row, "upper_ratio") for row in sub))
        ax.plot(xs, ys, marker="o", linewidth=2.0, color=base.DIST_COLOURS.get(dist), label=f"{base.DIST_LABELS.get(dist, dist)} distributional upper")

    grouped_drops = base.group_by(drop_summary, ("hop_count",))
    xs, qdisc, probe = [], [], []
    for (hop,), sub in sorted(grouped_drops.items(), key=lambda item: int(item[0][0])):
        xs.append(int(hop))
        qdisc.append(base.median(base.numeric(row, "median_first_qdisc_drop_ratio") for row in sub))
        probe.append(base.median(base.numeric(row, "median_first_probe_loss_ratio") for row in sub))
    if xs:
        ax.plot(xs, qdisc, marker="s", linewidth=2.0, color="#2ca02c", label="First queue-disc drop")
        ax.plot(xs, probe, marker="D", linewidth=2.0, color="#4d4d4d", label="First receiver-visible probe loss")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xlabel("Hop count")
    ax.set_ylabel("Detection load divided by per-link capacity")
    ax.set_title("Multi-hop distributional profiling compared with packet loss")
    ax.set_xticks(unique_hops(estimates))
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=9)
    out = plots_dir / "multi_hop_distributional_vs_loss.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_detection_success(estimates: list[dict], drop_summary: list[dict], plots_dir: Path, mode: str) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 6.0))
    rows = [row for row in estimates if row.get("mode") == mode]
    grouped_estimates = base.group_by(rows, ("hop_count",))
    hops, distributional = [], []
    for (hop,), sub in sorted(grouped_estimates.items(), key=lambda item: int(item[0][0])):
        hops.append(int(hop))
        distributional.append(sum(1 for row in sub if row["status"] == "detected") / len(sub))

    grouped_drops = base.group_by(drop_summary, ("hop_count",))
    qdisc, probe = [], []
    for hop in hops:
        sub = grouped_drops.get((str(hop),), [])
        qdisc.append(base.median(base.numeric(row, "qdisc_drop_detected_rate") for row in sub))
        probe.append(base.median(base.numeric(row, "probe_loss_detected_rate") for row in sub))

    ax.plot(hops, distributional, marker="o", linewidth=2.2, label="Distributional detection", color="#1f77b4")
    ax.plot(hops, qdisc, marker="s", linewidth=2.2, label="Queue-disc drop detection", color="#2ca02c")
    ax.plot(hops, probe, marker="D", linewidth=2.2, label="Probe-loss detection", color="#4d4d4d")
    ax.set_xlabel("Hop count")
    ax.set_ylabel("Detected run fraction")
    ax.set_ylim(-0.03, 1.03)
    ax.set_title("Multi-hop detection reliability over 100 seeds")
    ax.set_xticks(hops)
    ax.grid(True, alpha=0.25)
    ax.legend()
    out = plots_dir / "multi_hop_detection_success.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_response_curves(responses: list[dict], plots_dir: Path, mode: str, plot_dist: str, selected_hops: list[int]) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    colours = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b"]
    for idx, hop in enumerate(selected_hops):
        rows = [
            row for row in responses
            if int(float(row["hop_count"])) == hop
            and row.get("mode") == mode
            and row.get("dist") == plot_dist
        ]
        if not rows:
            continue
        groups = base.group_by(rows, ("load_ratio",))
        xs, ys, lo, hi = [], [], [], []
        for (ratio,), sub in sorted(groups.items(), key=lambda item: float(item[0][0])):
            vals = [base.numeric(row, "score_tvd_from_baseline") for row in sub]
            med = base.median(vals)
            q25 = base.percentile(vals, 25)
            q75 = base.percentile(vals, 75)
            xs.append(float(ratio))
            ys.append(med)
            lo.append(med - q25)
            hi.append(q75 - med)
        colour = colours[idx % len(colours)]
        ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", linewidth=2.0, capsize=3, color=colour, label=f"{hop} hops")
    ax.axvline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xlabel("Offered cross-traffic load per stressed hop divided by link capacity")
    ax.set_ylabel("TVD from initial low-load distribution")
    ax.set_title(f"Multi-hop response curves for {base.DIST_LABELS.get(plot_dist, plot_dist)} delays")
    ax.grid(True, alpha=0.25)
    ax.legend()
    out = plots_dir / f"multi_hop_response_curves_{plot_dist}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_probe_loss_heatmap(loads: list[dict], plots_dir: Path) -> Path:
    if not loads:
        out = plots_dir / "multi_hop_probe_loss_heatmap.png"
        out.write_text("")
        return out
    hops = unique_hops(loads)
    ratios = sorted({round(base.numeric(row, "load_ratio"), 4) for row in loads if finite(base.numeric(row, "load_ratio"))})
    matrix = np.full((len(hops), len(ratios)), np.nan)
    for i, hop in enumerate(hops):
        for j, ratio in enumerate(ratios):
            vals = [
                base.numeric(row, "probe_loss_count", 0)
                for row in loads
                if int(float(row["hop_count"])) == hop and round(base.numeric(row, "load_ratio"), 4) == ratio
            ]
            matrix[i, j] = statistics.median(vals) if vals else math.nan

    fig, ax = plt.subplots(figsize=(12, 6.8))
    im = ax.imshow(matrix, aspect="auto", origin="lower", cmap="magma")
    ax.set_yticks(range(len(hops)))
    ax.set_yticklabels(hops)
    ax.set_xticks(range(len(ratios)))
    ax.set_xticklabels([f"{ratio:.2f}" for ratio in ratios], rotation=45, ha="right")
    ax.set_xlabel("Offered load per stressed hop divided by link capacity")
    ax.set_ylabel("Hop count")
    ax.set_title("Median receiver-visible probe losses")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Probe losses per run")
    out = plots_dir / "multi_hop_probe_loss_heatmap.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def make_plots(results_dir: Path, args: argparse.Namespace) -> None:
    estimates = base.read_csv(results_dir / "estimates.csv")
    responses = base.read_csv(results_dir / "response_results.csv")
    loads = base.read_csv(results_dir / "load_results.csv")
    drop_summary = base.read_csv(results_dir / "drop_detection_summary_by_hop.csv")
    plots_dir = results_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    mode = args.plot_mode if args.plot_mode in args.modes else args.modes[0]
    available_hops = unique_hops(estimates)
    selected_hops = [hop for hop in args.plot_hops if hop in available_hops]
    if not selected_hops:
        selected_hops = [available_hops[0], available_hops[len(available_hops) // 2], available_hops[-1]] if available_hops else []
    paths = [
        plot_capacity_brackets(estimates, plots_dir, mode),
        plot_distributional_vs_loss(estimates, drop_summary, plots_dir, mode),
        plot_detection_success(estimates, drop_summary, plots_dir, mode),
        plot_probe_loss_heatmap(loads, plots_dir),
    ]
    if selected_hops:
        plot_dist = args.plot_dist if args.plot_dist in args.dists else args.dists[0]
        paths.append(plot_response_curves(responses, plots_dir, mode, plot_dist, selected_hops))
    for path in paths:
        base.log(f"Wrote plot {base.rel(path)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-hop capacity response experiments.")
    parser.add_argument("--results-dir", default=str(base.REPO_ROOT / "delay-monitoring" / "results" / "multi-hop-capacity-response"))
    parser.add_argument("--hop-counts", nargs="+", type=int, default=list(range(2, 11)))
    parser.add_argument("--capacity-mbps", type=float, default=10.0)
    parser.add_argument("--bottleneck-hop", type=int, default=-1)
    parser.add_argument("--cross-traffic-scope", default="path", choices=["path", "all-links", "single-hop"])
    parser.add_argument("--cross-traffic-stop-time", type=float, default=-1.0)
    parser.add_argument("--dists", nargs="+", default=list(base.DISTRIBUTIONS), choices=list(base.DISTRIBUTIONS))
    parser.add_argument("--modes", nargs="+", default=["binary"], choices=["binary", "additive"])
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-ns3-build", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--start-load-fraction", type=float, default=0.05)
    parser.add_argument("--min-start-load-mbps", type=float, default=0.1)
    parser.add_argument("--load-multiplier", type=float, default=2.0)
    parser.add_argument("--max-load-factor", type=float, default=2.4)
    parser.add_argument("--binary-iterations", type=int, default=6)
    parser.add_argument("--additive-steps", type=int, default=16)
    parser.add_argument("--loss-sweep-ratios", nargs="+", type=float, default=[0.8, 0.85, 0.9, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05, 1.1, 1.2, 1.4, 1.6])
    parser.add_argument("--refine-width-fraction", type=float, default=0.025)
    parser.add_argument("--min-refine-width-mbps", type=float, default=0.05)
    parser.add_argument("--min-additive-step-mbps", type=float, default=0.05)
    parser.add_argument("--min-history-slopes", type=int, default=2)
    parser.add_argument("--rate-multiplier", type=float, default=5.0)
    parser.add_argument("--min-score-jump", type=float, default=0.10)
    parser.add_argument("--min-baseline-rate", type=float, default=1.0e-4)
    parser.add_argument("--link-data-rate", default="10Mbps")
    parser.add_argument("--link-delay", default="2ms")
    parser.add_argument("--queue-size", type=int, default=50)
    parser.add_argument("--queue-disc-type", default="ns3::FifoQueueDisc")
    parser.add_argument("--use-queue-disc", action="store_true")
    parser.add_argument("--probe-packet-size", type=int, default=64)
    parser.add_argument("--probe-interval-mean-ms", type=float, default=2.0)
    parser.add_argument("--max-packets-per-load", type=int, default=2000)
    parser.add_argument("--simulation-stop-time", type=float, default=15.0)
    parser.add_argument("--plot-mode", default="binary", choices=["binary", "additive"])
    parser.add_argument("--plot-dist", default="weibull", choices=list(base.DISTRIBUTIONS))
    parser.add_argument("--plot-hops", nargs="+", type=int, default=[2, 5, 10])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.hop_counts = sorted({max(1, hop) for hop in args.hop_counts})
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    config_path = results_dir / ("collect_config.json" if args.collect_only else "run_config.json")
    with config_path.open("w") as f:
        json.dump(vars(args), f, indent=2)

    if not args.collect_only and not args.skip_ns3_build:
        build_ns3()

    all_load_rows: list[dict] = []
    all_response_rows: list[dict] = []
    all_estimates: list[dict] = []

    if not args.collect_only:
        futures = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for hop_count in args.hop_counts:
                for dist in args.dists:
                    for seed in range(args.seed_start, args.seed_end + 1):
                        futures.append(executor.submit(run_one_case, hop_count, dist, seed, results_dir, args))
            for future in as_completed(futures):
                load_rows, response_rows, estimates = future.result()
                all_load_rows.extend(load_rows)
                all_response_rows.extend(response_rows)
                all_estimates.extend(estimates)

        all_load_rows.sort(key=lambda row: (int(row["hop_count"]), row["dist"], int(row["seed"]), base.numeric(row, "offered_load_mbps")))
        all_response_rows.sort(key=lambda row: (int(row["hop_count"]), row["mode"], row["dist"], int(row["seed"]), row["phase"], int(row["step"]), base.numeric(row, "offered_load_mbps")))
        all_estimates.sort(key=lambda row: (int(row["hop_count"]), row["mode"], row["dist"], int(row["seed"])))
        base.write_csv(results_dir / "load_results.csv", all_load_rows)
        base.write_csv(results_dir / "response_results.csv", all_response_rows)
        base.write_csv(results_dir / "estimates.csv", all_estimates)
    else:
        all_load_rows = base.read_csv(results_dir / "load_results.csv")
        all_response_rows = base.read_csv(results_dir / "response_results.csv")
        all_estimates = base.read_csv(results_dir / "estimates.csv")

    summarise(all_estimates, all_response_rows, all_load_rows, results_dir)
    make_plots(results_dir, args)
    base.log(f"Wrote multi-hop results to {base.rel(results_dir)}")


if __name__ == "__main__":
    main()
