"""
Bin size experiment -- discrete distributions (direct sampling).

Research question: does using a finer bin size (more bins k) require more
samples to achieve a target TVD accuracy?  The theoretical bound is:

    n_theory = ceil((k + log(1 / epsilon)) / delta^2)

where k = number of bins covering the support at the chosen resolution,
and k grows as bin_size shrinks.

Three discrete distributions are tested over small integer supports (ms):
  - Binomial(N=20, p=0.5)            support {0, ..., 20}
  - Zipf(N=20, alpha=1.5)            support {1, ..., 20}
  - Piecewise (irregular 20-outcome) support {1, ..., 20}

For each (distribution, bin_size) pair:
  1. Compute k and n_theory.
  2. Draw samples at five sizes (n/4, n/2, n, 2n, 4n) across SEEDS seeds.
  3. Compute TVD between the empirical coarsened PMF and the true
     coarsened PMF (true probability mass summed within each bin).
  4. Save TVD data as CSV and generate plots.

Results are stored per distribution:
  results/bin-size-experiment/discrete/<dist>/data/  -- CSV files
  results/bin-size-experiment/discrete/<dist>/       -- per-distribution plots
  results/bin-size-experiment/discrete/              -- summary plots
"""

import csv
import math
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(
    SCRIPT_DIR, "../../../results/bin-size-experiment/discrete"
)

# ---------------------------------------------------------------------------
# experiment parameters
# ---------------------------------------------------------------------------

BIN_SIZES       = [0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]   # ms
EPSILON         = 0.05
DELTA           = 0.05
SEEDS           = list(range(1, 51))   # 50 independent seeds
X_TICK_LABELS   = ["n/4", "n/2", "n", "2n", "4n"]
BOX_POSITIONS   = list(range(5))

# Fine resolution for x-axis ticks in distribution comparison plots.
# At 0.005ms spacing the tick marks visually resolve individual 0.01ms bins.
PLOT_TICK_STEP  = 0.005   # ms; minor x-axis ticks -- 0.005ms resolves individual 0.01ms bins

# ---------------------------------------------------------------------------
# distributions
# ---------------------------------------------------------------------------

_PIECEWISE_PMF = np.array([
    0.12, 0.02, 0.08, 0.01, 0.10, 0.03, 0.07, 0.12, 0.02, 0.09,
    0.01, 0.08, 0.04, 0.06, 0.02, 0.05, 0.02, 0.04, 0.01, 0.01,
], dtype=float)

DISTRIBUTIONS = {
    "binomial": {
        "label":    "Binomial(N=20, p=0.5)",
        "color":    "#9b59b6",
        "support":  np.arange(0, 21, dtype=float),
        "true_pmf": stats.binom.pmf(np.arange(0, 21), n=20, p=0.5).astype(float),
    },
    "zipf": {
        "label":    "Zipf(N=20, alpha=1.5)",
        "color":    "#e67e22",
        "support":  np.arange(1, 21, dtype=float),
        "true_pmf": stats.zipfian.pmf(np.arange(1, 21), a=1.5, n=20).astype(float),
    },
    "piecewise": {
        "label":    "Piecewise (irregular multi-modal)",
        "color":    "#27ae60",
        "support":  np.arange(1, 21, dtype=float),
        "true_pmf": _PIECEWISE_PMF / _PIECEWISE_PMF.sum(),
    },
}

# Guard against floating-point rounding
for _d in DISTRIBUTIONS.values():
    _d["true_pmf"] = _d["true_pmf"] / _d["true_pmf"].sum()


# ---------------------------------------------------------------------------
# coarsening
# ---------------------------------------------------------------------------

def coarsen_pmf(support, fine_pmf, bin_size):
    """
    Sum true probability mass into coarsened bins of width bin_size.
    Returns (n_bins, coarsened_pmf).
    """
    min_val     = float(support[0])
    bin_indices = np.floor((support - min_val) / bin_size).astype(int)
    n_bins      = int(bin_indices[-1]) + 1
    coarse      = np.zeros(n_bins)
    for i, b in enumerate(bin_indices):
        coarse[b] += fine_pmf[i]
    total = coarse.sum()
    return n_bins, coarse / total if total > 0 else coarse


def bin_left_edges(support, bin_size, n_bins):
    """Left edge (ms) for each coarsened bin."""
    return float(support[0]) + np.arange(n_bins) * bin_size


def bin_geometry(support, bin_size, n_bins):
    """
    Return (centres, actual_widths) for plotting.

    The last bin is clamped so its right edge does not exceed
    support[-1] + 1 ms.  Without this, the last bin's centre falls
    outside the support whenever (support[-1] - support[0]) is not an
    exact multiple of bin_size -- e.g. value=20 in a 10ms bin would
    place the centre at 25ms instead of 20.5ms.
    """
    left_edges   = bin_left_edges(support, bin_size, n_bins)
    right_edges  = np.minimum(left_edges + bin_size, float(support[-1]) + 1.0)
    actual_widths = right_edges - left_edges
    centres      = left_edges + actual_widths / 2.0
    return centres, actual_widths


def bin_config(dist_name, bin_size):
    """Return (k, n_theory, [n/4, n/2, n, 2n, 4n]) for this (dist, bin_size)."""
    support  = DISTRIBUTIONS[dist_name]["support"]
    fine_pmf = DISTRIBUTIONS[dist_name]["true_pmf"]
    k, _     = coarsen_pmf(support, fine_pmf, bin_size)
    n_theory = math.ceil((k + math.log(1.0 / EPSILON)) / DELTA ** 2)
    return k, n_theory, [
        max(1, n_theory // 4), max(1, n_theory // 2),
        n_theory, n_theory * 2, n_theory * 4,
    ]


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------

def sample_distribution(dist_name, n, rng):
    """Draw n samples via inverse CDF from the named discrete distribution."""
    support  = DISTRIBUTIONS[dist_name]["support"]
    fine_pmf = DISTRIBUTIONS[dist_name]["true_pmf"]
    cdf      = np.cumsum(fine_pmf)
    u        = rng.uniform(size=n)
    indices  = np.clip(np.searchsorted(cdf, u), 0, len(support) - 1)
    return support[indices]


def empirical_coarsened_pmf(samples, support, bin_size, n_bins):
    """Empirical PMF in coarsened bins, normalised."""
    min_val     = float(support[0])
    bin_indices = np.floor((samples - min_val) / bin_size).astype(int)
    counts      = np.zeros(n_bins)
    for b in bin_indices:
        if 0 <= b < n_bins:
            counts[b] += 1
    total = counts.sum()
    return counts / total if total > 0 else counts


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


# ---------------------------------------------------------------------------
# run experiment for one distribution
# ---------------------------------------------------------------------------

def run_distribution(dist_name, dist_config, dist_results_dir):
    """
    For each bin_size, draw samples at all five sizes across all seeds,
    compute TVD, and save to CSV.

    Returns:
        all_tvds[bin_size]  = [tvds_for_n1, ..., tvds_for_n5]   (each a list of len(SEEDS))
        cached_seed1[bin_size] = samples drawn at seed=1, n=n_theory
    """
    data_dir = os.path.join(dist_results_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    support  = dist_config["support"]
    fine_pmf = dist_config["true_pmf"]

    all_tvds     = {}
    cached_seed1 = {}

    print(f"\n  {dist_config['label']}")

    for bin_size in BIN_SIZES:
        k, n_theory, sample_sizes = bin_config(dist_name, bin_size)
        n_bins, coarse_true       = coarsen_pmf(support, fine_pmf, bin_size)

        tvds_by_n = [[] for _ in sample_sizes]

        for i, (label, n) in enumerate(zip(X_TICK_LABELS, sample_sizes)):
            for seed in SEEDS:
                rng     = np.random.default_rng(seed)
                samples = sample_distribution(dist_name, n, rng)

                if seed == 1 and label == "n":
                    cached_seed1[bin_size] = samples

                coarse_emp = empirical_coarsened_pmf(
                    samples, support, bin_size, n_bins
                )
                tvds_by_n[i].append(tvd(coarse_true, coarse_emp))

            print(
                f"    bin={bin_size:>5}ms  k={k:>5}  {label:>4} (n={n:>8,})  "
                f"median TVD={np.median(tvds_by_n[i]):.5f}"
            )

        all_tvds[bin_size] = tvds_by_n

        # Save CSV data for this (distribution, bin_size)
        csv_path = os.path.join(data_dir, f"tvd_bin{bin_size:g}ms.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["dist", "bin_size_ms", "k", "n_theory", "n_label", "n", "seed", "tvd"]
            )
            for i, (label, n) in enumerate(zip(X_TICK_LABELS, sample_sizes)):
                for seed_idx, tvd_val in enumerate(tvds_by_n[i]):
                    writer.writerow([
                        dist_name, bin_size, k, n_theory,
                        label, n, SEEDS[seed_idx], tvd_val,
                    ])

    return all_tvds, cached_seed1


# ---------------------------------------------------------------------------
# per-distribution plots
# ---------------------------------------------------------------------------

def plot_tvd_vs_n(dist_name, dist_config, bin_size, tvds_by_n, results_dir):
    k, n_theory, sample_sizes = bin_config(dist_name, bin_size)
    color = dist_config["color"]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.boxplot(
        tvds_by_n, positions=BOX_POSITIONS, widths=0.55,
        patch_artist=True,
        boxprops=dict(facecolor=color, alpha=0.55),
        medianprops=dict(color="black", linewidth=2),
        flierprops=dict(marker="o", markersize=3, alpha=0.4),
    )
    ax.axhline(DELTA, color="red", linestyle=":", linewidth=1.2,
               label=f"TVD = {DELTA} (target)")

    tick_labels = [f"{lbl}\n({n:,})" for lbl, n in zip(X_TICK_LABELS, sample_sizes)]
    ax.set_xticks(BOX_POSITIONS)
    ax.set_xticklabels(tick_labels)
    ax.set_xlabel("Sample count")
    ax.set_ylabel("Total Variation Distance")
    ax.set_yscale("log")
    ax.set_title(
        f"{dist_config['label']}  --  TVD vs sample count\n"
        f"bin size = {bin_size:g}ms  |  k = {k}  |  n_theory = {n_theory:,}  |  "
        f"epsilon = {EPSILON},  delta = {DELTA}  |  {len(SEEDS)} seeds"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y", which="both")

    out = os.path.join(results_dir, f"tvd_vs_n_bin{bin_size:g}ms.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {out}")


def plot_distribution_comparison(dist_name, dist_config, cached_seed1, results_dir):
    """
    2x4 grid -- one panel per bin size.  Each panel shows:
      - filled bars: empirical coarsened PMF  (seed 1, n = n_theory)
      - outline bars: true coarsened PMF

    All panels share the same x-axis range and 0.005ms minor tick spacing,
    so the effect of each bin resolution is visually comparable.
    Bar width scales with bin_size but has a floor of 0.5ms so sub-ms
    bins remain visible.
    """
    support  = dist_config["support"]
    fine_pmf = dist_config["true_pmf"]

    # x-axis range: half a ms padding either side of the support
    xmin = math.floor((float(support[0])  - 0.5) / PLOT_TICK_STEP) * PLOT_TICK_STEP
    xmax = math.ceil( (float(support[-1]) + 1.5) / PLOT_TICK_STEP) * PLOT_TICK_STEP

    minor_ticks = np.round(
        np.arange(xmin, xmax + PLOT_TICK_STEP, PLOT_TICK_STEP), 4
    )

    fig, axes_grid = plt.subplots(2, 4, figsize=(26, 10), sharey=False)
    axes = axes_grid.flatten()
    fig.suptitle(
        f"{dist_config['label']}  --  Coarsened empirical vs true PMF\n"
        f"seed 1, n = n_theory for each bin size  |  "
        f"x-axis ticks every {PLOT_TICK_STEP}ms",
        fontsize=11,
    )

    for ax, bin_size in zip(axes, BIN_SIZES):
        k, n_theory, sample_sizes = bin_config(dist_name, bin_size)
        n       = sample_sizes[2]   # n_theory
        n_bins, coarse_true = coarsen_pmf(support, fine_pmf, bin_size)
        samples             = cached_seed1[bin_size]
        coarse_emp          = empirical_coarsened_pmf(
            samples, support, bin_size, n_bins
        )

        centres, actual_widths = bin_geometry(support, bin_size, n_bins)
        bar_widths = np.maximum(actual_widths * 0.9, 0.45)

        ax.bar(
            centres, coarse_emp,
            width=bar_widths, color=dist_config["color"], alpha=0.65,
            align="center", label=f"Empirical (n={n:,})",
        )
        ax.bar(
            centres, coarse_true,
            width=bar_widths, facecolor="none", edgecolor="black",
            linewidth=1.2, align="center", label="True PMF",
        )

        ax.set_xlim(xmin, xmax)
        ax.xaxis.set_major_locator(MultipleLocator(1.0))
        ax.set_xticks(minor_ticks, minor=True)
        ax.tick_params(axis="x", which="major", length=6, labelsize=7)
        ax.tick_params(axis="x", which="minor", length=2, width=0.5)
        ax.set_xlabel("Delay (ms)")
        ax.set_ylabel("Probability")
        ax.set_title(
            f"bin size = {bin_size:g}ms  |  k = {k}  |  n_theory = {n_theory:,}"
        )
        ax.legend(fontsize=8)
        ax.grid(True, which="major", alpha=0.3)
        ax.grid(True, which="minor", alpha=0.06, axis="x")

    plt.tight_layout()
    out = os.path.join(results_dir, "dist_comparison.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {out}")


def plot_histogram_per_binsize(dist_name, dist_config, cached_seed1, results_dir):
    """
    One standalone histogram per bin size (seed 1, n = n_theory).

    Bar widths reflect the actual bin extent:
      - Coarse bins (>=1ms): natural width = bin_size * 0.9, showing grouping.
      - Fine bins (<1ms): floored at 0.45ms so integer-spaced bars remain visible.
    The last bin is always clamped to support[-1]+1ms so its centre never
    falls outside the support range.

    X-axis trimmed to the data range; major labels every 0.5ms;
    minor tick marks every 0.05ms.
    """
    BAR_WIDTH_FLOOR = 0.45   # ms -- minimum display width for sub-ms bins
    MAJOR_STEP      = 0.5    # ms -- labelled tick spacing
    MINOR_STEP      = 0.05   # ms -- tick mark spacing

    support  = dist_config["support"]
    fine_pmf = dist_config["true_pmf"]

    hist_dir = os.path.join(results_dir, "histograms")
    os.makedirs(hist_dir, exist_ok=True)

    for bin_size in BIN_SIZES:
        k, n_theory, sample_sizes = bin_config(dist_name, bin_size)
        n = sample_sizes[2]   # n_theory

        n_bins, coarse_true = coarsen_pmf(support, fine_pmf, bin_size)
        samples             = cached_seed1[bin_size]
        coarse_emp          = empirical_coarsened_pmf(
            samples, support, bin_size, n_bins
        )

        centres, actual_widths = bin_geometry(support, bin_size, n_bins)
        bar_widths = np.maximum(actual_widths * 0.9, BAR_WIDTH_FLOOR)

        # x range: natural support extent with half-a-major-step padding
        xmin = math.floor((float(support[0])  - MAJOR_STEP) / MINOR_STEP) * MINOR_STEP
        xmax = math.ceil( (float(support[-1]) + MAJOR_STEP) / MINOR_STEP) * MINOR_STEP

        major_ticks = np.round(
            np.arange(
                math.ceil(xmin  / MAJOR_STEP) * MAJOR_STEP,
                math.floor(xmax / MAJOR_STEP) * MAJOR_STEP + MAJOR_STEP,
                MAJOR_STEP,
            ), 4
        )
        minor_ticks = np.round(
            np.arange(xmin, xmax + MINOR_STEP, MINOR_STEP), 4
        )

        fig, ax = plt.subplots(figsize=(20, 5))

        ax.bar(
            centres, coarse_emp,
            width=bar_widths, color=dist_config["color"], alpha=0.65,
            align="center", label=f"Empirical (n={n:,}, seed=1)",
        )
        ax.bar(
            centres, coarse_true,
            width=bar_widths, facecolor="none", edgecolor="black",
            linewidth=1.2, align="center", label="True PMF",
        )

        ax.set_xlim(xmin, xmax)
        ax.set_xticks(minor_ticks, minor=True)
        ax.set_xticks(major_ticks)
        ax.set_xticklabels([f"{t:g}" for t in major_ticks],
                           rotation=45, ha="right", fontsize=7)
        ax.tick_params(axis="x", which="major", length=6)
        ax.tick_params(axis="x", which="minor", length=3, width=0.6)
        ax.set_xlabel(
            f"Delay (ms)  [major labels every {MAJOR_STEP}ms, "
            f"minor marks every {MINOR_STEP}ms]"
        )
        ax.set_ylabel("Probability")
        ax.set_title(
            f"{dist_config['label']}  --  Empirical vs true PMF  |  "
            f"bin size = {bin_size:g}ms  |  k = {k}  |  n_theory = {n_theory:,}"
        )
        ax.legend(fontsize=9)
        ax.grid(True, which="major", alpha=0.3, axis="x")
        ax.grid(True, which="minor", alpha=0.08, axis="x")

        out = os.path.join(hist_dir, f"histogram_bin{bin_size:g}ms.png")
        plt.tight_layout()
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"    Saved: {out}")


# ---------------------------------------------------------------------------
# summary plots (all distributions)
# ---------------------------------------------------------------------------

def plot_k_and_ntheory_vs_binsize(results_dir):
    """
    Main result: shows that as bin_size decreases (more bins), n_theory
    grows -- finer resolution demands more samples.
    Two panels: k vs bin_size and n_theory vs bin_size.
    """
    colors  = {"binomial": "#9b59b6", "zipf": "#e67e22", "piecewise": "#27ae60"}
    markers = {"binomial": "o", "zipf": "s", "piecewise": "^"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Finer bins require more samples\n"
        f"n_theory = ceil((k + log(1/epsilon)) / delta^2),  "
        f"epsilon = {EPSILON},  delta = {DELTA}",
        fontsize=11,
    )

    for dist_name, dist_config in DISTRIBUTIONS.items():
        ks         = [bin_config(dist_name, b)[0] for b in BIN_SIZES]
        n_theories = [bin_config(dist_name, b)[1] for b in BIN_SIZES]
        kw = dict(
            color=colors[dist_name], marker=markers[dist_name],
            linewidth=2.0, markersize=8, label=dist_config["label"],
        )
        axes[0].plot(BIN_SIZES, ks, **kw)
        axes[1].plot(BIN_SIZES, n_theories, **kw)

    for ax, ylabel, title in [
        (axes[0], "Number of bins  k",         "k vs bin size"),
        (axes[1], "Samples required  n_theory", "n_theory vs bin size"),
    ]:
        ax.set_xscale("log")
        ax.set_xticks(BIN_SIZES)
        ax.set_xticklabels([f"{b:g}ms" for b in BIN_SIZES], fontsize=8)
        ax.set_xlabel("Bin size (ms)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    out = os.path.join(results_dir, "k_and_ntheory_vs_binsize.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_summary(all_results_by_dist, results_dir):
    """Median TVD at n_theory vs bin_size for all distributions."""
    colors  = {"binomial": "#9b59b6", "zipf": "#e67e22", "piecewise": "#27ae60"}
    markers = {"binomial": "o", "zipf": "s", "piecewise": "^"}

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_title(
        f"Median TVD at n_theory vs bin size\n"
        f"epsilon = {EPSILON},  delta = {DELTA},  {len(SEEDS)} seeds",
        fontsize=10,
    )

    for dist_name, dist_config in DISTRIBUTIONS.items():
        medians = [
            float(np.median(all_results_by_dist[dist_name][b][2]))
            for b in BIN_SIZES
        ]
        ax.plot(
            BIN_SIZES, medians,
            color=colors[dist_name], marker=markers[dist_name],
            linewidth=2.0, markersize=8, label=dist_config["label"],
        )

    ax.axhline(DELTA, color="red", linestyle=":", linewidth=1.2,
               label=f"TVD = {DELTA} (target)")
    ax.set_xscale("log")
    ax.set_xticks(BIN_SIZES)
    ax.set_xticklabels([f"{b:g}ms" for b in BIN_SIZES], fontsize=8)
    ax.set_xlabel("Bin size (ms)")
    ax.set_ylabel("Median TVD at n_theory")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, which="both")

    out = os.path.join(results_dir, "tvd_summary.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 70)
    print("Bin size experiment -- discrete distributions (direct sampling)")
    print("=" * 70)
    print(f"  BIN_SIZES : {BIN_SIZES}")
    print(f"  epsilon   : {EPSILON}")
    print(f"  delta     : {DELTA}")
    print(f"  Seeds     : {len(SEEDS)} ({SEEDS[0]}..{SEEDS[-1]})")
    print(f"  Formula   : n_theory = ceil((k + log(1/epsilon)) / delta^2)")
    print()
    header = f"  {'Distribution':<32}  {'Bin size':>9}  {'k':>5}  {'n_theory':>10}"
    print(header)
    print(f"  {'-' * 62}")
    for dist_name, dist_config in DISTRIBUTIONS.items():
        for bin_size in BIN_SIZES:
            k, n_theory, _ = bin_config(dist_name, bin_size)
            print(
                f"  {dist_config['label']:<32}  {bin_size:>8}ms  "
                f"{k:>5}  {n_theory:>10,}"
            )
        print()
    print("=" * 70)


def run():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print_parameters()

    all_results_by_dist = {}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        dist_results_dir = os.path.join(RESULTS_DIR, dist_name)
        os.makedirs(dist_results_dir, exist_ok=True)

        all_tvds, cached_seed1 = run_distribution(
            dist_name, dist_config, dist_results_dir
        )
        all_results_by_dist[dist_name] = all_tvds

        print(f"\n  Plots for {dist_name}...")
        for bin_size in BIN_SIZES:
            plot_tvd_vs_n(
                dist_name, dist_config, bin_size,
                all_tvds[bin_size], dist_results_dir,
            )
        plot_distribution_comparison(
            dist_name, dist_config, cached_seed1, dist_results_dir
        )
        plot_histogram_per_binsize(
            dist_name, dist_config, cached_seed1, dist_results_dir
        )

    print("\nSummary plots...")
    plot_k_and_ntheory_vs_binsize(RESULTS_DIR)
    plot_tvd_summary(all_results_by_dist, RESULTS_DIR)
    print("\nDone.")


if __name__ == "__main__":
    run()
