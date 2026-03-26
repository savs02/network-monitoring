"""
TVD experiment — discrete distributions (multi-seed).

Uses a Binomial(N, p) delay distribution. Since the distribution is discrete,
the monitor's estimate is the empirical PMF (observed counts / total), not a KDE.
TVD is the natural metric here: it is well-defined on discrete distributions
without any approximation or smoothing, and it has a clean sample complexity bound.

Theoretical sample requirement:
    n_theory = ceil((k * log(1/epsilon)) / delta^2)
where k = N + 1 (the support size of Binomial(N, p)).
This follows from the Theta(k * log(1/epsilon) / delta^2) sample complexity
for learning a discrete distribution over k outcomes to TVD <= delta with
probability >= 1 - epsilon.

For each sample count n in [n/4, n/2, n, 2n] and each random seed:
  - Load delay samples from the NS-3 simulation CSV
  - Build the empirical PMF over {0, 1, ..., N}
  - Compute TVD(true, empirical)

Summary plot: box plot of TVD vs n across all seeds, with theoretical bound.
Distribution plots: empirical vs true PMF for seed 1 at each n.

Outputs saved to results/sample-complexity-discrete-seeded/.
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

BINOMIAL_N = 20
BINOMIAL_P = 0.5

# support: {0, 1, ..., N} — this is exactly k, the number of outcomes
SUPPORT = np.arange(0, BINOMIAL_N + 1)
K       = len(SUPPORT)  # = N + 1 = 21

EPSILON = 0.05
DELTA   = 0.05

SEEDS = list(range(1, 101))  # 100 random seeds (NS-3 RngRun values)

n_theory = math.ceil((K * math.log(1.0 / EPSILON)) / (DELTA ** 2))

SAMPLE_SIZES = [
    n_theory // 4,
    n_theory // 2,
    n_theory,
    n_theory * 2,
]

RESULTS_DIR = "../results/sample-complexity-discrete-seeded"

DIST_COLOR = "#9b59b6"  # purple to distinguish from the continuous experiments


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 55)
    print("Discrete experiment parameters (multi-seed)")
    print("=" * 55)
    print(f"  Distribution : Binomial(N={BINOMIAL_N}, p={BINOMIAL_P})")
    print(f"  Support      : {{0, 1, ..., {BINOMIAL_N}}}")
    print(f"  k (outcomes) : {K}")
    print(f"  epsilon      : {EPSILON}")
    print(f"  delta        : {DELTA}")
    print(f"  log(1/eps)   : {math.log(1/EPSILON):.6f}")
    print(f"  n_theory     : ceil(({K} * {math.log(1/EPSILON):.4f}) / {DELTA**2})")
    print(f"               = {n_theory}")
    print(f"  Sample sizes : {SAMPLE_SIZES}  (n/4, n/2, n, 2n)")
    print(f"  Seeds        : {SEEDS}")
    print("=" * 55)
    print()


def load_samples(n, seed):
    filepath = os.path.join(RESULTS_DIR, f"delay_samples_binomial_{n}_seed{seed}.csv")
    raw = pd.read_csv(filepath)["delay_ms"].values
    # NS-3 returns float; convert to integers (binomial values are whole numbers)
    return np.round(raw).astype(int)


def true_pmf():
    """True probability mass function of Binomial(N, p) over its support."""
    return stats.binom.pmf(SUPPORT, n=BINOMIAL_N, p=BINOMIAL_P)


def empirical_pmf(samples):
    """Empirical PMF over {0, ..., N} from observed samples."""
    counts = np.zeros(K)
    for val in samples:
        if 0 <= val <= BINOMIAL_N:
            counts[val] += 1
    return counts / counts.sum()


def tvd(true_pmf_vals, est_pmf_vals):
    """Total Variation Distance between the true and estimated PMF."""
    return 0.5 * float(np.sum(np.abs(true_pmf_vals - est_pmf_vals)))


def theoretical_bound(n):
    """Upper bound on TVD: sqrt(k * log(1/epsilon) / n), clipped at 1."""
    return min(1.0, math.sqrt(K * math.log(1.0 / EPSILON) / n))


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_distribution(emp_pmf, true_pmf_vals, n, tvd_val, seed):
    """
    Bar chart of empirical PMF alongside the true PMF for one sample count.
    Produced for seed 1 only as a visual reference.
    """
    fig, ax = plt.subplots(figsize=(8, 4))

    bar_width = 0.35

    ax.bar(SUPPORT - bar_width / 2, emp_pmf, width=bar_width,
           color=DIST_COLOR, alpha=0.7, label=f"Empirical PMF (n={n:,}, seed={seed})")
    ax.bar(SUPPORT + bar_width / 2, true_pmf_vals, width=bar_width,
           color="black", alpha=0.5, label="True PMF")

    ax.set_title(
        f"Binomial(N={BINOMIAL_N}, p={BINOMIAL_P}) — n = {n:,}, seed = {seed}\n"
        f"TVD = {tvd_val:.6f}"
    )
    ax.set_xlabel("Delay (ms, integer-valued)")
    ax.set_ylabel("Probability")
    ax.set_xticks(SUPPORT)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    output_path = os.path.join(RESULTS_DIR, f"dist_binomial_n{n}_seed{seed}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_tvd_vs_n(ns, tvd_by_n):
    """
    Box plot of TVD vs n across all seeds, with theoretical bound overlaid.
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    positions = list(range(len(ns)))
    data      = [tvd_by_n[n] for n in ns]
    bounds    = [theoretical_bound(n) for n in ns]

    ax.boxplot(data, positions=positions, widths=0.4,
               patch_artist=True,
               boxprops=dict(facecolor=DIST_COLOR, alpha=0.5),
               medianprops=dict(color="black", linewidth=2),
               flierprops=dict(marker="o", markersize=4, alpha=0.5))

    ax.plot(positions, bounds, "--", color="black", linewidth=1.5,
            label=rf"Bound $\sqrt{{k \log(1/\varepsilon) / n}}$, k={K}, $\varepsilon$={EPSILON}")

    ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
               label=f"TVD = {DELTA} (accuracy target)")

    ax.set_xticks(positions)
    ax.set_xticklabels([f"{n:,}" for n in ns], rotation=15)
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("Total Variation Distance")
    ax.set_title(
        f"TVD vs n — Binomial(N={BINOMIAL_N}, p={BINOMIAL_P})\n"
        f"Empirical PMF, {len(SEEDS)} seeds"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")

    output_path = os.path.join(RESULTS_DIR, "tvd_binomial.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    print_parameters()

    true_pmf_vals = true_pmf()

    print(f"{'n':>10} {'median TVD':>12} {'min TVD':>10} {'max TVD':>10}")
    print("-" * 48)

    tvd_by_n = {}

    for n in SAMPLE_SIZES:
        tvd_vals = []

        for seed in SEEDS:
            samples = load_samples(n, seed)
            emp     = empirical_pmf(samples)
            tvd_vals.append(tvd(true_pmf_vals, emp))

            # distribution plot for seed 1 only
            if seed == 1:
                plot_distribution(emp, true_pmf_vals, n, tvd_vals[-1], seed)

        tvd_by_n[n] = tvd_vals
        print(f"{n:>10,} {np.median(tvd_vals):>12.6f} {np.min(tvd_vals):>10.6f} {np.max(tvd_vals):>10.6f}")

    plot_tvd_vs_n(SAMPLE_SIZES, tvd_by_n)
    print()


if __name__ == "__main__":
    run()
