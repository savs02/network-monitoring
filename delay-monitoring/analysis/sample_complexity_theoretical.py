"""
Sample complexity experiment — theoretical (direct sampling).

Identical in structure to sample_complexity.py but samples are drawn
directly from the configured distributions in Python rather than loaded
from NS-3 simulation output.  This allows multiple independent seeds to
be run cheaply, so the plot shows median TVD with an interquartile band
across seeds instead of a single trace.

Theoretical bound used: delta = sqrt(k * log(1/epsilon) / n)
  k       = number of grid bins
  epsilon = 0.05 (confidence parameter)

Results saved to: results/sample-complexity-theoretical/
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/sample-complexity-theoretical")

SAMPLE_SIZES = [50, 100, 200, 500, 1000, 2000, 5000, 10000]
SEEDS        = list(range(1, 31))   # 30 independent draws per sample size

# grid for discretising both KDE and true PDF
GRID_MIN  = 0.0
GRID_MAX  = 150.0
BIN_WIDTH = 1.0
GRID      = np.arange(GRID_MIN + BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)  # bin centres
K         = len(GRID)

EPSILON = 0.05

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


def sample_distribution(dist_name, params, n, rng):
    """Draw n samples directly from the named distribution."""
    if dist_name == "normal":
        return rng.normal(loc=params["mean"],
                          scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        # numpy.weibull gives the standard Weibull (scale=1); multiply by scale
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(f"Unknown distribution: {dist_name}")


def true_pdf_on_grid(dist_name, params):
    if dist_name == "normal":
        return stats.norm.pdf(GRID, loc=params["mean"],
                              scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm.pdf(GRID, s=params["sigma"],
                                 scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min.pdf(GRID, c=params["shape"],
                                     scale=params["scale"])
    raise ValueError(f"Unknown distribution: {dist_name}")


def to_probability_masses(pdf_values):
    masses = pdf_values * BIN_WIDTH
    return masses / masses.sum()


def tvd(p, q):
    return 0.5 * np.sum(np.abs(p - q))


def theoretical_bound(n):
    return min(1.0, np.sqrt((K + np.log(1.0 / EPSILON)) / n))


def param_label(dist_name, params):
    if dist_name == "normal":
        return f"mean={params['mean']}, variance={params['variance']}"
    elif dist_name == "lognormal":
        return f"mu={params['mu']}, sigma={params['sigma']}"
    elif dist_name == "weibull":
        return f"scale={params['scale']}, shape={params['shape']}"
    return ""


def run_analysis():
    """
    For every (distribution, sample size, seed) triple, draw samples, fit a
    KDE, and compute TVD against the true distribution.

    Returns a dict:
        results[dist_name][n] = list of TVD values (one per seed)
    """
    results = {d: {n: [] for n in SAMPLE_SIZES} for d in DISTRIBUTIONS}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        true_masses = to_probability_masses(
            true_pdf_on_grid(dist_name, dist_config["params"])
        )

        for n in SAMPLE_SIZES:
            for seed in SEEDS:
                rng     = np.random.default_rng(seed)
                samples = sample_distribution(
                    dist_name, dist_config["params"], n, rng
                )

                kde        = stats.gaussian_kde(samples, bw_method="scott")
                kde_masses = to_probability_masses(kde(GRID))

                results[dist_name][n].append(tvd(kde_masses, true_masses))

            tvd_vals = results[dist_name][n]
            print(
                f"  {dist_name:<12}  n={n:>7,}  "
                f"median={np.median(tvd_vals):.5f}  "
                f"IQR=[{np.percentile(tvd_vals, 25):.5f}, "
                f"{np.percentile(tvd_vals, 75):.5f}]"
            )

    return results


def print_table(results):
    print(f"\n{'Distribution':<15} {'n':>8} {'Median TVD':>12}  {'< 0.05?'}")
    print("-" * 50)

    for dist_name in DISTRIBUTIONS:
        print()
        for n in SAMPLE_SIZES:
            median = np.median(results[dist_name][n])
            marker = "yes" if median < 0.05 else ""
            print(f"{dist_name:<15} {n:>8} {median:>12.4f}  {marker}")


def plot_sample_complexity(results):
    for dist_name, dist_config in DISTRIBUTIONS.items():
        ns      = SAMPLE_SIZES
        medians = [np.median(results[dist_name][n]) for n in ns]
        q25     = [np.percentile(results[dist_name][n], 25) for n in ns]
        q75     = [np.percentile(results[dist_name][n], 75) for n in ns]
        bounds  = [theoretical_bound(n) for n in ns]

        fig, ax = plt.subplots(figsize=(7, 5))

        ax.fill_between(ns, q25, q75,
                        color=dist_config["color"], alpha=0.2,
                        label="IQR across seeds")
        ax.plot(ns, medians, "o-",
                color=dist_config["color"], linewidth=2, markersize=6,
                label="Median TVD (KDE vs true PDF)")
        ax.plot(ns, bounds, "--",
                color="black", linewidth=1.5,
                label=rf"Bound $\sqrt{{k \log(1/\varepsilon) / n}}$, "
                      rf"k={K}, $\varepsilon$={EPSILON}")
        ax.axhline(y=0.05, color="grey", linestyle=":", linewidth=1.2,
                   label="TVD = 0.05")

        ax.set_xscale("log")
        ax.set_xlabel("Number of samples (n)")
        ax.set_ylabel("TVD")
        ax.set_title(
            f"Sample complexity — {dist_config['label']} (direct sampling)\n"
            f"{param_label(dist_name, dist_config['params'])}  |  "
            f"{len(SEEDS)} seeds"
        )
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

        out = os.path.join(RESULTS_DIR, f"sample_complexity_{dist_name}.png")
        plt.tight_layout()
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")


if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"Running theoretical sample complexity experiment")
    print(f"  Distributions : {list(DISTRIBUTIONS.keys())}")
    print(f"  Sample sizes  : {SAMPLE_SIZES}")
    print(f"  Seeds         : {len(SEEDS)} ({SEEDS[0]}..{SEEDS[-1]})")
    print(f"  Grid          : {GRID_MIN}–{GRID_MAX}ms, {BIN_WIDTH}ms bins, k={K}")
    print()

    results = run_analysis()
    print_table(results)
    plot_sample_complexity(results)
