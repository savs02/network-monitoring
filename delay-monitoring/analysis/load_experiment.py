"""
Load / remaining-capacity experiment — analysis.

Physical model
--------------
A single-hop link with capacity C is shared between probe traffic and
background load.  As utilisation rho increases, packets experience more
queuing delay.  Under M/M/1 assumptions the sojourn time is:

    Exponential( mean = base_delay / (1 - rho) )

where base_delay is the mean delay at very low load (the service time).

The passive monitor collects n_theory delay samples at each load level
and builds an empirical PMF.  From the observed sample mean it estimates:

    rho_est       = 1 - base_delay / mean_observed
    remaining_cap = link_capacity * (1 - rho_est)
                  = link_capacity * base_delay / mean_observed

Plots
-----
1. Delay distributions at all load levels (overlaid PMFs).
2. Before / after: two specific load levels side-by-side (rho=0.1 and
   rho=0.8) with the true Exponential PDF overlaid — what the monitor
   sees before and after a load increase.
3. Observed mean vs true mean across load levels.
4. Estimated remaining capacity vs true remaining capacity.

Results saved to: results/load-experiment/
"""

import math
import os

import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

# ---------------------------------------------------------------------------
# parameters — must match run_load_experiment.sh
# ---------------------------------------------------------------------------

BASE_DELAY     = 5.0          # ms — service time / mean delay at rho -> 0
LINK_CAPACITY  = 1000.0       # Mbps — illustrative (scales the capacity estimate)
LOAD_LEVELS    = [0.1, 0.2, 0.4, 0.6, 0.8]

BIN_SIZE  = 1        # ms
GRID_MAX  = 150.0
EPSILON   = 0.05
DELTA     = 0.05

K        = int(GRID_MAX / BIN_SIZE)
n_theory = math.ceil((K + math.log(1.0 / EPSILON)) / DELTA ** 2)   # 61,199

SOURCE_DIR  = "../results/load-experiment"
RESULTS_DIR = "../results/load-experiment"

BIN_EDGES   = np.arange(0.0, GRID_MAX + BIN_SIZE, BIN_SIZE)
BIN_CENTRES = BIN_EDGES[:-1] + BIN_SIZE / 2.0

# colour ramp: light blue (low load) -> dark red (high load)
LOAD_COLORS = {
    0.1: "#74b9ff",
    0.2: "#0984e3",
    0.4: "#fdcb6e",
    0.6: "#e17055",
    0.8: "#d63031",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def true_mean(rho):
    """True M/M/1 mean sojourn time."""
    return BASE_DELAY / (1.0 - rho)


def load_samples(rho):
    tag  = f"{rho}".replace(".", "_")
    path = os.path.join(SOURCE_DIR, f"load_{tag}", f"delay_samples_{n_theory}.csv")
    return pd.read_csv(path)["delay_ms"].values


def empirical_pmf(samples, smoothing=0.5):
    counts = np.zeros(K)
    idx    = np.floor(samples / BIN_SIZE).astype(int)
    valid  = (idx >= 0) & (idx < K)
    np.add.at(counts, idx[valid], 1)
    smoothed = counts + smoothing
    return smoothed / smoothed.sum()


def true_pmf_exp(rho):
    """True PMF: Exponential(mean=base/1-rho) discretised onto 1ms bins."""
    mean = true_mean(rho)
    cdf  = stats.expon.cdf(BIN_EDGES, scale=mean)
    masses = np.diff(cdf)
    return masses / masses.sum()


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def estimate_rho(samples):
    """
    Estimate utilisation from the observed sample mean.
        rho_est = 1 - base_delay / mean_observed
    """
    mean_obs = np.mean(samples)
    rho_est  = 1.0 - BASE_DELAY / mean_obs
    return rho_est, mean_obs


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def plot_distributions(all_samples):
    """
    Overlay empirical PMFs at all load levels with the true Exponential
    PDF, zoomed to the region with meaningful probability mass.
    """
    fig, ax = plt.subplots(figsize=(9, 5))

    # x-range: show up to the 99th percentile of the highest-load distribution
    x_max = stats.expon.ppf(0.995, scale=true_mean(max(LOAD_LEVELS)))
    x_max = min(x_max, GRID_MAX - 1)
    mask  = BIN_CENTRES <= x_max
    x     = BIN_CENTRES[mask]

    for rho, samples in all_samples.items():
        color   = LOAD_COLORS[rho]
        emp_pmf = empirical_pmf(samples)

        # true PDF evaluated at bin centres, scaled to match PMF (×bin_size)
        true_pdf = stats.expon.pdf(x, scale=true_mean(rho)) * BIN_SIZE

        ax.plot(x, emp_pmf[mask], color=color, linewidth=1.8,
                label=f"ρ = {rho}  (mean = {true_mean(rho):.1f} ms)")
        ax.plot(x, true_pdf, color=color, linewidth=1.0,
                linestyle="--", alpha=0.6)

    # dummy lines for legend entries
    ax.plot([], [], "k-",  linewidth=1.5, label="Empirical PMF (monitor)")
    ax.plot([], [], "k--", linewidth=1.0, alpha=0.6, label="True Exponential PDF")

    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Probability mass per 1ms bin")
    ax.set_title(
        "Delay distribution under increasing link utilisation\n"
        f"M/M/1 model: mean = base_delay / (1 − ρ),  base_delay = {BASE_DELAY} ms,  "
        f"n = {n_theory:,} samples per level",
        fontsize=10
    )
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3, axis="y")

    out = os.path.join(RESULTS_DIR, "distributions_all_loads.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_before_after(samples_before, samples_after,
                      rho_before=0.1, rho_after=0.8):
    """
    Side-by-side: what the monitor sees before and after a load increase.
    Shows empirical PMF and true PDF at each load level.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
    fig.suptitle(
        "Before and after a load increase — what the monitor observes\n"
        f"n = {n_theory:,} samples per window,  base_delay = {BASE_DELAY} ms",
        fontsize=11
    )

    for ax, rho, samples, label in [
        (axes[0], rho_before, samples_before,
         f"Before  (ρ = {rho_before},  mean = {true_mean(rho_before):.1f} ms)"),
        (axes[1], rho_after,  samples_after,
         f"After   (ρ = {rho_after},   mean = {true_mean(rho_after):.1f} ms)"),
    ]:
        color   = LOAD_COLORS[rho]
        emp_pmf = empirical_pmf(samples)
        x_max   = stats.expon.ppf(0.995, scale=true_mean(rho_after))  # same scale both panels
        x_max   = min(x_max, GRID_MAX - 1)
        mask    = BIN_CENTRES <= x_max
        x       = BIN_CENTRES[mask]

        true_pdf = stats.expon.pdf(x, scale=true_mean(rho)) * BIN_SIZE

        ax.bar(x, emp_pmf[mask], width=BIN_SIZE * 0.85,
               color=color, alpha=0.6, label="Empirical PMF (monitor)")
        ax.plot(x, true_pdf, "k-", linewidth=2, label="True Exponential PDF")

        rho_est, mean_obs = estimate_rho(samples)
        remaining_est = LINK_CAPACITY * (1.0 - rho_est)
        remaining_true = LINK_CAPACITY * (1.0 - rho)

        ax.set_title(label, fontsize=10)
        ax.set_xlabel("Delay (ms)")
        ax.set_ylabel("Probability mass per 1ms bin")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis="y")

        info = (f"Observed mean = {mean_obs:.2f} ms\n"
                f"ρ_est = {rho_est:.3f}  (true: {rho})\n"
                f"Remaining capacity ≈ {remaining_est:.0f} / {LINK_CAPACITY:.0f} Mbps")
        ax.text(0.97, 0.97, info, transform=ax.transAxes,
                fontsize=8, va="top", ha="right",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8))

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "before_after_load_change.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_capacity_estimation(all_samples):
    """
    Two panels:
      Left:  Observed mean delay vs true mean delay at each load level.
             Shows the monitor accurately tracks the true mean with n_theory samples.
      Right: Estimated remaining capacity vs true remaining capacity.
             Shows the monitor's estimate closely follows the ground truth.
    """
    true_means     = [true_mean(rho)            for rho in LOAD_LEVELS]
    true_remaining = [LINK_CAPACITY * (1 - rho) for rho in LOAD_LEVELS]

    obs_means      = []
    est_rhos       = []
    est_remaining  = []
    tvd_vals       = []

    for rho in LOAD_LEVELS:
        samples          = all_samples[rho]
        rho_est, mean_obs = estimate_rho(samples)
        obs_means.append(mean_obs)
        est_rhos.append(rho_est)
        est_remaining.append(LINK_CAPACITY * (1.0 - rho_est))
        tvd_vals.append(tvd(true_pmf_exp(rho), empirical_pmf(samples)))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(
        "Remaining link capacity estimation from delay distributions\n"
        f"M/M/1 model,  base_delay = {BASE_DELAY} ms,  "
        f"C = {LINK_CAPACITY:.0f} Mbps,  n = {n_theory:,} samples",
        fontsize=11
    )

    # left: observed mean vs true mean
    ax = axes[0]
    ax.plot(LOAD_LEVELS, true_means, "k--o", linewidth=2, markersize=8,
            label=f"True mean = {BASE_DELAY} / (1 − ρ)")
    ax.plot(LOAD_LEVELS, obs_means, "b-s",  linewidth=2, markersize=8,
            label="Observed mean (monitor estimate)")

    for rho, tm, om in zip(LOAD_LEVELS, true_means, obs_means):
        ax.annotate(f"TVD={tvd_vals[LOAD_LEVELS.index(rho)]:.4f}",
                    xy=(rho, om), xytext=(4, 4), textcoords="offset points",
                    fontsize=7, color="blue")

    ax.set_xlabel("True utilisation ρ")
    ax.set_ylabel("Mean delay (ms)")
    ax.set_title("Observed vs true mean delay\n"
                 "(TVD shown at each point — accuracy of monitor)", fontsize=9)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # right: estimated vs true remaining capacity
    ax = axes[1]
    ax.plot(LOAD_LEVELS, true_remaining, "k--o", linewidth=2, markersize=8,
            label="True remaining capacity")
    ax.plot(LOAD_LEVELS, est_remaining,  "r-s",  linewidth=2, markersize=8,
            label="Estimated remaining capacity")

    ax.fill_between(LOAD_LEVELS, true_remaining, est_remaining,
                    alpha=0.15, color="red", label="Estimation error")

    ax.set_xlabel("True utilisation ρ")
    ax.set_ylabel("Remaining capacity (Mbps)")
    ax.set_title("Estimated vs true remaining link capacity\n"
                 f"estimate = C × base_delay / mean_observed", fontsize=9)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "capacity_estimation.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_between_levels(all_samples):
    """
    TVD between consecutive load levels — shows how distinguishable the
    distributions are as load increases.  A high TVD means the monitor
    can reliably detect that load has changed.
    """
    pairs      = list(zip(LOAD_LEVELS[:-1], LOAD_LEVELS[1:]))
    tvd_emp    = []   # TVD between empirical PMFs
    tvd_true   = []   # TVD between true PMFs (theoretical maximum detectability)

    for rho1, rho2 in pairs:
        p1 = empirical_pmf(all_samples[rho1])
        p2 = empirical_pmf(all_samples[rho2])
        tvd_emp.append(tvd(p1, p2))

        t1 = true_pmf_exp(rho1)
        t2 = true_pmf_exp(rho2)
        tvd_true.append(tvd(t1, t2))

    labels = [f"{r1}→{r2}" for r1, r2 in pairs]
    x      = np.arange(len(labels))
    width  = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, tvd_true, width, label="TVD between true distributions",
           color="#636e72", alpha=0.8)
    ax.bar(x + width / 2, tvd_emp,  width, label="TVD between monitor's PMFs",
           color="#0984e3", alpha=0.8)

    ax.axhline(y=DELTA, color="red", linestyle="--", linewidth=1.5,
               label=f"δ = {DELTA}  (accuracy target)")

    ax.set_xticks(x)
    ax.set_xticklabels([f"ρ: {l}" for l in labels])
    ax.set_ylabel("Total Variation Distance (TVD)")
    ax.set_title(
        "Detectability of load changes — TVD between consecutive load levels\n"
        f"n = {n_theory:,} samples per window",
        fontsize=10
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "tvd_between_levels.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run():
    print("=" * 65)
    print("Load / remaining-capacity experiment — analysis")
    print("=" * 65)
    print(f"  M/M/1 model:  mean = {BASE_DELAY} / (1 − ρ)")
    print(f"  Link capacity : {LINK_CAPACITY:.0f} Mbps  (illustrative)")
    print(f"  n per level   : {n_theory:,}")
    print(f"  1ms bins, k = {K}, ε = {EPSILON}, δ = {DELTA}")
    print()
    print(f"  {'ρ':>5}  {'true mean (ms)':>16}  {'true remaining cap':>20}")
    print(f"  {'-'*46}")
    for rho in LOAD_LEVELS:
        print(f"  {rho:>5}  {true_mean(rho):>16.2f}  "
              f"{LINK_CAPACITY*(1-rho):>18.0f} Mbps")
    print("=" * 65)
    print()

    # load all NS-3 outputs
    all_samples = {}
    for rho in LOAD_LEVELS:
        samples = load_samples(rho)
        rho_est, mean_obs = estimate_rho(samples)
        err = abs(rho_est - rho)
        cap_est  = LINK_CAPACITY * (1.0 - rho_est)
        cap_true = LINK_CAPACITY * (1.0 - rho)
        tvd_val  = tvd(true_pmf_exp(rho), empirical_pmf(samples))
        print(f"  ρ={rho}  mean_true={true_mean(rho):6.2f}ms  "
              f"mean_obs={mean_obs:6.2f}ms  "
              f"ρ_est={rho_est:.3f} (err={err:.3f})  "
              f"cap_est={cap_est:.0f}Mbps  TVD={tvd_val:.5f}")
        all_samples[rho] = samples

    print()
    print("Generating plots...")
    plot_distributions(all_samples)
    plot_before_after(all_samples[0.1], all_samples[0.8])
    plot_capacity_estimation(all_samples)
    plot_tvd_between_levels(all_samples)
    print("Done.")


if __name__ == "__main__":
    run()
