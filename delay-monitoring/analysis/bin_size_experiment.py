"""
Bin size experiment.

For each bin size, the theoretical sample requirement is computed as:
    n_theory = ceil((k + log(1 / epsilon)) / delta^2)
where k is the number of bins covering 0 to 150ms at the given resolution.

Two estimators are compared for each (bin size, distribution, sample count):
  - Kernel Density Estimate (KDE): a smooth continuous estimate fitted to the
    raw samples using Scott's rule, then discretised onto the bin grid.
  - Probability Mass Function (PMF): the raw sample counts rounded to the
    nearest bin and normalised — no smoothing applied.

Both Total Variation Distance (TVD) and Kullback-Leibler (KL) divergence
between the estimate and the true distribution are computed.

The x-axis of all per-distribution plots is normalised: each bin size's
sample counts are expressed as n/4, n/2, n, and 2n relative to its own
n_theory. This puts all bin sizes on a common scale for fair comparison.

Results saved to: results/bin-size-experiment/
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats

# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

BIN_SIZES = [1, 2, 5, 10]   # ms
GRID_MAX  = 150.0
EPSILON   = 0.05
DELTA     = 0.05

BASE_DIR    = "../results/bin-size-experiment"
RESULTS_DIR = "../results/bin-size-experiment"

DISTRIBUTIONS = {
    "normal": {
        "label": "Normal",
        "params": {"mean": 40.0, "variance": 4.0},
    },
    "lognormal": {
        "label": "Lognormal",
        "params": {"mu": 2.3, "sigma": 0.2},
    },
    "weibull": {
        "label": "Weibull",
        "params": {"scale": 10.0, "shape": 2.0},
    },
}

# distinct color and marker per bin size so lines are easily told apart
BIN_STYLE = {
    1:  {"color": "#2196F3", "marker": "o", "label": "1ms bins"},
    2:  {"color": "#FF9800", "marker": "s", "label": "2ms bins"},
    5:  {"color": "#4CAF50", "marker": "^", "label": "5ms bins"},
    10: {"color": "#E91E63", "marker": "D", "label": "10ms bins"},
}

# normalised x positions and their axis labels
X_POSITIONS  = [0.25, 0.5, 1.0, 2.0]   # multiples of n_theory
X_TICK_LABELS = ["n/4", "n/2", "n", "2n"]


def bin_config(bin_size):
    """Return k, n_theory, and the four sample sizes for a given bin size."""
    k        = int(GRID_MAX / bin_size)
    n_theory = math.ceil((k + math.log(1.0 / EPSILON)) / DELTA ** 2)
    return k, n_theory, [n_theory // 4, n_theory // 2, n_theory, n_theory * 2]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 70)
    print("Bin size experiment — parameters")
    print("=" * 70)
    print(f"  Grid max : {GRID_MAX} ms")
    print(f"  epsilon  : {EPSILON}")
    print(f"  delta    : {DELTA}")
    print(f"  Formula  : n_theory = ceil((k + log(1/epsilon)) / delta^2)")
    print()
    print(f"  {'Bin size':>10}  {'k':>5}  {'n_theory':>10}  Sample sizes (n/4, n/2, n, 2n)")
    print(f"  {'-'*65}")
    for b in BIN_SIZES:
        k, n_theory, sizes = bin_config(b)
        size_str = "  ".join(f"{s:,}" for s in sizes)
        print(f"  {b:>9}ms  {k:>5}  {n_theory:>10,}  {size_str}")
    print("=" * 70)
    print()


def load_samples(bin_size, dist_name, n):
    path = os.path.join(BASE_DIR, f"bin_{bin_size}ms",
                        f"delay_samples_{dist_name}_{n}.csv")
    return pd.read_csv(path)["delay_ms"].values


def make_grid(bin_size):
    """Return bin edges and centres for a given bin size."""
    edges   = np.arange(0.0, GRID_MAX + bin_size, bin_size)
    centres = edges[:-1] + bin_size / 2
    return edges, centres


def true_pmf(dist_name, params, bin_edges):
    """True probability mass per bin via CDF differences."""
    if dist_name == "normal":
        cdf = stats.norm.cdf(bin_edges, loc=params["mean"],
                             scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        cdf = stats.lognorm.cdf(bin_edges, s=params["sigma"],
                                scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        cdf = stats.weibull_min.cdf(bin_edges, c=params["shape"],
                                    scale=params["scale"])
    masses = np.diff(cdf)
    return masses / masses.sum()


def kde_pmf(samples, bin_centres, bin_size):
    """
    Kernel Density Estimate discretised onto the bin grid.
    Bandwidth chosen by Scott's rule with no knowledge of the underlying family.
    """
    kde    = stats.gaussian_kde(samples, bw_method="scott")
    masses = kde(bin_centres) * bin_size
    return masses / masses.sum()


def empirical_pmf(samples, bin_size, n_bins, smoothing=0.5):
    """
    Probability Mass Function from raw counts.
    Samples are rounded to the nearest bin. A small pseudocount (Laplace
    smoothing) is added to each bin so that unobserved bins do not cause
    Kullback-Leibler divergence to be undefined.
    """
    bin_indices = np.floor(samples / bin_size).astype(int)
    counts = np.zeros(n_bins)
    for idx in bin_indices:
        if 0 <= idx < n_bins:
            counts[idx] += 1
    smoothed = counts + smoothing
    return smoothed / smoothed.sum()


def tvd(p, q):
    """Total Variation Distance between two probability distributions."""
    return 0.5 * float(np.sum(np.abs(p - q)))


def kl_divergence(true_masses, est_masses, eps=1e-10):
    """
    Kullback-Leibler divergence KL(true || estimate).
    Measures how much the estimate diverges from the true distribution.
    """
    est_safe = np.clip(est_masses, eps, None)
    mask = true_masses > 0
    return float(np.sum(true_masses[mask] * np.log(true_masses[mask] / est_safe[mask])))


def param_label(dist_name, params):
    if dist_name == "normal":
        return f"mean = {params['mean']}, variance = {params['variance']}"
    elif dist_name == "lognormal":
        return f"mu = {params['mu']}, sigma = {params['sigma']}"
    elif dist_name == "weibull":
        return f"scale = {params['scale']}, shape = {params['shape']}"
    return ""


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def ntheory_subtitle(dist_name):
    """
    One-line string listing n_theory for each bin size.
    Placed as a subtitle so the reader knows the absolute sample counts.
    """
    parts = []
    for b in BIN_SIZES:
        k, n_theory, _ = bin_config(b)
        parts.append(f"{b}ms bins: n = {n_theory:,}")
    return "  |  ".join(parts)


def plot_tvd_vs_n(dist_name, dist_config, results_by_binsize):
    """
    Two-panel plot: Total Variation Distance vs sample count for each bin size.
    Left panel: Kernel Density Estimate.  Right panel: Probability Mass Function.
    x-axis is normalised (n/4, n/2, n, 2n) so all bin sizes share the same scale.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)

    fig.suptitle(
        f"{dist_config['label']}  —  Total Variation Distance vs sample count\n"
        f"{param_label(dist_name, dist_config['params'])}",
        fontsize=11
    )

    # subtitle showing n_theory for each bin size
    fig.text(0.5, 0.91, ntheory_subtitle(dist_name),
             ha="center", fontsize=8, color="#555555")

    for ax, estimator_key, estimator_label in [
        (axes[0], "kde", "Kernel Density Estimate (KDE)"),
        (axes[1], "pmf", "Probability Mass Function (PMF)"),
    ]:
        for bin_size, (kde_tvds, pmf_tvds, _kl_kde, _kl_pmf) in results_by_binsize.items():
            style = BIN_STYLE[bin_size]
            tvds  = kde_tvds if estimator_key == "kde" else pmf_tvds

            ax.plot(X_POSITIONS, tvds,
                    color=style["color"],
                    marker=style["marker"],
                    linestyle="-",
                    linewidth=2.0,
                    markersize=7,
                    label=style["label"])

        ax.set_xscale("log")
        ax.xaxis.set_major_locator(mticker.FixedLocator(X_POSITIONS))
        ax.xaxis.set_major_formatter(mticker.FixedFormatter(X_TICK_LABELS))
        ax.xaxis.set_minor_formatter(mticker.NullFormatter())
        ax.set_xlabel("Sample count (relative to n_theory)")
        ax.set_ylabel("Total Variation Distance")
        ax.set_title(estimator_label)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    plt.subplots_adjust(top=0.82)
    out = os.path.join(RESULTS_DIR, f"tvd_vs_n_{dist_name}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_vs_binsize_summary(all_results):
    """
    Summary: Total Variation Distance at n (the theoretical sample count)
    vs bin size, for each distribution.
    Left: Kernel Density Estimate.  Right: Probability Mass Function.
    """
    dist_colors = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
    dist_markers = {"normal": "o", "lognormal": "s", "weibull": "^"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Total Variation Distance at n_theory vs bin size — all distributions\n"
        "n_theory = ceil((k + log(1/epsilon)) / delta^2),  epsilon = 0.05,  delta = 0.05",
        fontsize=11
    )

    for ax, estimator_key, estimator_label in [
        (axes[0], "kde", "Kernel Density Estimate (KDE)"),
        (axes[1], "pmf", "Probability Mass Function (PMF)"),
    ]:
        for dist_name, dist_config in DISTRIBUTIONS.items():
            tvd_at_n = []
            for bin_size in BIN_SIZES:
                kde_tvds, pmf_tvds, _, _ = all_results[dist_name][bin_size]
                tvds = kde_tvds if estimator_key == "kde" else pmf_tvds
                tvd_at_n.append(tvds[2])   # index 2 = n (not n/4, n/2, or 2n)

            ax.plot(BIN_SIZES, tvd_at_n,
                    color=dist_colors[dist_name],
                    marker=dist_markers[dist_name],
                    linestyle="-", linewidth=2.0, markersize=8,
                    label=dist_config["label"])

        ax.set_xlabel("Bin size (ms)")
        ax.set_ylabel("Total Variation Distance at n_theory")
        ax.set_title(estimator_label)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

    out = os.path.join(RESULTS_DIR, "tvd_summary.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print_parameters()

    # all_results[dist_name][bin_size] = (kde_tvds, pmf_tvds, kl_kdes, kl_pmfs)
    all_results = {d: {} for d in DISTRIBUTIONS}

    col = (f"{'Distribution':<12} {'Bin size':>9} {'Sample count':>15} "
           f"{'TVD (KDE)':>11} {'TVD (PMF)':>11} "
           f"{'KL (KDE)':>10} {'KL (PMF)':>10}")
    print(col)
    print("-" * len(col))

    for bin_size in BIN_SIZES:
        k, n_theory, sample_sizes = bin_config(bin_size)
        bin_edges, bin_centres = make_grid(bin_size)
        n_bins = len(bin_centres)

        for dist_name, dist_config in DISTRIBUTIONS.items():
            true_masses = true_pmf(dist_name, dist_config["params"], bin_edges)

            kde_tvds, pmf_tvds, kl_kdes, kl_pmfs = [], [], [], []
            first = True

            for label, n in zip(X_TICK_LABELS, sample_sizes):
                samples = load_samples(bin_size, dist_name, n)

                kde_masses = kde_pmf(samples, bin_centres, bin_size)
                pmf_masses = empirical_pmf(samples, bin_size, n_bins)

                tvd_kde = tvd(true_masses, kde_masses)
                tvd_pmf = tvd(true_masses, pmf_masses)
                kl_kde  = kl_divergence(true_masses, kde_masses)
                kl_pmf  = kl_divergence(true_masses, pmf_masses)

                d_col = dist_name if first else ""
                b_col = f"{bin_size}ms" if first else ""
                print(f"{d_col:<12} {b_col:>9} {label:>6} ({n:>7,}) "
                      f"{tvd_kde:>11.5f} {tvd_pmf:>11.5f} "
                      f"{kl_kde:>10.6f} {kl_pmf:>10.6f}")
                first = False

                kde_tvds.append(tvd_kde)
                pmf_tvds.append(tvd_pmf)
                kl_kdes.append(kl_kde)
                kl_pmfs.append(kl_pmf)

            all_results[dist_name][bin_size] = (kde_tvds, pmf_tvds, kl_kdes, kl_pmfs)
            print()

    print("Generating plots...")
    for dist_name, dist_config in DISTRIBUTIONS.items():
        plot_tvd_vs_n(dist_name, dist_config, all_results[dist_name])

    plot_tvd_vs_binsize_summary(all_results)
    print("Done.")


if __name__ == "__main__":
    run()
