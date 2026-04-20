"""
Bin size experiment — continuous distributions, theoretical (direct sampling).

For each bin size, the theoretical sample requirement is computed as:
    n_theory = ceil((k + log(1 / epsilon)) / delta^2)
where k is the number of bins covering 0 to 150ms at the given resolution.

Two estimators are compared for each (bin size, distribution, sample count):
  - Kernel Density Estimate (KDE): a smooth continuous estimate fitted to the
    raw samples using Scott's rule, then discretised onto the bin grid.
  - Probability Mass Function (PMF): the raw sample counts rounded to the
    nearest bin and normalised — no smoothing applied.

Samples are drawn directly from the configured distributions in Python.
No NS-3 simulation output is required.

TVD between the estimate and the true distribution is computed for each
random seed. Box plots across seeds show the variability of TVD at each
sample count.

Results saved to: results/bin-size-experiment/continuous/
"""

import math
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from scipy import stats
from scipy.signal import fftconvolve
from scipy.interpolate import make_interp_spline

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

BIN_SIZES = [0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]   # ms
GRID_MAX  = 150.0
EPSILON   = 0.05
DELTA     = 0.05
PLOT_BASE_BIN_SIZE = 0.01  # ms; use a common fine plotting scale for comparisons

SEEDS = list(range(1, 101))

RESULTS_DIR = os.path.join(SCRIPT_DIR, "../../../results/bin-size-experiment/continuous")

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

BIN_STYLE = {
    0.01: {"color": "#1a237e", "label": "0.01ms bins"},
    0.05: {"color": "#0288d1", "label": "0.05ms bins"},
    0.1:  {"color": "#00bcd4", "label": "0.1ms bins"},
    0.5:  {"color": "#4caf50", "label": "0.5ms bins"},
    1:    {"color": "#8bc34a", "label": "1ms bins"},
    2:    {"color": "#ff9800", "label": "2ms bins"},
    5:    {"color": "#f44336", "label": "5ms bins"},
    10:   {"color": "#9c27b0", "label": "10ms bins"},
}

X_TICK_LABELS = ["n/4", "n/2", "n", "2n", "4n"]
BOX_POSITIONS = list(range(len(X_TICK_LABELS)))


def bin_config(bin_size):
    """Return k, n_theory, and the five sample sizes for a given bin size."""
    k        = int(GRID_MAX / bin_size)
    n_theory = math.ceil((k + math.log(1.0 / EPSILON)) / DELTA ** 2)
    return k, n_theory, [n_theory // 4, n_theory // 2, n_theory, n_theory * 2, n_theory * 4]


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------

def sample_distribution(dist_name, params, n, rng):
    """Draw n samples directly from the named distribution."""
    if dist_name == "normal":
        return rng.normal(loc=params["mean"],
                          scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(f"Unknown distribution: {dist_name}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 70)
    print("Bin size experiment — continuous distributions (direct sampling)")
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


def make_grid(bin_size):
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


def kde_pmf(samples, bin_edges):
    """
    Kernel Density Estimate discretised onto the bin grid.
    Bandwidth chosen by Scott's rule with no knowledge of the underlying family.

    Uses an FFT convolution approach rather than direct broadcasting:
      1. Bin samples into a histogram over the existing grid.
      2. Convolve with a Gaussian kernel of the Scott's-rule bandwidth.

    This is O(n + k log k) instead of O(n * k), avoiding the memory
    blowup (a 24M x 15000 matrix = ~2.9 TB) that occurs for fine bins
    and large sample counts.  For all practically relevant bandwidths the
    result is indistinguishable from the exact integral.
    """
    n         = len(samples)
    bin_width = bin_edges[1] - bin_edges[0]
    h         = np.std(samples, ddof=1) * n ** (-0.2)   # Scott's rule

    # Bin samples into the existing grid
    counts, _ = np.histogram(samples, bins=bin_edges)
    counts    = counts.astype(float)

    # Gaussian kernel truncated at ±4σ on the same grid
    half_k   = int(np.ceil(4.0 * h / bin_width))
    kernel_x = np.arange(-half_k, half_k + 1) * bin_width
    kernel   = np.exp(-0.5 * (kernel_x / h) ** 2)
    kernel  /= kernel.sum()

    smoothed = fftconvolve(counts, kernel, mode="same")
    smoothed = np.maximum(smoothed, 0.0)
    total    = smoothed.sum()
    return smoothed / total if total > 0 else smoothed


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
    _, n_theory, sample_sizes = bin_config(bin_size)
    color = BIN_STYLE[bin_size]["color"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)
    fig.suptitle(
        f"{dist_config['label']}  —  TVD vs sample count  |  {bin_size:g}ms bins\n"
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
    out = os.path.join(RESULTS_DIR, f"tvd_vs_n_{dist_name}_bin{bin_size:g}ms.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def dist_xlim(dist_name, params):
    if dist_name == "normal":
        d = stats.norm(loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        d = stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        d = stats.weibull_min(c=params["shape"], scale=params["scale"])
    xmin = max(0.0, d.ppf(0.001))
    xmax = d.ppf(0.999)
    xmin = math.floor(xmin / PLOT_BASE_BIN_SIZE) * PLOT_BASE_BIN_SIZE
    xmax = math.ceil(xmax / PLOT_BASE_BIN_SIZE) * PLOT_BASE_BIN_SIZE
    return xmin, xmax


def true_pdf_fine(dist_name, params, x):
    if dist_name == "normal":
        return stats.norm.pdf(x, loc=params["mean"],
                              scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm.pdf(x, s=params["sigma"],
                                 scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min.pdf(x, c=params["shape"],
                                     scale=params["scale"])


def plot_distribution_comparison(dist_name, dist_config, cached_samples):
    """
    2x4 grid (one panel per bin size) overlaying empirical PMF bars,
    a smoothed spline through the bar tops, and the true PDF.
    Uses seed 1 at n_theory samples.

    All panels are drawn on the same 0.01ms base scale so the visual effect
    of each coarser bin size remains directly comparable.
    """
    params = dist_config["params"]
    xmin, xmax = dist_xlim(dist_name, params)
    x_fine = np.arange(xmin, xmax + PLOT_BASE_BIN_SIZE, PLOT_BASE_BIN_SIZE)
    true_pdf_vals = true_pdf_fine(dist_name, params, x_fine)

    fig, axes_grid = plt.subplots(2, 4, figsize=(26, 10), sharey=False)
    axes = axes_grid.flatten()
    fig.suptitle(
        f"{dist_config['label']}  —  Empirical PMF, smoothed PMF, and true PDF\n"
        f"{param_label(dist_name, params)}  |  seed 1, n = n_theory",
        fontsize=11
    )

    for ax, bin_size in zip(axes, BIN_SIZES):
        _, n_theory, sample_sizes = bin_config(bin_size)
        n = sample_sizes[2]
        bin_edges, bin_centres = make_grid(bin_size)
        n_bins = len(bin_centres)

        samples = cached_samples[dist_name][bin_size]

        pmf_masses  = empirical_pmf(samples, bin_size, n_bins)
        pmf_density = pmf_masses / bin_size

        visible = (bin_centres >= xmin) & (bin_centres <= xmax)
        centres_visible     = bin_centres[visible]
        pmf_density_visible = pmf_density[visible]

        if len(centres_visible) >= 4:
            spline = make_interp_spline(centres_visible, pmf_density_visible, k=3)
        else:
            spline = make_interp_spline(centres_visible, pmf_density_visible,
                                        k=len(centres_visible) - 1)
        spline_vals = np.clip(spline(x_fine), 0, None)

        ax.bar(bin_centres[visible], pmf_density[visible],
               width=bin_size * 0.85, color="#FF9800", alpha=0.55,
               label="Empirical PMF")
        ax.plot(x_fine, spline_vals, color="#9b59b6", linewidth=2.0,
                label="Smoothed PMF")
        ax.plot(x_fine, true_pdf_vals, color="black", linewidth=2.0,
                linestyle="--", label="True PDF")

        ax.set_xlim(xmin, xmax)
        ax.xaxis.set_major_locator(MultipleLocator(1.0))
        minor_ticks = np.round(
            np.arange(xmin, xmax + PLOT_BASE_BIN_SIZE, PLOT_BASE_BIN_SIZE), 3
        )
        ax.set_xticks(minor_ticks, minor=True)
        ax.tick_params(axis="x", which="major", length=6, labelsize=7)
        ax.tick_params(axis="x", which="minor", length=2, width=0.5)
        ax.set_xlabel("Delay (ms)")
        ax.set_ylabel("Probability density")
        ax.set_title(f"{bin_size:g}ms bins  |  n = {n:,}")
        ax.legend(fontsize=8)
        ax.grid(True, which="major", alpha=0.3)
        ax.grid(True, which="minor", alpha=0.1, axis="x")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, f"dist_comparison_{dist_name}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_vs_binsize_summary(all_results):
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
                tvds_at_n = all_results[dist_name][bin_size][estimator_key][2]
                medians.append(float(np.median(tvds_at_n)))

            ax.plot(BIN_SIZES, medians,
                    color=dist_colors[dist_name],
                    marker=dist_markers[dist_name],
                    linestyle="-", linewidth=2.0, markersize=8,
                    label=dist_config["label"])

        ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
                   label=f"TVD = {DELTA} (accuracy target)")
        ax.set_xscale("log")
        ax.set_xticks(BIN_SIZES)
        ax.set_xticklabels([f"{b:g}" for b in BIN_SIZES], fontsize=8)
        ax.set_xlabel("Bin size (ms)")
        ax.set_ylabel("Median TVD at n_theory")
        ax.set_title(estimator_label)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

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

    all_results    = {d: {} for d in DISTRIBUTIONS}
    cached_samples = {d: {} for d in DISTRIBUTIONS}

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
                    rng     = np.random.default_rng(seed)
                    samples = sample_distribution(
                        dist_name, dist_config["params"], n, rng
                    )

                    if seed == 1 and label == "n":
                        cached_samples[dist_name][bin_size] = samples

                    kde_masses = kde_pmf(samples, bin_edges)
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
        plot_distribution_comparison(dist_name, dist_config, cached_samples)

    plot_tvd_vs_binsize_summary(all_results)
    print("Done.")


if __name__ == "__main__":
    run()
