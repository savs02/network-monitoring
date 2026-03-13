"""
KL divergence experiment.

Computes the theoretically required number of samples using:
    n_theory = ceil((k + log(1/epsilon)) / delta^2)

where:
    k       = number of 1ms bins covering 0-150ms (the resolution of the monitor)
    epsilon = confidence parameter
    delta   = desired accuracy

Then for n in [n/4, n/2, n, 2n], fits a KDE to the delay samples and computes
KL(true || KDE) to measure how accurately the monitor reconstructs the
underlying distribution at each sample count.

Outputs:
    - one distribution plot per (distribution, n) pair
    - one KL divergence vs n plot per distribution
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

# ---------------------------------------------------------------------------
# experiment parameters
# ---------------------------------------------------------------------------

GRID_MIN  = 0.0
GRID_MAX  = 150.0
BIN_WIDTH = 1.0

# bin centres for discretisation
GRID = np.arange(GRID_MIN + BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)
K    = len(GRID)  # number of bins

EPSILON = 0.05
DELTA   = 0.05

n_theory = math.ceil((K + math.log(1.0 / EPSILON)) / (DELTA ** 2))

SAMPLE_SIZES = [
    n_theory // 4,
    n_theory // 2,
    n_theory,
    n_theory * 2,
]

RESULTS_DIR = "../results/sample-complexity"

# distribution configs — must match NS-3 simulation defaults
DISTRIBUTIONS = {
    "normal": {
        "label": "Normal",
        "params": {"mean": 40.0, "variance": 4.0},
        "color": "#3498db",
    },
    "lognormal": {
        "label": "Lognormal",
        "params": {"mu": 2.3, "sigma": 0.2},
        "color": "#e74c3c",
    },
    "weibull": {
        "label": "Weibull",
        "params": {"scale": 10.0, "shape": 2.0},
        "color": "#2ecc71",
    },
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 55)
    print("Experiment parameters")
    print("=" * 55)
    print(f"  Grid        : {GRID_MIN}–{GRID_MAX} ms, bin width = {BIN_WIDTH} ms")
    print(f"  k (bins)    : {K}")
    print(f"  epsilon     : {EPSILON}")
    print(f"  delta       : {DELTA}")
    print(f"  log(1/eps)  : {math.log(1/EPSILON):.6f}")
    print(f"  n_theory    : ceil(({K} + {math.log(1/EPSILON):.4f}) / {DELTA**2})")
    print(f"              = {n_theory}")
    print(f"  Sample sizes: {SAMPLE_SIZES}  (n/4, n/2, n, 2n)")
    print("=" * 55)
    print()


def load_samples(dist_name, n):
    filepath = os.path.join(RESULTS_DIR, f"delay_samples_{dist_name}_{n}.csv")
    return pd.read_csv(filepath)["delay_ms"].values


def true_pdf_on_grid(dist_name, params):
    if dist_name == "normal":
        return stats.norm.pdf(GRID, loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm.pdf(GRID, s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min.pdf(GRID, c=params["shape"], scale=params["scale"])
    raise ValueError(f"Unknown distribution: {dist_name}")


def true_pdf_on_x(dist_name, params, x):
    """Evaluate the true PDF on an arbitrary x array (used for smooth plot curves)."""
    if dist_name == "normal":
        return stats.norm.pdf(x, loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm.pdf(x, s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min.pdf(x, c=params["shape"], scale=params["scale"])
    raise ValueError(f"Unknown distribution: {dist_name}")


def to_probability_masses(pdf_values):
    """Multiply PDF by bin width and normalise so masses sum to 1."""
    masses = pdf_values * BIN_WIDTH
    return masses / masses.sum()


def kl_divergence(true_masses, kde_masses, eps=1e-10):
    """
    KL(true || KDE): expected log ratio under the true distribution.
    Measures how much the KDE diverges from the truth.
    Small epsilon added to KDE to avoid log(0).
    """
    kde_safe = np.clip(kde_masses, eps, None)
    mask = true_masses > 0
    return float(np.sum(true_masses[mask] * np.log(true_masses[mask] / kde_safe[mask])))


def param_label(dist_name, params):
    if dist_name == "normal":
        return f"mean={params['mean']}, variance={params['variance']}"
    elif dist_name == "lognormal":
        return f"mu={params['mu']}, sigma={params['sigma']}"
    elif dist_name == "weibull":
        return f"scale={params['scale']}, shape={params['shape']}"
    return ""


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_distribution(samples, dist_name, dist_config, n, kl_val):
    """
    Plot histogram of samples, KDE estimate, and true PDF for one (dist, n) pair.
    Saved to results/sample-complexity/dist_{dist}_n{n}.png
    """
    params = dist_config["params"]
    color  = dist_config["color"]

    # x range: just wide enough to show the distribution, not the full 0-150ms grid
    true_pdf_fine = true_pdf_on_x(dist_name, params, GRID)
    significant   = GRID[true_pdf_fine > 0.001 * true_pdf_fine.max()]
    x_min = max(GRID_MIN, significant[0]  - 2)
    x_max = min(GRID_MAX, significant[-1] + 2)
    x     = np.linspace(x_min, x_max, 500)

    kde = stats.gaussian_kde(samples, bw_method="scott")

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.hist(samples, bins=60, density=True, alpha=0.3,
            color=color, edgecolor="white", label=f"Samples (n={n:,})")
    ax.plot(x, kde(x), color=color, linewidth=2.0, label="KDE estimate")
    ax.plot(x, true_pdf_on_x(dist_name, params, x), color="black",
            linewidth=1.8, linestyle="--", label="True PDF")

    ax.set_xlim(x_min, x_max)
    ax.set_title(
        f"{dist_config['label']} — n = {n:,}\n"
        f"{param_label(dist_name, params)}    KL = {kl_val:.5f}"
    )
    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Density")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    output_path = os.path.join(RESULTS_DIR, f"dist_{dist_name}_n{n}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_kl_vs_n(dist_name, dist_config, ns, kl_values):
    """KL divergence vs n for one distribution, with n_theory marked."""
    fig, ax = plt.subplots(figsize=(7, 5))

    ax.plot(ns, kl_values, "o-", color=dist_config["color"],
            linewidth=2, markersize=7, label="KL divergence (KDE vs true)")

    ax.axvline(x=n_theory, color="grey", linestyle=":",
               linewidth=1.5, label=f"n_theory = {n_theory:,}")

    ax.set_xscale("log")
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("KL divergence")
    ax.set_title(
        f"KL divergence vs n — {dist_config['label']}\n"
        f"{param_label(dist_name, dist_config['params'])}"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, which="both")

    output_path = os.path.join(RESULTS_DIR, f"kl_{dist_name}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    print_parameters()

    print(f"{'Distribution':<15} {'n':>10} {'KL divergence':>16}")
    print("-" * 45)

    for dist_name, dist_config in DISTRIBUTIONS.items():
        true_masses = to_probability_masses(true_pdf_on_grid(dist_name, dist_config["params"]))

        ns         = []
        kl_values  = []
        first_row  = True

        for n in SAMPLE_SIZES:
            samples   = load_samples(dist_name, n)
            kde       = stats.gaussian_kde(samples, bw_method="scott")
            kde_masses = to_probability_masses(kde(GRID))
            kl_val    = kl_divergence(true_masses, kde_masses)

            label = dist_name if first_row else ""
            print(f"{label:<15} {n:>10,} {kl_val:>16.6f}")
            first_row = False

            plot_distribution(samples, dist_name, dist_config, n, kl_val)

            ns.append(n)
            kl_values.append(kl_val)

        plot_kl_vs_n(dist_name, dist_config, ns, kl_values)
        print()


if __name__ == "__main__":
    run()
