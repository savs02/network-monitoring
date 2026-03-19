"""
Load change experiment — analysis.

Physical model
--------------
A single-hop link carries traffic whose delay follows Normal, Lognormal,
or Weibull.  As link utilisation rho increases, queuing adds to the
base delay.  Following M/M/1 scaling, the mean grows as:

    mean(rho) = base_mean / (1 - rho)

The distribution family stays the same; only the parameters shift:
  Normal    : mean scales, variance fixed
  Lognormal : mu shifts by ln(1/(1-rho)), sigma fixed
  Weibull   : scale shifts by 1/(1-rho), shape fixed

Three monitoring windows
------------------------
  before : rho = 0.1  — low load (baseline)
  during : rho = 0.5  — load ramping up
  after  : rho = 0.8  — high load (congested)

The monitor collects n_theory = 61,199 samples in each window (the
theoretical bound at k=150, epsilon=0.05, delta=0.05) and builds an
empirical PMF.

Plots
-----
1. Per-distribution overlay: before / during / after PMFs + true PDFs.
   Shows the distribution shifting right as load increases.
2. TVD summary: TVD between consecutive windows for each distribution.
   The TVD between before and after should be >> delta, confirming the
   monitor can reliably detect the load change.
3. Mean shift: observed mean per window vs true mean — shows the monitor
   tracks the load-induced mean shift accurately.

Results saved to: results/load-change/
"""

import math
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

# ---------------------------------------------------------------------------
# parameters — must match run_load_change_experiment.sh
# ---------------------------------------------------------------------------

WINDOWS      = ["before", "during", "after"]
LOAD_LEVELS  = {"before": 0.1, "during": 0.5, "after": 0.8}
WINDOW_COLORS = {"before": "#0984e3", "during": "#fdcb6e", "after": "#d63031"}

N_THEORY = 61199
BIN_SIZE = 1        # ms
GRID_MAX = 150.0
EPSILON  = 0.05
DELTA    = 0.05

K = int(GRID_MAX / BIN_SIZE)

BIN_EDGES   = np.arange(0.0, GRID_MAX + BIN_SIZE, BIN_SIZE)
BIN_CENTRES = BIN_EDGES[:-1] + BIN_SIZE / 2.0

SOURCE_DIR  = "../results/load-change"
RESULTS_DIR = "../results/load-change"

# base distribution parameters (rho -> 0)
BASE_PARAMS = {
    "normal":    {"mean": 10.0, "variance": 1.0},
    "lognormal": {"mu": 1.5,    "sigma": 0.3},
    "weibull":   {"scale": 5.0, "shape": 2.0},
}

DIST_LABELS = {
    "normal":    "Normal",
    "lognormal": "Lognormal",
    "weibull":   "Weibull",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def scaled_params(dist_name, rho):
    """Return distribution parameters at utilisation rho."""
    base = BASE_PARAMS[dist_name]
    if dist_name == "normal":
        return {"mean": base["mean"] / (1 - rho), "variance": base["variance"]}
    elif dist_name == "lognormal":
        return {"mu": base["mu"] + math.log(1.0 / (1 - rho)),
                "sigma": base["sigma"]}
    elif dist_name == "weibull":
        return {"scale": base["scale"] / (1 - rho), "shape": base["shape"]}


def true_mean_at(dist_name, rho):
    p = scaled_params(dist_name, rho)
    if dist_name == "normal":
        return p["mean"]
    elif dist_name == "lognormal":
        return math.exp(p["mu"] + p["sigma"] ** 2 / 2)
    elif dist_name == "weibull":
        return p["scale"] * math.gamma(1 + 1 / p["shape"])


def true_pmf(dist_name, rho):
    """True PMF discretised onto 1ms bins."""
    p = scaled_params(dist_name, rho)
    if dist_name == "normal":
        cdf = stats.norm.cdf(BIN_EDGES, loc=p["mean"],
                             scale=math.sqrt(p["variance"]))
    elif dist_name == "lognormal":
        cdf = stats.lognorm.cdf(BIN_EDGES, s=p["sigma"],
                                scale=math.exp(p["mu"]))
    elif dist_name == "weibull":
        cdf = stats.weibull_min.cdf(BIN_EDGES, c=p["shape"],
                                    scale=p["scale"])
    masses = np.diff(cdf)
    return masses / masses.sum()


def true_pdf_vals(dist_name, rho, x):
    """True PDF evaluated at x (for overlay on plots), scaled to PMF units."""
    p = scaled_params(dist_name, rho)
    if dist_name == "normal":
        return stats.norm.pdf(x, loc=p["mean"],
                              scale=math.sqrt(p["variance"])) * BIN_SIZE
    elif dist_name == "lognormal":
        return stats.lognorm.pdf(x, s=p["sigma"],
                                 scale=math.exp(p["mu"])) * BIN_SIZE
    elif dist_name == "weibull":
        return stats.weibull_min.pdf(x, c=p["shape"],
                                     scale=p["scale"]) * BIN_SIZE


def load_samples(window, dist_name):
    path = os.path.join(SOURCE_DIR, window,
                        f"delay_samples_{dist_name}_{N_THEORY}.csv")
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

def plot_distribution_shift(dist_name, all_samples):
    """
    Overlay before / during / after empirical PMFs and true PDFs for one
    distribution.  Shows the distribution shifting right as load increases.
    """
    rho_after = LOAD_LEVELS["after"]
    x_max = min(stats.expon.ppf(0.995, scale=true_mean_at(dist_name, rho_after)),
                GRID_MAX - 1)
    mask = BIN_CENTRES <= x_max
    x    = BIN_CENTRES[mask]

    fig, ax = plt.subplots(figsize=(9, 5))

    for window in WINDOWS:
        rho     = LOAD_LEVELS[window]
        color   = WINDOW_COLORS[window]
        samples = all_samples[dist_name][window]
        emp     = empirical_pmf(samples)
        t_pdf   = true_pdf_vals(dist_name, rho, x)
        mean_obs = np.mean(samples)

        ax.plot(x, emp[mask], color=color, linewidth=2.0,
                label=f"{window.capitalize()}  (ρ={rho}, "
                      f"true mean={true_mean_at(dist_name, rho):.1f}ms, "
                      f"obs mean={mean_obs:.1f}ms)")
        ax.plot(x, t_pdf, color=color, linewidth=1.0,
                linestyle="--", alpha=0.5)

    ax.plot([], [], "k-",  linewidth=1.5, label="Empirical PMF (monitor)")
    ax.plot([], [], "k--", linewidth=1.0, alpha=0.5,
            label="True PDF (ground truth)")

    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Probability mass per 1ms bin")
    ax.set_title(
        f"{DIST_LABELS[dist_name]} delay distribution under increasing load\n"
        f"base parameters: {BASE_PARAMS[dist_name]}    "
        f"n = {N_THEORY:,} samples per window",
        fontsize=10
    )
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, f"distribution_shift_{dist_name}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_summary(all_samples):
    """
    For each distribution, show:
      - TVD between empirical PMFs of consecutive windows
        (before→during, during→after, before→after)
      - TVD between the true distributions at the same load levels
        (upper bound — what a perfect monitor would see)
    The delta accuracy line shows the detection threshold.
    """
    pairs       = [("before", "during"), ("during", "after"), ("before", "after")]
    pair_labels = ["before→during\n(ρ: 0.1→0.5)",
                   "during→after\n(ρ: 0.5→0.8)",
                   "before→after\n(ρ: 0.1→0.8)"]

    dists = list(BASE_PARAMS.keys())
    x     = np.arange(len(pairs))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle(
        "Detectability of load changes — TVD between monitoring windows\n"
        f"n = {N_THEORY:,} samples per window  |  δ = {DELTA} (accuracy target)",
        fontsize=11
    )

    colors = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
    offsets = [-width, 0, width]

    for dist_name, offset in zip(dists, offsets):
        tvd_emp  = []
        tvd_true = []
        for w1, w2 in pairs:
            p_emp1 = empirical_pmf(all_samples[dist_name][w1])
            p_emp2 = empirical_pmf(all_samples[dist_name][w2])
            tvd_emp.append(tvd(p_emp1, p_emp2))

            p_true1 = true_pmf(dist_name, LOAD_LEVELS[w1])
            p_true2 = true_pmf(dist_name, LOAD_LEVELS[w2])
            tvd_true.append(tvd(p_true1, p_true2))

        ax.bar(x + offset, tvd_emp, width * 0.9,
               color=colors[dist_name], alpha=0.85,
               label=DIST_LABELS[dist_name])
        ax.bar(x + offset, tvd_true, width * 0.9,
               color=colors[dist_name], alpha=0.25,
               edgecolor=colors[dist_name], linewidth=1.2)

    ax.axhline(y=DELTA, color="red", linestyle="--", linewidth=1.5,
               label=f"δ = {DELTA}  (TVD above this = detectable change)")

    # legend entries for solid vs outline bars
    from matplotlib.patches import Patch
    handles, labels = ax.get_legend_handles_labels()
    handles += [Patch(facecolor="grey", alpha=0.85, label="Empirical (monitor)"),
                Patch(facecolor="grey", alpha=0.25,
                      edgecolor="grey", linewidth=1.2,
                      label="True distributions (upper bound)")]
    ax.legend(handles=handles, fontsize=8, ncol=2)

    ax.set_xticks(x)
    ax.set_xticklabels(pair_labels)
    ax.set_ylabel("Total Variation Distance (TVD)")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "tvd_summary.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_mean_shift(all_samples):
    """
    Observed sample mean vs true mean across the three windows for each
    distribution.  Shows the monitor accurately tracks the load-induced
    mean shift.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    colors = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
    x      = np.arange(len(WINDOWS))

    for dist_name in BASE_PARAMS:
        true_means = [true_mean_at(dist_name, LOAD_LEVELS[w]) for w in WINDOWS]
        obs_means  = [np.mean(all_samples[dist_name][w]) for w in WINDOWS]

        ax.plot(x, true_means, color=colors[dist_name],
                linestyle="--", marker="o", linewidth=1.5, markersize=7,
                label=f"{DIST_LABELS[dist_name]} — true mean")
        ax.plot(x, obs_means, color=colors[dist_name],
                linestyle="-",  marker="s", linewidth=2.0, markersize=7,
                label=f"{DIST_LABELS[dist_name]} — observed mean")

    ax.set_xticks(x)
    ax.set_xticklabels([f"{w.capitalize()}\n(ρ = {LOAD_LEVELS[w]})"
                        for w in WINDOWS])
    ax.set_ylabel("Mean delay (ms)")
    ax.set_title(
        "Observed vs true mean delay across monitoring windows\n"
        f"(n = {N_THEORY:,} samples per window — dashed = true, solid = monitor)",
        fontsize=10
    )
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "mean_shift.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    print("=" * 65)
    print("Load change experiment — analysis")
    print("=" * 65)
    print(f"  Windows : before (ρ=0.1) | during (ρ=0.5) | after (ρ=0.8)")
    print(f"  n / window : {N_THEORY:,}   (k={K}, ε={EPSILON}, δ={DELTA})")
    print()

    header = (f"  {'dist':<12} {'window':<8}  {'true mean':>10}  "
              f"{'obs mean':>10}  {'TVD vs true':>12}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    all_samples = {d: {} for d in BASE_PARAMS}

    for dist_name in BASE_PARAMS:
        for window in WINDOWS:
            rho     = LOAD_LEVELS[window]
            samples = load_samples(window, dist_name)
            t_mean  = true_mean_at(dist_name, rho)
            o_mean  = np.mean(samples)
            tvd_val = tvd(true_pmf(dist_name, rho), empirical_pmf(samples))

            d_col = dist_name if window == "before" else ""
            print(f"  {d_col:<12} {window:<8}  {t_mean:>10.2f}ms  "
                  f"{o_mean:>10.2f}ms  {tvd_val:>12.5f}")
            all_samples[dist_name][window] = samples
        print()

    print("Generating plots...")
    for dist_name in BASE_PARAMS:
        plot_distribution_shift(dist_name, all_samples)
    plot_tvd_summary(all_samples)
    plot_mean_shift(all_samples)
    print("Done.")


if __name__ == "__main__":
    run()
