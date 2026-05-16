"""
Multipath bimodality and capacity-response analysis.

This experiment reuses stopped single-link NS-3 distributions as two endpoint
visible path components. One component remains at the low-load state. The other
component is shifted by a fixed delay offset and swept through the offered-load
grid. The receiver observes only the mixture. A KDE mode split is then used to
test whether the stressed component can be isolated and associated with the
capacity response.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
from collections import defaultdict
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
    "overall_first_change": "Mixture first change",
    "overall_rate_change": "Mixture TVD rate",
    "upper_component_rate": "Upper-mode TVD rate",
    "lower_component_rate": "Lower-mode TVD rate",
}

METHOD_COLOURS = {
    "overall_first_change": "#1f77b4",
    "overall_rate_change": "#d62728",
    "upper_component_rate": "#2ca02c",
    "lower_component_rate": "#7f7f7f",
}


def numeric(value: object, default: float = math.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_masses(path: Path) -> np.ndarray:
    rows = read_csv(path)
    masses = np.array([numeric(row["probability_mass"]) for row in rows], dtype=float)
    total = float(np.sum(masses))
    if not math.isfinite(total) or total <= 0:
        return np.ones_like(base.GRID) / len(base.GRID)
    return masses / total


def distribution_path(single_results: Path, dist: str, seed: int, load_mbps: float) -> Path:
    return (
        single_results
        / "single_hop"
        / base.capacity_label(10.0)
        / "processed"
        / dist
        / f"seed_{seed:03d}"
        / base.load_label(load_mbps)
        / "stopped_distribution.csv"
    )


def shift_masses(masses: np.ndarray, offset_ms: float) -> np.ndarray:
    shift_bins = int(round(offset_ms / base.BIN_WIDTH))
    out = np.zeros_like(masses)
    if shift_bins <= 0:
        out[:] = masses
    elif shift_bins < len(masses):
        out[shift_bins:] = masses[:-shift_bins]
    total = float(np.sum(out))
    if total <= 0:
        return np.ones_like(masses) / len(masses)
    return out / total


def mixture_masses(lower: np.ndarray, upper: np.ndarray, upper_share: float) -> np.ndarray:
    combined = (1.0 - upper_share) * lower + upper_share * upper
    total = float(np.sum(combined))
    return combined / total


def local_peaks(masses: np.ndarray, prominence_fraction: float = 0.01, min_distance_bins: int = 8) -> list[int]:
    if len(masses) < 3:
        return []
    peak_candidates = []
    max_value = float(np.max(masses))
    min_height = max_value * prominence_fraction
    for i in range(1, len(masses) - 1):
        if masses[i] > masses[i - 1] and masses[i] >= masses[i + 1] and masses[i] >= min_height:
            peak_candidates.append(i)
    peak_candidates.sort(key=lambda idx: masses[idx], reverse=True)
    selected: list[int] = []
    for idx in peak_candidates:
        if all(abs(idx - existing) >= min_distance_bins for existing in selected):
            selected.append(idx)
    return sorted(selected)


def modal_split(masses: np.ndarray) -> tuple[int | None, int, float, float, float]:
    peaks = local_peaks(masses)
    if len(peaks) < 2:
        return None, len(peaks), math.nan, math.nan, math.nan
    strongest = sorted(peaks, key=lambda idx: masses[idx], reverse=True)[:2]
    left_peak, right_peak = sorted(strongest)
    if right_peak <= left_peak + 1:
        return None, len(peaks), math.nan, math.nan, math.nan
    valley_slice = masses[left_peak : right_peak + 1]
    valley = left_peak + int(np.argmin(valley_slice))
    valley_ratio = float(masses[valley] / max(1.0e-12, min(masses[left_peak], masses[right_peak])))
    lower_weight = float(np.sum(masses[: valley + 1]))
    upper_weight = float(np.sum(masses[valley + 1 :]))
    return valley, len(peaks), valley_ratio, lower_weight, upper_weight


def component_masses(masses: np.ndarray, split_index: int | None, upper: bool) -> np.ndarray:
    out = np.zeros_like(masses)
    if split_index is None:
        out[:] = masses
    elif upper:
        out[split_index + 1 :] = masses[split_index + 1 :]
    else:
        out[: split_index + 1] = masses[: split_index + 1]
    total = float(np.sum(out))
    if total <= 0:
        return np.ones_like(masses) / len(masses)
    return out / total


def detect_response(points: list[dict], score_key: str, args: argparse.Namespace) -> dict:
    previous = None
    previous_score = math.nan
    slopes: list[float] = []
    first_change = None
    first_rate = None

    for row in sorted(points, key=lambda item: numeric(item["load_ratio"])):
        score = numeric(row[score_key])
        if first_change is None and score >= args.change_threshold:
            first_change = row
        if previous is not None:
            load_delta = numeric(row["load_mbps"]) - numeric(previous["load_mbps"])
            score_delta = score - previous_score
            slope = max(0.0, score_delta / load_delta) if load_delta > 0 else math.nan
            usable = [value for value in slopes if math.isfinite(value)]
            baseline_rate = statistics.median(usable) if len(usable) >= args.min_history_slopes else math.nan
            denom = max(baseline_rate, args.min_baseline_rate) if math.isfinite(baseline_rate) else math.nan
            rate_ratio = slope / denom if math.isfinite(denom) and denom > 0 else math.nan
            if first_rate is None and score_delta >= args.min_score_jump and math.isfinite(rate_ratio) and rate_ratio >= args.rate_multiplier:
                first_rate = row
            if math.isfinite(slope):
                slopes.append(slope)
        previous = row
        previous_score = score

    return {
        "first_change": first_change,
        "first_rate": first_rate,
    }


def detect_ratio(row: dict | None) -> float:
    return numeric(row["load_ratio"]) if row is not None else math.nan


def run_analysis(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    single_results = Path(args.single_results).resolve()
    load_rows = read_csv(single_results / "load_results.csv")
    loads = sorted({
        (round(numeric(row["load_ratio"]), 6), round(numeric(row["offered_load_mbps"]), 6))
        for row in load_rows
        if row["dist"] in args.dists and args.seed_start <= int(row["seed"]) <= args.seed_end
    })
    load_by_ratio = {ratio: load for ratio, load in loads}
    baseline_ratio = min(load_by_ratio)
    baseline_load = load_by_ratio[baseline_ratio]

    response_rows: list[dict] = []
    method_rows: list[dict] = []

    for share in args.upper_shares:
        for dist in args.dists:
            for seed in range(args.seed_start, args.seed_end + 1):
                lower_baseline = read_masses(distribution_path(single_results, dist, seed, baseline_load))
                upper_baseline = shift_masses(lower_baseline, args.upper_path_offset_ms)
                baseline_mix = mixture_masses(lower_baseline, upper_baseline, share)
                split_index, mode_count, valley_ratio, lower_weight, upper_weight = modal_split(baseline_mix)
                split_valid = (
                    split_index is not None
                    and math.isfinite(valley_ratio)
                    and valley_ratio <= args.max_valley_ratio
                )
                baseline_lower = component_masses(baseline_mix, split_index, upper=False) if split_valid else None
                baseline_upper = component_masses(baseline_mix, split_index, upper=True) if split_valid else None
                case_rows: list[dict] = []

                for ratio, load_mbps in loads:
                    lower = lower_baseline
                    upper = shift_masses(read_masses(distribution_path(single_results, dist, seed, load_mbps)), args.upper_path_offset_ms)
                    mix = mixture_masses(lower, upper, share)
                    current_split, current_modes, current_valley_ratio, current_lower_weight, current_upper_weight = modal_split(mix)
                    lower_component = component_masses(mix, split_index, upper=False)
                    upper_component = component_masses(mix, split_index, upper=True)
                    row = {
                        "dist": dist,
                        "seed": seed,
                        "upper_share": share,
                        "upper_offset_ms": args.upper_path_offset_ms,
                        "load_ratio": ratio,
                        "load_mbps": load_mbps,
                        "baseline_mode_count": mode_count,
                        "baseline_valley_ratio": valley_ratio,
                        "baseline_split_valid": split_valid,
                        "baseline_split_ms": base.GRID[split_index] if split_index is not None else math.nan,
                        "baseline_lower_weight": lower_weight,
                        "baseline_upper_weight": upper_weight,
                        "mode_count": current_modes,
                        "valley_ratio": current_valley_ratio,
                        "lower_weight": current_lower_weight,
                        "upper_weight": current_upper_weight,
                        "overall_tvd": base.tvd(mix, baseline_mix),
                        "lower_component_tvd": base.tvd(lower_component, baseline_lower) if split_valid else math.nan,
                        "upper_component_tvd": base.tvd(upper_component, baseline_upper) if split_valid else math.nan,
                    }
                    case_rows.append(row)
                    response_rows.append(row)

                overall = detect_response(case_rows, "overall_tvd", args)
                lower = detect_response(case_rows, "lower_component_tvd", args)
                upper = detect_response(case_rows, "upper_component_tvd", args)
                method_rows.extend([
                    {
                        "dist": dist,
                        "seed": seed,
                        "upper_share": share,
                        "upper_offset_ms": args.upper_path_offset_ms,
                        "method": "overall_first_change",
                        "detected": overall["first_change"] is not None,
                        "detection_load_ratio": detect_ratio(overall["first_change"]),
                    },
                    {
                        "dist": dist,
                        "seed": seed,
                        "upper_share": share,
                        "upper_offset_ms": args.upper_path_offset_ms,
                        "method": "overall_rate_change",
                        "detected": overall["first_rate"] is not None,
                        "detection_load_ratio": detect_ratio(overall["first_rate"]),
                    },
                    {
                        "dist": dist,
                        "seed": seed,
                        "upper_share": share,
                        "upper_offset_ms": args.upper_path_offset_ms,
                        "method": "lower_component_rate",
                        "detected": lower["first_rate"] is not None,
                        "detection_load_ratio": detect_ratio(lower["first_rate"]),
                    },
                    {
                        "dist": dist,
                        "seed": seed,
                        "upper_share": share,
                        "upper_offset_ms": args.upper_path_offset_ms,
                        "method": "upper_component_rate",
                        "detected": upper["first_rate"] is not None,
                        "detection_load_ratio": detect_ratio(upper["first_rate"]),
                    },
                ])

    return response_rows, method_rows


def percentile(values: list[float], q: float) -> float:
    vals = sorted(value for value in values if math.isfinite(value))
    if not vals:
        return math.nan
    return float(np.percentile(vals, q))


def summarise(method_rows: list[dict], response_rows: list[dict], results_dir: Path) -> None:
    summary_rows: list[dict] = []
    for (share, method), rows in sorted(group_by(method_rows, ("upper_share", "method")).items()):
        ratios = [numeric(row["detection_load_ratio"]) for row in rows]
        detected = [value for value in ratios if math.isfinite(value)]
        summary_rows.append({
            "upper_share": share,
            "method": method,
            "runs": len(rows),
            "detected_rate": len(detected) / len(rows) if rows else math.nan,
            "median_detection_ratio": statistics.median(detected) if detected else math.nan,
            "q25_detection_ratio": percentile(detected, 25),
            "q75_detection_ratio": percentile(detected, 75),
            "early_rate_below_0p9": sum(value < 0.9 for value in detected) / len(rows) if rows else math.nan,
            "late_rate_above_0p925": sum(value > 0.925 for value in detected) / len(rows) if rows else math.nan,
        })
    write_csv(results_dir / "summary_by_method.csv", summary_rows)

    dist_rows: list[dict] = []
    for (share, dist, method), rows in sorted(group_by(method_rows, ("upper_share", "dist", "method")).items()):
        ratios = [numeric(row["detection_load_ratio"]) for row in rows]
        detected = [value for value in ratios if math.isfinite(value)]
        dist_rows.append({
            "upper_share": share,
            "dist": dist,
            "method": method,
            "runs": len(rows),
            "detected_rate": len(detected) / len(rows) if rows else math.nan,
            "median_detection_ratio": statistics.median(detected) if detected else math.nan,
            "q25_detection_ratio": percentile(detected, 25),
            "q75_detection_ratio": percentile(detected, 75),
        })
    write_csv(results_dir / "summary_by_distribution.csv", dist_rows)

    mode_rows: list[dict] = []
    for (share, dist), rows in sorted(group_by(response_rows, ("upper_share", "dist")).items()):
        baseline = [row for row in rows if numeric(row["load_ratio"]) == min(numeric(r["load_ratio"]) for r in rows)]
        mode_rows.append({
            "upper_share": share,
            "dist": dist,
            "runs": len(baseline),
            "bimodal_rate": sum(numeric(row["baseline_mode_count"], 0) >= 2 and numeric(row["baseline_valley_ratio"], 1) <= 0.8 for row in baseline) / len(baseline) if baseline else math.nan,
            "median_valley_ratio": statistics.median(numeric(row["baseline_valley_ratio"]) for row in baseline) if baseline else math.nan,
            "median_split_ms": statistics.median(numeric(row["baseline_split_ms"]) for row in baseline) if baseline else math.nan,
        })
    write_csv(results_dir / "summary_by_bimodality.csv", mode_rows)


def group_by(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return groups


def plot_methods(method_rows: list[dict], plots_dir: Path) -> Path:
    methods = ["overall_first_change", "overall_rate_change", "upper_component_rate", "lower_component_rate"]
    shares = sorted({numeric(row["upper_share"]) for row in method_rows})
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    offsets = np.linspace(-0.018, 0.018, len(methods))
    for offset, method in zip(offsets, methods):
        medians = []
        lows = []
        highs = []
        for share in shares:
            vals = [
                numeric(row["detection_load_ratio"])
                for row in method_rows
                if numeric(row["upper_share"]) == share and row["method"] == method
            ]
            vals = [value for value in vals if math.isfinite(value)]
            med = statistics.median(vals) if vals else math.nan
            q25 = percentile(vals, 25)
            q75 = percentile(vals, 75)
            medians.append(med)
            lows.append(med - q25 if math.isfinite(med) and math.isfinite(q25) else 0)
            highs.append(q75 - med if math.isfinite(med) and math.isfinite(q75) else 0)
        ax.errorbar(
            [share + offset for share in shares],
            medians,
            yerr=[lows, highs],
            marker="o",
            linewidth=2,
            capsize=3,
            color=METHOD_COLOURS[method],
            label=METHOD_LABELS[method],
        )
    ax.axhline(0.925, color="black", linestyle="--", linewidth=1.2, label="Single-path grid point")
    ax.set_xlabel("Fraction of traffic on the stressed upper-delay path")
    ax.set_ylabel("Detected load ratio")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, ncols=2)
    ax.set_title("Multipath capacity boundary by modal component")
    plots_dir.mkdir(parents=True, exist_ok=True)
    out = plots_dir / "multipath_detection_by_method.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_component_response(response_rows: list[dict], plots_dir: Path, dist: str = "weibull", share: float = 0.5) -> Path:
    rows = [
        row
        for row in response_rows
        if row["dist"] == dist and int(row["seed"]) <= 100 and abs(numeric(row["upper_share"]) - share) < 1.0e-9
    ]
    grouped = group_by(rows, ("load_ratio",))
    ratios = sorted(numeric(key[0]) for key in grouped)
    series = {
        "overall_tvd": ("Mixture", "#1f77b4"),
        "lower_component_tvd": ("Lower mode", "#7f7f7f"),
        "upper_component_tvd": ("Upper mode", "#2ca02c"),
    }
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for key, (label, colour) in series.items():
        med = []
        q25 = []
        q75 = []
        for ratio in ratios:
            vals = [numeric(row[key]) for row in grouped[(ratio,)]]
            med.append(statistics.median(vals))
            q25.append(percentile(vals, 25))
            q75.append(percentile(vals, 75))
        ax.plot(ratios, med, marker="o", linewidth=2, color=colour, label=label)
        ax.fill_between(ratios, q25, q75, color=colour, alpha=0.16)
    ax.axvline(0.925, color="black", linestyle="--", linewidth=1.2, label="Single-path grid point")
    ax.axhline(0.05, color="#555555", linestyle=":", linewidth=1.2, label="TVD target")
    ax.set_xlabel("Offered load on upper-delay path divided by its configured capacity")
    ax.set_ylabel("TVD from low-load mixture")
    ax.set_title("Component response in a bimodal multipath mixture")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    plots_dir.mkdir(parents=True, exist_ok=True)
    out = plots_dir / "multipath_component_response_weibull_share50.png"
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_bimodal_example(response_rows: list[dict], args: argparse.Namespace, plots_dir: Path) -> Path:
    single_results = Path(args.single_results).resolve()
    dist = "weibull"
    seed = args.seed_start
    share = 0.5
    load_ratios = [0.05, 0.925, 1.1]
    load_rows = read_csv(single_results / "load_results.csv")
    load_by_ratio = {round(numeric(row["load_ratio"]), 6): round(numeric(row["offered_load_mbps"]), 6) for row in load_rows if row["dist"] == dist and int(row["seed"]) == seed}
    lower = read_masses(distribution_path(single_results, dist, seed, load_by_ratio[0.05]))

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2), sharey=True)
    for ax, ratio, colour in zip(axes, load_ratios, ["#1f77b4", "#d62728", "#2ca02c"]):
        upper = shift_masses(read_masses(distribution_path(single_results, dist, seed, load_by_ratio[ratio])), args.upper_path_offset_ms)
        mix = mixture_masses(lower, upper, share)
        split, _, _, _, _ = modal_split(mix)
        ax.plot(base.GRID, mix, linewidth=2.3, color=colour)
        if split is not None:
            ax.axvline(base.GRID[split], color="black", linestyle="--", linewidth=1.1)
        ax.set_xlim(0, 90)
        ax.set_xlabel("Delay grid in milliseconds")
        ax.set_title(f"Load ratio {ratio:.3f}")
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("Probability mass")
    fig.suptitle("Bimodal receiver distribution from two path components")
    plots_dir.mkdir(parents=True, exist_ok=True)
    out = plots_dir / "multipath_bimodal_example.png"
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def make_plots(response_rows: list[dict], method_rows: list[dict], results_dir: Path, args: argparse.Namespace) -> list[Path]:
    plots_dir = results_dir / "plots"
    return [
        plot_methods(method_rows, plots_dir),
        plot_component_response(response_rows, plots_dir),
        plot_bimodal_example(response_rows, args, plots_dir),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyse bimodal multipath capacity response from stopped NS-3 distributions.")
    parser.add_argument("--single-results", default=str(REPO_ROOT / "delay-monitoring" / "results" / "observable-capacity-single-100-seed"))
    parser.add_argument("--results-dir", default=str(REPO_ROOT / "delay-monitoring" / "results" / "multipath-bimodal-capacity"))
    parser.add_argument("--dists", nargs="+", choices=list(base.DISTRIBUTIONS), default=list(base.DISTRIBUTIONS))
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=100)
    parser.add_argument("--upper-shares", nargs="+", type=float, default=[0.25, 0.5, 0.75])
    parser.add_argument("--upper-path-offset-ms", type=float, default=30.0)
    parser.add_argument("--max-valley-ratio", type=float, default=0.8)
    parser.add_argument("--change-threshold", type=float, default=base.DELTA)
    parser.add_argument("--min-history-slopes", type=int, default=2)
    parser.add_argument("--rate-multiplier", type=float, default=5.0)
    parser.add_argument("--min-score-jump", type=float, default=0.05)
    parser.add_argument("--min-baseline-rate", type=float, default=1.0e-4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / "run_config.json").open("w") as f:
        import json

        json.dump(vars(args), f, indent=2)

    response_rows, method_rows = run_analysis(args)
    write_csv(results_dir / "multipath_response_results.csv", response_rows)
    write_csv(results_dir / "multipath_method_results.csv", method_rows)
    summarise(method_rows, response_rows, results_dir)
    paths = make_plots(response_rows, method_rows, results_dir, args)
    for path in paths:
        print(path)
    print(f"Wrote multipath bimodal results to {results_dir}")


if __name__ == "__main__":
    main()
