"""
KL divergence experiment — discrete distributions.

Uses a Binomial(N, p) delay distribution. Since the distribution is discrete,
the monitor's estimate is the empirical PMF (observed counts / total), not a KDE.

Theoretical sample requirement:
    n_theory = ceil((k + log(1/epsilon)) / delta^2)
where k = N + 1 (the support size of Binomial(N, p)).

For each sample count n in [n/4, n/2, n, 2n]:
  - Load delay samples from the NS-3 simulation CSV
  - Build the empirical PMF over {0, 1, ..., N}
  - Apply Laplace smoothing to handle unobserved values at small n
  - Compute KL(true || empirical)
  - Plot the empirical PMF alongside the true PMF

Outputs saved to results/sample-complexity-discrete/.
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

n_theory = math.ceil((K + math.log(1.0 / EPSILON)) / (DELTA ** 2))

SAMPLE_SIZES = [
    n_theory // 4,
    n_theory // 2,
    n_theory,
    n_theory * 2,
]

RESULTS_DIR = "../results/sample-complexity-discrete"

DIST_COLOR = "#9b59b6"  # purple to distinguish from the continuous experiments


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 55)
    print("Discrete experiment parameters")
    print("=" * 55)
    print(f"  Distribution : Binomial(N={BINOMIAL_N}, p={BINOMIAL_P})")
    print(f"  Support      : {{0, 1, ..., {BINOMIAL_N}}}")
    print(f"  k (outcomes) : {K}")
    print(f"  epsilon      : {EPSILON}")
    print(f"  delta        : {DELTA}")
    print(f"  log(1/eps)   : {math.log(1/EPSILON):.6f}")
    print(f"  n_theory     : ceil(({K} + {math.log(1/EPSILON):.4f}) / {DELTA**2})")
    print(f"               = {n_theory}")
    print(f"  Sample sizes : {SAMPLE_SIZES}  (n/4, n/2, n, 2n)")
    print("=" * 55)
    print()


def load_samples(n):
    filepath = os.path.join(RESULTS_DIR, f"delay_samples_binomial_{n}.csv")
    raw = pd.read_csv(filepath)["delay_ms"].values
    # NS-3 returns float; convert to integers (binomial values are whole numbers)
    return np.round(raw).astype(int)


def true_pmf():
    """True probability mass function of Binomial(N, p) over its support."""
    return stats.binom.pmf(SUPPORT, n=BINOMIAL_N, p=BINOMIAL_P)


def empirical_pmf(samples, smoothing=1.0):
    """
    Empirical PMF over {0, ..., N} with Laplace smoothing.
    Smoothing adds a pseudocount to each outcome to avoid zero probability
    for unobserved values, which would make KL divergence undefined.
    With enough samples this has negligible effect.
    """
    counts = np.zeros(K)
    for val in samples:
        if 0 <= val <= BINOMIAL_N:
            counts[val] += 1
    # Laplace smoothing: add pseudocount to each outcome
    smoothed = counts + smoothing
    return smoothed / smoothed.sum()


def kl_divergence(true_pmf_vals, est_pmf_vals, eps=1e-10):
    """KL(true || estimated): how much the estimate diverges from the true PMF."""
    est_safe = np.clip(est_pmf_vals, eps, None)
    mask = true_pmf_vals > 0
    return float(np.sum(true_pmf_vals[mask] * np.log(true_pmf_vals[mask] / est_safe[mask])))


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_distribution(samples, emp_pmf, true_pmf_vals, n, kl_val):
    """
    Bar chart of empirical PMF alongside the true PMF for one sample count.
    """
    fig, ax = plt.subplots(figsize=(8, 4))

    bar_width = 0.35
    x = np.arange(K)

    ax.bar(SUPPORT - bar_width / 2, emp_pmf, width=bar_width,
           color=DIST_COLOR, alpha=0.7, label=f"Empirical PMF (n={n:,})")
    ax.bar(SUPPORT + bar_width / 2, true_pmf_vals, width=bar_width,
           color="black", alpha=0.5, label="True PMF")

    ax.set_title(
        f"Binomial(N={BINOMIAL_N}, p={BINOMIAL_P}) — n = {n:,}\n"
        f"KL divergence = {kl_val:.6f}"
    )
    ax.set_xlabel("Delay (ms, integer-valued)")
    ax.set_ylabel("Probability")
    ax.set_xticks(SUPPORT)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    output_path = os.path.join(RESULTS_DIR, f"dist_binomial_n{n}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_kl_vs_n(ns, kl_values):
    fig, ax = plt.subplots(figsize=(7, 5))

    ax.plot(ns, kl_values, "o-", color=DIST_COLOR,
            linewidth=2, markersize=7, label="KL divergence (empirical PMF vs true)")

    ax.axvline(x=n_theory, color="grey", linestyle=":",
               linewidth=1.5, label=f"n_theory = {n_theory:,}")

    ax.set_xscale("log")
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("KL divergence")
    ax.set_title(
        f"KL divergence vs n — Binomial(N={BINOMIAL_N}, p={BINOMIAL_P})\n"
        f"Empirical PMF estimate (no KDE)"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, which="both")

    output_path = os.path.join(RESULTS_DIR, "kl_binomial.png")
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

    print(f"{'n':>10} {'KL divergence':>16}  {'unobserved values'}")
    print("-" * 50)

    ns        = []
    kl_values = []

    for n in SAMPLE_SIZES:
        samples  = load_samples(n)
        emp_pmf  = empirical_pmf(samples)
        kl_val   = kl_divergence(true_pmf_vals, emp_pmf)

        # count how many of the 21 outcomes were never observed (before smoothing)
        counts = np.zeros(K)
        for val in samples:
            if 0 <= val <= BINOMIAL_N:
                counts[val] += 1
        unobserved = int(np.sum(counts == 0))

        print(f"{n:>10,} {kl_val:>16.6f}  {unobserved} / {K}")

        plot_distribution(samples, emp_pmf, true_pmf_vals, n, kl_val)

        ns.append(n)
        kl_values.append(kl_val)

    plot_kl_vs_n(ns, kl_values)
    print()


if __name__ == "__main__":
    run()
