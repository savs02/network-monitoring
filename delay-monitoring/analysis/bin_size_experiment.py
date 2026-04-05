"""
Bin size experiment — multi-seed.

For each bin size, the theoretical sample requirement is computed as:
    n_theory = ceil((k + log(1 / epsilon)) / delta^2)
where k is the number of bins covering 0 to 150ms at the given resolution.

Two estimators are compared for each (bin size, distribution, sample count):
  - Kernel Density Estimate (KDE): a smooth continuous estimate fitted to the
    raw samples using Scott's rule, then discretised onto the bin grid.
  - Probability Mass Function (PMF): the raw sample counts rounded to the
    nearest bin and normalised — no smoothing applied.

TVD between the estimate and the true distribution is computed for each
random seed. Box plots across seeds show the variability of TVD at each
sample count, using the same multi-seed methodology as the discrete experiment.

The x-axis of all per-distribution-per-binsize plots is normalised:
sample counts are expressed as n/4, n/2, n, and 2n relative to n_theory.

Results saved to: results/bin-size-experiment/
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

BIN_SIZES = [1, 2, 5, 10]   # ms
GRID_MAX  = 150.0
EPSILON   = 0.05
DELTA     = 0.05

SEEDS = list(range(1, 31))   # 30 random seeds (NS-3 RngRun values)

BASE_DIR    = os.path.join(SCRIPT_DIR, "../results/bin-size-experiment")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/bin-size-experiment")

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

# distinct colour per bin size
BIN_STYLE = {
    1:  {"color": "#2196F3", "label": "1ms bins"},
    2:  {"color": "#FF9800", "label": "2ms bins"},
    5:  {"color": "#4CAF50", "label": "5ms bins"},
    10: {"color": "#E91E63", "label": "10ms bins"},
}

# normalised x positions and their axis labels
X_TICK_LABELS = ["n/4", "n/2", "n", "2n", "4n"]
BOX_POSITIONS = list(range(len(X_TICK_LABELS)))


def bin_config(bin_size):
    """Return k, n_theory, and the four sample sizes for a given bin size."""
    k        = int(GRID_MAX / bin_size)
    n_theory = math.ceil((k + math.log(1.0 / EPSILON)) / DELTA ** 2)
    return k, n_theory, [n_theory // 4, n_theory // 2, n_theory, n_theory * 2, n_theory * 4]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 70)
    print("Bin size experiment — parameters (multi-seed)")
    print("=" * 70)
    print(f"  Grid max : {GRID_MAX} ms")
    print(f"  epsilon  : {EPSILON}")
    print(f"  delta    : {DELTA}")
    print(f"  Seeds    : {len(SEEDS)} ({SEEDS[0]}..{SEEDS[-1]})")
    print(f"  Formula  : n_theory = ceil((k + log(1/epsilon)) / delta^2)")
    print()
    print(f"  {'Bin size':>10}  {'k':>5}  {'n_theory':>10}  Sample sizes (n/4, n/2, n, 2n, 4n)")
    print(f"  {'-'*65}")
    for b in BIN_SIZES:
        k, n_theory, sizes = bin_config(b)
        size_str = "  ".join(f"{s:,}" for s in sizes)
        print(f"  {b:>9}ms  {k:>5}  {n_theory:>10,}  {size_str}")
    print("=" * 70)
    print()


def load_samples(bin_size, dist_name, n, seed):
    path = os.path.join(BASE_DIR, f"bin_{bin_size}ms",
                        f"delay_samples_{dist_name}_{n}_seed{seed}.csv")
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


def empirical_pmf(samples, bin_size, n_bins):
    """Probability Mass Function from raw counts, rounded to the nearest bin."""
    bin_indices = np.floor(samples / bin_size).astype(int)
    counts = np.zeros(n_bins)
    for idx in bin_indices:
        if 0 <= idx < n_bins:
            counts[idx] += 1
    total = counts.sum()
    return counts / total if total > 0 else counts


def tvd(p, q):
    """Total Variation Distance between two probability distributions."""
    return 0.5 * float(np.sum(np.abs(p - q)))


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

def plot_tvd_vs_n(dist_name, dist_config, bin_size, kde_tvds_by_n, pmf_tvds_by_n):
    """
    Two-panel box plot of TVD vs sample count for one distribution and bin size.
    Left panel: Kernel Density Estimate.  Right panel: Probability Mass Function.
    Each box shows the spread of TVD across all seeds at that sample count.
    """
    _, n_theory, sample_sizes = bin_config(bin_size)
    color = BIN_STYLE[bin_size]["color"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)
    fig.suptitle(
        f"{dist_config['label']}  —  TVD vs sample count  |  {bin_size}ms bins\n"
        f"{param_label(dist_name, dist_config['params'])}",
        fontsize=11
    )
    fig.text(
        0.5, 0.91,
        f"n_theory = {n_theory:,}  |  k = {int(GRID_MAX / bin_size)}  |  "
        f"ε = {EPSILON}, δ = {DELTA}  |  {len(SEEDS)} seeds",
        ha="center", fontsize=8, color="#555555"
    )

    for ax, tvds_by_n, estimator_label in [
        (axes[0], kde_tvds_by_n, "Kernel Density Estimate (KDE)"),
        (axes[1], pmf_tvds_by_n, "Probability Mass Function (PMF)"),
    ]:
        ax.boxplot(tvds_by_n, positions=BOX_POSITIONS, widths=0.5,
                   patch_artist=True,
                   boxprops=dict(facecolor=color, alpha=0.5),
                   medianprops=dict(color="black", linewidth=2),
                   flierprops=dict(marker="o", markersize=3, alpha=0.4))

        ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
                   label=f"TVD = {DELTA} (accuracy target)")

        tick_labels = [f"{l}\n({n:,})" for l, n in zip(X_TICK_LABELS, sample_sizes)]
        ax.set_xticks(BOX_POSITIONS)
        ax.set_xticklabels(tick_labels)
        ax.set_xlabel("Sample count")
        ax.set_ylabel("Total Variation Distance")
        ax.set_yscale("log")
        ax.set_title(estimator_label)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, axis="y", which="both")

    plt.subplots_adjust(top=0.82)
    out = os.path.join(RESULTS_DIR,
                       f"tvd_vs_n_{dist_name}_bin{bin_size}ms.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def dist_xlim(dist_name, params):
    """Return (xmin, xmax) covering the 0.1th–99.9th percentile of the distribution."""
    if dist_name == "normal":
        d = stats.norm(loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        d = stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        d = stats.weibull_min(c=params["shape"], scale=params["scale"])
    return max(0.0, d.ppf(0.001)), d.ppf(0.999)


def true_pdf_fine(dist_name, params, x):
    """Evaluate the true PDF at points x."""
    if dist_name == "normal":
        return stats.norm.pdf(x, loc=params["mean"],
                              scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm.pdf(x, s=params["sigma"],
                                 scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min.pdf(x, c=params["shape"],
                                     scale=params["scale"])


def plot_distribution_comparison(dist_name, dist_config):
    """
    For 1ms and 2ms bins, overlay the true underlying PDF, empirical PMF
    (as a bar histogram), and KDE on the same axes.  Uses seed 1 at n_theory
    samples as a representative single run.

    This motivates the choice to focus on finer bins: coarser bins visibly
    lose the shape of the underlying distribution, while the KDE adds a
    smoothing approximation on top of the PMF.
    """
    bin_sizes_to_show = [1, 2, 5, 10]
    params = dist_config["params"]

    xmin, xmax = dist_xlim(dist_name, params)
    x_fine = np.linspace(xmin, xmax, 1000)
    true_pdf_vals = true_pdf_fine(dist_name, params, x_fine)

    fig, axes_grid = plt.subplots(2, 2, figsize=(14, 10), sharey=False)
    axes = axes_grid.flatten()
    fig.suptitle(
        f"{dist_config['label']}  —  Underlying distribution, PMF, and KDE\n"
        f"{param_label(dist_name, params)}  |  seed 1, n = n_theory",
        fontsize=11
    )

    for ax, bin_size in zip(axes, bin_sizes_to_show):
        _, n_theory, sample_sizes = bin_config(bin_size)
        n = sample_sizes[2]   # n_theory
        bin_edges, bin_centres = make_grid(bin_size)
        n_bins = len(bin_centres)

        samples = load_samples(bin_size, dist_name, n, seed=1)

        # PMF masses converted to density for a common y-axis scale
        pmf_masses = empirical_pmf(samples, bin_size, n_bins)
        pmf_density = pmf_masses / bin_size

        # KDE as continuous density
        kde_obj  = stats.gaussian_kde(samples, bw_method="scott")
        kde_vals = kde_obj(x_fine)

        # restrict bar centres to the visible x range
        visible = (bin_centres >= xmin) & (bin_centres <= xmax)

        ax.bar(bin_centres[visible], pmf_density[visible],
               width=bin_size * 0.9, color="#FF9800", alpha=0.55,
               label=f"PMF ({bin_size}ms bins)")
        ax.plot(x_fine, kde_vals, color="#9b59b6", linewidth=2.0,
                label="KDE (Scott's rule)")
        ax.plot(x_fine, true_pdf_vals, color="black", linewidth=2.0,
                linestyle="--", label="True distribution")

        ax.set_xlim(xmin, xmax)
        ax.set_xlabel("Delay (ms)")
        ax.set_ylabel("Probability density")
        ax.set_title(f"{bin_size}ms bins  |  n = {n:,}")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, f"dist_comparison_{dist_name}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_vs_binsize_summary(all_results):
    """
    Summary: median TVD at n_theory vs bin size, for each distribution.
    Left panel: KDE.  Right panel: PMF.
    """
    dist_colors  = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
    dist_markers = {"normal": "o", "lognormal": "s", "weibull": "^"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Median TVD at n_theory vs bin size — all distributions\n"
        f"n_theory = ceil((k + log(1/ε)) / δ²),  ε = {EPSILON},  δ = {DELTA},  "
        f"{len(SEEDS)} seeds",
        fontsize=11
    )

    for ax, estimator_key, estimator_label in [
        (axes[0], "kde", "Kernel Density Estimate (KDE)"),
        (axes[1], "pmf", "Probability Mass Function (PMF)"),
    ]:
        for dist_name, dist_config in DISTRIBUTIONS.items():
            medians = []
            for bin_size in BIN_SIZES:
                tvds_at_n = all_results[dist_name][bin_size][estimator_key][2]  # index 2 = n
                medians.append(float(np.median(tvds_at_n)))

            ax.plot(BIN_SIZES, medians,
                    color=dist_colors[dist_name],
                    marker=dist_markers[dist_name],
                    linestyle="-", linewidth=2.0, markersize=8,
                    label=dist_config["label"])

        ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
                   label=f"TVD = {DELTA} (accuracy target)")
        ax.set_xlabel("Bin size (ms)")
        ax.set_ylabel("Median TVD at n_theory")
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

    # all_results[dist_name][bin_size] = {
    #   'kde': [tvds_for_n1, tvds_for_n2, tvds_for_n3, tvds_for_n4],
    #   'pmf': [tvds_for_n1, tvds_for_n2, tvds_for_n3, tvds_for_n4],
    # }
    # each tvds_for_ni is a list of len(SEEDS) TVD values
    all_results = {d: {} for d in DISTRIBUTIONS}

    for bin_size in BIN_SIZES:
        k, n_theory, sample_sizes = bin_config(bin_size)
        bin_edges, bin_centres = make_grid(bin_size)
        n_bins = len(bin_centres)

        print(f"\n=== bin_size={bin_size}ms  k={k}  n_theory={n_theory:,} ===")

        for dist_name, dist_config in DISTRIBUTIONS.items():
            true_masses = true_pmf(dist_name, dist_config["params"], bin_edges)

            kde_tvds_by_n = [[] for _ in sample_sizes]
            pmf_tvds_by_n = [[] for _ in sample_sizes]

            for i, (label, n) in enumerate(zip(X_TICK_LABELS, sample_sizes)):
                for seed in SEEDS:
                    samples = load_samples(bin_size, dist_name, n, seed)

                    kde_masses = kde_pmf(samples, bin_centres, bin_size)
                    pmf_masses = empirical_pmf(samples, bin_size, n_bins)

                    kde_tvds_by_n[i].append(tvd(true_masses, kde_masses))
                    pmf_tvds_by_n[i].append(tvd(true_masses, pmf_masses))

                print(f"  {dist_name:<12} {label:>4} (n={n:>8,})  "
                      f"KDE median={np.median(kde_tvds_by_n[i]):.5f}  "
                      f"PMF median={np.median(pmf_tvds_by_n[i]):.5f}")

            all_results[dist_name][bin_size] = {
                "kde": kde_tvds_by_n,
                "pmf": pmf_tvds_by_n,
            }

    print("\nGenerating plots...")
    for dist_name, dist_config in DISTRIBUTIONS.items():
        for bin_size in BIN_SIZES:
            r = all_results[dist_name][bin_size]
            plot_tvd_vs_n(dist_name, dist_config, bin_size,
                          r["kde"], r["pmf"])
        plot_distribution_comparison(dist_name, dist_config)

    plot_tvd_vs_binsize_summary(all_results)
    print("Done.")


if __name__ == "__main__":
    run()
