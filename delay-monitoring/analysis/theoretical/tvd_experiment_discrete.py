"""
TVD experiment — discrete distributions, theoretical mode (multi-seed).

Compares three discrete delay distributions:
  - Binomial(N=20, p=0.5)
  - Zipf(N=20, alpha=1.5)
  - Piecewise (irregular multi-modal, k=20)

For each distribution, loads samples across 100 seeds, computes TVD, and
produces box plots vs n with the theoretical bound overlaid.

Note: KS test is not applied to discrete distributions because scipy.stats.kstest
is designed for continuous distributions.  For a discrete CDF, D_n converges to
max_k P(X=k) rather than 0, making the statistic uninformative.

Theoretical sample requirement:
    n_theory = ceil((k + log(1/epsilon)) / delta^2)
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# experiment parameters
# ---------------------------------------------------------------------------

EPSILON = 0.05
DELTA   = 0.05
SEEDS   = list(range(1, 101))

RESULTS_DIR = os.path.join(SCRIPT_DIR, "../../results/sample-complexity/discrete/theoretical/seeded")

DISTRIBUTIONS = {
    "binomial": {
        "label":        "Binomial(N=20, p=0.5)",
        "color":        "#9b59b6",
        "support":      np.arange(0, 21),
        "k":            21,
        "true_pmf":     lambda support: stats.binom.pmf(support, n=20, p=0.5),
        # n_theory = ceil((21 + ln(1/0.05)) / 0.05^2) = 9599
        "n_theory":     9599,
        "sample_sizes": [480, 960, 2400, 4800, 9599, 19197, 38393],
    },
    "zipf": {
        "label":        "Zipf(N=20, alpha=1.5)",
        "color":        "#e67e22",
        "support":      np.arange(1, 21),
        "k":            20,
        "true_pmf":     lambda support: stats.zipfian.pmf(support, a=1.5, n=20),
        # n_theory = ceil((20 + ln(1/0.05)) / 0.05^2) = 9199
        "n_theory":     9199,
        "sample_sizes": [460, 920, 2300, 4599, 9199, 18397, 36793],
    },
    "piecewise": {
        "label":        "Piecewise (irregular multi-modal)",
        "color":        "#27ae60",
        "support":      np.arange(1, 21),
        "k":            20,
        "true_pmf":     lambda support: np.array([
                            0.12, 0.02, 0.08, 0.01, 0.10, 0.03, 0.07, 0.12, 0.02, 0.09,
                            0.01, 0.08, 0.04, 0.06, 0.02, 0.05, 0.02, 0.04, 0.01, 0.01
                        ]),
        # n_theory = ceil((20 + ln(1/0.05)) / 0.05^2) = 9199
        "n_theory":     9199,
        "sample_sizes": [460, 920, 2300, 4599, 9199, 18397, 36793],
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 60)
    print("Discrete TVD experiment parameters (multi-seed)")
    print("=" * 60)
    for name, d in DISTRIBUTIONS.items():
        print(f"  {d['label']}")
        print(f"    k (outcomes) : {d['k']}")
        print(f"    n_theory     : {d['n_theory']:,}")
        print(f"    sample sizes : {d['sample_sizes']}")
    print(f"  epsilon : {EPSILON}    delta : {DELTA}")
    print(f"  seeds   : 1 - {max(SEEDS)}")
    print("=" * 60)
    print()


def load_samples(dist_name, n, seed):
    filepath = os.path.join(RESULTS_DIR, f"delay_samples_{dist_name}_{n}_seed{seed}.csv")
    raw = pd.read_csv(filepath)["delay_ms"].values
    return np.round(raw).astype(int)


def empirical_pmf(samples, support):
    counts = np.zeros(len(support))
    lo, hi = support[0], support[-1]
    for val in samples:
        if lo <= val <= hi:
            counts[val - lo] += 1
    total = counts.sum()
    return counts / total if total > 0 else counts


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def theoretical_bound(n, n_theory):
    return min(1.0, DELTA * math.sqrt(n_theory / n))


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_distribution(emp_pmf, true_pmf_vals, support, dist_config, n, tvd_val, seed):
    fig, ax = plt.subplots(figsize=(9, 4))

    bar_width = 0.35
    ax.bar(support - bar_width / 2, emp_pmf, width=bar_width,
           color=dist_config["color"], alpha=0.7,
           label=f"Empirical PMF (n={n:,}, seed={seed})")
    ax.bar(support + bar_width / 2, true_pmf_vals, width=bar_width,
           color="black", alpha=0.5, label="True PMF")

    ax.set_title(f"{dist_config['label']} — n = {n:,}, seed = {seed}\nTVD = {tvd_val:.6f}")
    ax.set_xlabel("Delay (ms, integer-valued)")
    ax.set_ylabel("Probability")
    ax.set_xticks(support)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    dist_name = [k for k, v in DISTRIBUTIONS.items() if v is dist_config][0]
    output_path = os.path.join(RESULTS_DIR, f"dist_{dist_name}_n{n}_seed{seed}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {output_path}")


def plot_tvd_vs_n(dist_name, dist_config, ns, tvd_by_n):
    n_theory = dist_config["n_theory"]

    fig, ax = plt.subplots(figsize=(12, 7))

    positions = list(range(len(ns)))
    data      = [tvd_by_n[n] for n in ns]
    bounds    = [theoretical_bound(n, n_theory) for n in ns]

    ax.boxplot(data, positions=positions, widths=0.4,
               patch_artist=True,
               boxprops=dict(facecolor=dist_config["color"], alpha=0.5),
               medianprops=dict(color="black", linewidth=2),
               flierprops=dict(marker="o", markersize=4, alpha=0.5))

    ax.plot(positions, bounds, "--", color="black", linewidth=1.5,
            label=rf"Theoretical bound ($n_{{theory}}={n_theory:,}$)")
    ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
               label=f"TVD = {DELTA} (accuracy target)")

    ax.set_xticks(positions)
    ax.set_xticklabels([f"{n:,}" for n in ns], rotation=15)
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("Total Variation Distance")
    ax.set_title(f"TVD vs n — {dist_config['label']}\nEmpirical PMF, {len(SEEDS)} seeds")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")

    output_path = os.path.join(RESULTS_DIR, f"tvd_{dist_name}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {output_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    print_parameters()

    for dist_name, dist_config in DISTRIBUTIONS.items():
        print(f"--- {dist_config['label']} ---")

        support       = dist_config["support"]
        true_pmf_vals = dist_config["true_pmf"](support)
        sample_sizes  = dist_config["sample_sizes"]

        print(f"  {'n':>10} {'median TVD':>12} {'min TVD':>10} {'max TVD':>10}")
        print("  " + "-" * 46)

        tvd_by_n = {}

        for n in sample_sizes:
            tvd_vals = []

            for seed in SEEDS:
                samples = load_samples(dist_name, n, seed)
                emp     = empirical_pmf(samples, support)
                tvd_vals.append(tvd(true_pmf_vals, emp))

                if seed == 1:
                    plot_distribution(emp, true_pmf_vals, support, dist_config, n, tvd_vals[-1], seed)

            tvd_by_n[n] = tvd_vals
            print(f"  {n:>10,} {np.median(tvd_vals):>12.6f} {np.min(tvd_vals):>10.6f} {np.max(tvd_vals):>10.6f}")

        plot_tvd_vs_n(dist_name, dist_config, sample_sizes, tvd_by_n)
        print()


if __name__ == "__main__":
    run()
