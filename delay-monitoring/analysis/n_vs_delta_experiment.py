"""
n vs delta experiment — theoretical bound vs empirical sample requirement.

Varies the TVD accuracy target delta and computes, for each value:

  Theoretical bound (PAC-style guarantee):
    Continuous (KDE, 1ms grid): n_theory = ceil(K · log(1/ε) / δ²)
    Discrete   (PMF, b ms):     n_theory = ceil((k + log(1/ε)) / δ²)

  Empirical requirement:
    Smallest n in SAMPLE_SIZES such that the median TVD across 20 seeds
    falls at or below δ.

The theoretical bound is the same regardless of which of the three
distributions generated the data — it is a worst-case guarantee.  The
empirical requirement depends on the distribution and the estimator.

The central question is: how conservative is the theoretical bound compared
to what is actually needed in practice?

Plots:
  n_vs_delta_main.png        — theoretical and empirical n on the same axes;
                               left panel: continuous (KDE),
                               right panel: discrete (PMF, multiple bin sizes)
  n_vs_delta_overlay.png     — KDE empirical vs PMF empirical on one set of axes,
                               to compare the two estimators directly
  tvd_vs_n_{dist}.png        — TVD vs n per distribution with delta reference lines
                               and the theoretical bound curve, for both estimators

Results saved to: results/n-vs-delta/
Clears the results directory on each run.
"""

import math
import os
import shutil
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/n-vs-delta")

# ============================================================
# parameters
# ============================================================

EPSILON = 0.05          # confidence parameter — fixed throughout
GRID_MAX = 150.0        # ms

# Accuracy targets to sweep
DELTAS = [0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]

# Sample sizes for the empirical experiments
SAMPLE_SIZES = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
SEEDS        = list(range(1, 21))   # 20 independent draws per (distribution, n)

# Fine grid for KDE evaluation (continuous case)
BIN_WIDTH = 1.0
GRID      = np.arange(BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)
K         = len(GRID)   # 149 bins

# Bin sizes tested for the discrete PMF
BIN_SIZES = [1, 2, 5, 10]

DISTRIBUTIONS = {
    "normal": {
        "label":  "Normal",
        "params": {"mean": 40.0, "variance": 4.0},
        "color":  "#3498db",
    },
    "lognormal": {
        "label":  "Lognormal",
        "params": {"mu": 2.3, "sigma": 0.2},
        "color":  "#e74c3c",
    },
    "weibull": {
        "label":  "Weibull",
        "params": {"scale": 10.0, "shape": 2.0},
        "color":  "#2ecc71",
    },
}

DISC_COLORS = {1: "#2196F3", 2: "#FF9800", 5: "#4CAF50", 10: "#E91E63"}
DELTA_COLORS = ["#c0392b", "#e67e22", "#f39c12", "#27ae60", "#2980b9",
                "#8e44ad", "#16a085"]


# ============================================================
# theoretical bounds
# ============================================================

def n_theory_continuous(delta):
    """n = ceil(K · log(1/ε) / δ²)"""
    return math.ceil(K * math.log(1.0 / EPSILON) / delta ** 2)


def n_theory_discrete(delta, bin_size):
    """n = ceil((k + log(1/ε)) / δ²)"""
    k = int(GRID_MAX / bin_size)
    return math.ceil((k + math.log(1.0 / EPSILON)) / delta ** 2)


def bound_curve_continuous(n_array):
    """Theoretical TVD bound as a function of n: sqrt(K · log(1/ε) / n)"""
    return np.minimum(1.0, np.sqrt(K * math.log(1.0 / EPSILON) / n_array))


def bound_curve_discrete(n_array, bin_size):
    """Theoretical TVD bound as a function of n: sqrt((k + log(1/ε)) / n)"""
    k = int(GRID_MAX / bin_size)
    return np.minimum(1.0, np.sqrt((k + math.log(1.0 / EPSILON)) / n_array))


# ============================================================
# sampling and estimation
# ============================================================

def sample_distribution(dist_name, params, n, rng):
    if dist_name == "normal":
        return rng.normal(loc=params["mean"],
                          scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(f"Unknown distribution: {dist_name}")


def true_masses_fine(dist_name, params):
    """True probability masses on the 1ms fine grid."""
    if dist_name == "normal":
        pdf = stats.norm.pdf(GRID, loc=params["mean"],
                             scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        pdf = stats.lognorm.pdf(GRID, s=params["sigma"],
                                scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        pdf = stats.weibull_min.pdf(GRID, c=params["shape"],
                                    scale=params["scale"])
    masses = pdf * BIN_WIDTH
    return masses / masses.sum()


def true_pmf_coarse(dist_name, params, bin_size):
    """True probability masses on coarse bins via CDF differences."""
    edges = np.arange(0.0, GRID_MAX + bin_size, bin_size)
    if dist_name == "normal":
        cdf = stats.norm.cdf(edges, loc=params["mean"],
                             scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        cdf = stats.lognorm.cdf(edges, s=params["sigma"],
                                scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        cdf = stats.weibull_min.cdf(edges, c=params["shape"],
                                    scale=params["scale"])
    masses = np.diff(cdf)
    return masses / masses.sum()


def kde_masses_fine(samples):
    """KDE evaluated on the fine 1ms grid, converted to probability masses."""
    kde    = stats.gaussian_kde(samples, bw_method="scott")
    masses = kde(GRID) * BIN_WIDTH
    return masses / masses.sum()


def empirical_pmf_coarse(samples, bin_size):
    """Raw histogram PMF on coarse bins."""
    k   = int(GRID_MAX / bin_size)
    idx = np.clip(np.floor(samples / bin_size).astype(int), 0, k - 1)
    counts = np.bincount(idx, minlength=k).astype(float)
    total  = counts.sum()
    return counts / total if total > 0 else counts


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


# ============================================================
# experiments
# ============================================================

def run_experiments():
    """
    For every (distribution, n, seed): draw samples, compute TVD for the
    KDE estimator and for each PMF bin size.

    Returns:
        results[dist_name] = {
            "kde": {n: [tvd_seed1, ..., tvd_seed20]},
            "pmf": {bin_size: {n: [tvd_seed1, ...]}},
        }
    """
    results = {}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        print(f"\n--- {dist_config['label']} ---")
        params = dist_config["params"]

        true_cont = true_masses_fine(dist_name, params)
        true_disc = {bs: true_pmf_coarse(dist_name, params, bs)
                     for bs in BIN_SIZES}

        kde_tvds = {n: [] for n in SAMPLE_SIZES}
        pmf_tvds = {bs: {n: [] for n in SAMPLE_SIZES} for bs in BIN_SIZES}

        for n in SAMPLE_SIZES:
            for seed in SEEDS:
                rng     = np.random.default_rng(seed)
                samples = sample_distribution(dist_name, params, n, rng)

                kde_tvds[n].append(tvd(true_cont, kde_masses_fine(samples)))

                for bs in BIN_SIZES:
                    pmf_tvds[bs][n].append(
                        tvd(true_disc[bs], empirical_pmf_coarse(samples, bs))
                    )

            print(
                f"  n={n:>7,}  "
                f"KDE={np.median(kde_tvds[n]):.4f}  "
                + "  ".join(
                    f"PMF({bs}ms)={np.median(pmf_tvds[bs][n]):.4f}"
                    for bs in BIN_SIZES
                )
            )

        results[dist_name] = {"kde": kde_tvds, "pmf": pmf_tvds}

    return results


def find_n_empirical(tvds_by_n, delta):
    """
    Smallest n in SAMPLE_SIZES where median TVD <= delta.
    Returns None if not achieved within the sample grid.
    """
    for n in SAMPLE_SIZES:
        if np.median(tvds_by_n[n]) <= delta:
            return n
    return None


# ============================================================
# plots
# ============================================================

def param_str(dist_name, params):
    if dist_name == "normal":
        return f"μ={params['mean']}, σ²={params['variance']}"
    elif dist_name == "lognormal":
        return f"μ={params['mu']}, σ={params['sigma']}"
    elif dist_name == "weibull":
        return f"scale={params['scale']}, shape={params['shape']}"
    return ""


def plot_n_vs_delta_main(results):
    """
    Central result: theoretical n_theory(delta) and empirical n_needed(delta).

    Layout (GridSpec):
      Left column  — continuous (KDE), spans both rows
      Right 2×2    — discrete (PMF), one panel per bin size

    Distributes empirical lines across separate panels so nothing overlaps.
    Distinct markers (o / s / ^) and small x-offsets separate distributions
    within the KDE panel where they converge to similar values.
    """
    delta_fine  = np.linspace(DELTAS[0], DELTAS[-1], 300)
    dist_items  = list(DISTRIBUTIONS.items())
    markers     = ["o", "s", "^"]
    # Slight x-offsets so overlapping distributions are still distinguishable
    x_offsets   = [-0.002, 0.000, 0.002]

    fig = plt.figure(figsize=(22, 12))
    gs  = fig.add_gridspec(2, 3, hspace=0.40, wspace=0.32,
                           left=0.06, right=0.98, top=0.90, bottom=0.08)

    ax_kde = fig.add_subplot(gs[:, 0])          # KDE spans both rows
    pmf_axes = {
        1:  fig.add_subplot(gs[0, 1]),
        2:  fig.add_subplot(gs[0, 2]),
        5:  fig.add_subplot(gs[1, 1]),
        10: fig.add_subplot(gs[1, 2]),
    }

    fig.suptitle(
        "Theoretical bound vs empirical sample requirement as δ varies\n"
        r"Continuous bound: $n = \lceil K \log(1/\varepsilon)/\delta^2 \rceil$   "
        r"Discrete bound: $n = \lceil (k+\log(1/\varepsilon))/\delta^2 \rceil$"
        f"   |   ε = {EPSILON}",
        fontsize=12,
    )

    # ── left: continuous (KDE) ──────────────────────────────────────────────
    ax_kde.plot(delta_fine,
                [n_theory_continuous(d) for d in delta_fine],
                "--", color="black", linewidth=2.5,
                label=f"Theoretical bound (K={K})", zorder=5)

    for (dist_name, dist_config), mk, xoff in zip(dist_items, markers, x_offsets):
        tvds_by_n = results[dist_name]["kde"]
        empirical = [find_n_empirical(tvds_by_n, d) for d in DELTAS]
        valid     = [(d + xoff, n) for d, n in zip(DELTAS, empirical)
                     if n is not None]
        if valid:
            xd, xn = zip(*valid)
            ax_kde.plot(xd, xn, f"{mk}-",
                        color=dist_config["color"], linewidth=2, markersize=11,
                        markeredgecolor="white", markeredgewidth=0.8,
                        label=dist_config["label"])

    ax_kde.set_yscale("log")
    ax_kde.set_xlabel("Accuracy target δ", fontsize=12)
    ax_kde.set_ylabel("n required (log scale)", fontsize=12)
    ax_kde.set_title("Continuous estimator (KDE, 1ms grid)", fontsize=11)
    ax_kde.legend(fontsize=10)
    ax_kde.grid(True, alpha=0.3, which="both")

    # ── right: discrete (PMF) — one panel per bin size ─────────────────────
    for bs, ax in pmf_axes.items():
        k_val = int(GRID_MAX / bs)

        # Theoretical bound for this bin size
        ax.plot(delta_fine,
                [n_theory_discrete(d, bs) for d in delta_fine],
                "--", color="black", linewidth=2.2,
                label=f"Theoretical bound (k={k_val})", zorder=5)

        # Empirical per distribution — distinct markers + x-offsets
        for (dist_name, dist_config), mk, xoff in zip(dist_items, markers, x_offsets):
            tvds_by_n = results[dist_name]["pmf"][bs]
            empirical = [find_n_empirical(tvds_by_n, d) for d in DELTAS]
            valid     = [(d + xoff, n) for d, n in zip(DELTAS, empirical)
                         if n is not None]
            if valid:
                xd, xn = zip(*valid)
                ax.plot(xd, xn, f"{mk}-",
                        color=dist_config["color"], linewidth=2, markersize=10,
                        markeredgecolor="white", markeredgewidth=0.8,
                        label=dist_config["label"])

        ax.set_yscale("log")
        ax.set_xlabel("Accuracy target δ", fontsize=11)
        ax.set_ylabel("n required (log scale)", fontsize=11)
        ax.set_title(f"Discrete PMF — {bs}ms bins  (k = {k_val})", fontsize=11)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    out = os.path.join(RESULTS_DIR, "n_vs_delta_main.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_n_vs_delta_overlay(results):
    """
    KDE vs PMF comparison — one panel per distribution (1×3 grid).

    Each panel shows four lines:
      - Theoretical continuous bound (dashed black)
      - Theoretical discrete 1ms bound (dotted black)
      - Empirical KDE (solid, distribution colour)
      - Empirical PMF 1ms (dashed, same colour, square markers)

    Separating by distribution prevents the estimator lines from overlapping
    across distributions, making the KDE-vs-PMF gap clear for each case.
    """
    delta_fine = np.linspace(DELTAS[0], DELTAS[-1], 300)
    theory_cont = [n_theory_continuous(d) for d in delta_fine]
    theory_disc = [n_theory_discrete(d, 1) for d in delta_fine]

    fig, axes = plt.subplots(1, 3, figsize=(20, 7), sharey=True)
    fig.suptitle(
        "KDE vs PMF (1ms bins) — n required vs δ, per distribution\n"
        "Solid circle: KDE (continuous)  |  Dashed square: PMF (discrete, 1ms bins)  |  "
        "Black lines: theoretical bounds",
        fontsize=12,
    )

    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        col = dist_config["color"]

        # Theoretical bounds (same in every panel)
        ax.plot(delta_fine, theory_cont, "--", color="black", linewidth=2.0,
                label=f"Theoretical (continuous, K={K})")
        ax.plot(delta_fine, theory_disc, ":", color="black", linewidth=2.0,
                label="Theoretical (discrete, 1ms, k=150)")

        # Empirical KDE
        kde_emp   = [find_n_empirical(results[dist_name]["kde"], d) for d in DELTAS]
        kde_valid = [(d, n) for d, n in zip(DELTAS, kde_emp) if n is not None]
        if kde_valid:
            xd, xn = zip(*kde_valid)
            ax.plot(xd, xn, "o-", color=col, linewidth=2.5, markersize=12,
                    markeredgecolor="white", markeredgewidth=0.8,
                    label="KDE (empirical)")

        # Empirical PMF 1ms
        pmf_emp   = [find_n_empirical(results[dist_name]["pmf"][1], d) for d in DELTAS]
        pmf_valid = [(d, n) for d, n in zip(DELTAS, pmf_emp) if n is not None]
        if pmf_valid:
            xd, xn = zip(*pmf_valid)
            ax.plot(xd, xn, "s--", color=col, linewidth=2.5, markersize=11,
                    markeredgecolor="white", markeredgewidth=0.8,
                    alpha=0.85, label="PMF 1ms (empirical)")

        ax.set_yscale("log")
        ax.set_xlabel("Accuracy target δ", fontsize=12)
        if ax is axes[0]:
            ax.set_ylabel("n required (log scale)", fontsize=12)
        ax.set_title(
            f"{dist_config['label']}\n{param_str(dist_name, dist_config['params'])}",
            fontsize=11,
        )
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "n_vs_delta_overlay.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_tvd_vs_n_per_dist(results):
    """
    Per-distribution, two-panel plot: TVD vs n for KDE (left) and PMF 1ms (right).

    Each panel shows:
      - Median TVD with IQR band (empirical)
      - Theoretical bound curve (dashed black): sqrt(K·log(1/ε)/n) or sqrt((k+log(1/ε))/n)
      - Horizontal reference lines at each delta level
    """
    n_fine = np.logspace(
        np.log10(SAMPLE_SIZES[0]), np.log10(SAMPLE_SIZES[-1]), 300
    )
    bound_cont = bound_curve_continuous(n_fine)
    bound_disc = bound_curve_discrete(n_fine, bin_size=1)

    for dist_name, dist_config in DISTRIBUTIONS.items():
        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        fig.suptitle(
            f"{dist_config['label']} — TVD vs n  (log–log axes)\n"
            f"{param_str(dist_name, dist_config['params'])}  |  {len(SEEDS)} seeds",
            fontsize=12,
        )

        for ax, tvds_by_n, bound, bound_label, panel_title in [
            (
                axes[0],
                results[dist_name]["kde"],
                bound_cont,
                rf"Bound $\sqrt{{K\log(1/\varepsilon)/n}}$, K={K}",
                "Continuous (KDE, 1ms grid)",
            ),
            (
                axes[1],
                results[dist_name]["pmf"][1],
                bound_disc,
                rf"Bound $\sqrt{{(k+\log(1/\varepsilon))/n}}$, k=150",
                "Discrete (PMF, 1ms bins)",
            ),
        ]:
            medians = [np.median(tvds_by_n[n]) for n in SAMPLE_SIZES]
            q25     = [np.percentile(tvds_by_n[n], 25) for n in SAMPLE_SIZES]
            q75     = [np.percentile(tvds_by_n[n], 75) for n in SAMPLE_SIZES]
            # clip to avoid log(0) — set floor at a small positive value
            q25  = [max(v, 1e-4) for v in q25]

            ax.fill_between(SAMPLE_SIZES, q25, q75,
                            color=dist_config["color"], alpha=0.2,
                            label="IQR across seeds")
            ax.plot(SAMPLE_SIZES, medians, "o-",
                    color=dist_config["color"], linewidth=2.5, markersize=7,
                    label="Median TVD (empirical)")
            ax.plot(n_fine, bound, "--", color="black", linewidth=2.0,
                    label=bound_label)

            for delta, col in zip(DELTAS, DELTA_COLORS):
                ax.axhline(y=delta, color=col, linestyle=":",
                           linewidth=1.2, label=f"δ = {delta}")

            ax.set_xscale("log")
            ax.set_yscale("log")   # log y so bound and empirical are both readable
            ax.set_xlabel("Number of samples (n)")
            ax.set_ylabel("TVD (log scale)")
            ax.set_title(panel_title)
            ax.legend(fontsize=8, ncol=2)
            ax.grid(True, alpha=0.3, which="both")

        plt.tight_layout()
        out = os.path.join(RESULTS_DIR, f"tvd_vs_n_{dist_name}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")


# ============================================================
# console summary table
# ============================================================

def print_summary(results):
    max_n = SAMPLE_SIZES[-1]

    print("\n" + "=" * 90)
    print(f"Empirical n required — smallest n where median TVD ≤ δ  "
          f"('>{ max_n:,}' = not achieved)")
    print("=" * 90)

    for method_key, method_label in [
        ("kde_cont", "Continuous (KDE, 1ms grid)"),
        ("pmf_1ms",  "Discrete   (PMF, 1ms bins)"),
        ("pmf_10ms", "Discrete   (PMF, 10ms bins)"),
    ]:
        print(f"\n{method_label}")
        header = f"{'Distribution':<15}" + "".join(
            f"  {('δ='+str(d)):>8}" for d in DELTAS
        )
        print(header)
        print("-" * len(header))

        for dist_name, dist_config in DISTRIBUTIONS.items():
            if method_key == "kde_cont":
                tvds_by_n = results[dist_name]["kde"]
            elif method_key == "pmf_1ms":
                tvds_by_n = results[dist_name]["pmf"][1]
            else:
                tvds_by_n = results[dist_name]["pmf"][10]

            row = f"{dist_config['label']:<15}"
            for d in DELTAS:
                n = find_n_empirical(tvds_by_n, d)
                s = f"{n:,}" if n is not None else f">{max_n:,}"
                row += f"  {s:>8}"
            print(row)

    print(f"\n{'Theoretical n_theory (formula, distribution-agnostic)'}")
    print(f"{'Method':<35}" + "".join(
        f"  {('δ='+str(d)):>8}" for d in DELTAS
    ))
    print("-" * 90)

    row = f"{'Continuous (KDE, K='+str(K)+')':<35}"
    for d in DELTAS:
        row += f"  {n_theory_continuous(d):>8,}"
    print(row)

    for bs in BIN_SIZES:
        k_val = int(GRID_MAX / bs)
        row = f"{'Discrete (PMF, '+str(bs)+'ms, k='+str(k_val)+')':<35}"
        for d in DELTAS:
            row += f"  {n_theory_discrete(d, bs):>8,}"
        print(row)

    print()


# ============================================================
# main
# ============================================================

if __name__ == "__main__":
    # Clear previous results for this experiment
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR)

    print("n vs delta experiment — theoretical bound vs empirical requirement")
    print(f"  Distributions : {list(DISTRIBUTIONS.keys())}")
    print(f"  Delta range   : {DELTAS}")
    print(f"  Sample sizes  : {SAMPLE_SIZES}")
    print(f"  Seeds         : {len(SEEDS)}")
    print(f"  Epsilon       : {EPSILON}")
    print(f"  Grid K        : {K}  ({BIN_WIDTH}ms bins, 0–{GRID_MAX}ms)")
    print()

    print("Running empirical experiments ...")
    results = run_experiments()

    print_summary(results)

    print("Generating plots ...")
    plot_n_vs_delta_main(results)
    plot_n_vs_delta_overlay(results)
    plot_tvd_vs_n_per_dist(results)

    print("\nDone.")
