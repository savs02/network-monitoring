"""
Adaptive capacity use-case experiment.

This script uses the NS-3 two-node, one-link model. It does not sample
delay distributions directly. For each offered-load level, NS-3 produces a
packet-delay stream. The monitor then applies the conservative adaptive
stopping setting selected in the previous evaluation:

    batch size B = 200
    stopping threshold theta = delta / 6
    delta = 0.05

The search algorithm does not use the configured link capacity and does not
know a reference delay distribution. The first load chosen by the exponential
search is only the first empirical reference state. The configured capacity is
used after the search, only to report evaluation error.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
NS3_DIR = REPO_ROOT / "ns-3.46"

os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "delay-monitoring" / "results" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


DELTA = 0.05
EPSILON = 0.05
BATCH_SIZE = 200
THETA = DELTA / 6.0
THETA_LABEL = "delta/6"

GRID_MIN = 0.0
GRID_MAX = 200.0
BIN_WIDTH = 1.0
GRID = np.arange(GRID_MIN + BIN_WIDTH / 2.0, GRID_MAX, BIN_WIDTH)
BIN_EDGES = np.arange(GRID_MIN, GRID_MAX + BIN_WIDTH, BIN_WIDTH)

DISTRIBUTIONS = ("normal", "lognormal", "weibull")
DIST_COLOURS = {
    "normal": "#2874a6",
    "lognormal": "#c0392b",
    "weibull": "#d68910",
}
DIST_LABELS = {
    "normal": "Normal",
    "lognormal": "Lognormal",
    "weibull": "Weibull",
}

SIMULATION = {
    "configured_capacity_mbps": 10.0,
    "link_data_rate": "10Mbps",
    "link_delay": "2ms",
    "queue_size_packets": 50,
    "probe_packet_size_bytes": 64,
    "probe_interval_mean_ms": 10.0,
    "max_packets_per_load": 4000,
}

print_lock = threading.Lock()


def sync_simulation(config: dict) -> None:
    if "configured_capacity_mbps" in config:
        SIMULATION["configured_capacity_mbps"] = float(config["configured_capacity_mbps"])
    if "link_data_rate" in config:
        SIMULATION["link_data_rate"] = str(config["link_data_rate"])
    if "link_delay" in config:
        SIMULATION["link_delay"] = str(config["link_delay"])
    if "queue_size" in config:
        SIMULATION["queue_size_packets"] = int(config["queue_size"])
    if "probe_packet_size" in config:
        SIMULATION["probe_packet_size_bytes"] = int(config["probe_packet_size"])
    if "probe_interval_mean_ms" in config:
        SIMULATION["probe_interval_mean_ms"] = float(config["probe_interval_mean_ms"])
    if "max_packets_per_load" in config:
        SIMULATION["max_packets_per_load"] = int(config["max_packets_per_load"])


def sync_simulation_from_args(args: argparse.Namespace) -> None:
    sync_simulation(vars(args))


def sync_simulation_from_results(results_dir: Path) -> None:
    config_path = results_dir / "run_config.json"
    if not config_path.exists():
        return
    with config_path.open() as f:
        sync_simulation(json.load(f))


@dataclass
class LoadState:
    dist: str
    seed: int
    phase: str
    step: int
    load_mbps: float
    raw_path: Path
    n_received: int
    n_stop: int
    capped: bool
    stop_between_tvd: float
    mean_delay_ms: float
    median_delay_ms: float
    p95_delay_ms: float
    p99_delay_ms: float
    masses: np.ndarray
    distribution_path: Path
    stopped_samples_path: Path
    trace_path: Path


def log(message: str) -> None:
    with print_lock:
        print(message, flush=True)


def load_label(load_mbps: float) -> str:
    return f"load_{load_mbps:08.3f}Mbps".replace(".", "p")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_rate_to_mbps(rate: str) -> float:
    value = rate.strip()
    if value.endswith("Gbps"):
        return float(value[:-4]) * 1000.0
    if value.endswith("Mbps"):
        return float(value[:-4])
    if value.endswith("Kbps"):
        return float(value[:-4]) / 1000.0
    if value.endswith("bps"):
        return float(value[:-3]) / 1.0e6
    return float(value) / 1.0e6


def tvd(p: np.ndarray, q: np.ndarray) -> float:
    return 0.5 * float(np.sum(np.abs(p - q)))


def histogram_masses(samples: np.ndarray) -> np.ndarray:
    if samples.size == 0:
        return np.ones(len(GRID), dtype=float) / len(GRID)
    counts, _ = np.histogram(samples, bins=BIN_EDGES)
    masses = counts.astype(float)
    total = float(masses.sum())
    if total <= 0.0:
        return np.ones(len(GRID), dtype=float) / len(GRID)
    return masses / total


def kde_masses(samples: np.ndarray) -> np.ndarray:
    if samples.size < 2 or float(np.std(samples)) < 1.0e-9:
        return histogram_masses(samples)
    try:
        kde = stats.gaussian_kde(samples, bw_method="scott")
        masses = kde(GRID) * BIN_WIDTH
        total = float(masses.sum())
        if not np.isfinite(total) or total <= 0.0:
            return histogram_masses(samples)
        return masses / total
    except Exception:
        return histogram_masses(samples)


def read_delay_samples(path: Path) -> np.ndarray:
    if not path.exists() or path.stat().st_size == 0:
        return np.array([], dtype=float)
    try:
        samples = np.loadtxt(path, delimiter=",", skiprows=1, usecols=1)
    except ValueError:
        return np.array([], dtype=float)
    samples = np.atleast_1d(samples).astype(float)
    samples = samples[np.isfinite(samples)]
    return samples


def write_distribution(path: Path, masses: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["delay_ms_grid", "probability_mass"])
        for x, p in zip(GRID, masses):
            writer.writerow([f"{x:.6f}", f"{p:.12g}"])


def write_stopped_samples(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seq_num", "delay_ms"])
        for i, value in enumerate(samples):
            writer.writerow([i, f"{float(value):.12g}"])


def write_trace(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        fieldnames = ["n", "between_tvd", "stopped"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def adaptive_stop(samples: np.ndarray) -> tuple[int, bool, float, np.ndarray, list[dict]]:
    if samples.size == 0:
        masses = kde_masses(samples)
        return 0, True, math.nan, masses, [{"n": 0, "between_tvd": math.nan, "stopped": False}]

    if samples.size < 2 * BATCH_SIZE:
        n = int(samples.size)
        masses = kde_masses(samples[:n])
        return n, True, math.nan, masses, [{"n": n, "between_tvd": math.nan, "stopped": False}]

    n = BATCH_SIZE
    previous = kde_masses(samples[:n])
    trace = [{"n": n, "between_tvd": math.nan, "stopped": False}]

    last_between = math.nan
    while n + BATCH_SIZE <= samples.size:
        n += BATCH_SIZE
        current = kde_masses(samples[:n])
        last_between = tvd(previous, current)
        stopped = last_between < THETA
        trace.append({"n": n, "between_tvd": last_between, "stopped": stopped})
        if stopped:
            return n, False, last_between, current, trace
        previous = current

    return n, True, last_between, previous, trace


def ns3_target(dist: str, seed: int, load_mbps: float, output_path: Path, args: argparse.Namespace) -> str:
    return (
        "scratch/delay-monitoring/single-hop-underlying-network "
        f"--delayDist={dist} "
        "--crossTrafficMode=true "
        f"--crossTrafficDataRate={load_mbps:.6f}Mbps "
        f"--linkDataRate={args.link_data_rate} "
        f"--linkDelay={args.link_delay} "
        f"--queueSize={args.queue_size} "
        f"--packetSize={args.probe_packet_size} "
        f"--intervalMean={args.probe_interval_mean_ms:.6f} "
        f"--numPackets={args.max_packets_per_load} "
        f"--RngRun={seed} "
        f"--outputFile={output_path}"
    )


def run_ns3(dist: str, seed: int, load_mbps: float, output_path: Path, args: argparse.Namespace) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.force and output_path.exists():
        existing = read_delay_samples(output_path)
        if existing.size >= BATCH_SIZE:
            return

    command = [
        "./ns3",
        "run",
        "--no-build",
        "--quiet",
        ns3_target(dist, seed, load_mbps, output_path, args),
    ]
    completed = subprocess.run(
        command,
        cwd=NS3_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        message = (
            f"NS-3 failed for dist={dist} seed={seed} load={load_mbps:.3f} Mbps\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )
        raise RuntimeError(message)


def evaluate_load(
    dist: str,
    seed: int,
    load_mbps: float,
    phase: str,
    step: int,
    results_dir: Path,
    args: argparse.Namespace,
    cache: dict[float, LoadState],
) -> LoadState:
    key = round(load_mbps, 6)
    if key in cache:
        return cache[key]

    label = load_label(load_mbps)
    raw_path = results_dir / "raw" / dist / f"seed_{seed:03d}" / label / "delay_samples.csv"
    run_ns3(dist, seed, load_mbps, raw_path, args)

    samples = read_delay_samples(raw_path)
    n_stop, capped, stop_between, masses, trace = adaptive_stop(samples)
    stopped = samples[:n_stop]

    processed_dir = results_dir / "processed" / dist / f"seed_{seed:03d}" / label
    distribution_path = processed_dir / "stopped_distribution.csv"
    stopped_samples_path = processed_dir / "stopped_samples.csv"
    trace_path = processed_dir / "stopping_trace.csv"

    write_distribution(distribution_path, masses)
    write_stopped_samples(stopped_samples_path, stopped)
    write_trace(trace_path, trace)

    if stopped.size > 0:
        mean_delay = float(np.mean(stopped))
        median_delay = float(np.median(stopped))
        p95 = float(np.percentile(stopped, 95))
        p99 = float(np.percentile(stopped, 99))
    else:
        mean_delay = median_delay = p95 = p99 = math.nan

    state = LoadState(
        dist=dist,
        seed=seed,
        phase=phase,
        step=step,
        load_mbps=load_mbps,
        raw_path=raw_path,
        n_received=int(samples.size),
        n_stop=int(n_stop),
        capped=bool(capped),
        stop_between_tvd=float(stop_between),
        mean_delay_ms=mean_delay,
        median_delay_ms=median_delay,
        p95_delay_ms=p95,
        p99_delay_ms=p99,
        masses=masses,
        distribution_path=distribution_path,
        stopped_samples_path=stopped_samples_path,
        trace_path=trace_path,
    )
    cache[key] = state
    log(
        f"  {dist:<9} seed={seed:03d} {phase:<11} load={load_mbps:6.3f} Mbps "
        f"n_stop={state.n_stop:5d} received={state.n_received:5d} capped={int(state.capped)}"
    )
    return state


def state_row(state: LoadState) -> dict:
    return {
        "dist": state.dist,
        "seed": state.seed,
        "phase": state.phase,
        "step": state.step,
        "offered_load_mbps": state.load_mbps,
        "n_received": state.n_received,
        "n_stop": state.n_stop,
        "capped": state.capped,
        "stop_between_tvd": state.stop_between_tvd,
        "mean_delay_ms": state.mean_delay_ms,
        "median_delay_ms": state.median_delay_ms,
        "p95_delay_ms": state.p95_delay_ms,
        "p99_delay_ms": state.p99_delay_ms,
        "raw_path": rel(state.raw_path),
        "distribution_path": rel(state.distribution_path),
        "stopped_samples_path": rel(state.stopped_samples_path),
        "trace_path": rel(state.trace_path),
    }


def comparison_row(
    dist: str,
    seed: int,
    phase: str,
    step: int,
    reference: LoadState,
    candidate: LoadState,
) -> dict:
    distance = tvd(reference.masses, candidate.masses)
    return {
        "dist": dist,
        "seed": seed,
        "phase": phase,
        "step": step,
        "reference_load_mbps": reference.load_mbps,
        "candidate_load_mbps": candidate.load_mbps,
        "tvd": distance,
        "significant": distance > DELTA,
        "reference_n_stop": reference.n_stop,
        "candidate_n_stop": candidate.n_stop,
    }


def run_one_seed(dist: str, seed: int, results_dir: Path, args: argparse.Namespace) -> tuple[list[dict], list[dict], dict]:
    cache: dict[float, LoadState] = {}
    load_rows: list[dict] = []
    comparisons: list[dict] = []

    low = evaluate_load(dist, seed, args.start_load_mbps, "exponential", 0, results_dir, args, cache)
    load_rows.append(state_row(low))
    first_load_mbps = low.load_mbps

    previous = low
    last_stable = low
    first_changed = None
    first_changed_tvd = math.nan

    current_load = args.start_load_mbps * args.load_multiplier
    exp_step = 1
    while current_load <= args.max_load_mbps + 1.0e-9:
        current = evaluate_load(dist, seed, current_load, "exponential", exp_step, results_dir, args, cache)
        load_rows.append(state_row(current))
        comp = comparison_row(dist, seed, "exponential", exp_step, previous, current)
        comparisons.append(comp)
        if comp["significant"]:
            first_changed = current
            first_changed_tvd = comp["tvd"]
            break
        last_stable = current
        previous = current
        current_load *= args.load_multiplier
        exp_step += 1

    if first_changed is None:
        estimate = {
            "dist": dist,
            "seed": seed,
            "status": "not_detected",
            "initial_load_mbps": first_load_mbps,
            "exponential_detection_load_mbps": math.nan,
            "exponential_detection_tvd": math.nan,
            "estimated_lower_mbps": last_stable.load_mbps,
            "estimated_upper_mbps": math.nan,
            "estimated_midpoint_mbps": math.nan,
            "estimated_threshold_mbps": math.nan,
            "configured_capacity_mbps": args.configured_capacity_mbps,
            "midpoint_error_mbps": math.nan,
            "threshold_error_mbps": math.nan,
            "relative_midpoint_error": math.nan,
            "relative_threshold_error": math.nan,
            "binary_iterations": 0,
        }
        return load_rows, comparisons, estimate

    lower = last_stable
    upper = first_changed
    binary_count = 0
    for binary_step in range(1, args.binary_iterations + 1):
        if upper.load_mbps - lower.load_mbps <= args.binary_min_width_mbps:
            break
        midpoint = 0.5 * (lower.load_mbps + upper.load_mbps)
        current = evaluate_load(dist, seed, midpoint, "binary", binary_step, results_dir, args, cache)
        load_rows.append(state_row(current))
        comp = comparison_row(dist, seed, "binary", binary_step, lower, current)
        comparisons.append(comp)
        binary_count += 1
        if comp["significant"]:
            upper = current
        else:
            lower = current

    midpoint_estimate = 0.5 * (lower.load_mbps + upper.load_mbps)
    threshold_estimate = upper.load_mbps
    capacity = args.configured_capacity_mbps
    estimate = {
        "dist": dist,
        "seed": seed,
        "status": "detected",
        "initial_load_mbps": first_load_mbps,
        "exponential_detection_load_mbps": first_changed.load_mbps,
        "exponential_detection_tvd": first_changed_tvd,
        "estimated_lower_mbps": lower.load_mbps,
        "estimated_upper_mbps": upper.load_mbps,
        "estimated_midpoint_mbps": midpoint_estimate,
        "estimated_threshold_mbps": threshold_estimate,
        "configured_capacity_mbps": capacity,
        "midpoint_error_mbps": midpoint_estimate - capacity,
        "threshold_error_mbps": threshold_estimate - capacity,
        "relative_midpoint_error": (midpoint_estimate - capacity) / capacity,
        "relative_threshold_error": (threshold_estimate - capacity) / capacity,
        "binary_iterations": binary_count,
    }
    return load_rows, comparisons, estimate


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_ns3() -> None:
    log("Building NS-3 single-hop target")
    output_path = REPO_ROOT / "delay-monitoring" / "results" / ".ns3_build_probe.csv"
    completed = subprocess.run(
        [
            "./ns3",
            "run",
            "--quiet",
            (
                "scratch/delay-monitoring/single-hop-underlying-network "
                "--delayDist=normal --numPackets=1 "
                f"--outputFile={output_path}"
            ),
        ],
        cwd=NS3_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "NS-3 build failed\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )


def load_distribution(path: Path) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(path)
    return df["delay_ms_grid"].to_numpy(dtype=float), df["probability_mass"].to_numpy(dtype=float)


def select_representative_seed(estimates: pd.DataFrame, dist: str) -> int:
    sub = estimates[(estimates["dist"] == dist) & (estimates["status"] == "detected")].copy()
    if sub.empty:
        sub = estimates[estimates["dist"] == dist].copy()
    target = float(sub["estimated_threshold_mbps"].median()) if sub["estimated_threshold_mbps"].notna().any() else float(sub["estimated_lower_mbps"].median())
    sub["distance"] = (sub["estimated_threshold_mbps"].fillna(sub["estimated_lower_mbps"]) - target).abs()
    return int(sub.sort_values(["distance", "seed"]).iloc[0]["seed"])


def plot_stopped_distributions(loads: pd.DataFrame, estimates: pd.DataFrame, plots_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for dist in DISTRIBUTIONS:
        if dist not in set(estimates["dist"]):
            continue
        seed = select_representative_seed(estimates, dist)
        est = estimates[(estimates["dist"] == dist) & (estimates["seed"] == seed)].iloc[0]
        candidates = [
            float(est["initial_load_mbps"]),
            float(est["estimated_lower_mbps"]),
            float(est["estimated_upper_mbps"]) if pd.notna(est["estimated_upper_mbps"]) else float(est["estimated_lower_mbps"]),
            float(est["exponential_detection_load_mbps"]) if pd.notna(est["exponential_detection_load_mbps"]) else float(est["estimated_lower_mbps"]),
        ]
        selected = []
        for value in candidates:
            if value not in selected:
                selected.append(value)

        fig, ax = plt.subplots(figsize=(9, 5.4))
        sub = loads[(loads["dist"] == dist) & (loads["seed"] == seed)].copy()
        for load in selected:
            nearest = sub.iloc[(sub["offered_load_mbps"] - load).abs().argsort()[:1]]
            if nearest.empty:
                continue
            row = nearest.iloc[0]
            x, p = load_distribution(REPO_ROOT / row["distribution_path"])
            ax.plot(x, p, linewidth=2.2, label=f"{row['offered_load_mbps']:.3f} Mbps, n={int(row['n_stop'])}")

        ax.set_title(f"{DIST_LABELS[dist]} stopped delay distributions, seed {seed}")
        ax.set_xlabel("Observed packet delay on 1 ms grid")
        ax.set_ylabel("Probability mass")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
        out = plots_dir / f"stopped_distributions_{dist}.png"
        fig.tight_layout()
        fig.savefig(out, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths.append(out)
    return paths


def plot_tvd_vs_load(comparisons: pd.DataFrame, plots_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for dist in list(DISTRIBUTIONS) + ["all"]:
        if dist == "all":
            sub = comparisons.copy()
            title = "All distributions"
            out_name = "tvd_vs_load_all.png"
        else:
            sub = comparisons[comparisons["dist"] == dist].copy()
            title = DIST_LABELS[dist]
            out_name = f"tvd_vs_load_{dist}.png"
        if sub.empty:
            continue

        fig, ax = plt.subplots(figsize=(9.5, 5.4))
        for name, group in sub.groupby("dist"):
            ax.scatter(
                group["candidate_load_mbps"],
                group["tvd"],
                s=18,
                alpha=0.20 if dist == "all" else 0.28,
                color=DIST_COLOURS.get(name, "#555555"),
                label=DIST_LABELS.get(name, name),
            )
            med = group.groupby("candidate_load_mbps")["tvd"].median().reset_index()
            med = med.sort_values("candidate_load_mbps")
            ax.plot(
                med["candidate_load_mbps"],
                med["tvd"],
                color=DIST_COLOURS.get(name, "#555555"),
                linewidth=2.4,
            )
        ax.axhline(DELTA, color="black", linestyle="--", linewidth=1.2, label=f"Delta = {DELTA}")
        ax.axvline(SIMULATION["configured_capacity_mbps"], color="grey", linestyle=":", linewidth=1.3, label="Configured capacity")
        ax.set_title(f"{title} total variation distance during load search")
        ax.set_xlabel("Candidate offered load in Mbps")
        ax.set_ylabel("Total variation distance")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
        out = plots_dir / out_name
        fig.tight_layout()
        fig.savefig(out, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths.append(out)
    return paths


def plot_search_process(comparisons: pd.DataFrame, estimates: pd.DataFrame, plots_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for dist in DISTRIBUTIONS:
        if dist not in set(estimates["dist"]):
            continue
        seed = select_representative_seed(estimates, dist)
        sub = comparisons[(comparisons["dist"] == dist) & (comparisons["seed"] == seed)].copy()
        if sub.empty:
            continue
        sub["order"] = range(1, len(sub) + 1)

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
        colours = sub["significant"].map({True: "#c0392b", False: "#2874a6"})
        axes[0].scatter(sub["order"], sub["candidate_load_mbps"], c=colours, s=70)
        axes[0].plot(sub["order"], sub["candidate_load_mbps"], color="#555555", alpha=0.5)
        axes[0].axhline(SIMULATION["configured_capacity_mbps"], color="black", linestyle=":", linewidth=1.2)
        axes[0].set_xlabel("Search comparison")
        axes[0].set_ylabel("Candidate load in Mbps")
        axes[0].set_title("Exponential and binary search loads")
        axes[0].grid(True, alpha=0.25)

        axes[1].scatter(sub["order"], sub["tvd"], c=colours, s=70)
        axes[1].plot(sub["order"], sub["tvd"], color="#555555", alpha=0.5)
        axes[1].axhline(DELTA, color="black", linestyle="--", linewidth=1.2)
        axes[1].set_xlabel("Search comparison")
        axes[1].set_ylabel("Total variation distance")
        axes[1].set_title("Distribution change test")
        axes[1].grid(True, alpha=0.25)

        fig.suptitle(f"{DIST_LABELS[dist]} search process, representative seed {seed}")
        fig.tight_layout()
        out = plots_dir / f"search_process_{dist}.png"
        fig.savefig(out, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths.append(out)
    return paths


def plot_capacity_summaries(loads: pd.DataFrame, comparisons: pd.DataFrame, estimates: pd.DataFrame, plots_dir: Path) -> list[Path]:
    paths: list[Path] = []
    detected = estimates[estimates["status"] == "detected"].copy()
    if detected.empty:
        return paths

    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    data = [detected[detected["dist"] == dist]["estimated_threshold_mbps"].dropna().to_numpy() for dist in DISTRIBUTIONS]
    ax.boxplot(data, labels=[DIST_LABELS[d] for d in DISTRIBUTIONS], patch_artist=True)
    ax.axhline(SIMULATION["configured_capacity_mbps"], color="black", linestyle="--", linewidth=1.3, label="Configured capacity")
    ax.set_ylabel("Estimated threshold in Mbps")
    ax.set_title("Estimated capacity threshold across 100 seeds")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    out = plots_dir / "estimated_capacity_by_distribution.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(out)

    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    data = [detected[detected["dist"] == dist]["threshold_error_mbps"].dropna().to_numpy() for dist in DISTRIBUTIONS]
    ax.boxplot(data, labels=[DIST_LABELS[d] for d in DISTRIBUTIONS], patch_artist=True)
    ax.axhline(0.0, color="black", linestyle="--", linewidth=1.3)
    ax.set_ylabel("Threshold error in Mbps")
    ax.set_title("Error against configured simulation capacity")
    ax.grid(True, axis="y", alpha=0.25)
    out = plots_dir / "capacity_error_by_distribution.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(out)

    fig, ax = plt.subplots(figsize=(9, 5.4))
    load_subset = loads[loads["phase"].isin(["exponential", "binary"])].copy()
    data = [load_subset[load_subset["dist"] == dist]["n_stop"].dropna().to_numpy() for dist in DISTRIBUTIONS]
    ax.boxplot(data, labels=[DIST_LABELS[d] for d in DISTRIBUTIONS], patch_artist=True)
    ax.set_ylabel("Stopped sample count")
    ax.set_title("Adaptive stopping sample counts by distribution")
    ax.grid(True, axis="y", alpha=0.25)
    out = plots_dir / "stopping_counts_by_distribution.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(out)

    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    first = comparisons[(comparisons["phase"] == "exponential") & (comparisons["significant"])].copy()
    first = first.sort_values(["dist", "seed", "step"]).groupby(["dist", "seed"], as_index=False).first()
    data = [first[first["dist"] == dist]["candidate_load_mbps"].dropna().to_numpy() for dist in DISTRIBUTIONS]
    ax.boxplot(data, labels=[DIST_LABELS[d] for d in DISTRIBUTIONS], patch_artist=True)
    ax.axhline(SIMULATION["configured_capacity_mbps"], color="black", linestyle="--", linewidth=1.3)
    ax.set_ylabel("First significant exponential load in Mbps")
    ax.set_title("Distribution-change detection points")
    ax.grid(True, axis="y", alpha=0.25)
    out = plots_dir / "detection_points_by_distribution.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(out)

    summary = (
        detected.groupby("dist")
        .agg(
            median_threshold_mbps=("estimated_threshold_mbps", "median"),
            q25_threshold_mbps=("estimated_threshold_mbps", lambda x: np.percentile(x.dropna(), 25)),
            q75_threshold_mbps=("estimated_threshold_mbps", lambda x: np.percentile(x.dropna(), 75)),
            median_error_mbps=("threshold_error_mbps", "median"),
        )
        .reindex(DISTRIBUTIONS)
    )
    x = np.arange(len(summary))
    fig, ax = plt.subplots(figsize=(9, 5.4))
    med = summary["median_threshold_mbps"].to_numpy()
    yerr = np.vstack([
        med - summary["q25_threshold_mbps"].to_numpy(),
        summary["q75_threshold_mbps"].to_numpy() - med,
    ])
    ax.bar(x, med, color=[DIST_COLOURS[d] for d in DISTRIBUTIONS], alpha=0.8)
    ax.errorbar(x, med, yerr=yerr, fmt="none", ecolor="black", capsize=5)
    ax.axhline(SIMULATION["configured_capacity_mbps"], color="black", linestyle="--", linewidth=1.3)
    ax.set_xticks(x)
    ax.set_xticklabels([DIST_LABELS[d] for d in DISTRIBUTIONS])
    ax.set_ylabel("Median threshold in Mbps")
    ax.set_title("Aggregate capacity comparison")
    ax.grid(True, axis="y", alpha=0.25)
    out = plots_dir / "aggregate_capacity_comparison.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(out)

    return paths


def write_summary_tables(loads: pd.DataFrame, comparisons: pd.DataFrame, estimates: pd.DataFrame, results_dir: Path) -> None:
    detected = estimates[estimates["status"] == "detected"].copy()
    if detected.empty:
        return

    summary = (
        detected.groupby("dist")
        .agg(
            seeds=("seed", "count"),
            median_lower_mbps=("estimated_lower_mbps", "median"),
            median_upper_mbps=("estimated_upper_mbps", "median"),
            median_threshold_mbps=("estimated_threshold_mbps", "median"),
            mean_threshold_mbps=("estimated_threshold_mbps", "mean"),
            q25_threshold_mbps=("estimated_threshold_mbps", lambda x: np.percentile(x.dropna(), 25)),
            q75_threshold_mbps=("estimated_threshold_mbps", lambda x: np.percentile(x.dropna(), 75)),
            median_threshold_error_mbps=("threshold_error_mbps", "median"),
            median_relative_threshold_error=("relative_threshold_error", "median"),
            median_binary_iterations=("binary_iterations", "median"),
        )
        .reset_index()
    )
    summary.to_csv(results_dir / "summary_by_distribution.csv", index=False)

    stop_summary = (
        loads.groupby("dist")
        .agg(
            load_evaluations=("offered_load_mbps", "count"),
            median_n_stop=("n_stop", "median"),
            q25_n_stop=("n_stop", lambda x: np.percentile(x.dropna(), 25)),
            q75_n_stop=("n_stop", lambda x: np.percentile(x.dropna(), 75)),
            cap_rate=("capped", "mean"),
            median_received=("n_received", "median"),
        )
        .reset_index()
    )
    stop_summary.to_csv(results_dir / "stopping_summary_by_distribution.csv", index=False)

    first = comparisons[(comparisons["phase"] == "exponential") & (comparisons["significant"])].copy()
    if not first.empty:
        first = first.sort_values(["dist", "seed", "step"]).groupby(["dist", "seed"], as_index=False).first()
        detection_summary = (
            first.groupby("dist")
            .agg(
                seeds=("seed", "count"),
                median_first_detection_mbps=("candidate_load_mbps", "median"),
                q25_first_detection_mbps=("candidate_load_mbps", lambda x: np.percentile(x.dropna(), 25)),
                q75_first_detection_mbps=("candidate_load_mbps", lambda x: np.percentile(x.dropna(), 75)),
                median_first_detection_tvd=("tvd", "median"),
            )
            .reset_index()
        )
        detection_summary.to_csv(results_dir / "detection_summary_by_distribution.csv", index=False)

    aggregate = {
        "seeds": int(detected["seed"].count()),
        "distributions": int(detected["dist"].nunique()),
        "configured_capacity_mbps": SIMULATION["configured_capacity_mbps"],
        "median_threshold_mbps": float(detected["estimated_threshold_mbps"].median()),
        "mean_threshold_mbps": float(detected["estimated_threshold_mbps"].mean()),
        "median_threshold_error_mbps": float(detected["threshold_error_mbps"].median()),
        "median_relative_threshold_error": float(detected["relative_threshold_error"].median()),
        "median_n_stop": float(loads["n_stop"].median()),
        "cap_rate": float(loads["capped"].mean()),
    }
    with (results_dir / "aggregate_summary.json").open("w") as f:
        json.dump(aggregate, f, indent=2)


def generate_plots(results_dir: Path) -> list[Path]:
    sync_simulation_from_results(results_dir)
    plots_dir = results_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    loads = pd.read_csv(results_dir / "load_results.csv")
    comparisons = pd.read_csv(results_dir / "comparisons.csv")
    estimates = pd.read_csv(results_dir / "seed_estimates.csv")

    paths: list[Path] = []
    paths.extend(plot_stopped_distributions(loads, estimates, plots_dir))
    paths.extend(plot_tvd_vs_load(comparisons, plots_dir))
    paths.extend(plot_search_process(comparisons, estimates, plots_dir))
    paths.extend(plot_capacity_summaries(loads, comparisons, estimates, plots_dir))
    return paths


def make_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the adaptive capacity use-case experiment.")
    parser.add_argument("--results-dir", default=str(REPO_ROOT / "delay-monitoring" / "results" / "use-case-adaptive-capacity"))
    parser.add_argument("--dists", nargs="+", default=list(DISTRIBUTIONS), choices=list(DISTRIBUTIONS))
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="Rerun NS-3 even when raw CSV files exist.")
    parser.add_argument("--start-load-mbps", type=float, default=0.5)
    parser.add_argument("--load-multiplier", type=float, default=2.0)
    parser.add_argument("--max-load-mbps", type=float, default=32.0)
    parser.add_argument("--binary-iterations", type=int, default=5)
    parser.add_argument("--binary-min-width-mbps", type=float, default=0.25)
    parser.add_argument("--configured-capacity-mbps", type=float, default=SIMULATION["configured_capacity_mbps"])
    parser.add_argument("--link-data-rate", default=SIMULATION["link_data_rate"])
    parser.add_argument("--link-delay", default=SIMULATION["link_delay"])
    parser.add_argument("--queue-size", type=int, default=SIMULATION["queue_size_packets"])
    parser.add_argument("--probe-packet-size", type=int, default=SIMULATION["probe_packet_size_bytes"])
    parser.add_argument("--probe-interval-mean-ms", type=float, default=SIMULATION["probe_interval_mean_ms"])
    parser.add_argument("--max-packets-per-load", type=int, default=SIMULATION["max_packets_per_load"])
    parser.add_argument("--skip-ns3-build", action="store_true")
    parser.add_argument("--plots-only", action="store_true")
    return parser.parse_args()


def save_config(args: argparse.Namespace, results_dir: Path) -> None:
    config = vars(args).copy()
    config.update(
        {
            "delta": DELTA,
            "epsilon": EPSILON,
            "batch_size": BATCH_SIZE,
            "theta": THETA,
            "theta_label": THETA_LABEL,
            "grid_min_ms": GRID_MIN,
            "grid_max_ms": GRID_MAX,
            "bin_width_ms": BIN_WIDTH,
            "note": "Configured capacity is used only after search for evaluation.",
        }
    )
    with (results_dir / "run_config.json").open("w") as f:
        json.dump(config, f, indent=2)


def run_experiment(args: argparse.Namespace) -> None:
    sync_simulation_from_args(args)
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    save_config(args, results_dir)

    if not args.skip_ns3_build:
        build_ns3()

    seeds = list(range(args.seed_start, args.seed_end + 1))
    tasks = [(dist, seed) for dist in args.dists for seed in seeds]
    log("Adaptive capacity use-case experiment")
    log(f"  distributions: {', '.join(args.dists)}")
    log(f"  seeds: {args.seed_start} to {args.seed_end} ({len(seeds)} per distribution)")
    log(f"  adaptive stopping: B={BATCH_SIZE}, theta={THETA_LABEL}, delta={DELTA}")
    log(f"  search loads: start={args.start_load_mbps} Mbps, multiplier={args.load_multiplier}")
    log(f"  results: {rel(results_dir)}")

    all_load_rows: list[dict] = []
    all_comparisons: list[dict] = []
    estimates: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(run_one_seed, dist, seed, results_dir, args): (dist, seed)
            for dist, seed in tasks
        }
        completed = 0
        for future in as_completed(futures):
            dist, seed = futures[future]
            load_rows, comparisons, estimate = future.result()
            all_load_rows.extend(load_rows)
            all_comparisons.extend(comparisons)
            estimates.append(estimate)
            completed += 1
            log(
                f"completed {completed:3d}/{len(tasks)}: {dist} seed={seed:03d} "
                f"status={estimate['status']} range=[{estimate['estimated_lower_mbps']:.3f}, "
                f"{estimate['estimated_upper_mbps'] if pd.notna(estimate['estimated_upper_mbps']) else math.nan:.3f}]"
            )

    load_path = results_dir / "load_results.csv"
    comparison_path = results_dir / "comparisons.csv"
    estimate_path = results_dir / "seed_estimates.csv"

    all_load_rows.sort(key=lambda r: (r["dist"], r["seed"], r["phase"], r["step"], r["offered_load_mbps"]))
    all_comparisons.sort(key=lambda r: (r["dist"], r["seed"], r["phase"], r["step"], r["candidate_load_mbps"]))
    estimates.sort(key=lambda r: (r["dist"], r["seed"]))

    write_csv(load_path, all_load_rows)
    write_csv(comparison_path, all_comparisons)
    write_csv(estimate_path, estimates)

    loads_df = pd.read_csv(load_path)
    comparisons_df = pd.read_csv(comparison_path)
    estimates_df = pd.read_csv(estimate_path)
    write_summary_tables(loads_df, comparisons_df, estimates_df, results_dir)

    plot_paths = generate_plots(results_dir)
    log(f"Generated {len(plot_paths)} plots in {rel(results_dir / 'plots')}")


def main() -> int:
    args = make_args()
    results_dir = Path(args.results_dir).resolve()
    if args.plots_only:
        plot_paths = generate_plots(results_dir)
        log(f"Generated {len(plot_paths)} plots in {rel(results_dir / 'plots')}")
        return 0
    run_experiment(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
