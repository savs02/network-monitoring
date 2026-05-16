"""
Observable capacity experiments.

The experiment uses only signals that are visible at the traffic endpoints:
probe packets sent and received, cross-traffic packets sent and received, and
delay distributions reconstructed from received probes after adaptive stopping.
Internal queue-disc drops are not used as a detection method.
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

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "delay-monitoring" / "results" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

import distributional_capacity_response as base


METHOD_LABELS = {
    "distribution_change": "Distribution change",
    "tvd_rate_change": "TVD rate change",
    "probe_loss": "Probe loss",
    "traffic_loss": "Traffic loss",
    "any_visible_loss": "Any visible loss",
}

METHOD_COLOURS = {
    "distribution_change": "#1f77b4",
    "tvd_rate_change": "#d62728",
    "probe_loss": "#4d4d4d",
    "traffic_loss": "#2ca02c",
    "any_visible_loss": "#9467bd",
}


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def cross_traffic_rate_mbps(load_mbps: float, args: argparse.Namespace) -> float:
    if args.cross_traffic_pattern == "bursty":
        return load_mbps * args.burst_rate_multiplier
    return load_mbps


def scenario_value(args: argparse.Namespace) -> str:
    return getattr(args, "scenario_label", "") or (
        "single_link" if args.topology == "single" else f"{args.topology}_{args.cross_traffic_scope}"
    )


def experiment_metadata(args: argparse.Namespace) -> dict:
    return {
        "scenario": scenario_value(args),
        "topology": args.topology,
        "hop_count": args.hop_count,
        "traffic_scope": args.cross_traffic_scope if args.topology == "multi" else "single-link",
        "traffic_pattern": args.cross_traffic_pattern,
        "burst_rate_multiplier": args.burst_rate_multiplier if args.cross_traffic_pattern == "bursty" else 1.0,
        "link_data_rate": args.link_data_rate,
        "link_data_rates": args.link_data_rates if args.topology == "multi" else "",
        "bottleneck_hop": args.bottleneck_hop if args.topology == "multi" else -1,
    }


def observable_ns3_target(dist: str, seed: int, load_mbps: float, raw_path: Path, drop_path: Path, args: argparse.Namespace) -> str:
    offered_rate_mbps = cross_traffic_rate_mbps(load_mbps, args)
    common = (
        f"--delayDist={dist} "
        f"--crossTrafficDataRate={offered_rate_mbps:.6f}Mbps "
        f"--crossTrafficStopTime={args.cross_traffic_stop_time:.6f} "
        f"--crossTrafficPattern={args.cross_traffic_pattern} "
        f"--crossTrafficOnTime={args.cross_traffic_on_time} "
        f"--crossTrafficOffTime={args.cross_traffic_off_time} "
        f"--linkDataRate={args.link_data_rate} "
        f"--linkDelay={args.link_delay} "
        f"--queueSize={args.queue_size} "
        f"--queueDiscType={args.queue_disc_type} "
        f"--useQueueDisc={bool_text(args.use_queue_disc)} "
        f"--packetSize={args.probe_packet_size} "
        f"--intervalMean={args.probe_interval_mean_ms:.6f} "
        f"--numPackets={args.max_packets_per_load} "
        f"--simulationStopTime={args.simulation_stop_time:.6f} "
        f"--RngRun={seed} "
        f"--outputFile={raw_path} "
        f"--dropStatsFile={drop_path}"
    )
    if args.topology == "single":
        return "scratch/delay-monitoring/single-hop-underlying-network --crossTrafficMode=true " + common

    return (
        "scratch/delay-monitoring-multihop/multi-hop-capacity-network "
        f"--hopCount={args.hop_count} "
        f"--crossTrafficScope={args.cross_traffic_scope} "
        f"--bottleneckHop={args.bottleneck_hop} "
        f"--linkDataRates={args.link_data_rates} "
        + common
    )


base.ns3_target = observable_ns3_target


def build_targets(args: argparse.Namespace) -> None:
    targets = ["scratch/delay-monitoring/single-hop-underlying-network"]
    if args.topology == "multi":
        targets.append("scratch/delay-monitoring-multihop/multi-hop-capacity-network")
    for target in targets:
        base.log(f"Building NS-3 target {target}")
        completed = subprocess.run(
            ["./ns3", "build", target],
            cwd=base.NS3_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"NS-3 build failed for {target}\n"
                f"stdout:\n{completed.stdout[-4000:]}\n"
                f"stderr:\n{completed.stderr[-4000:]}"
            )


def additive_loads(capacity_mbps: float, args: argparse.Namespace) -> list[float]:
    start = max(args.min_start_load_mbps, capacity_mbps * args.start_load_fraction)
    stop = capacity_mbps * args.max_load_factor
    step = max(args.min_load_step_mbps, capacity_mbps * args.load_step_fraction)
    values = []
    current = start
    while current <= stop + 1.0e-9:
        values.append(round(current, 6))
        current += step
    for ratio in (0.9, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05):
        value = round(capacity_mbps * ratio, 6)
        if start <= value <= stop and value not in values:
            values.append(value)
    return sorted(values)


def finite(value: float) -> bool:
    return np.isfinite(float(value))


def ratio_or_nan(state: base.LoadState | None) -> float:
    return state.load_mbps / state.capacity_mbps if state else math.nan


def analyse_states(states: list[base.LoadState], args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    ordered = sorted(states, key=lambda state: state.load_mbps)
    if not ordered:
        return [], []
    baseline = ordered[0]
    previous = None
    previous_score = math.nan
    slopes: list[float] = []
    detail_rows: list[dict] = []

    first_distribution_change: base.LoadState | None = None
    first_rate_change: base.LoadState | None = None
    first_probe_loss: base.LoadState | None = None
    first_traffic_loss: base.LoadState | None = None
    first_any_loss: base.LoadState | None = None
    meta = experiment_metadata(args)

    for state in ordered:
        score = base.tvd(state.masses, baseline.masses)
        previous_tvd = base.tvd(state.masses, previous.masses) if previous else math.nan
        score_delta = score - previous_score if previous else math.nan
        load_delta = state.load_mbps - previous.load_mbps if previous else math.nan
        slope = max(0.0, score_delta / load_delta) if previous and load_delta > 0 else math.nan

        usable_slopes = [value for value in slopes if finite(value)]
        baseline_rate = statistics.median(usable_slopes) if len(usable_slopes) >= args.min_history_slopes else math.nan
        denom = max(baseline_rate, args.min_baseline_rate) if finite(baseline_rate) else math.nan
        rate_ratio = slope / denom if finite(slope) and finite(denom) and denom > 0 else math.nan
        accelerated = (
            finite(score_delta)
            and finite(rate_ratio)
            and score_delta >= args.min_score_jump
            and rate_ratio >= args.rate_multiplier
        )

        if previous and first_distribution_change is None and score >= args.change_threshold:
            first_distribution_change = state
        if first_rate_change is None and accelerated:
            first_rate_change = state
        if first_probe_loss is None and state.drops.probe_loss_count > 0:
            first_probe_loss = state
        if first_traffic_loss is None and state.drops.cross_traffic_loss_count > 0:
            first_traffic_loss = state
        if first_any_loss is None and (state.drops.probe_loss_count > 0 or state.drops.cross_traffic_loss_count > 0):
            first_any_loss = state

        row = base.state_row(state)
        row.update(meta)
        row.update({
            "tvd_from_baseline": score,
            "tvd_from_previous_load": previous_tvd,
            "tvd_score_delta": score_delta,
            "tvd_response_rate": slope,
            "tvd_baseline_rate": baseline_rate,
            "tvd_rate_ratio": rate_ratio,
            "tvd_rate_accelerated": accelerated,
        })
        detail_rows.append(row)

        if finite(slope):
            slopes.append(slope)
        previous = state
        previous_score = score

    method_states = {
        "distribution_change": first_distribution_change,
        "tvd_rate_change": first_rate_change,
        "probe_loss": first_probe_loss,
        "traffic_loss": first_traffic_loss,
        "any_visible_loss": first_any_loss,
    }
    result_rows = []
    for method, state in method_states.items():
        result = {
            "capacity_mbps": baseline.capacity_mbps,
            "dist": baseline.dist,
            "seed": baseline.seed,
            "method": method,
            "detected": state is not None,
            "detection_load_mbps": state.load_mbps if state else math.nan,
            "detection_load_ratio": ratio_or_nan(state),
            "probe_loss_count_at_detection": state.drops.probe_loss_count if state else math.nan,
            "traffic_loss_count_at_detection": state.drops.cross_traffic_loss_count if state else math.nan,
            "tvd_from_baseline_at_detection": base.tvd(state.masses, baseline.masses) if state else math.nan,
            "max_probe_loss_count": max((s.drops.probe_loss_count for s in ordered), default=0),
            "max_traffic_loss_count": max((s.drops.cross_traffic_loss_count for s in ordered), default=0),
            "max_tvd_from_baseline": max((base.tvd(s.masses, baseline.masses) for s in ordered), default=math.nan),
            "load_evaluations": len(ordered),
        }
        result.update(meta)
        result_rows.append(result)
    return detail_rows, result_rows


def run_one_case(hop_count: int, dist: str, seed: int, results_dir: Path, args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    local_args = argparse.Namespace(**vars(args))
    local_args.hop_count = hop_count
    local_args.configured_capacity_mbps = args.capacity_mbps
    local_args.link_data_rate = f"{base.fmt_float(args.capacity_mbps)}Mbps"
    if args.topology == "multi" and args.link_data_rates:
        rates = [rate.strip() for rate in args.link_data_rates.split(",") if rate.strip()]
        if len(rates) != hop_count:
            raise ValueError("--link-data-rates must contain exactly one rate per hop")
    case_dir = results_dir / (f"hop_{hop_count:02d}" if args.topology == "multi" else "single_hop")

    cache: dict[float, base.LoadState] = {}
    states = [
        base.evaluate_load(dist, seed, args.capacity_mbps, load_mbps, case_dir, local_args, cache)
        for load_mbps in additive_loads(args.capacity_mbps, args)
    ]
    return analyse_states(states, local_args)


def group_by(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    return groups


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


def summarise(results: list[dict], details: list[dict], results_dir: Path) -> None:
    summary = []
    for key, rows in sorted(group_by(results, ("scenario", "topology", "hop_count", "traffic_scope", "traffic_pattern", "link_data_rates", "bottleneck_hop", "method")).items()):
        scenario, topology, hop_count, traffic_scope, traffic_pattern, link_data_rates, bottleneck_hop, method = key
        summary.append({
            "scenario": scenario,
            "topology": topology,
            "hop_count": hop_count,
            "traffic_scope": traffic_scope,
            "traffic_pattern": traffic_pattern,
            "link_data_rates": link_data_rates,
            "bottleneck_hop": bottleneck_hop,
            "method": method,
            "runs": len(rows),
            "detected_rate": sum(1 for row in rows if str(row["detected"]).lower() == "true") / len(rows),
            "median_detection_load_ratio": median(numeric(row, "detection_load_ratio") for row in rows),
            "q25_detection_load_ratio": percentile((numeric(row, "detection_load_ratio") for row in rows), 25),
            "q75_detection_load_ratio": percentile((numeric(row, "detection_load_ratio") for row in rows), 75),
            "median_probe_loss_at_detection": median(numeric(row, "probe_loss_count_at_detection") for row in rows),
            "median_traffic_loss_at_detection": median(numeric(row, "traffic_loss_count_at_detection") for row in rows),
            "median_tvd_at_detection": median(numeric(row, "tvd_from_baseline_at_detection") for row in rows),
        })

    by_distribution = []
    for key, rows in sorted(group_by(results, ("scenario", "topology", "hop_count", "dist", "method")).items()):
        scenario, topology, hop_count, dist, method = key
        by_distribution.append({
            "scenario": scenario,
            "topology": topology,
            "hop_count": hop_count,
            "dist": dist,
            "method": method,
            "runs": len(rows),
            "detected_rate": sum(1 for row in rows if str(row["detected"]).lower() == "true") / len(rows),
            "median_detection_load_ratio": median(numeric(row, "detection_load_ratio") for row in rows),
        })

    base.write_csv(results_dir / "summary_by_method.csv", summary)
    base.write_csv(results_dir / "summary_by_distribution.csv", by_distribution)

    loss_by_load = []
    for key, rows in sorted(group_by(details, ("scenario", "topology", "hop_count", "traffic_scope", "traffic_pattern", "load_ratio")).items(), key=lambda item: (item[0][0], item[0][1], int(float(item[0][2])), float(item[0][5]))):
        scenario, topology, hop_count, traffic_scope, traffic_pattern, load_ratio = key
        loss_by_load.append({
            "scenario": scenario,
            "topology": topology,
            "hop_count": hop_count,
            "traffic_scope": traffic_scope,
            "traffic_pattern": traffic_pattern,
            "load_ratio": load_ratio,
            "median_probe_loss_count": median(numeric(row, "probe_loss_count") for row in rows),
            "median_traffic_loss_count": median(numeric(row, "cross_traffic_loss_count") for row in rows),
            "median_tvd_from_baseline": median(numeric(row, "tvd_from_baseline") for row in rows),
        })
    base.write_csv(results_dir / "summary_by_load.csv", loss_by_load)


def make_plots(results_dir: Path, args: argparse.Namespace) -> None:
    results = base.read_csv(results_dir / "method_results.csv")
    details = base.read_csv(results_dir / "load_results.csv")
    plots_dir = results_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    for method in METHOD_LABELS:
        rows = [row for row in results if row["method"] == method and str(row["detected"]).lower() == "true"]
        if not rows:
            continue
        groups = group_by(rows, ("hop_count",))
        xs, ys, lo, hi = [], [], [], []
        for (hop,), sub in sorted(groups.items(), key=lambda item: int(float(item[0][0]))):
            vals = [numeric(row, "detection_load_ratio") for row in sub]
            med = median(vals)
            xs.append(int(float(hop)))
            ys.append(med)
            lo.append(med - percentile(vals, 25))
            hi.append(percentile(vals, 75) - med)
        ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", linewidth=2.0, capsize=3, label=METHOD_LABELS[method], color=METHOD_COLOURS[method])
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured link capacity")
    ax.set_xlabel("Hop count")
    ax.set_ylabel("Detection load divided by configured link capacity")
    ax.set_title("Observable capacity detection mechanisms")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=9)
    out = plots_dir / "observable_detection_by_method.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)

    fig, ax1 = plt.subplots(figsize=(11.5, 6.5))
    selected_hop = args.plot_hop if args.topology == "multi" else 1
    selected = [
        row for row in details
        if int(float(row["hop_count"])) == selected_hop
        and row["dist"] == args.plot_dist
    ]
    grouped = group_by(selected, ("load_ratio",))
    xs, tvd_vals, probe_vals, traffic_vals = [], [], [], []
    for (ratio,), rows in sorted(grouped.items(), key=lambda item: float(item[0][0])):
        xs.append(float(ratio))
        tvd_vals.append(median(numeric(row, "tvd_from_baseline") for row in rows))
        probe_vals.append(median(numeric(row, "probe_loss_count") for row in rows))
        traffic_vals.append(median(numeric(row, "cross_traffic_loss_count") for row in rows))
    ax1.plot(xs, tvd_vals, marker="o", linewidth=2.0, color="#1f77b4", label="TVD from baseline")
    ax1.axhline(args.change_threshold, color="#1f77b4", linestyle=":", linewidth=1.4, label="Distribution-change threshold")
    ax1.axvline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax1.set_xlabel("Offered load divided by configured link capacity")
    ax1.set_ylabel("TVD")
    ax2 = ax1.twinx()
    ax2.plot(xs, probe_vals, marker="s", linewidth=1.8, color="#4d4d4d", label="Probe losses")
    ax2.plot(xs, traffic_vals, marker="^", linewidth=1.8, color="#2ca02c", label="Traffic losses")
    ax2.set_ylabel("Median lost packets")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
    ax1.grid(True, alpha=0.25)
    ax1.set_title(f"Observable TVD and packet loss for {base.DIST_LABELS.get(args.plot_dist, args.plot_dist)} delays")
    out = plots_dir / f"observable_tvd_loss_curve_{args.plot_dist}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)

    base.log(f"Wrote plots to {base.rel(plots_dir)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run observable capacity experiments.")
    parser.add_argument("--topology", choices=["single", "multi"], default="single")
    parser.add_argument("--results-dir", default=str(REPO_ROOT / "delay-monitoring" / "results" / "observable-capacity"))
    parser.add_argument("--capacity-mbps", type=float, default=10.0)
    parser.add_argument("--hop-counts", nargs="+", type=int, default=list(range(2, 11)))
    parser.add_argument("--cross-traffic-scope", choices=["path", "all-links", "single-hop"], default="path")
    parser.add_argument("--cross-traffic-stop-time", type=float, default=-1.0)
    parser.add_argument("--cross-traffic-pattern", choices=["constant", "bursty"], default="constant")
    parser.add_argument("--cross-traffic-on-time", default="ns3::ConstantRandomVariable[Constant=1]")
    parser.add_argument("--cross-traffic-off-time", default="ns3::ConstantRandomVariable[Constant=0]")
    parser.add_argument("--burst-rate-multiplier", type=float, default=2.0)
    parser.add_argument("--link-data-rates", default="")
    parser.add_argument("--scenario-label", default="")
    parser.add_argument("--bottleneck-hop", type=int, default=-1)
    parser.add_argument("--dists", nargs="+", choices=list(base.DISTRIBUTIONS), default=list(base.DISTRIBUTIONS))
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-ns3-build", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--start-load-fraction", type=float, default=0.05)
    parser.add_argument("--min-start-load-mbps", type=float, default=0.5)
    parser.add_argument("--max-load-factor", type=float, default=1.3)
    parser.add_argument("--load-step-fraction", type=float, default=0.025)
    parser.add_argument("--min-load-step-mbps", type=float, default=0.25)
    parser.add_argument("--change-threshold", type=float, default=base.DELTA)
    parser.add_argument("--min-history-slopes", type=int, default=2)
    parser.add_argument("--rate-multiplier", type=float, default=5.0)
    parser.add_argument("--min-score-jump", type=float, default=0.05)
    parser.add_argument("--min-baseline-rate", type=float, default=1.0e-4)
    parser.add_argument("--link-delay", default="2ms")
    parser.add_argument("--queue-size", type=int, default=50)
    parser.add_argument("--queue-disc-type", default="ns3::FifoQueueDisc")
    parser.add_argument("--use-queue-disc", action="store_true")
    parser.add_argument("--probe-packet-size", type=int, default=64)
    parser.add_argument("--probe-interval-mean-ms", type=float, default=2.0)
    parser.add_argument("--max-packets-per-load", type=int, default=2000)
    parser.add_argument("--simulation-stop-time", type=float, default=15.0)
    parser.add_argument("--plot-dist", choices=list(base.DISTRIBUTIONS), default="weibull")
    parser.add_argument("--plot-hop", type=int, default=5)
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.quiet_progress:
        base.log = lambda message: None
    args.link_data_rate = f"{base.fmt_float(args.capacity_mbps)}Mbps"
    args.hop_counts = [1] if args.topology == "single" else sorted({max(2, hop) for hop in args.hop_counts})

    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / ("collect_config.json" if args.collect_only else "run_config.json")).open("w") as f:
        json.dump(vars(args), f, indent=2)

    if not args.collect_only and not args.skip_ns3_build:
        build_targets(args)

    if args.collect_only:
        load_rows = base.read_csv(results_dir / "load_results.csv")
        method_rows = base.read_csv(results_dir / "method_results.csv")
    else:
        load_rows: list[dict] = []
        method_rows: list[dict] = []
        futures = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for hop_count in args.hop_counts:
                for dist in args.dists:
                    for seed in range(args.seed_start, args.seed_end + 1):
                        futures.append(executor.submit(run_one_case, hop_count, dist, seed, results_dir, args))
            for future in as_completed(futures):
                details, methods = future.result()
                load_rows.extend(details)
                method_rows.extend(methods)

        load_rows.sort(key=lambda row: (int(float(row["hop_count"])), row["dist"], int(row["seed"]), numeric(row, "offered_load_mbps")))
        method_rows.sort(key=lambda row: (int(float(row["hop_count"])), row["dist"], int(row["seed"]), row["method"]))
        base.write_csv(results_dir / "load_results.csv", load_rows)
        base.write_csv(results_dir / "method_results.csv", method_rows)

    summarise(method_rows, load_rows, results_dir)
    make_plots(results_dir, args)
    base.log(f"Wrote observable capacity results to {base.rel(results_dir)}")


if __name__ == "__main__":
    main()
