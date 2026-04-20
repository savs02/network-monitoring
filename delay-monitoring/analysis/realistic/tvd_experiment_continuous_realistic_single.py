"""
TVD + KS experiment — continuous distributions, realistic mode (single seed).

In realistic mode the sampled delay is a floor: each packet is sent over
the wire and the receiver records the actual end-to-end delay.  The link
uses linkDelay=1ns and linkDataRate=1Gbps so network overhead is
sub-millisecond and negligible relative to ms-scale delays.

TVD is computed by binning: observed delays are placed into 1ms bins over
[0, 150ms] and compared to the true probability mass per bin from the CDF.

  TVD = 0.5 * sum_i |p_hat_i - p_i|

KS is computed directly against the continuous CDF via scipy.stats.kstest.

Reads CSVs from results/sample-complexity/continuous/realistic/single_seed/.
Overlays theoretical-mode results if available.
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR     = os.path.join(SCRIPT_DIR, "../../results/sample-complexity/continuous/realistic/single_seed")
THEORETICAL_DIR = os.path.join(SCRIPT_DIR, "../../results/sample-complexity/continuous/theoretical/single_seed")

# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

EPSILON   = 0.05
DELTA     = 0.05
BIN_SIZE  = 1.0    # ms
BIN_MAX   = 150.0  # ms
N_BINS    = int(BIN_MAX / BIN_SIZE)   # 150 bins
N_THEORY  = 61199                     # ceil((150 + ln(1/0.05)) / 0.05^2)

SAMPLE_SIZES = [3060, 6120, 15299, 30599, 61199, 122398, 244796]

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


def load_samples(results_dir, dist_name, n, seed=None):
    if seed is None:
        path = os.path.join(results_dir, f"delay_samples_{dist_name}_{n}.csv")
    else:
        path = os.path.join(results_dir, f"delay_samples_{dist_name}_{n}_seed{seed}.csv")
    return pd.read_csv(path)["delay_ms"].values


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_histogram(emp_probs, true_probs, dist_config, n, tvd_val):
    fig, ax = plt.subplots(figsize=(10, 4))

    ax.bar(BIN_CENTRES, emp_probs, width=BIN_SIZE * 0.9,
           color=dist_config["color"], alpha=0.6,
           label=f"Empirical (n={n:,}, realistic)")
    ax.step(np.append(BIN_EDGES[:-1], BIN_EDGES[-1]),
            np.append(true_probs, true_probs[-1]),
            where="post", color="black", linewidth=1.5, label="True PMF (binned)")

    ax.set_title(f"{dist_config['label']} — realistic mode, n = {n:,}\nTVD = {tvd_val:.6f}")
    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Probability mass per bin")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    dist_name   = [k for k, v in DISTRIBUTIONS.items() if v is dist_config][0]
    output_path = os.path.join(RESULTS_DIR, f"hist_{dist_name}_n{n}.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_tvd_vs_n(results, theoretical_results):
    fig, ax = plt.subplots(figsize=(10, 6))

    bounds = [theoretical_bound(n) for n in SAMPLE_SIZES]

    for dist_name, (dist_config, tvd_vals, _) in results.items():
        ax.plot(SAMPLE_SIZES, tvd_vals, "o-", color=dist_config["color"],
                linewidth=2, markersize=7, label=f"{dist_config['label']} (realistic)")
        if dist_name in theoretical_results:
            ax.plot(SAMPLE_SIZES, theoretical_results[dist_name][0], "s:",
                    color=dist_config["color"], linewidth=1.5, markersize=5, alpha=0.7,
                    label=f"{dist_config['label']} (theoretical)")

    ax.plot(SAMPLE_SIZES, bounds, "--", color="black", linewidth=1.5,
            label=rf"Theoretical bound ($n_{{theory}}={N_THEORY:,}$)")
    ax.axhline(y=DELTA, color="red", linestyle=":", linewidth=1.2,
               label=f"TVD = {DELTA} (accuracy target)")

    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("Total Variation Distance")
    ax.set_title("TVD vs n — continuous distributions, realistic mode (single seed)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    output_path = os.path.join(RESULTS_DIR, "tvd_continuous_realistic_single.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_ks_vs_n(results, theoretical_results):
    fig, ax = plt.subplots(figsize=(10, 6))

    for dist_name, (dist_config, _, ks_vals) in results.items():
        ax.plot(SAMPLE_SIZES, ks_vals, "o-", color=dist_config["color"],
                linewidth=2, markersize=7, label=f"{dist_config['label']} (realistic)")
        if dist_name in theoretical_results:
            ax.plot(SAMPLE_SIZES, theoretical_results[dist_name][1], "s:",
                    color=dist_config["color"], linewidth=1.5, markersize=5, alpha=0.7,
                    label=f"{dist_config['label']} (theoretical)")

    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("KS Statistic")
    ax.set_title("KS statistic vs n — continuous distributions, realistic mode (single seed)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    output_path = os.path.join(RESULTS_DIR, "ks_continuous_realistic_single.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print(f"{'Distribution':<35} {'n':>8} {'TVD':>10} {'KS':>10}")
    print("-" * 66)

    results             = {}
    theoretical_results = {}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        true_probs = true_bin_probs(dist_config)
        tvd_vals   = []
        ks_vals    = []
        first      = True

        for n in SAMPLE_SIZES:
            samples   = load_samples(RESULTS_DIR, dist_name, n)
            emp       = empirical_bin_probs(samples)
            tvd_val   = tvd(true_probs, emp)
            ks_val    = ks_stat(samples, dist_config)
            tvd_vals.append(tvd_val)
            ks_vals.append(ks_val)

            label = dist_config["label"] if first else ""
            print(f"{label:<35} {n:>8,} {tvd_val:>10.6f} {ks_val:>10.6f}")
            first = False

            plot_histogram(emp, true_probs, dist_config, n, tvd_val)

        results[dist_name] = (dist_config, tvd_vals, ks_vals)
        print()

        # load theoretical results for overlay if available
        th_tvds = []
        th_ks   = []
        for n in SAMPLE_SIZES:
            try:
                samples = load_samples(THEORETICAL_DIR, dist_name, n)
                emp     = empirical_bin_probs(samples)
                th_tvds.append(tvd(true_bin_probs(dist_config), emp))
                th_ks.append(ks_stat(samples, dist_config))
            except FileNotFoundError:
                break
        if len(th_tvds) == len(SAMPLE_SIZES):
            theoretical_results[dist_name] = (th_tvds, th_ks)

    plot_tvd_vs_n(results, theoretical_results)
    plot_ks_vs_n(results, theoretical_results)


if __name__ == "__main__":
    run()
