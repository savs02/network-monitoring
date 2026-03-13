"""
Sample complexity experiment: TVD between KDE estimate and true distribution
as a function of sample size n, for each delay distribution.

The KDE is the monitor's reconstructed distribution — it has no knowledge of
the underlying family. TVD is computed post-hoc against the true PDF using a
shared discretisation grid.

Theoretical bound used: delta = sqrt(k * log(1/epsilon) / n)
  k       = number of grid bins
  epsilon = 0.05 (confidence parameter)
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

RESULTS_DIR = "../results/sample-complexity"

SAMPLE_SIZES = [50, 100, 200, 500, 1000, 2000, 5000, 10000]

# grid for discretising both KDE and true PDF
# 0–150ms at 1ms bin width covers all three distributions comfortably
GRID_MIN    = 0.0
GRID_MAX    = 150.0
BIN_WIDTH   = 1.0
GRID        = np.arange(GRID_MIN + BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)  # bin centres
K           = len(GRID)  # number of bins

EPSILON = 0.05  # confidence parameter for the theoretical bound

# distribution configurations — must match NS-3 simulation defaults
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


def to_probability_masses(pdf_values):
    """Multiply PDF by bin width and normalise so masses sum to 1."""
    masses = pdf_values * BIN_WIDTH
    return masses / masses.sum()


def tvd(p, q):
    return 0.5 * np.sum(np.abs(p - q))


def theoretical_bound(n):
    """Upper bound on TVD: sqrt(k * log(1/epsilon) / n), clipped at 1."""
    return min(1.0, np.sqrt(K * np.log(1.0 / EPSILON) / n))


def param_label(dist_name, params):
    if dist_name == "normal":
        return f"mean={params['mean']}, variance={params['variance']}"
    elif dist_name == "lognormal":
        return f"mu={params['mu']}, sigma={params['sigma']}"
    elif dist_name == "weibull":
        return f"scale={params['scale']}, shape={params['shape']}"
    return ""


def run_analysis():
    """Compute TVD for every (distribution, n) pair. Returns list of (dist, n, tvd)."""
    results = []

    for dist_name, dist_config in DISTRIBUTIONS.items():
        true_masses = to_probability_masses(true_pdf_on_grid(dist_name, dist_config["params"]))

        for n in SAMPLE_SIZES:
            samples = load_samples(dist_name, n)

            # KDE using Scott's rule — no knowledge of the underlying family
            kde = stats.gaussian_kde(samples, bw_method="scott")
            kde_masses = to_probability_masses(kde(GRID))

            tvd_value = tvd(kde_masses, true_masses)
            results.append((dist_name, n, tvd_value))

    return results


def print_table(results):
    print(f"\n{'Distribution':<15} {'n':>8} {'TVD':>10}  {'< 0.05?'}")
    print("-" * 47)

    current_dist = None
    for dist_name, n, tvd_val in results:
        if dist_name != current_dist:
            if current_dist is not None:
                print()
            current_dist = dist_name
        marker = "yes" if tvd_val < 0.05 else ""
        print(f"{dist_name:<15} {n:>8} {tvd_val:>10.4f}  {marker}")
    print()


def plot_sample_complexity(results):
    for dist_name, dist_config in DISTRIBUTIONS.items():
        dist_results = [(n, tvd_val) for d, n, tvd_val in results if d == dist_name]
        ns   = [r[0] for r in dist_results]
        tvds = [r[1] for r in dist_results]
        bounds = [theoretical_bound(n) for n in ns]

        fig, ax = plt.subplots(figsize=(7, 5))

        ax.plot(ns, tvds, "o-",
                color=dist_config["color"], linewidth=2, markersize=6,
                label="Empirical TVD (KDE vs true PDF)")

        ax.plot(ns, bounds, "--",
                color="black", linewidth=1.5,
                label=rf"Bound $\sqrt{{k \log(1/\varepsilon) / n}}$, k={K}, $\varepsilon$={EPSILON}")

        ax.axhline(y=0.05, color="grey", linestyle=":", linewidth=1.2,
                   label="TVD = 0.05")

        ax.set_xscale("log")
        ax.set_xlabel("Number of samples (n)")
        ax.set_ylabel("TVD")
        ax.set_title(
            f"Sample complexity — {dist_config['label']}\n"
            f"{param_label(dist_name, dist_config['params'])}"
        )
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

        output_path = os.path.join(RESULTS_DIR, f"sample_complexity_{dist_name}.png")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")


if __name__ == "__main__":
    results = run_analysis()
    print_table(results)
    plot_sample_complexity(results)
