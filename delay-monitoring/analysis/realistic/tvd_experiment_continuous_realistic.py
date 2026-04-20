"""
TVD + KS experiment — continuous distributions, realistic mode (multi-seed).

In realistic mode the sampled delay is a floor: each packet is sent over
the wire and the receiver records the actual end-to-end delay.  The link
uses linkDelay=1ns and linkDataRate=1Gbps so network overhead is
sub-millisecond and negligible relative to ms-scale delays.

TVD is computed by binning: observed delays are placed into 1ms bins over
[0, 150ms] and compared to the true probability mass per bin from the CDF.

  TVD = 0.5 * sum_i |p_hat_i - p_i|

KS is computed directly against the continuous CDF via scipy.stats.kstest.

Reads CSVs from results/sample-complexity/continuous/realistic/seeded/.
For each distribution and sample size, computes TVD and KS across all 100
seeds and produces box plots vs n with the theoretical bound overlaid.
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

EPSILON   = 0.05
DELTA     = 0.05
SEEDS     = list(range(1, 101))
BIN_SIZE  = 1.0    # ms
BIN_MAX   = 150.0  # ms
N_BINS    = int(BIN_MAX / BIN_SIZE)   # 150 bins
N_THEORY  = 61199                     # ceil((150 + ln(1/0.05)) / 0.05^2)

SAMPLE_SIZES = [3060, 6120, 15299, 30599, 61199, 122398, 244796]

RESULTS_DIR = os.path.join(SCRIPT_DIR, "../../results/sample-complexity/continuous/realistic/seeded")

BIN_EDGES   = np.linspace(0.0, BIN_MAX, N_BINS + 1)
BIN_CENTRES = 0.5 * (BIN_EDGES[:-1] + BIN_EDGES[1:])

DISTRIBUTIONS = {
    "lognormal": {
        "label":  "Lognormal(mu=2.3, sigma=0.2)",
        "color":  "#2980b9",
        "scipy":  stats.lognorm(s=0.2, scale=math.exp(2.3)),
    },
    "normal": {
        "label":  "Normal(mean=40, var=4)",
        "color":  "#c0392b",
        "scipy":  stats.norm(loc=40.0, scale=2.0),
    },
    "weibull": {
        "label":  "Weibull(scale=10, shape=2)",
        "color":  "#d35400",
        "scipy":  stats.weibull_min(c=2.0, scale=10.0),
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def print_parameters():
    print("=" * 60)
    print("Continuous TVD + KS experiment — realistic mode (multi-seed)")
    print("=" * 60)
    for name, d in DISTRIBUTIONS.items():
        print(f"  {d['label']}")
    print(f"  k (bins)    : {N_BINS}  ({BIN_SIZE}ms each, 0-{BIN_MAX}ms)")
    print(f"  n_theory    : {N_THEORY:,}")
    print(f"  sample sizes: {SAMPLE_SIZES}")
    print(f"  epsilon : {EPSILON}    delta : {DELTA}")
    print(f"  seeds   : 1 - {max(SEEDS)}")
    print("=" * 60)
    print()


def true_bin_probs(dist_config):
    cdf_vals = dist_config["scipy"].cdf(BIN_EDGES)
    probs    = np.diff(cdf_vals)
    return probs / probs.sum() if probs.sum() > 0 else probs


def empirical_bin_probs(samples):
    counts, _ = np.histogram(samples, bins=BIN_EDGES)
    total      = counts.sum()
    return counts / total if total > 0 else counts.astype(float)


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def ks_stat(samples, dist_config):
    return stats.kstest(samples, dist_config["scipy"].cdf).statistic


def theoretical_bound(n):
    return min(1.0, DELTA * math.sqrt(N_THEORY / n))


def load_samples(dist_name, n, seed):
    path = os.path.join(RESULTS_DIR, f"delay_samples_{dist_name}_{n}_seed{seed}.csv")
    return pd.read_csv(path)["delay_ms"].values


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_histogram(emp_probs, true_probs, dist_config, n, tvd_val, seed):
    fig, ax = plt.subplots(figsize=(10, 4))

    ax.bar(BIN_CENTRES, emp_probs, width=BIN_SIZE * 0.9,
           color=dist_config["color"], alpha=0.6,
           label=f"Empirical (n={n:,}, seed={seed}, realistic)")
    ax.step(np.append(BIN_EDGES[:-1], BIN_EDGES[-1]),
            np.append(true_probs, true_probs[-1]),
            where="post", color="black", linewidth=1.5, label="True PMF (binned)")

    ax.set_title(f"{dist_config['label']} — realistic mode, n = {n:,}, seed = {seed}\nTVD = {tvd_val:.6f}")
    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Probability mass per bin")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    dist_name   = [k for k, v in DISTRIBUTIONS.items() if v is dist_config][0]
    output_path = os.path.join(RESULTS_DIR, f"hist_{dist_name}_n{n}_seed{seed}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {output_path}")


def plot_tvd_vs_n(dist_name, dist_config, tvd_by_n):
    fig, ax = plt.subplots(figsize=(12, 7))

    positions = list(range(len(SAMPLE_SIZES)))
    data      = [tvd_by_n[n] for n in SAMPLE_SIZES]
    bounds    = [theoretical_bound(n) for n in SAMPLE_SIZES]

    ax.boxplot(data, positions=positions, widths=0.4,
               patch_artist=True,
               boxprops=dict(facecolor=dist_config["color"], alpha=0.5),
               medianprops=dict(color="black", linewidth=2),
               flierprops=dict(marker="o", markersize=4, alpha=0.5))

    ax.plot(positions, bounds, "--", color="black", linewidth=1.5,
            label=rf"Theoretical bound ($n_{{theory}}={N_THEORY:,}$)")
    ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
               label=f"TVD = {DELTA} (accuracy target)")

    ax.set_xticks(positions)
    ax.set_xticklabels([f"{n:,}" for n in SAMPLE_SIZES], rotation=15)
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("Total Variation Distance")
    ax.set_title(f"TVD vs n — {dist_config['label']}, realistic mode\n"
                 f"1ms bins, {len(SEEDS)} seeds")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")

    output_path = os.path.join(RESULTS_DIR, f"tvd_{dist_name}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {output_path}")


def plot_ks_vs_n(dist_name, dist_config, ks_by_n):
    fig, ax = plt.subplots(figsize=(12, 7))

    positions = list(range(len(SAMPLE_SIZES)))
    data      = [ks_by_n[n] for n in SAMPLE_SIZES]

    ax.boxplot(data, positions=positions, widths=0.4,
               patch_artist=True,
               boxprops=dict(facecolor=dist_config["color"], alpha=0.5),
               medianprops=dict(color="black", linewidth=2),
               flierprops=dict(marker="o", markersize=4, alpha=0.5))

    ax.set_xticks(positions)
    ax.set_xticklabels([f"{n:,}" for n in SAMPLE_SIZES], rotation=15)
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("KS Statistic")
    ax.set_title(f"KS statistic vs n — {dist_config['label']}, realistic mode\n"
                 f"{len(SEEDS)} seeds")
    ax.grid(True, alpha=0.3, axis="y")

    output_path = os.path.join(RESULTS_DIR, f"ks_{dist_name}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"    Saved: {output_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print_parameters()

    for dist_name, dist_config in DISTRIBUTIONS.items():
        print(f"--- {dist_config['label']} ---")

        true_probs = true_bin_probs(dist_config)

        print(f"  {'n':>10} {'median TVD':>12} {'min TVD':>10} {'max TVD':>10} {'median KS':>12}")
        print("  " + "-" * 62)

        tvd_by_n = {}
        ks_by_n  = {}

        for n in SAMPLE_SIZES:
            tvd_vals = []
            ks_vals  = []

            for seed in SEEDS:
                samples  = load_samples(dist_name, n, seed)
                emp      = empirical_bin_probs(samples)
                tvd_vals.append(tvd(true_probs, emp))
                ks_vals.append(ks_stat(samples, dist_config))

                if seed == 1:
                    plot_histogram(emp, true_probs, dist_config, n, tvd_vals[-1], seed)

            tvd_by_n[n] = tvd_vals
            ks_by_n[n]  = ks_vals
            print(f"  {n:>10,} {np.median(tvd_vals):>12.6f} {np.min(tvd_vals):>10.6f} "
                  f"{np.max(tvd_vals):>10.6f} {np.median(ks_vals):>12.6f}")

        plot_tvd_vs_n(dist_name, dist_config, tvd_by_n)
        plot_ks_vs_n(dist_name, dist_config, ks_by_n)
        print()


if __name__ == "__main__":
    run()
