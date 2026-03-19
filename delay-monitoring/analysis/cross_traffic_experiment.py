"""
Cross-traffic experiment — analysis.

Physical setup
--------------
A single 10 Mbps point-to-point link (2 ms propagation delay) carries probe
traffic alongside a second OnOff UDP cross-traffic sender.

The probe sender applies a base delay sampled from the underlying distribution
(Normal, Lognormal, or Weibull) — same parametric families as the
load-change experiment.  A DelayProbeTag records the send time before the
artificial delay fires, so the receiver measures the full end-to-end delay:

    E2E_delay = base_delay  (sampled from dist)
              + propagation  (2 ms, fixed)
              + queuing      (grows with cross-traffic utilisation)

As cross-traffic increases, queuing inflates the distribution.  Unlike the
load-change experiment (which used M/M/1 parameter scaling), this is a
purely empirical measurement: NS-3's DropTail queue produces the actual
queuing delay with no model assumptions.

Cross-traffic utilisation levels
---------------------------------
  ct_00 :  0 %   no cross-traffic (baseline — pure underlying distribution)
  ct_20 : 20 %   light load
  ct_40 : 40 %   moderate load
  ct_60 : 60 %   heavy load
  ct_80 : 80 %   near-saturation

Monitor
-------
n_theory = 61,199 samples per (distribution, level) combination
(k=150, epsilon=0.05, delta=0.05 — same theoretical bound throughout)

Plots
-----
1. Per-distribution overlay: baseline vs loaded PMFs (one panel per dist).
2. TVD vs utilisation: TVD from baseline for each distribution.
3. Mean delay vs utilisation: observed mean tracks queuing-induced growth.

Results saved to: results/cross-traffic/
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# parameters — must match run_cross_traffic_experiment.sh
# ---------------------------------------------------------------------------

DISTS      = ["normal", "lognormal", "weibull"]
DIST_LABELS = {"normal": "Normal(μ=10, σ²=1)",
               "lognormal": "Lognormal(μ=1.5, σ=0.3)",
               "weibull": "Weibull(scale=5, shape=2)"}

CT_LEVELS  = [0.0, 0.2, 0.4, 0.6, 0.8]
CT_LABELS  = ["ct_00", "ct_20", "ct_40", "ct_60", "ct_80"]
CT_NAMES   = ["0 %", "20 %", "40 %", "60 %", "80 %"]
CT_COLORS  = ["#2d3436", "#0984e3", "#00b894", "#fdcb6e", "#d63031"]

N_THEORY = 61199
BIN_SIZE = 1        # ms
GRID_MAX = 150.0    # ms
EPSILON  = 0.05
DELTA    = 0.05

K = int(GRID_MAX / BIN_SIZE)

BIN_EDGES   = np.arange(0.0, GRID_MAX + BIN_SIZE, BIN_SIZE)
BIN_CENTRES = BIN_EDGES[:-1] + BIN_SIZE / 2.0

SOURCE_DIR  = "../results/cross-traffic"
RESULTS_DIR = "../results/cross-traffic"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_samples(dist, label):
    path = os.path.join(SOURCE_DIR, dist, label, "delay_samples.csv")
    return pd.read_csv(path)["delay_ms"].values


def empirical_pmf(samples, smoothing=0.5):
    counts = np.zeros(K)
    idx    = np.floor(samples / BIN_SIZE).astype(int)
    valid  = (idx >= 0) & (idx < K)
    np.add.at(counts, idx[valid], 1)
    smoothed = counts + smoothing
    return smoothed / smoothed.sum()


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def plot_distribution_shift(all_samples):
    """
    One subplot per distribution.  Overlay all CT levels to show how
    queuing inflates the distribution as cross-traffic increases.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    fig.suptitle(
        "Delay distribution under increasing cross-traffic load\n"
        "10 Mbps link, 2 ms propagation, DropTail queue — empirical E2E measurement",
        fontsize=11
    )

    for ax, dist in zip(axes, DISTS):
        samples_80 = all_samples[dist][CT_LABELS[-1]]
        x_max = max(np.percentile(samples_80, 99.5), 20.0)
        mask  = BIN_CENTRES <= x_max

        for label, name, color in zip(CT_LABELS, CT_NAMES, CT_COLORS):
            samples  = all_samples[dist][label]
            emp      = empirical_pmf(samples)
            mean_obs = np.mean(samples)

            ax.plot(BIN_CENTRES[mask], emp[mask], color=color, linewidth=2.0,
                    label=f"CT {name}  (mean={mean_obs:.2f} ms)")

        ax.set_title(DIST_LABELS[dist], fontsize=9)
        ax.set_xlabel("E2E delay (ms)")
        ax.set_ylabel("Probability mass per 1 ms bin")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "distribution_shift.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_vs_utilisation(all_samples):
    """
    TVD between each loaded level and the 0% CT baseline, per distribution.
    Shows how detectable each load increase is.
    """
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.suptitle(
        f"Detectability of cross-traffic load — TVD from baseline (0 % CT)\n"
        f"n = {N_THEORY:,} samples per level  |  δ = {DELTA}",
        fontsize=11
    )

    dist_colors = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
    markers     = {"normal": "o", "lognormal": "s", "weibull": "^"}
    x = [level * 100 for level in CT_LEVELS[1:]]

    for dist in DISTS:
        baseline_pmf = empirical_pmf(all_samples[dist][CT_LABELS[0]])
        tvds = []
        for label in CT_LABELS[1:]:
            loaded_pmf = empirical_pmf(all_samples[dist][label])
            tvds.append(tvd(baseline_pmf, loaded_pmf))

        ax.plot(x, tvds, color=dist_colors[dist], marker=markers[dist],
                linewidth=2.0, markersize=8,
                label=DIST_LABELS[dist])

    ax.axhline(y=DELTA, color="red", linestyle="--", linewidth=1.5,
               label=f"δ = {DELTA}  (TVD above this → detectable)")

    ax.set_xlabel("Cross-traffic utilisation (%)")
    ax.set_ylabel("TVD vs baseline (0 % load)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(xi)} %" for xi in x])
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "tvd_vs_utilisation.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_mean_vs_utilisation(all_samples):
    """
    Observed sample mean vs cross-traffic utilisation for each distribution.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    dist_colors = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
    markers     = {"normal": "o", "lognormal": "s", "weibull": "^"}
    x = [level * 100 for level in CT_LEVELS]

    for dist in DISTS:
        means = [np.mean(all_samples[dist][label]) for label in CT_LABELS]
        ax.plot(x, means, color=dist_colors[dist], marker=markers[dist],
                linewidth=2.0, markersize=8, label=DIST_LABELS[dist])

    ax.set_xlabel("Cross-traffic utilisation (%)")
    ax.set_ylabel("Mean E2E delay (ms)")
    ax.set_title(
        f"Mean observed delay vs cross-traffic utilisation\n"
        f"n = {N_THEORY:,} samples per level — empirical measurement",
        fontsize=10
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(xi)} %" for xi in x])
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "mean_vs_utilisation.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    print("=" * 65)
    print("Cross-traffic experiment — analysis")
    print("=" * 65)
    print(f"  Distributions      : {DISTS}")
    print(f"  Utilisation levels : {CT_NAMES}")
    print(f"  n / level          : {N_THEORY:,}   (k={K}, ε={EPSILON}, δ={DELTA})")
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    all_samples = {d: {} for d in DISTS}

    for dist in DISTS:
        print(f"  {'dist':<12} {'level':<8}  {'n_received':>10}  "
              f"{'obs mean':>10}  {'TVD vs baseline':>16}")
        print("  " + "-" * 62)

        baseline_pmf = None
        for label, name in zip(CT_LABELS, CT_NAMES):
            samples = load_samples(dist, label)
            all_samples[dist][label] = samples
            emp = empirical_pmf(samples)

            if baseline_pmf is None:
                baseline_pmf = emp
                tvd_val = 0.0
            else:
                tvd_val = tvd(baseline_pmf, emp)

            d_col = dist if label == CT_LABELS[0] else ""
            print(f"  {d_col:<12} {name:<8}  {len(samples):>10,}  "
                  f"{np.mean(samples):>10.3f} ms  {tvd_val:>16.5f}")
        print()

    print("Generating plots...")
    plot_distribution_shift(all_samples)
    plot_tvd_vs_utilisation(all_samples)
    plot_mean_vs_utilisation(all_samples)
    print("Done.")


if __name__ == "__main__":
    run()
