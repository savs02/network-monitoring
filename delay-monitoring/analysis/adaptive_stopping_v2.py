"""
Adaptive stopping experiment v2 — 100 seeds, extended parameter sweep.

Stopping rule: collect samples in batches; after each batch compute
TVD(F_current, F_previous); stop when that TVD < theta.  No ground truth
is used at stopping time.  Ground truth is used only here, post-hoc, to
verify correctness and measure efficiency.

Parameter grid (48 configurations):
  batch_size in [100, 200, 300, 500, 750, 1000, 1500, 2000]
  theta      in [delta/6, delta/5, delta/4, delta/3, delta/2, delta]

Each (distribution, batch_size, theta) pair is evaluated over 100 seeds.

Produces:
  results_continuous.csv / results_discrete.csv
  heatmap_*   — correctness and efficiency as a function of (B, theta)
  boxplot_*   — n_stop distributions per configuration
  scatter_*   — correctness vs efficiency scatter
  tvd_at_stop_* — distribution of TVD(F_stop, true) at stopping time
  stopping_cdf_* — empirical CDF of n_stop for selected configurations
"""

import math, os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/adaptive-stopping-v2")

# ── parameters ────────────────────────────────────────────────────────────────

DELTA   = 0.05
EPSILON = 0.05
SEEDS   = list(range(1, 101))

BATCH_SIZES  = [100, 200, 300, 500, 750, 1000, 1500, 2000]
THETA_FRACS  = [1/6, 1/5, 1/4, 1/3, 1/2, 1]
THRESHOLDS   = [DELTA * f for f in THETA_FRACS]
THETA_LABELS = ["δ/6", "δ/5", "δ/4", "δ/3", "δ/2", "δ"]

MAX_SAMPLES_CONTINUOUS = 60_000
MAX_SAMPLES_DISCRETE   = 30_000

# ── continuous grid ───────────────────────────────────────────────────────────

GRID_MAX  = 150.0
BIN_WIDTH = 1.0
GRID      = np.arange(BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)
K         = len(GRID)

N_THEORY_CONT = math.ceil((K + math.log(1.0 / EPSILON)) / DELTA ** 2)

CONTINUOUS_DISTS = {
    "normal":    {"label": "Normal(40, 4)",        "params": {"mean": 40.0, "variance": 4.0}, "color": "#3498db"},
    "lognormal": {"label": "Lognormal(2.3, 0.2)",  "params": {"mu": 2.3, "sigma": 0.2},       "color": "#e74c3c"},
    "weibull":   {"label": "Weibull(10, 2)",        "params": {"scale": 10.0, "shape": 2.0},   "color": "#2ecc71"},
}

DISCRETE_DISTS = {
    "binomial": {
        "label": "Binomial(N=20, p=0.5)", "color": "#9b59b6",
        "support": np.arange(0, 21), "k": 21,
        "true_pmf": stats.binom.pmf(np.arange(0, 21), n=20, p=0.5),
        "n_theory": math.ceil((21 + math.log(1.0 / EPSILON)) / DELTA ** 2),
    },
    "zipf": {
        "label": "Zipf(N=20, α=1.5)", "color": "#e67e22",
        "support": np.arange(1, 21), "k": 20,
        "true_pmf": stats.zipfian.pmf(np.arange(1, 21), a=1.5, n=20),
        "n_theory": math.ceil((20 + math.log(1.0 / EPSILON)) / DELTA ** 2),
    },
    "piecewise": {
        "label": "Piecewise (multi-modal)", "color": "#27ae60",
        "support": np.arange(1, 21), "k": 20,
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
    s = m.sum()
    return m / s if s > 0 else np.ones_like(m) / len(m)

def kde_estimate(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    return _to_masses(kde(GRID))

def true_cont_masses(dist_name, params):
    if dist_name == "normal":
        pdf = stats.norm.pdf(GRID, loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        pdf = stats.lognorm.pdf(GRID, s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        pdf = stats.weibull_min.pdf(GRID, c=params["shape"], scale=params["scale"])
    else:
        raise ValueError(dist_name)
    return _to_masses(pdf)

def sample_continuous_all(dist_name, params, n, rng):
    if dist_name == "normal":
        return rng.normal(loc=params["mean"], scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(dist_name)

def empirical_pmf(samples, support):
    counts = np.array([(samples == v).sum() for v in support], dtype=float)
    s = counts.sum()
    return counts / s if s > 0 else np.ones(len(support)) / len(support)

# ── adaptive stopping ─────────────────────────────────────────────────────────

def adaptive_continuous(dist_name, params, batch_size, theta, seed, max_samples):
    rng       = np.random.default_rng(seed)
    true_m    = true_cont_masses(dist_name, params)
    # Pre-generate all samples; slice as needed (faster than repeated concat)
    pool      = sample_continuous_all(dist_name, params, max_samples, rng)
    n         = batch_size
    f_prev    = kde_estimate(pool[:n])
    tvds_between = []

    while n + batch_size <= max_samples:
        n     += batch_size
        f_cur  = kde_estimate(pool[:n])
        tb     = tvd(f_cur, f_prev)
        tvds_between.append(tb)
        if tb < theta:
            return n, tvd(f_cur, true_m), False, tvds_between
        f_prev = f_cur

    return n, tvd(f_prev, true_m), True, tvds_between

def adaptive_discrete(dist_name, cfg, batch_size, theta, seed, max_samples):
    rng     = np.random.default_rng(seed)
    support = cfg["support"]
    true_m  = cfg["true_pmf"]
    pool    = rng.choice(support, size=max_samples, p=true_m)
    n       = batch_size
    f_prev  = empirical_pmf(pool[:n], support)
    tvds_between = []

    while n + batch_size <= max_samples:
        n    += batch_size
        f_cur = empirical_pmf(pool[:n], support)
        tb    = tvd(f_cur, f_prev)
        tvds_between.append(tb)
        if tb < theta:
            return n, tvd(f_cur, true_m), False, tvds_between
        f_prev = f_cur

    return n, tvd(f_prev, true_m), True, tvds_between

# ── run experiments ───────────────────────────────────────────────────────────

def run_all(dist_dict, is_continuous):
    rows = []
    fn   = adaptive_continuous if is_continuous else adaptive_discrete
    max_s = MAX_SAMPLES_CONTINUOUS if is_continuous else MAX_SAMPLES_DISCRETE

    for dist_name, cfg in dist_dict.items():
        n_theory = N_THEORY_CONT if is_continuous else cfg["n_theory"]
        args = (cfg["params"],) if is_continuous else (cfg,)

        for batch_size in BATCH_SIZES:
            for theta, theta_label in zip(THRESHOLDS, THETA_LABELS):
                n_stops, tvd_vals, caps = [], [], []
                for seed in SEEDS:
                    n_stop, tvd_val, capped, _ = fn(dist_name, *args, batch_size, theta, seed, max_s)
                    n_stops.append(n_stop)
                    tvd_vals.append(tvd_val)
                    caps.append(capped)

                correctness = float(np.mean(np.array(tvd_vals) <= DELTA))
                median_n    = float(np.median(n_stops))
                efficiency  = n_theory / median_n

                rows.append({
                    "dist":          dist_name,
                    "batch_size":    batch_size,
                    "theta":         theta,
                    "theta_label":   theta_label,
                    "n_theory":      n_theory,
                    "median_n_stop": median_n,
                    "mean_n_stop":   float(np.mean(n_stops)),
                    "q25_n_stop":    float(np.percentile(n_stops, 25)),
                    "q75_n_stop":    float(np.percentile(n_stops, 75)),
                    "correctness":   correctness,
                    "efficiency":    efficiency,
                    "cap_rate":      float(np.mean(caps)),
                    "n_stops":       n_stops,
                    "tvd_vals":      tvd_vals,
                })
                print(
                    f"  {dist_name:<12}  B={batch_size:<5}  θ={theta_label:<4}  "
                    f"correct={correctness:.2f}  med_n={median_n:>7.0f}  "
                    f"eff={efficiency:>6.1f}x  caps={np.mean(caps):.2f}"
                )
    return rows

# ── plotting ──────────────────────────────────────────────────────────────────

def heatmaps(rows, dist_dict, suffix):
    for dist_name, cfg in dist_dict.items():
        sub = [r for r in rows if r["dist"] == dist_name]
        corr = np.zeros((len(BATCH_SIZES), len(THRESHOLDS)))
        eff  = np.zeros((len(BATCH_SIZES), len(THRESHOLDS)))
        for r in sub:
            i = BATCH_SIZES.index(r["batch_size"])
            j = THRESHOLDS.index(r["theta"])
            corr[i, j] = r["correctness"]
            eff[i, j]  = r["efficiency"]

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        im0 = axes[0].imshow(corr, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        axes[0].set_xticks(range(len(THRESHOLDS))); axes[0].set_xticklabels(THETA_LABELS)
        axes[0].set_yticks(range(len(BATCH_SIZES))); axes[0].set_yticklabels(BATCH_SIZES)
        axes[0].set_xlabel("Stopping threshold θ"); axes[0].set_ylabel("Batch size")
        axes[0].set_title("Correctness (fraction with TVD ≤ δ at stop)")
        plt.colorbar(im0, ax=axes[0])
        for i in range(len(BATCH_SIZES)):
            for j in range(len(THRESHOLDS)):
                c = corr[i, j]
                axes[0].text(j, i, f"{c:.2f}", ha="center", va="center", fontsize=8,
                             color="black" if 0.25 < c < 0.75 else "white")

        im1 = axes[1].imshow(eff, cmap="YlOrRd", aspect="auto")
        axes[1].set_xticks(range(len(THRESHOLDS))); axes[1].set_xticklabels(THETA_LABELS)
        axes[1].set_yticks(range(len(BATCH_SIZES))); axes[1].set_yticklabels(BATCH_SIZES)
        axes[1].set_xlabel("Stopping threshold θ"); axes[1].set_ylabel("Batch size")
        axes[1].set_title("Efficiency (n_theory / median n_stop)")
        plt.colorbar(im1, ax=axes[1])
        for i in range(len(BATCH_SIZES)):
            for j in range(len(THRESHOLDS)):
                axes[1].text(j, i, f"{eff[i,j]:.0f}x", ha="center", va="center",
                             fontsize=8, color="white")

        fig.suptitle(f"{cfg['label']} — correctness and efficiency grid\n"
                     f"100 seeds, δ={DELTA}, ε={EPSILON}", fontsize=11, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(RESULTS_DIR, f"heatmap_{suffix}_{dist_name}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
        print(f"  Saved: {path}")


def boxplots_n_stop(rows, dist_dict, suffix):
    for dist_name, cfg in dist_dict.items():
        sub       = [r for r in rows if r["dist"] == dist_name]
        n_theory  = sub[0]["n_theory"]

        fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharey=True)
        axes = axes.flatten()

        for j, (theta, theta_label) in enumerate(zip(THRESHOLDS, THETA_LABELS)):
            ax   = axes[j]
            data = [r["n_stops"] for r in sub if r["theta"] == theta]
            ax.boxplot(data, tick_labels=BATCH_SIZES, patch_artist=True,
                       boxprops=dict(facecolor="#aec6e8", alpha=0.75),
                       medianprops=dict(color="#c0392b", linewidth=2))
            ax.axhline(n_theory, color="red", linestyle="--", linewidth=1.2,
                       label=f"n_theory = {n_theory:,}")
            ax.set_xlabel("Batch size"); ax.set_title(f"θ = {theta_label}")
            if j % 3 == 0: ax.set_ylabel("n_stop")
            ax.legend(fontsize=7); ax.grid(True, alpha=0.3, axis="y")

        fig.suptitle(f"{cfg['label']} — n_stop by (batch size, θ)\n"
                     f"100 seeds, δ={DELTA}", fontsize=11, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(RESULTS_DIR, f"boxplot_{suffix}_{dist_name}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
        print(f"  Saved: {path}")


def tvd_at_stop_plots(rows, dist_dict, suffix):
    """Violin plots of TVD(F_stop, true) at stopping time."""
    for dist_name, cfg in dist_dict.items():
        sub = [r for r in rows if r["dist"] == dist_name]

        fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharey=True)
        axes = axes.flatten()

        for j, (theta, theta_label) in enumerate(zip(THRESHOLDS, THETA_LABELS)):
            ax   = axes[j]
            data = [r["tvd_vals"] for r in sub if r["theta"] == theta]
            parts = ax.violinplot(data, positions=range(1, len(BATCH_SIZES) + 1),
                                  showmedians=True, showextrema=True)
            for pc in parts["bodies"]:
                pc.set_facecolor("#85c1e9"); pc.set_alpha(0.7)
            ax.axhline(DELTA, color="red", linestyle="--", linewidth=1.2,
                       label=f"δ = {DELTA}")
            ax.set_xticks(range(1, len(BATCH_SIZES) + 1))
            ax.set_xticklabels(BATCH_SIZES, fontsize=8)
            ax.set_xlabel("Batch size"); ax.set_title(f"θ = {theta_label}")
            if j % 3 == 0: ax.set_ylabel("TVD(F_stop, true)")
            ax.legend(fontsize=7); ax.grid(True, alpha=0.3, axis="y")

        fig.suptitle(f"{cfg['label']} — TVD against truth at stopping time\n"
                     f"100 seeds, δ={DELTA}", fontsize=11, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(RESULTS_DIR, f"tvd_at_stop_{suffix}_{dist_name}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
        print(f"  Saved: {path}")


def stopping_cdf_plots(rows, dist_dict, suffix):
    """
    Empirical CDF of n_stop for each (batch_size, theta) combo on one axes.
    One figure per distribution.  Lines coloured by theta; one panel per batch size.
    """
    cmap   = plt.get_cmap("plasma")
    colors = [cmap(i / (len(THRESHOLDS) - 1)) for i in range(len(THRESHOLDS))]

    for dist_name, cfg in dist_dict.items():
        sub      = [r for r in rows if r["dist"] == dist_name]
        n_theory = sub[0]["n_theory"]
        nbatch   = len(BATCH_SIZES)
        ncols    = 4
        nrows    = math.ceil(nbatch / ncols)

        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows), sharey=True)
        axes = axes.flatten()

        for i, batch_size in enumerate(BATCH_SIZES):
            ax = axes[i]
            for theta, theta_label, color in zip(THRESHOLDS, THETA_LABELS, colors):
                matches = [r for r in sub if r["batch_size"] == batch_size and r["theta"] == theta]
                if not matches:
                    continue
                ns = np.sort(matches[0]["n_stops"])
                ys = np.arange(1, len(ns) + 1) / len(ns)
                ax.step(ns, ys, where="post", color=color, linewidth=1.5,
                        label=f"θ={theta_label}")
            ax.axvline(n_theory, color="red", linestyle=":", linewidth=1.0,
                       label=f"n_theory={n_theory:,}")
            ax.set_title(f"B = {batch_size}")
            ax.set_xlabel("n_stop"); ax.grid(True, alpha=0.3)
            if i % ncols == 0: ax.set_ylabel("Empirical CDF")
            if i == 0: ax.legend(fontsize=7, loc="lower right")

        for j in range(nbatch, len(axes)):
            axes[j].set_visible(False)

        fig.suptitle(f"{cfg['label']} — CDF of n_stop by configuration\n"
                     f"100 seeds, δ={DELTA}", fontsize=11, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(RESULTS_DIR, f"stopping_cdf_{suffix}_{dist_name}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
        print(f"  Saved: {path}")


def correctness_efficiency_scatter(rows, dist_dict, suffix):
    """Scatter: efficiency (x) vs correctness (y), colour = theta, marker = batch_size."""
    cmap   = plt.get_cmap("plasma")
    colors = [cmap(i / (len(THRESHOLDS) - 1)) for i in range(len(THRESHOLDS))]
    markers = ["o", "s", "^", "D", "v", "P", "X", "*"]

    dist_names = list(dist_dict.keys())
    fig, axes  = plt.subplots(1, len(dist_names), figsize=(5 * len(dist_names), 5),
                              sharey=True)
    if len(dist_names) == 1:
        axes = [axes]

    for ax, dist_name in zip(axes, dist_names):
        sub = [r for r in rows if r["dist"] == dist_name]
        cfg = dist_dict[dist_name]

        for j, (theta, theta_label, color) in enumerate(zip(THRESHOLDS, THETA_LABELS, colors)):
            sub_t = [r for r in sub if r["theta"] == theta]
            xs    = [r["efficiency"]   for r in sub_t]
            ys    = [r["correctness"]  for r in sub_t]
            bsz   = [r["batch_size"]   for r in sub_t]
            for x, y, b, mk in zip(xs, ys, bsz, markers):
                ax.scatter(x, y, color=color, marker=mk, s=70, zorder=3,
                           label=f"θ={theta_label}, B={b}" if j == 0 else "")
                ax.annotate(str(b), (x, y), textcoords="offset points",
                            xytext=(4, 2), fontsize=6.5)
            ax.plot(xs, ys, color=color, linewidth=0.8, alpha=0.5)

        ax.axhline(0.95, color="grey", linestyle=":", linewidth=1.0, label="95% target")
        ax.set_xlabel("Efficiency (n_theory / median n_stop)")
        ax.set_title(cfg["label"]); ax.grid(True, alpha=0.3)

        handles = [plt.Line2D([0], [0], color=c, linewidth=2, label=f"θ={l}")
                   for c, l in zip(colors, THETA_LABELS)]
        handles.append(plt.Line2D([0], [0], color="grey", linestyle=":", label="95%"))
        ax.legend(handles=handles, fontsize=8, loc="lower right")

    axes[0].set_ylabel("Correctness (fraction with TVD ≤ δ)")
    fig.suptitle(f"Correctness vs efficiency — {suffix}\n"
                 f"100 seeds, δ={DELTA}", fontsize=11, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"scatter_{suffix}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  Saved: {path}")


def summary_correctness_grid(rows, dist_dict, suffix):
    """
    Single figure: correctness heatmap for all distributions side by side,
    showing the full (B, θ) grid.  Useful for comparing across distributions.
    """
    ndists = len(dist_dict)
    fig, axes = plt.subplots(1, ndists, figsize=(5 * ndists, 5))
    if ndists == 1:
        axes = [axes]

    for ax, (dist_name, cfg) in zip(axes, dist_dict.items()):
        sub  = [r for r in rows if r["dist"] == dist_name]
        corr = np.zeros((len(BATCH_SIZES), len(THRESHOLDS)))
        for r in sub:
            i = BATCH_SIZES.index(r["batch_size"])
            j = THRESHOLDS.index(r["theta"])
            corr[i, j] = r["correctness"]

        im = ax.imshow(corr, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(THRESHOLDS))); ax.set_xticklabels(THETA_LABELS, fontsize=9)
        ax.set_yticks(range(len(BATCH_SIZES))); ax.set_yticklabels(BATCH_SIZES, fontsize=9)
        ax.set_xlabel("θ"); ax.set_title(cfg["label"], fontsize=10)
        for i in range(len(BATCH_SIZES)):
            for j in range(len(THRESHOLDS)):
                c = corr[i, j]
                ax.text(j, i, f"{c:.2f}", ha="center", va="center", fontsize=7.5,
                        color="black" if 0.25 < c < 0.75 else "white")
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    axes[0].set_ylabel("Batch size")
    fig.suptitle(f"Correctness across all distributions — {suffix}\n"
                 f"100 seeds, δ={DELTA}", fontsize=11, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"correctness_grid_{suffix}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  Saved: {path}")


def save_csv(rows, filename):
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("n_stops", "tvd_vals")}
                       for r in rows])
    df = df.sort_values(["dist", "batch_size", "theta"]).reset_index(drop=True)
    path = os.path.join(RESULTS_DIR, filename)
    df.to_csv(path, index=False, float_format="%.4f")
    print(f"  Saved CSV: {path}")
    return df

# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Adaptive stopping experiment v2")
    print(f"  seeds={len(SEEDS)}  δ={DELTA}  ε={EPSILON}")
    print(f"  batch sizes : {BATCH_SIZES}")
    print(f"  thresholds  : {THETA_LABELS}")
    print(f"  configs     : {len(BATCH_SIZES) * len(THRESHOLDS)} per distribution")
    print(f"  n_theory (continuous, K={K}) = {N_THEORY_CONT:,}")
    print()

    print("── Continuous ─────────────────────────────────────────────────────")
    cont_rows = run_all(CONTINUOUS_DISTS, is_continuous=True)
    df_cont   = save_csv(cont_rows, "results_continuous.csv")

    print("\nPlotting continuous ...")
    heatmaps(cont_rows, CONTINUOUS_DISTS, "cont")
    boxplots_n_stop(cont_rows, CONTINUOUS_DISTS, "cont")
    tvd_at_stop_plots(cont_rows, CONTINUOUS_DISTS, "cont")
    stopping_cdf_plots(cont_rows, CONTINUOUS_DISTS, "cont")
    correctness_efficiency_scatter(cont_rows, CONTINUOUS_DISTS, "cont")
    summary_correctness_grid(cont_rows, CONTINUOUS_DISTS, "cont")

    print("\n── Discrete ───────────────────────────────────────────────────────")
    disc_rows = run_all(DISCRETE_DISTS, is_continuous=False)
    df_disc   = save_csv(disc_rows, "results_discrete.csv")

    print("\nPlotting discrete ...")
    heatmaps(disc_rows, DISCRETE_DISTS, "disc")
    boxplots_n_stop(disc_rows, DISCRETE_DISTS, "disc")
    tvd_at_stop_plots(disc_rows, DISCRETE_DISTS, "disc")
    stopping_cdf_plots(disc_rows, DISCRETE_DISTS, "disc")
    correctness_efficiency_scatter(disc_rows, DISCRETE_DISTS, "disc")
    summary_correctness_grid(disc_rows, DISCRETE_DISTS, "disc")

    print("\nDone. All results in:", RESULTS_DIR)
