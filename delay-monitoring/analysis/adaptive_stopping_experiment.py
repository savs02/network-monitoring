"""
Adaptive stopping experiment.

Implements a ground-truth-free stopping rule for distribution estimation.
The procedure collects samples in batches and compares successive KDE (or PMF)
estimates via TVD.  It stops when the change between consecutive estimates
falls below a threshold theta.

The key property: no ground truth is needed at stopping time.  Ground truth
is used only here in evaluation to verify correctness and measure efficiency.

Varies:
  batch_size in [100, 200, 500, 1000]
  theta      in [delta/4, delta/3, delta/2, delta]  where delta = 0.05

For each (distribution, batch_size, theta, seed):
  1. Stream samples batch by batch
  2. After each batch compute TVD(F_current, F_previous)
  3. Stop when that TVD < theta (first check at n = 2 * batch_size)
  4. Cap at MAX_SAMPLES to handle non-convergence
  5. Evaluate TVD(F_stop, true) against ground truth

Reports:
  - Correctness: fraction of seeds where TVD(F_stop, true) <= delta
  - Efficiency : n_theory / median(n_stop)
  - Summary CSV and a set of heatmap + box-plot figures

Continuous distributions use a KDE on a 1ms grid (K=150 bins, matching
sample_complexity_theoretical.py).  Discrete distributions use the empirical PMF.

Theoretical sample requirements (delta=0.05, epsilon=0.05):
  Continuous (KDE, K=150): n_theory = ceil((K + ln(1/eps)) / delta^2) = 61 199
  Binomial  (k=21):        n_theory = ceil((k + ln(1/eps)) / delta^2) = 9 599
  Zipf      (k=20):        n_theory = ceil((k + ln(1/eps)) / delta^2) = 9 199
  Piecewise (k=20):        n_theory = 9 199
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/adaptive-stopping")

# ── experiment parameters ────────────────────────────────────────────────────

DELTA   = 0.05
EPSILON = 0.05
SEEDS   = list(range(1, 51))   # 50 independent draws per configuration

BATCH_SIZES = [100, 200, 500, 1000]
THRESHOLDS  = [DELTA / 4, DELTA / 3, DELTA / 2, DELTA]   # [0.0125, 0.0167, 0.025, 0.05]
THETA_LABELS = ["δ/4", "δ/3", "δ/2", "δ"]

MAX_SAMPLES_CONTINUOUS = 50_000
MAX_SAMPLES_DISCRETE   = 30_000

# ── continuous distributions ─────────────────────────────────────────────────

GRID_MAX  = 150.0
BIN_WIDTH = 1.0
GRID      = np.arange(BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)   # 150 bin centres
K         = len(GRID)

N_THEORY_CONTINUOUS = math.ceil((K + math.log(1.0 / EPSILON)) / DELTA ** 2)

CONTINUOUS_DISTRIBUTIONS = {
    "normal": {
        "label":  "Normal(40, 4)",
        "params": {"mean": 40.0, "variance": 4.0},
        "color":  "#3498db",
    },
    "lognormal": {
        "label":  "Lognormal(2.3, 0.2)",
        "params": {"mu": 2.3, "sigma": 0.2},
        "color":  "#e74c3c",
    },
    "weibull": {
        "label":  "Weibull(10, 2)",
        "params": {"scale": 10.0, "shape": 2.0},
        "color":  "#2ecc71",
    },
}

# ── discrete distributions ───────────────────────────────────────────────────

DISCRETE_DISTRIBUTIONS = {
    "binomial": {
        "label":    "Binomial(N=20, p=0.5)",
        "color":    "#9b59b6",
        "support":  np.arange(0, 21),
        "k":        21,
        "true_pmf": stats.binom.pmf(np.arange(0, 21), n=20, p=0.5),
        "n_theory": math.ceil((21 + math.log(1.0 / EPSILON)) / DELTA ** 2),
    },
    "zipf": {
        "label":    "Zipf(N=20, α=1.5)",
        "color":    "#e67e22",
        "support":  np.arange(1, 21),
        "k":        20,
        "true_pmf": stats.zipfian.pmf(np.arange(1, 21), a=1.5, n=20),
        "n_theory": math.ceil((20 + math.log(1.0 / EPSILON)) / DELTA ** 2),
    },
    "piecewise": {
        "label":    "Piecewise (multi-modal)",
        "color":    "#27ae60",
        "support":  np.arange(1, 21),
        "k":        20,
        "true_pmf": np.array([
            0.12, 0.02, 0.08, 0.01, 0.10, 0.03, 0.07, 0.12, 0.02, 0.09,
            0.01, 0.08, 0.04, 0.06, 0.02, 0.05, 0.02, 0.04, 0.01, 0.01,
        ]),
        "n_theory": math.ceil((20 + math.log(1.0 / EPSILON)) / DELTA ** 2),
    },
}


# ── helpers ───────────────────────────────────────────────────────────────────

def tvd(p, q):
    return 0.5 * np.sum(np.abs(p - q))


def _to_masses(pdf_values):
    m = pdf_values * BIN_WIDTH
    return m / m.sum()


def kde_estimate(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    return _to_masses(kde(GRID))


def true_continuous_masses(dist_name, params):
    if dist_name == "normal":
        pdf = stats.norm.pdf(GRID, loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        pdf = stats.lognorm.pdf(GRID, s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        pdf = stats.weibull_min.pdf(GRID, c=params["shape"], scale=params["scale"])
    else:
        raise ValueError(dist_name)
    return _to_masses(pdf)


def sample_continuous(dist_name, params, n, rng):
    if dist_name == "normal":
        return rng.normal(loc=params["mean"], scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(dist_name)


def empirical_pmf(samples, support):
    counts = np.array([(samples == v).sum() for v in support], dtype=float)
    total  = counts.sum()
    return counts / total if total > 0 else np.ones(len(support)) / len(support)


def sample_discrete(dist_name, cfg, n, rng):
    pmf     = cfg["true_pmf"]
    support = cfg["support"]
    return rng.choice(support, size=n, p=pmf)


# ── adaptive stopping procedure ───────────────────────────────────────────────

def run_adaptive_continuous(dist_name, params, batch_size, theta, seed, max_samples):
    """
    Returns (n_stop, tvd_at_stop_vs_truth, capped).
    capped=True means MAX_SAMPLES was reached without triggering the criterion.
    """
    rng        = np.random.default_rng(seed)
    true_m     = true_continuous_masses(dist_name, params)
    all_samples = np.array([], dtype=float)

    # collect first batch — no comparison yet
    all_samples = np.concatenate([all_samples, sample_continuous(dist_name, params, batch_size, rng)])
    f_prev      = kde_estimate(all_samples)

    while len(all_samples) < max_samples:
        new_batch   = sample_continuous(dist_name, params, batch_size, rng)
        all_samples = np.concatenate([all_samples, new_batch])
        f_curr      = kde_estimate(all_samples)

        if tvd(f_curr, f_prev) < theta:
            return len(all_samples), tvd(f_curr, true_m), False

        f_prev = f_curr

    # cap reached
    return len(all_samples), tvd(f_prev, true_m), True


def run_adaptive_discrete(dist_name, cfg, batch_size, theta, seed, max_samples):
    rng        = np.random.default_rng(seed)
    support    = cfg["support"]
    true_m     = cfg["true_pmf"]
    all_samples = np.array([], dtype=int)

    all_samples = np.concatenate([all_samples, sample_discrete(dist_name, cfg, batch_size, rng)])
    f_prev      = empirical_pmf(all_samples, support)

    while len(all_samples) < max_samples:
        new_batch   = sample_discrete(dist_name, cfg, batch_size, rng)
        all_samples = np.concatenate([all_samples, new_batch])
        f_curr      = empirical_pmf(all_samples, support)

        if tvd(f_curr, f_prev) < theta:
            return len(all_samples), tvd(f_curr, true_m), False

        f_prev = f_curr

    return len(all_samples), tvd(f_prev, true_m), True


# ── run all combinations ──────────────────────────────────────────────────────

def run_continuous():
    rows = []
    total = len(CONTINUOUS_DISTRIBUTIONS) * len(BATCH_SIZES) * len(THRESHOLDS) * len(SEEDS)
    done  = 0

    for dist_name, cfg in CONTINUOUS_DISTRIBUTIONS.items():
        true_m = true_continuous_masses(dist_name, cfg["params"])
        for batch_size in BATCH_SIZES:
            for theta, theta_label in zip(THRESHOLDS, THETA_LABELS):
                n_stops, tvds, caps = [], [], []
                for seed in SEEDS:
                    n_stop, tvd_val, capped = run_adaptive_continuous(
                        dist_name, cfg["params"], batch_size, theta, seed,
                        MAX_SAMPLES_CONTINUOUS
                    )
                    n_stops.append(n_stop)
                    tvds.append(tvd_val)
                    caps.append(capped)
                    done += 1

                correctness  = np.mean(np.array(tvds) <= DELTA)
                median_n     = np.median(n_stops)
                cap_rate     = np.mean(caps)
                efficiency   = N_THEORY_CONTINUOUS / median_n

                rows.append({
                    "dist":        dist_name,
                    "batch_size":  batch_size,
                    "theta":       theta,
                    "theta_label": theta_label,
                    "n_theory":    N_THEORY_CONTINUOUS,
                    "median_n_stop":   median_n,
                    "mean_n_stop":     np.mean(n_stops),
                    "q25_n_stop":      np.percentile(n_stops, 25),
                    "q75_n_stop":      np.percentile(n_stops, 75),
                    "correctness": correctness,
                    "efficiency":  efficiency,
                    "cap_rate":    cap_rate,
                    "n_stops":     n_stops,
                    "tvds":        tvds,
                })
                print(
                    f"  {dist_name:<12}  B={batch_size:<5}  θ={theta_label:<4}  "
                    f"correct={correctness:.2f}  median_n={median_n:>7.0f}  "
                    f"efficiency={efficiency:.1f}x  caps={cap_rate:.2f}"
                )

    return rows


def run_discrete():
    rows = []
    for dist_name, cfg in DISCRETE_DISTRIBUTIONS.items():
        for batch_size in BATCH_SIZES:
            for theta, theta_label in zip(THRESHOLDS, THETA_LABELS):
                n_stops, tvds, caps = [], [], []
                for seed in SEEDS:
                    n_stop, tvd_val, capped = run_adaptive_discrete(
                        dist_name, cfg, batch_size, theta, seed,
                        MAX_SAMPLES_DISCRETE
                    )
                    n_stops.append(n_stop)
                    tvds.append(tvd_val)
                    caps.append(capped)

                correctness = np.mean(np.array(tvds) <= DELTA)
                median_n    = np.median(n_stops)
                cap_rate    = np.mean(caps)
                efficiency  = cfg["n_theory"] / median_n

                rows.append({
                    "dist":        dist_name,
                    "batch_size":  batch_size,
                    "theta":       theta,
                    "theta_label": theta_label,
                    "n_theory":    cfg["n_theory"],
                    "median_n_stop":   median_n,
                    "mean_n_stop":     np.mean(n_stops),
                    "q25_n_stop":      np.percentile(n_stops, 25),
                    "q75_n_stop":      np.percentile(n_stops, 75),
                    "correctness": correctness,
                    "efficiency":  efficiency,
                    "cap_rate":    cap_rate,
                    "n_stops":     n_stops,
                    "tvds":        tvds,
                })
                print(
                    f"  {dist_name:<12}  B={batch_size:<5}  θ={theta_label:<4}  "
                    f"correct={correctness:.2f}  median_n={median_n:>7.0f}  "
                    f"efficiency={efficiency:.1f}x  caps={cap_rate:.2f}"
                )

    return rows


# ── plotting ──────────────────────────────────────────────────────────────────

def heatmaps(rows, title_prefix, dist_names, out_suffix):
    """
    For each distribution, produce a 2×2 subplot grid:
      left  column: correctness rate (colour)
      right column: efficiency       (colour)
    Rows = batch sizes, columns within each panel = theta labels.
    """
    for dist_name in dist_names:
        subset = [r for r in rows if r["dist"] == dist_name]

        corr_grid = np.zeros((len(BATCH_SIZES), len(THRESHOLDS)))
        eff_grid  = np.zeros((len(BATCH_SIZES), len(THRESHOLDS)))

        for r in subset:
            i = BATCH_SIZES.index(r["batch_size"])
            j = THRESHOLDS.index(r["theta"])
            corr_grid[i, j] = r["correctness"]
            eff_grid[i, j]  = r["efficiency"]

        fig, axes = plt.subplots(1, 2, figsize=(11, 4))

        # correctness
        im0 = axes[0].imshow(corr_grid, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        axes[0].set_xticks(range(len(THRESHOLDS)))
        axes[0].set_xticklabels(THETA_LABELS)
        axes[0].set_yticks(range(len(BATCH_SIZES)))
        axes[0].set_yticklabels([str(b) for b in BATCH_SIZES])
        axes[0].set_xlabel("Stopping threshold θ")
        axes[0].set_ylabel("Batch size")
        axes[0].set_title("Correctness (fraction TVD ≤ δ)")
        plt.colorbar(im0, ax=axes[0])
        for i in range(len(BATCH_SIZES)):
            for j in range(len(THRESHOLDS)):
                axes[0].text(j, i, f"{corr_grid[i,j]:.2f}",
                             ha="center", va="center", fontsize=9,
                             color="black" if 0.3 < corr_grid[i,j] < 0.8 else "white")

        # efficiency
        im1 = axes[1].imshow(eff_grid, cmap="Blues", aspect="auto")
        axes[1].set_xticks(range(len(THRESHOLDS)))
        axes[1].set_xticklabels(THETA_LABELS)
        axes[1].set_yticks(range(len(BATCH_SIZES)))
        axes[1].set_yticklabels([str(b) for b in BATCH_SIZES])
        axes[1].set_xlabel("Stopping threshold θ")
        axes[1].set_ylabel("Batch size")
        axes[1].set_title("Efficiency (n_theory / median n_stop)")
        plt.colorbar(im1, ax=axes[1])
        for i in range(len(BATCH_SIZES)):
            for j in range(len(THRESHOLDS)):
                axes[1].text(j, i, f"{eff_grid[i,j]:.1f}x",
                             ha="center", va="center", fontsize=9, color="white")

        dist_label = (CONTINUOUS_DISTRIBUTIONS.get(dist_name) or
                      DISCRETE_DISTRIBUTIONS.get(dist_name))["label"]
        fig.suptitle(f"{title_prefix} — {dist_label}", fontsize=12, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(RESULTS_DIR, f"heatmap_{out_suffix}_{dist_name}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")


def boxplots_n_stop(rows, title_prefix, dist_names, out_suffix):
    """
    For each distribution, box plots of n_stop grouped by batch size,
    with one subplot per theta.  n_theory is shown as a horizontal dashed line.
    """
    for dist_name in dist_names:
        subset    = [r for r in rows if r["dist"] == dist_name]
        n_theory  = subset[0]["n_theory"]
        dist_label = (CONTINUOUS_DISTRIBUTIONS.get(dist_name) or
                      DISCRETE_DISTRIBUTIONS.get(dist_name))["label"]

        fig, axes = plt.subplots(1, len(THRESHOLDS), figsize=(14, 5), sharey=True)

        for j, (theta, theta_label) in enumerate(zip(THRESHOLDS, THETA_LABELS)):
            ax     = axes[j]
            data   = [r["n_stops"] for r in subset if r["theta"] == theta]
            labels = [str(b) for b in BATCH_SIZES]

            ax.boxplot(data, labels=labels, patch_artist=True,
                       boxprops=dict(facecolor="#aec6e8", alpha=0.7))
            ax.axhline(n_theory, color="red", linestyle="--", linewidth=1.2,
                       label=f"n_theory = {n_theory:,}")
            ax.set_xlabel("Batch size")
            ax.set_title(f"θ = {theta_label}")
            if j == 0:
                ax.set_ylabel("n_stop")
            if j == len(THRESHOLDS) - 1:
                ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3, axis="y")

        fig.suptitle(f"{title_prefix} n_stop distributions — {dist_label}",
                     fontsize=11, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(RESULTS_DIR, f"boxplot_{out_suffix}_{dist_name}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")


def correctness_vs_efficiency_scatter(rows, title_prefix, dist_names, out_suffix):
    """
    Scatter plot: x = efficiency (n_theory / median n_stop), y = correctness.
    Each point is a (batch_size, theta) combination.  Colour encodes theta.
    """
    fig, axes = plt.subplots(1, len(dist_names), figsize=(5 * len(dist_names), 4),
                             sharey=True)
    if len(dist_names) == 1:
        axes = [axes]

    cmap   = plt.get_cmap("plasma")
    colors = [cmap(i / (len(THRESHOLDS) - 1)) for i in range(len(THRESHOLDS))]

    for ax, dist_name in zip(axes, dist_names):
        dist_label = (CONTINUOUS_DISTRIBUTIONS.get(dist_name) or
                      DISCRETE_DISTRIBUTIONS.get(dist_name))["label"]
        subset = [r for r in rows if r["dist"] == dist_name]

        for theta, theta_label, color in zip(THRESHOLDS, THETA_LABELS, colors):
            sub = [r for r in subset if r["theta"] == theta]
            xs  = [r["efficiency"]   for r in sub]
            ys  = [r["correctness"]  for r in sub]
            bs  = [r["batch_size"]   for r in sub]
            sc  = ax.scatter(xs, ys, color=color, s=60, label=f"θ={theta_label}", zorder=3)
            for x, y, b in zip(xs, ys, bs):
                ax.annotate(str(b), (x, y), textcoords="offset points",
                            xytext=(4, 2), fontsize=7)

        ax.axhline(0.95, color="grey", linestyle=":", linewidth=1.0, label="95% target")
        ax.set_xlabel("Efficiency (n_theory / median n_stop)")
        ax.set_title(dist_label)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel("Correctness (fraction TVD ≤ δ)")
    fig.suptitle(f"{title_prefix} — correctness vs efficiency",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"scatter_{out_suffix}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def save_csv(rows, filename):
    df = pd.DataFrame([
        {k: v for k, v in r.items() if k not in ("n_stops", "tvds")}
        for r in rows
    ])
    df = df.sort_values(["dist", "batch_size", "theta"]).reset_index(drop=True)
    path = os.path.join(RESULTS_DIR, filename)
    df.to_csv(path, index=False, float_format="%.4f")
    print(f"  Saved: {path}")
    return df


def print_summary(df, n_theory_col="n_theory"):
    print(f"\n{'Distribution':<15} {'Batch':>6} {'θ':>5} {'Correct':>8} "
          f"{'Med n_stop':>12} {'Efficiency':>11} {'Cap%':>6}")
    print("─" * 72)
    for _, r in df.iterrows():
        print(
            f"{r['dist']:<15} {int(r['batch_size']):>6} {r['theta_label']:>5} "
            f"{r['correctness']:>8.2f} {r['median_n_stop']:>12.0f} "
            f"{r['efficiency']:>10.1f}x {r['cap_rate']*100:>5.1f}%"
        )


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print(f"Adaptive stopping experiment")
    print(f"  delta={DELTA}  epsilon={EPSILON}  seeds={len(SEEDS)}")
    print(f"  batch sizes : {BATCH_SIZES}")
    print(f"  thresholds  : {[f'{t:.4f} ({l})' for t, l in zip(THRESHOLDS, THETA_LABELS)]}")
    print(f"  n_theory (continuous, K={K}) = {N_THEORY_CONTINUOUS:,}")
    print()

    # ── continuous ────────────────────────────────────────────────────────────
    print("── Continuous distributions ────────────────────────────────────────")
    cont_rows = run_continuous()
    df_cont   = save_csv(cont_rows, "results_continuous.csv")
    print_summary(df_cont)

    print("\nGenerating continuous plots ...")
    heatmaps(cont_rows, "Continuous", list(CONTINUOUS_DISTRIBUTIONS), "continuous")
    boxplots_n_stop(cont_rows, "Continuous", list(CONTINUOUS_DISTRIBUTIONS), "continuous")
    correctness_vs_efficiency_scatter(
        cont_rows, "Continuous", list(CONTINUOUS_DISTRIBUTIONS), "continuous"
    )

    # ── discrete ──────────────────────────────────────────────────────────────
    print("\n── Discrete distributions ──────────────────────────────────────────")
    disc_rows = run_discrete()
    df_disc   = save_csv(disc_rows, "results_discrete.csv")
    print_summary(df_disc)

    print("\nGenerating discrete plots ...")
    heatmaps(disc_rows, "Discrete", list(DISCRETE_DISTRIBUTIONS), "discrete")
    boxplots_n_stop(disc_rows, "Discrete", list(DISCRETE_DISTRIBUTIONS), "discrete")
    correctness_vs_efficiency_scatter(
        disc_rows, "Discrete", list(DISCRETE_DISTRIBUTIONS), "discrete"
    )

    print("\nDone. Results in:", RESULTS_DIR)
