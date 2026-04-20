"""
Cross-traffic experiment — analysis.

Physical setup
--------------
A single 10 Mbps point-to-point link (2 ms propagation delay) carries probe
traffic alongside a second OnOff UDP cross-traffic sender.

The probe sender applies a base delay sampled from the underlying distribution
(Normal, Lognormal, or Weibull) before transmitting each packet.  A
DelayProbeTag records the send time before the artificial delay fires, so the
receiver measures the full end-to-end delay:

    E2E_delay = base_delay  (sampled from dist)
              + propagation  (2 ms, fixed)
              + queuing      (grows with cross-traffic utilisation)

The monitor is unaware of the cross-traffic load.  The aim is to show that
distributional shifts can reveal the presence and severity of congestion, and
to identify the saturation point (maximum link capacity) from the observed
delay distributions alone.

Cross-traffic utilisation levels
---------------------------------
0% to 200% in 10% steps.  Above 100% the DropTail queue saturates: the link
cannot carry the offered load, probe packets begin to be dropped, and only a
fraction of transmitted probe packets are received.

Distribution base parameters (same throughout)
-----------------------------------------------
  Normal    : mean = 10 ms, variance = 1 ms^2
  Lognormal : mu = 1.5, sigma = 0.3
  Weibull   : scale = 5 ms, shape = 2.0

Plots
-----
1. Distribution shift — PMF overlay across all levels (one panel per dist).
2. TVD from baseline vs utilisation — with saturation marker at 100%.
3. Mean delay vs utilisation — inflection at saturation.
4. Reception rate vs utilisation — drops appear above 100%.
5. Capacity estimation — gradient of mean delay identifies saturation point.

Results saved to: results/cross-traffic/
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as cm

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# parameters — must match run_cross_traffic_experiment.sh
# ---------------------------------------------------------------------------

DISTS = ["normal", "lognormal", "weibull"]
DIST_LABELS = {
    "normal":    "Normal(mean=10 ms, var=1)",
    "lognormal": "Lognormal(mu=1.5, sigma=0.3)",
    "weibull":   "Weibull(scale=5 ms, shape=2)",
}
DIST_COLORS = {"normal": "#3498db", "lognormal": "#e74c3c", "weibull": "#2ecc71"}
DIST_MARKERS = {"normal": "o", "lognormal": "s", "weibull": "^"}

# 0% to 200% in 10% steps
CT_PCT    = list(range(0, 201, 10))          # [0, 10, 20, ..., 200]
CT_RATES  = [p / 100.0 for p in CT_PCT]     # [0.0, 0.1, ..., 2.0]
CT_LABELS = [f"ct_{p:03d}" for p in CT_PCT] # ["ct_000", "ct_010", ..., "ct_200"]

N_TRANSMITTED = 61199
BIN_SIZE  = 1       # ms
GRID_MAX  = 150.0   # ms
DELTA     = 0.05

K           = int(GRID_MAX / BIN_SIZE)
BIN_EDGES   = np.arange(0.0, GRID_MAX + BIN_SIZE, BIN_SIZE)
BIN_CENTRES = BIN_EDGES[:-1] + BIN_SIZE / 2.0

SOURCE_DIR  = os.path.join(SCRIPT_DIR, "../results/cross-traffic")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/cross-traffic")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_samples(dist, label):
    path = os.path.join(SOURCE_DIR, dist, label, "delay_samples.csv")
    return pd.read_csv(path)["delay_ms"].values


def empirical_pmf(samples):
    counts = np.zeros(K)
    idx    = np.floor(samples / BIN_SIZE).astype(int)
    valid  = (idx >= 0) & (idx < K)
    np.add.at(counts, idx[valid], 1)
    return counts / counts.sum() if counts.sum() > 0 else counts


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def plot_distribution_shift(all_samples):
    """
    One panel per distribution.  Overlay PMF curves for every utilisation
    level, coloured from blue (0%) to red (200%) so congestion build-up is
    immediately visible.  Levels above 100% are shown with dashed lines.
    """
    cmap = cm.turbo
    n_levels = len(CT_PCT)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=False)
    fig.suptitle(
        "Delay distribution under increasing cross-traffic load  (0% → 200%)\n"
        "10 Mbps link, 2 ms propagation, DropTail queue — empirical E2E measurement",
        fontsize=11
    )

    for ax, dist in zip(axes, DISTS):
        # x-axis: use 99.5th percentile at highest load with enough samples
        samples_by_level = all_samples[dist]
        valid_last = [s for s in [samples_by_level.get(l) for l in CT_LABELS[-3:]] if s is not None and len(s) > 10]
        x_max = max(np.percentile(np.concatenate(valid_last), 99.5), 20.0) if valid_last else 50.0
        mask = BIN_CENTRES <= x_max

        for i, (label, pct) in enumerate(zip(CT_LABELS, CT_PCT)):
            samples = samples_by_level.get(label)
            if samples is None or len(samples) < 10:
                continue
            color     = cmap(i / (n_levels - 1))
            linestyle = "--" if pct > 100 else "-"
            alpha     = 0.6 if pct > 100 else 0.85
            lw        = 1.2 if pct % 50 != 0 else 2.0
            label_str = f"{pct}%" if pct % 50 == 0 else None

            emp = empirical_pmf(samples)
            ax.plot(BIN_CENTRES[mask], emp[mask],
                    color=color, linewidth=lw, linestyle=linestyle,
                    alpha=alpha, label=label_str)

        ax.axvline(x=0, color="none")   # force origin
        ax.set_title(DIST_LABELS[dist], fontsize=9)
        ax.set_xlabel("E2E delay (ms)")
        ax.set_ylabel("Probability mass per 1 ms bin")
        ax.legend(fontsize=7, title="CT load")
        ax.grid(True, alpha=0.3, axis="y")

    sm = cm.ScalarMappable(cmap=cm.turbo, norm=plt.Normalize(0, 200))
    sm.set_array([])
    fig.colorbar(sm, ax=axes.tolist(), label="Cross-traffic load (%)", shrink=0.8)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "distribution_shift.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_tvd_vs_utilisation(all_samples):
    """
    TVD between each loaded level and the 0% CT baseline.
    Vertical dashed line marks 100% (link saturation).
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle(
        "TVD from baseline (0% CT) vs cross-traffic utilisation\n"
        f"n transmitted = {N_TRANSMITTED:,} per level  |  δ = {DELTA}",
        fontsize=11
    )

    for dist in DISTS:
        baseline_pmf = empirical_pmf(all_samples[dist][CT_LABELS[0]])
        x, tvds = [], []
        for label, pct in zip(CT_LABELS[1:], CT_PCT[1:]):
            samples = all_samples[dist].get(label)
            if samples is None or len(samples) < 10:
                continue
            x.append(pct)
            tvds.append(tvd(baseline_pmf, empirical_pmf(samples)))

        ax.plot(x, tvds, color=DIST_COLORS[dist], marker=DIST_MARKERS[dist],
                linewidth=2.0, markersize=6, label=DIST_LABELS[dist])

    ax.axvline(x=100, color="black", linestyle=":", linewidth=1.5,
               label="100% — link saturation")
    ax.axhline(y=DELTA, color="red", linestyle="--", linewidth=1.2,
               label=f"δ = {DELTA}  (detectable shift)")

    ax.set_xlabel("Cross-traffic utilisation (%)")
    ax.set_ylabel("TVD vs baseline (0% load)")
    ax.set_xticks(CT_PCT[1:])
    ax.set_xticklabels([f"{p}%" for p in CT_PCT[1:]], rotation=45, fontsize=7)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "tvd_vs_utilisation.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_mean_vs_utilisation(all_samples):
    """
    Observed mean E2E delay vs utilisation.
    Shows the queuing-induced rise and the sharp knee at saturation.
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_title(
        "Mean observed E2E delay vs cross-traffic utilisation\n"
        f"n transmitted = {N_TRANSMITTED:,} per level",
        fontsize=10
    )

    for dist in DISTS:
        x, means = [], []
        for label, pct in zip(CT_LABELS, CT_PCT):
            samples = all_samples[dist].get(label)
            if samples is None or len(samples) < 10:
                continue
            x.append(pct)
            means.append(float(np.mean(samples)))
        ax.plot(x, means, color=DIST_COLORS[dist], marker=DIST_MARKERS[dist],
                linewidth=2.0, markersize=6, label=DIST_LABELS[dist])

    ax.axvline(x=100, color="black", linestyle=":", linewidth=1.5,
               label="100% — link saturation")
    ax.set_xlabel("Cross-traffic utilisation (%)")
    ax.set_ylabel("Mean E2E delay (ms)")
    ax.set_xticks(CT_PCT)
    ax.set_xticklabels([f"{p}%" for p in CT_PCT], rotation=45, fontsize=7)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "mean_vs_utilisation.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_reception_rate(all_samples):
    """
    Fraction of transmitted probe packets actually received vs utilisation.
    At sub-saturation loads this is ~1.0.  Above 100% the DropTail queue
    overflows and probe packets are dropped.
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_title(
        "Probe packet reception rate vs cross-traffic utilisation\n"
        f"Drops appear when offered load exceeds link capacity  (n transmitted = {N_TRANSMITTED:,})",
        fontsize=10
    )

    for dist in DISTS:
        x, rates = [], []
        for label, pct in zip(CT_LABELS, CT_PCT):
            samples = all_samples[dist].get(label)
            if samples is None:
                continue
            x.append(pct)
            rates.append(len(samples) / N_TRANSMITTED)
        ax.plot(x, rates, color=DIST_COLORS[dist], marker=DIST_MARKERS[dist],
                linewidth=2.0, markersize=6, label=DIST_LABELS[dist])

    ax.axvline(x=100, color="black", linestyle=":", linewidth=1.5,
               label="100% — link saturation")
    ax.axhline(y=1.0, color="grey", linestyle="--", linewidth=1.0, alpha=0.6)
    ax.set_xlabel("Cross-traffic utilisation (%)")
    ax.set_ylabel("Reception rate  (received / transmitted)")
    ax.set_ylim(0, 1.1)
    ax.set_xticks(CT_PCT)
    ax.set_xticklabels([f"{p}%" for p in CT_PCT], rotation=45, fontsize=7)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "reception_rate_vs_utilisation.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


def plot_capacity_estimation(all_samples):
    """
    Capacity estimation from distributional shifts alone.

    The gradient of the observed mean delay with respect to utilisation peaks
    at the saturation point.  A monitor that does not know the cross-traffic
    load can estimate the link capacity by identifying this inflection point.

    Left panel  : mean delay curve with estimated saturation point marked.
    Right panel : gradient (finite difference) of mean delay vs utilisation.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Capacity estimation from observed delay distributions\n"
        "Gradient of mean delay peaks at link saturation (monitor has no knowledge of CT load)",
        fontsize=11
    )

    for dist in DISTS:
        x_all, means_all = [], []
        for label, pct in zip(CT_LABELS, CT_PCT):
            samples = all_samples[dist].get(label)
            if samples is None or len(samples) < 10:
                continue
            x_all.append(pct)
            means_all.append(float(np.mean(samples)))

        x_all   = np.array(x_all)
        means_all = np.array(means_all)

        # finite-difference gradient: d(mean_delay)/d(utilisation_pct)
        grad = np.gradient(means_all, x_all)

        # estimated saturation = argmax of gradient (only look at sub-200% range
        # to avoid artefacts where drops reduce the observed mean)
        sub_sat_mask = x_all <= 150
        if sub_sat_mask.sum() >= 2:
            est_idx = int(np.argmax(grad[sub_sat_mask]))
            est_cap = x_all[sub_sat_mask][est_idx]
        else:
            est_cap = None

        axes[0].plot(x_all, means_all, color=DIST_COLORS[dist],
                     marker=DIST_MARKERS[dist], linewidth=2.0, markersize=6,
                     label=DIST_LABELS[dist])
        if est_cap is not None:
            axes[0].axvline(x=est_cap, color=DIST_COLORS[dist],
                            linestyle=":", linewidth=1.2, alpha=0.7)

        axes[1].plot(x_all, grad, color=DIST_COLORS[dist],
                     marker=DIST_MARKERS[dist], linewidth=2.0, markersize=6,
                     label=f"{DIST_LABELS[dist]}  (est. cap = {est_cap}%)" if est_cap else DIST_LABELS[dist])

    for ax in axes:
        ax.axvline(x=100, color="black", linestyle="--", linewidth=1.5,
                   label="True saturation (100%)")
        ax.set_xticks(CT_PCT)
        ax.set_xticklabels([f"{p}%" for p in CT_PCT], rotation=45, fontsize=7)
        ax.set_xlabel("Cross-traffic utilisation (%)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7)

    axes[0].set_ylabel("Mean E2E delay (ms)")
    axes[0].set_title("Mean delay — vertical lines = estimated saturation per dist")
    axes[1].set_ylabel("d(mean delay) / d(utilisation)  (ms / %)")
    axes[1].set_title("Gradient of mean delay  — peak = estimated saturation")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "capacity_estimation.png")
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
    print(f"  Utilisation levels : 0% to 200% in 10% steps ({len(CT_LABELS)} levels)")
    print(f"  n transmitted      : {N_TRANSMITTED:,}")
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    all_samples = {d: {} for d in DISTS}

    for dist in DISTS:
        print(f"  {'dist':<12} {'level':<10}  {'n_received':>10}  "
              f"{'reception':>10}  {'obs mean':>10}  {'TVD vs 0%':>10}")
        print("  " + "-" * 65)

        baseline_pmf = None
        for label, pct in zip(CT_LABELS, CT_PCT):
            try:
                samples = load_samples(dist, label)
            except FileNotFoundError:
                print(f"  {'':12} {pct:>3}%        {'missing':>10}")
                continue

            all_samples[dist][label] = samples
            emp = empirical_pmf(samples)

            if baseline_pmf is None:
                baseline_pmf = emp
                tvd_val = 0.0
            else:
                tvd_val = tvd(baseline_pmf, emp)

            reception = len(samples) / N_TRANSMITTED
            d_col = dist if pct == 0 else ""
            print(f"  {d_col:<12} {pct:>3}%        {len(samples):>10,}  "
                  f"{reception:>10.3f}  {np.mean(samples):>10.3f} ms  {tvd_val:>10.5f}")
        print()

    print("Generating plots...")
    plot_distribution_shift(all_samples)
    plot_tvd_vs_utilisation(all_samples)
    plot_mean_vs_utilisation(all_samples)
    plot_reception_rate(all_samples)
    plot_capacity_estimation(all_samples)
    print("Done.")


if __name__ == "__main__":
    run()
