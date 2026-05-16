"""
Distributional response-rate capacity experiments.

This script evaluates the capacity use case with a stronger criterion than
first distributional change. For each offered load r_i, it builds a stopped
delay distribution P_i using the conservative adaptive stopping setting. It
then computes a cumulative distributional score

    S_i = TVD(P_i, P_0)

against the initial low-load distribution. Capacity is bracketed when the
response rate

    (S_i - S_{i-1}) / (r_i - r_{i-1})

accelerates relative to the lower-load baseline. Two refinement strategies are
implemented: binary refinement inside the slow-start bracket and additive
refinement from the lower edge of the bracket.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
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
from scipy import stats


DELTA = 0.05
BATCH_SIZE = 200
THETA = DELTA / 6.0

GRID_MIN = 0.0
GRID_MAX = 200.0
BIN_WIDTH = 1.0
GRID = np.arange(GRID_MIN + BIN_WIDTH / 2.0, GRID_MAX, BIN_WIDTH)
BIN_EDGES = np.arange(GRID_MIN, GRID_MAX + BIN_WIDTH, BIN_WIDTH)

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
MODE_LABELS = {
    "binary": "Slow start and binary",
    "additive": "Slow start and additive",
}
MODE_COLOURS = {
    "binary": "#1f77b4",
    "additive": "#d62728",
}

print_lock = threading.Lock()


@dataclass
class DropStats:
    sent_probe_packets: int
    received_probe_packets: int
    probe_loss_count: int
    queue_drop_count: int
    cross_traffic_tx_packets: int = 0
    cross_traffic_rx_packets: int = 0
    cross_traffic_loss_count: int = 0
    cross_traffic_tx_bytes: int = 0
    qdisc_drop_count: int = 0
    bottleneck_qdisc_drop_count: int = 0
    qdisc_drop_before_enqueue_count: int = 0
    qdisc_drop_after_dequeue_count: int = 0
    qdisc_mark_count: int = 0
    qdisc_received_packets: int = 0
    qdisc_sent_packets: int = 0
    cross_traffic_rx_bytes: int = 0
    active_cross_traffic_flows: int = 0
    use_queue_disc: int = 0
    max_hop_qdisc_drop_count: int = 0
    max_hop_qdisc_drop_hop: int = 0


@dataclass
class LoadState:
    dist: str
    seed: int
    capacity_mbps: float
    load_mbps: float
    raw_path: Path
    drop_stats_path: Path
    distribution_path: Path
    stopped_samples_path: Path
    trace_path: Path
    n_received: int
    n_stop: int
    capped: bool
    stop_between_tvd: float
    mean_delay_ms: float
    median_delay_ms: float
    p95_delay_ms: float
    p99_delay_ms: float
    masses: np.ndarray
    drops: DropStats


@dataclass
class ResponsePoint:
    state: LoadState
    score: float
    slope: float
    baseline_rate: float
    rate_ratio: float
    score_delta: float
    accelerated: bool


def log(message: str) -> None:
    with print_lock:
        print(message, flush=True)


def fmt_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def capacity_label(capacity_mbps: float) -> str:
    return f"cap_{fmt_float(capacity_mbps).replace('.', 'p')}Mbps"


def load_label(load_mbps: float) -> str:
    return f"load_{load_mbps:09.4f}Mbps".replace(".", "p")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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


def read_drop_stats(path: Path, sent_packets: int, received_packets: int) -> DropStats:
    if not path.exists() or path.stat().st_size == 0:
        return DropStats(
            sent_probe_packets=sent_packets,
            received_probe_packets=received_packets,
            probe_loss_count=max(0, sent_packets - received_packets),
            queue_drop_count=0,
        )
    with path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return DropStats(sent_packets, received_packets, max(0, sent_packets - received_packets), 0)
    row = rows[0]
    return DropStats(
        sent_probe_packets=int(float(row.get("sent_probe_packets", sent_packets))),
        received_probe_packets=int(float(row.get("received_probe_packets", received_packets))),
        probe_loss_count=int(float(row.get("probe_loss_count", max(0, sent_packets - received_packets)))),
        queue_drop_count=int(float(row.get("queue_drop_count", 0))),
        cross_traffic_tx_packets=int(float(row.get("cross_traffic_tx_packets", 0))),
        cross_traffic_rx_packets=int(float(row.get("cross_traffic_rx_packets", 0))),
        cross_traffic_loss_count=int(float(row.get("cross_traffic_loss_count", 0))),
        cross_traffic_tx_bytes=int(float(row.get("cross_traffic_tx_bytes", 0))),
        qdisc_drop_count=int(float(row.get("qdisc_drop_count", 0))),
        bottleneck_qdisc_drop_count=int(float(row.get("bottleneck_qdisc_drop_count", 0))),
        qdisc_drop_before_enqueue_count=int(float(row.get("qdisc_drop_before_enqueue_count", 0))),
        qdisc_drop_after_dequeue_count=int(float(row.get("qdisc_drop_after_dequeue_count", 0))),
        qdisc_mark_count=int(float(row.get("qdisc_mark_count", 0))),
        qdisc_received_packets=int(float(row.get("qdisc_received_packets", 0))),
        qdisc_sent_packets=int(float(row.get("qdisc_sent_packets", 0))),
        cross_traffic_rx_bytes=int(float(row.get("cross_traffic_rx_bytes", 0))),
        active_cross_traffic_flows=int(float(row.get("active_cross_traffic_flows", 0))),
        use_queue_disc=int(float(row.get("use_queue_disc", 0))),
        max_hop_qdisc_drop_count=int(float(row.get("max_hop_qdisc_drop_count", row.get("bottleneck_qdisc_drop_count", 0)))),
        max_hop_qdisc_drop_hop=int(float(row.get("max_hop_qdisc_drop_hop", row.get("bottleneck_hop", 0)))),
    )


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
        writer = csv.DictWriter(f, fieldnames=["n", "between_tvd", "stopped"])
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


def ns3_target(dist: str, seed: int, load_mbps: float, raw_path: Path, drop_path: Path, args: argparse.Namespace) -> str:
    return (
        "scratch/delay-monitoring/single-hop-underlying-network "
        f"--delayDist={dist} "
        "--crossTrafficMode=true "
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
        f"--simulationStopTime={getattr(args, 'simulation_stop_time', 15.0):.6f} "
        f"--RngRun={seed} "
        f"--outputFile={raw_path} "
        f"--dropStatsFile={drop_path}"
    )


def run_ns3(dist: str, seed: int, load_mbps: float, raw_path: Path, drop_path: Path, args: argparse.Namespace) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    drop_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.force and raw_path.exists() and drop_path.exists():
        existing = read_delay_samples(raw_path)
        if existing.size >= BATCH_SIZE:
            return

    command = [
        "./ns3",
        "run",
        "--no-build",
        "--quiet",
        ns3_target(dist, seed, load_mbps, raw_path, drop_path, args),
    ]
    completed = subprocess.run(
        command,
        cwd=NS3_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"NS-3 failed for dist={dist} seed={seed} load={load_mbps:.4f} Mbps\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )


def evaluate_load(
    dist: str,
    seed: int,
    capacity_mbps: float,
    load_mbps: float,
    results_dir: Path,
    args: argparse.Namespace,
    cache: dict[float, LoadState],
) -> LoadState:
    key = round(load_mbps, 6)
    if key in cache:
        return cache[key]

    cap_dir = results_dir / capacity_label(capacity_mbps)
    label = load_label(load_mbps)
    raw_path = cap_dir / "raw" / dist / f"seed_{seed:03d}" / label / "delay_samples.csv"
    drop_path = cap_dir / "raw" / dist / f"seed_{seed:03d}" / label / "drop_stats.csv"
    run_ns3(dist, seed, load_mbps, raw_path, drop_path, args)

    samples = read_delay_samples(raw_path)
    n_stop, capped, stop_between, masses, trace = adaptive_stop(samples)
    stopped = samples[:n_stop]

    processed_dir = cap_dir / "processed" / dist / f"seed_{seed:03d}" / label
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

    drops = read_drop_stats(drop_path, args.max_packets_per_load, int(samples.size))
    state = LoadState(
        dist=dist,
        seed=seed,
        capacity_mbps=capacity_mbps,
        load_mbps=load_mbps,
        raw_path=raw_path,
        drop_stats_path=drop_path,
        distribution_path=distribution_path,
        stopped_samples_path=stopped_samples_path,
        trace_path=trace_path,
        n_received=int(samples.size),
        n_stop=int(n_stop),
        capped=bool(capped),
        stop_between_tvd=float(stop_between),
        mean_delay_ms=mean_delay,
        median_delay_ms=median_delay,
        p95_delay_ms=p95,
        p99_delay_ms=p99,
        masses=masses,
        drops=drops,
    )
    cache[key] = state
    log(
        f"  cap={capacity_mbps:g} {dist:<9} seed={seed:03d} load={load_mbps:8.4f} "
        f"n_stop={state.n_stop:4d} ploss={state.drops.probe_loss_count:4d} "
        f"tloss={state.drops.cross_traffic_loss_count:5d}"
    )
    return state


def sorted_points(points: list[ResponsePoint]) -> list[ResponsePoint]:
    return sorted(points, key=lambda point: point.state.load_mbps)


def slopes_from_points(points: list[ResponsePoint]) -> list[float]:
    ordered = sorted_points(points)
    slopes: list[float] = []
    for prev, cur in zip(ordered, ordered[1:]):
        delta_load = cur.state.load_mbps - prev.state.load_mbps
        if delta_load <= 0.0:
            continue
        slopes.append(max(0.0, (cur.score - prev.score) / delta_load))
    return slopes


def make_response_point(
    state: LoadState,
    baseline: LoadState,
    previous_points: list[ResponsePoint],
    args: argparse.Namespace,
) -> ResponsePoint:
    score = tvd(state.masses, baseline.masses)
    if not previous_points:
        return ResponsePoint(state, score, math.nan, math.nan, math.nan, math.nan, False)

    previous = sorted_points(previous_points)[-1]
    delta_load = state.load_mbps - previous.state.load_mbps
    score_delta = score - previous.score
    slope = max(0.0, score_delta / delta_load) if delta_load > 0 else math.nan

    prior_slopes = slopes_from_points(previous_points)
    usable = [s for s in prior_slopes if np.isfinite(s)]
    if len(usable) < args.min_history_slopes:
        return ResponsePoint(state, score, slope, math.nan, math.nan, score_delta, False)

    baseline_rate = statistics.median(usable)
    denom = max(baseline_rate, args.min_baseline_rate)
    rate_ratio = slope / denom if denom > 0 else math.inf
    accelerated = (
        score_delta >= args.min_score_jump
        and rate_ratio >= args.rate_multiplier
    )
    return ResponsePoint(state, score, slope, baseline_rate, rate_ratio, score_delta, accelerated)


def state_row(state: LoadState) -> dict:
    return {
        "capacity_mbps": state.capacity_mbps,
        "dist": state.dist,
        "seed": state.seed,
        "offered_load_mbps": state.load_mbps,
        "load_ratio": state.load_mbps / state.capacity_mbps if state.capacity_mbps else math.nan,
        "n_received": state.n_received,
        "n_stop": state.n_stop,
        "capped": state.capped,
        "stop_between_tvd": state.stop_between_tvd,
        "mean_delay_ms": state.mean_delay_ms,
        "median_delay_ms": state.median_delay_ms,
        "p95_delay_ms": state.p95_delay_ms,
        "p99_delay_ms": state.p99_delay_ms,
        "sent_probe_packets": state.drops.sent_probe_packets,
        "received_probe_packets": state.drops.received_probe_packets,
        "probe_loss_count": state.drops.probe_loss_count,
        "cross_traffic_tx_packets": state.drops.cross_traffic_tx_packets,
        "cross_traffic_rx_packets": state.drops.cross_traffic_rx_packets,
        "cross_traffic_loss_count": state.drops.cross_traffic_loss_count,
        "cross_traffic_tx_bytes": state.drops.cross_traffic_tx_bytes,
        "cross_traffic_rx_bytes": state.drops.cross_traffic_rx_bytes,
        "active_cross_traffic_flows": state.drops.active_cross_traffic_flows,
        "use_queue_disc": state.drops.use_queue_disc,
        "queue_drop_count": state.drops.queue_drop_count,
        "qdisc_drop_count": state.drops.qdisc_drop_count,
        "bottleneck_qdisc_drop_count": state.drops.bottleneck_qdisc_drop_count,
        "qdisc_drop_before_enqueue_count": state.drops.qdisc_drop_before_enqueue_count,
        "qdisc_drop_after_dequeue_count": state.drops.qdisc_drop_after_dequeue_count,
        "qdisc_mark_count": state.drops.qdisc_mark_count,
        "qdisc_received_packets": state.drops.qdisc_received_packets,
        "qdisc_sent_packets": state.drops.qdisc_sent_packets,
        "max_hop_qdisc_drop_count": state.drops.max_hop_qdisc_drop_count,
        "max_hop_qdisc_drop_hop": state.drops.max_hop_qdisc_drop_hop,
        "raw_path": rel(state.raw_path),
        "drop_stats_path": rel(state.drop_stats_path),
        "distribution_path": rel(state.distribution_path),
        "stopped_samples_path": rel(state.stopped_samples_path),
        "trace_path": rel(state.trace_path),
    }


def response_row(mode: str, phase: str, step: int, point: ResponsePoint, baseline: LoadState) -> dict:
    state = point.state
    return {
        "mode": mode,
        "phase": phase,
        "step": step,
        "capacity_mbps": state.capacity_mbps,
        "dist": state.dist,
        "seed": state.seed,
        "baseline_load_mbps": baseline.load_mbps,
        "offered_load_mbps": state.load_mbps,
        "load_ratio": state.load_mbps / state.capacity_mbps if state.capacity_mbps else math.nan,
        "score_tvd_from_baseline": point.score,
        "response_rate": point.slope,
        "baseline_response_rate": point.baseline_rate,
        "rate_ratio": point.rate_ratio,
        "score_delta": point.score_delta,
        "accelerated": point.accelerated,
        "queue_drop_count": state.drops.queue_drop_count,
        "qdisc_drop_count": state.drops.qdisc_drop_count,
        "probe_loss_count": state.drops.probe_loss_count,
        "cross_traffic_loss_count": state.drops.cross_traffic_loss_count,
        "n_stop": state.n_stop,
    }


def run_search(
    mode: str,
    dist: str,
    seed: int,
    capacity_mbps: float,
    results_dir: Path,
    args: argparse.Namespace,
    cache: dict[float, LoadState],
) -> tuple[list[dict], dict]:
    response_rows: list[dict] = []

    start_load = max(args.min_start_load_mbps, capacity_mbps * args.start_load_fraction)
    max_load = capacity_mbps * args.max_load_factor
    width = max(args.min_refine_width_mbps, capacity_mbps * args.refine_width_fraction)

    baseline_state = evaluate_load(dist, seed, capacity_mbps, start_load, results_dir, args, cache)
    baseline = ResponsePoint(baseline_state, 0.0, math.nan, math.nan, math.nan, math.nan, False)
    points: list[ResponsePoint] = [baseline]
    response_rows.append(response_row(mode, "slow_start", 0, baseline, baseline_state))

    bracket_lower: ResponsePoint | None = None
    bracket_upper: ResponsePoint | None = None

    current_load = start_load * args.load_multiplier
    step = 1
    while current_load <= max_load + 1.0e-9:
        state = evaluate_load(dist, seed, capacity_mbps, current_load, results_dir, args, cache)
        point = make_response_point(state, baseline_state, points, args)
        response_rows.append(response_row(mode, "slow_start", step, point, baseline_state))
        if point.accelerated:
            bracket_lower = sorted_points(points)[-1]
            bracket_upper = point
            break
        points.append(point)
        current_load *= args.load_multiplier
        step += 1

    if bracket_lower is None or bracket_upper is None:
        last = sorted_points(points)[-1]
        estimate = {
            "mode": mode,
            "capacity_mbps": capacity_mbps,
            "dist": dist,
            "seed": seed,
            "status": "not_detected",
            "initial_load_mbps": start_load,
            "estimated_lower_mbps": last.state.load_mbps,
            "estimated_upper_mbps": math.nan,
            "estimated_capacity_mbps": last.state.load_mbps,
            "estimated_capacity_ratio": last.state.load_mbps / capacity_mbps,
            "upper_ratio": math.nan,
            "relative_error": (last.state.load_mbps - capacity_mbps) / capacity_mbps,
            "first_accelerated_load_mbps": math.nan,
            "first_accelerated_ratio": math.nan,
            "refinement_steps": 0,
            "load_evaluations": len(points),
            "max_queue_drop_count": max((p.state.drops.queue_drop_count for p in points), default=0),
            "max_qdisc_drop_count": max((p.state.drops.qdisc_drop_count for p in points), default=0),
            "max_probe_loss_count": max((p.state.drops.probe_loss_count for p in points), default=0),
        }
        return response_rows, estimate

    lower = bracket_lower
    upper = bracket_upper
    refinement_steps = 0
    evaluated_points = points + [upper]

    if mode == "binary":
        for refine_step in range(1, args.binary_iterations + 1):
            if upper.state.load_mbps - lower.state.load_mbps <= width:
                break
            midpoint = 0.5 * (lower.state.load_mbps + upper.state.load_mbps)
            state = evaluate_load(dist, seed, capacity_mbps, midpoint, results_dir, args, cache)
            previous_points = [p for p in evaluated_points if p.state.load_mbps < midpoint]
            point = make_response_point(state, baseline_state, previous_points, args)
            response_rows.append(response_row(mode, "binary_refine", refine_step, point, baseline_state))
            evaluated_points.append(point)
            refinement_steps += 1
            if point.accelerated:
                upper = point
            else:
                lower = point
    elif mode == "additive":
        step_size = max(args.min_additive_step_mbps, (upper.state.load_mbps - lower.state.load_mbps) / args.additive_steps)
        current = lower.state.load_mbps + step_size
        refine_step = 1
        while current < upper.state.load_mbps - 1.0e-9:
            state = evaluate_load(dist, seed, capacity_mbps, current, results_dir, args, cache)
            previous_points = [p for p in evaluated_points if p.state.load_mbps < current]
            point = make_response_point(state, baseline_state, previous_points, args)
            response_rows.append(response_row(mode, "additive_refine", refine_step, point, baseline_state))
            evaluated_points.append(point)
            refinement_steps += 1
            if point.accelerated:
                upper = point
                break
            lower = point
            current += step_size
            refine_step += 1
    else:
        raise ValueError(f"Unknown mode {mode}")

    all_states = [point.state for point in evaluated_points]
    estimate = {
        "mode": mode,
        "capacity_mbps": capacity_mbps,
        "dist": dist,
        "seed": seed,
        "status": "detected",
        "initial_load_mbps": start_load,
        "estimated_lower_mbps": lower.state.load_mbps,
        "estimated_upper_mbps": upper.state.load_mbps,
        "estimated_capacity_mbps": lower.state.load_mbps,
        "estimated_capacity_ratio": lower.state.load_mbps / capacity_mbps,
        "upper_ratio": upper.state.load_mbps / capacity_mbps,
        "relative_error": (lower.state.load_mbps - capacity_mbps) / capacity_mbps,
        "first_accelerated_load_mbps": bracket_upper.state.load_mbps,
        "first_accelerated_ratio": bracket_upper.state.load_mbps / capacity_mbps,
        "refinement_steps": refinement_steps,
        "load_evaluations": len({round(s.load_mbps, 6) for s in all_states}),
        "max_queue_drop_count": max((s.drops.queue_drop_count for s in all_states), default=0),
        "max_qdisc_drop_count": max((s.drops.qdisc_drop_count for s in all_states), default=0),
        "max_probe_loss_count": max((s.drops.probe_loss_count for s in all_states), default=0),
    }
    return response_rows, estimate


def run_one_case(dist: str, seed: int, capacity_mbps: float, results_dir: Path, args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict]]:
    local_args = argparse.Namespace(**vars(args))
    local_args.configured_capacity_mbps = capacity_mbps
    local_args.link_data_rate = f"{fmt_float(capacity_mbps)}Mbps"

    cache: dict[float, LoadState] = {}
    all_response_rows: list[dict] = []
    estimates: list[dict] = []
    for mode in args.modes:
        rows, estimate = run_search(mode, dist, seed, capacity_mbps, results_dir, local_args, cache)
        all_response_rows.extend(rows)
        estimates.append(estimate)

    load_rows = [state_row(state) for state in sorted(cache.values(), key=lambda s: s.load_mbps)]
    return load_rows, all_response_rows, estimates


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def numeric(row: dict, key: str, default: float = math.nan) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def median(values: Iterable[float]) -> float:
    usable = [float(v) for v in values if np.isfinite(float(v))]
    return statistics.median(usable) if usable else math.nan


def percentile(values: Iterable[float], pct: float) -> float:
    usable = [float(v) for v in values if np.isfinite(float(v))]
    return float(np.percentile(usable, pct)) if usable else math.nan


def group_by(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        groups.setdefault(key, []).append(row)
    return groups


def summarise(estimates: list[dict], responses: list[dict], loads: list[dict], results_dir: Path) -> None:
    by_mode_capacity = []
    for (mode, capacity), rows in sorted(group_by(estimates, ("mode", "capacity_mbps")).items(), key=lambda item: (item[0][0], float(item[0][1]))):
        by_mode_capacity.append({
            "mode": mode,
            "capacity_mbps": capacity,
            "runs": len(rows),
            "detected_rate": sum(1 for row in rows if row["status"] == "detected") / len(rows),
            "median_estimated_capacity_mbps": median(numeric(row, "estimated_capacity_mbps") for row in rows),
            "median_estimated_capacity_ratio": median(numeric(row, "estimated_capacity_ratio") for row in rows),
            "q25_estimated_capacity_ratio": percentile((numeric(row, "estimated_capacity_ratio") for row in rows), 25),
            "q75_estimated_capacity_ratio": percentile((numeric(row, "estimated_capacity_ratio") for row in rows), 75),
            "median_upper_ratio": median(numeric(row, "upper_ratio") for row in rows),
            "median_relative_error": median(numeric(row, "relative_error") for row in rows),
            "median_refinement_steps": median(numeric(row, "refinement_steps") for row in rows),
            "median_load_evaluations": median(numeric(row, "load_evaluations") for row in rows),
            "drop_run_rate": sum(1 for row in rows if numeric(row, "max_queue_drop_count", 0) > 0 or numeric(row, "max_qdisc_drop_count", 0) > 0 or numeric(row, "max_probe_loss_count", 0) > 0) / len(rows),
            "median_max_queue_drops": median(numeric(row, "max_queue_drop_count", 0) for row in rows),
            "median_max_qdisc_drops": median(numeric(row, "max_qdisc_drop_count", 0) for row in rows),
            "median_max_probe_losses": median(numeric(row, "max_probe_loss_count", 0) for row in rows),
        })

    by_mode_dist = []
    for (mode, dist), rows in sorted(group_by(estimates, ("mode", "dist")).items()):
        by_mode_dist.append({
            "mode": mode,
            "dist": dist,
            "runs": len(rows),
            "median_estimated_capacity_ratio": median(numeric(row, "estimated_capacity_ratio") for row in rows),
            "median_relative_error": median(numeric(row, "relative_error") for row in rows),
            "drop_run_rate": sum(1 for row in rows if numeric(row, "max_queue_drop_count", 0) > 0 or numeric(row, "max_qdisc_drop_count", 0) > 0 or numeric(row, "max_probe_loss_count", 0) > 0) / len(rows),
        })

    drop_rows = []
    for (capacity, dist, seed), rows in sorted(group_by(loads, ("capacity_mbps", "dist", "seed")).items(), key=lambda item: (float(item[0][0]), item[0][1], int(item[0][2]))):
        ordered = sorted(rows, key=lambda row: numeric(row, "offered_load_mbps"))
        first_queue = next((row for row in ordered if numeric(row, "queue_drop_count", 0) > 0), None)
        first_qdisc = next((row for row in ordered if numeric(row, "qdisc_drop_count", 0) > 0), None)
        first_probe = next((row for row in ordered if numeric(row, "probe_loss_count", 0) > 0), None)
        drop_rows.append({
            "capacity_mbps": capacity,
            "dist": dist,
            "seed": seed,
            "first_queue_drop_load_mbps": numeric(first_queue, "offered_load_mbps") if first_queue else math.nan,
            "first_queue_drop_ratio": numeric(first_queue, "load_ratio") if first_queue else math.nan,
            "first_qdisc_drop_load_mbps": numeric(first_qdisc, "offered_load_mbps") if first_qdisc else math.nan,
            "first_qdisc_drop_ratio": numeric(first_qdisc, "load_ratio") if first_qdisc else math.nan,
            "first_probe_loss_load_mbps": numeric(first_probe, "offered_load_mbps") if first_probe else math.nan,
            "first_probe_loss_ratio": numeric(first_probe, "load_ratio") if first_probe else math.nan,
            "max_tested_ratio": max((numeric(row, "load_ratio", 0) for row in ordered), default=0),
            "max_queue_drop_count": max((numeric(row, "queue_drop_count", 0) for row in ordered), default=0),
            "max_qdisc_drop_count": max((numeric(row, "qdisc_drop_count", 0) for row in ordered), default=0),
            "max_probe_loss_count": max((numeric(row, "probe_loss_count", 0) for row in ordered), default=0),
        })

    drop_summary = []
    for (capacity,), rows in sorted(group_by(drop_rows, ("capacity_mbps",)).items(), key=lambda item: float(item[0][0])):
        drop_summary.append({
            "capacity_mbps": capacity,
            "runs": len(rows),
            "queue_drop_detected_rate": sum(1 for row in rows if np.isfinite(numeric(row, "first_queue_drop_ratio"))) / len(rows),
            "median_first_queue_drop_ratio": median(numeric(row, "first_queue_drop_ratio") for row in rows),
            "qdisc_drop_detected_rate": sum(1 for row in rows if np.isfinite(numeric(row, "first_qdisc_drop_ratio"))) / len(rows),
            "median_first_qdisc_drop_ratio": median(numeric(row, "first_qdisc_drop_ratio") for row in rows),
            "probe_loss_detected_rate": sum(1 for row in rows if np.isfinite(numeric(row, "first_probe_loss_ratio"))) / len(rows),
            "median_first_probe_loss_ratio": median(numeric(row, "first_probe_loss_ratio") for row in rows),
            "median_max_tested_ratio": median(numeric(row, "max_tested_ratio") for row in rows),
            "median_max_queue_drops": median(numeric(row, "max_queue_drop_count", 0) for row in rows),
            "median_max_qdisc_drops": median(numeric(row, "max_qdisc_drop_count", 0) for row in rows),
            "median_max_probe_losses": median(numeric(row, "max_probe_loss_count", 0) for row in rows),
        })

    write_csv(results_dir / "summary_by_mode_capacity.csv", by_mode_capacity)
    write_csv(results_dir / "summary_by_mode_distribution.csv", by_mode_dist)
    write_csv(results_dir / "drop_detection_by_run.csv", drop_rows)
    write_csv(results_dir / "drop_detection_summary.csv", drop_summary)


def plot_estimate_ratios(estimates: list[dict], plots_dir: Path) -> Path:
    plots_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 6))
    for mode in MODE_LABELS:
        rows = [row for row in estimates if row["mode"] == mode and row["status"] == "detected"]
        groups = group_by(rows, ("capacity_mbps",))
        xs, ys, lo, hi = [], [], [], []
        for (capacity,), sub in sorted(groups.items(), key=lambda item: float(item[0][0])):
            vals = [numeric(row, "estimated_capacity_ratio") for row in sub]
            med = median(vals)
            q25 = percentile(vals, 25)
            q75 = percentile(vals, 75)
            xs.append(float(capacity))
            ys.append(med)
            lo.append(med - q25)
            hi.append(q75 - med)
        if xs:
            ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", linewidth=2.0, capsize=3, label=MODE_LABELS[mode], color=MODE_COLOURS[mode])
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xscale("log")
    ax.set_xlabel("Configured link capacity in Mbit/s")
    ax.set_ylabel("Estimated capacity divided by configured capacity")
    ax.set_title("Distributional response-rate capacity estimates")
    ax.grid(True, alpha=0.25)
    ax.legend()
    out = plots_dir / "response_capacity_ratio_by_mode.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_response_curve(responses: list[dict], plots_dir: Path, target_capacity: float) -> Path:
    rows = [
        row for row in responses
        if abs(numeric(row, "capacity_mbps") - target_capacity) < 1.0e-9
        and row["mode"] == "additive"
    ]
    fig, ax = plt.subplots(figsize=(11, 6))
    for dist in DISTRIBUTIONS:
        sub = [row for row in rows if row["dist"] == dist]
        groups = group_by(sub, ("offered_load_mbps",))
        xs, ys, lo, hi = [], [], [], []
        for (load,), group in sorted(groups.items(), key=lambda item: float(item[0][0])):
            vals = [numeric(row, "score_tvd_from_baseline") for row in group]
            med = median(vals)
            q25 = percentile(vals, 25)
            q75 = percentile(vals, 75)
            xs.append(float(load))
            ys.append(med)
            lo.append(med - q25)
            hi.append(q75 - med)
        if xs:
            ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", linewidth=2.0, capsize=3, label=DIST_LABELS[dist], color=DIST_COLOURS[dist])
    ax.axvline(target_capacity, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xlabel("Offered cross-traffic load in Mbit/s")
    ax.set_ylabel("TVD from initial low-load distribution")
    ax.set_title(f"Distributional response curve at {target_capacity:g} Mbit/s")
    ax.grid(True, alpha=0.25)
    ax.legend()
    out = plots_dir / f"response_curve_{fmt_float(target_capacity).replace('.', 'p')}Mbps.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_drop_comparison(estimates: list[dict], drop_summary: list[dict], plots_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    for mode in MODE_LABELS:
        rows = [row for row in estimates if row["mode"] == mode and row["status"] == "detected"]
        groups = group_by(rows, ("capacity_mbps",))
        xs, ys = [], []
        for (capacity,), sub in sorted(groups.items(), key=lambda item: float(item[0][0])):
            xs.append(float(capacity))
            ys.append(median(numeric(row, "estimated_capacity_ratio") for row in sub))
        if xs:
            ax.plot(xs, ys, marker="o", linewidth=2.0, label=MODE_LABELS[mode], color=MODE_COLOURS[mode])
    xs, ys = [], []
    no_drop_xs, no_drop_ys = [], []
    for row in sorted(drop_summary, key=lambda r: numeric(r, "capacity_mbps")):
        ratio = numeric(row, "median_first_qdisc_drop_ratio")
        if np.isfinite(ratio):
            xs.append(numeric(row, "capacity_mbps"))
            ys.append(ratio)
        else:
            no_drop_xs.append(numeric(row, "capacity_mbps"))
            no_drop_ys.append(numeric(row, "median_max_tested_ratio"))
    if xs:
        ax.plot(xs, ys, marker="s", linewidth=2.0, color="#2ca02c", label="First queue-disc drop")
    if no_drop_xs:
        ax.scatter(
            no_drop_xs,
            no_drop_ys,
            marker="v",
            s=56,
            facecolors="white",
            edgecolors="#2ca02c",
            linewidths=1.6,
            label="No queue-disc drop observed by max tested load",
        )
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Configured capacity")
    ax.set_xscale("log")
    ax.set_xlabel("Configured link capacity in Mbit/s")
    ax.set_ylabel("Detection load divided by configured capacity")
    ax.set_title("Distributional detection compared with packet-drop detection")
    ax.grid(True, alpha=0.25)
    ax.legend()
    out = plots_dir / "distributional_vs_drop_detection.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def make_plots(results_dir: Path) -> None:
    estimates = read_csv(results_dir / "estimates.csv")
    responses = read_csv(results_dir / "response_results.csv")
    drop_summary = read_csv(results_dir / "drop_detection_summary.csv")
    plots_dir = results_dir / "plots"
    paths = [
        plot_estimate_ratios(estimates, plots_dir),
        plot_response_curve(responses, plots_dir, 10.0),
        plot_drop_comparison(estimates, drop_summary, plots_dir),
    ]
    for path in paths:
        log(f"Wrote plot {rel(path)}")


def build_ns3() -> None:
    log("Building NS-3 single-hop target")
    output_path = REPO_ROOT / "delay-monitoring" / "results" / ".response_build_probe.csv"
    drop_path = REPO_ROOT / "delay-monitoring" / "results" / ".response_build_drops.csv"
    completed = subprocess.run(
        [
            "./ns3",
            "run",
            "--quiet",
            (
                "scratch/delay-monitoring/single-hop-underlying-network "
                "--delayDist=normal --numPackets=1 "
                f"--outputFile={output_path} "
                f"--dropStatsFile={drop_path}"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run distributional response-rate capacity experiments.")
    parser.add_argument("--results-dir", default=str(REPO_ROOT / "delay-monitoring" / "results" / "use-case-response-rate"))
    parser.add_argument("--capacities-mbps", nargs="+", type=float, default=[2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 32.0, 64.0])
    parser.add_argument("--dists", nargs="+", default=list(DISTRIBUTIONS), choices=list(DISTRIBUTIONS))
    parser.add_argument("--modes", nargs="+", default=["binary", "additive"], choices=["binary", "additive"])
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-ns3-build", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--start-load-fraction", type=float, default=0.05)
    parser.add_argument("--min-start-load-mbps", type=float, default=0.1)
    parser.add_argument("--load-multiplier", type=float, default=2.0)
    parser.add_argument("--max-load-factor", type=float, default=2.4)
    parser.add_argument("--binary-iterations", type=int, default=6)
    parser.add_argument("--additive-steps", type=int, default=16)
    parser.add_argument("--refine-width-fraction", type=float, default=0.025)
    parser.add_argument("--min-refine-width-mbps", type=float, default=0.05)
    parser.add_argument("--min-additive-step-mbps", type=float, default=0.05)
    parser.add_argument("--min-history-slopes", type=int, default=2)
    parser.add_argument("--rate-multiplier", type=float, default=5.0)
    parser.add_argument("--min-score-jump", type=float, default=0.10)
    parser.add_argument("--min-baseline-rate", type=float, default=1.0e-4)
    parser.add_argument("--link-data-rate", default="10Mbps")
    parser.add_argument("--link-delay", default="2ms")
    parser.add_argument("--cross-traffic-stop-time", type=float, default=-1.0)
    parser.add_argument("--queue-size", type=int, default=50)
    parser.add_argument("--queue-disc-type", default="ns3::FifoQueueDisc")
    parser.add_argument("--use-queue-disc", action="store_true")
    parser.add_argument("--probe-packet-size", type=int, default=64)
    parser.add_argument("--probe-interval-mean-ms", type=float, default=10.0)
    parser.add_argument("--max-packets-per-load", type=int, default=4000)
    parser.add_argument("--simulation-stop-time", type=float, default=15.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
            for capacity in args.capacities_mbps:
                for dist in args.dists:
                    for seed in range(args.seed_start, args.seed_end + 1):
                        futures.append(executor.submit(run_one_case, dist, seed, capacity, results_dir, args))
            for future in as_completed(futures):
                load_rows, response_rows, estimates = future.result()
                all_load_rows.extend(load_rows)
                all_response_rows.extend(response_rows)
                all_estimates.extend(estimates)

        all_load_rows.sort(key=lambda row: (numeric(row, "capacity_mbps"), row["dist"], int(row["seed"]), numeric(row, "offered_load_mbps")))
        all_response_rows.sort(key=lambda row: (row["mode"], numeric(row, "capacity_mbps"), row["dist"], int(row["seed"]), row["phase"], int(row["step"]), numeric(row, "offered_load_mbps")))
        all_estimates.sort(key=lambda row: (row["mode"], numeric(row, "capacity_mbps"), row["dist"], int(row["seed"])))
        write_csv(results_dir / "load_results.csv", all_load_rows)
        write_csv(results_dir / "response_results.csv", all_response_rows)
        write_csv(results_dir / "estimates.csv", all_estimates)
    else:
        all_load_rows = read_csv(results_dir / "load_results.csv")
        all_response_rows = read_csv(results_dir / "response_results.csv")
        all_estimates = read_csv(results_dir / "estimates.csv")

    summarise(all_estimates, all_response_rows, all_load_rows, results_dir)
    make_plots(results_dir)
    log(f"Wrote results to {rel(results_dir)}")


if __name__ == "__main__":
    main()
