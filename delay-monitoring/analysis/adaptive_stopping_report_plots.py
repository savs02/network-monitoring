"""
Report plots for the adaptive stopping evaluation.

This script reuses the 100-seed adaptive stopping sweep in
results/adaptive-stopping-v2 and adds report-specific diagnostics:

* heatmaps with batch size increasing upwards;
* continuous stopping summaries for normal, lognormal, and Weibull;
* zoomed B=200 stopped KDE reconstructions with true distributions overlaid;
* continued traces after an early B=100 stop.

The additional stopped-distribution and trace plots are illustrative follow-up
runs. They use the same estimator and stopping rule as adaptive_stopping_v2.py.
"""

import csv
import math
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("MPLCONFIGDIR", os.path.join(SCRIPT_DIR, "../results/.matplotlib"))

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from scipy import stats

plt.rcParams.update(
    {
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.titlesize": 15,
    }
)

V2_RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/adaptive-stopping-v2")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/adaptive-stopping-report")

DELTA = 0.05
EPSILON = 0.05
BIN_WIDTH = 1.0
GRID_MAX = 150.0
GRID = np.arange(BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)

BATCH_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000]
THETA_FRACS = [1 / 6, 1 / 5, 1 / 4, 1 / 3, 1 / 2, 1]
THETA_VALUES = [DELTA * f for f in THETA_FRACS]
THETA_KEYS = ["delta/6", "delta/5", "delta/4", "delta/3", "delta/2", "delta"]
THETA_DISPLAY = [
    r"$\delta/6$",
    r"$\delta/5$",
    r"$\delta/4$",
    r"$\delta/3$",
    r"$\delta/2$",
    r"$\delta$",
]

LABEL_OUTLINE = [pe.withStroke(linewidth=2.2, foreground="white", alpha=0.95)]

CONTINUOUS_DISTS = {
    "normal": {
        "label": "Normal",
        "params": {"mean": 40.0, "variance": 4.0},
        "color": "#2874a6",
    },
    "lognormal": {
        "label": "Lognormal",
        "params": {"mu": 2.3, "sigma": 0.2},
        "color": "#c0392b",
    },
    "weibull": {
        "label": "Weibull",
        "params": {"scale": 10.0, "shape": 2.0},
        "color": "#d68910",
    },
}

STOPPED_XLIMS = {
    "normal": (32, 48),
    "lognormal": (5, 16),
    "weibull": (0, 24),
}

DISCRETE_LABELS = {
    "binomial": "Binomial",
    "zipf": "Zipfian",
    "piecewise": "Piecewise",
}


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def theta_key(value):
    idx = int(np.argmin([abs(value - t) for t in THETA_VALUES]))
    return THETA_KEYS[idx]


def load_rows(filename):
    path = os.path.join(V2_RESULTS_DIR, filename)
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            theta = float(row["theta"])
            rows.append(
                {
                    "dist": row["dist"],
                    "batch_size": int(float(row["batch_size"])),
                    "theta": theta,
                    "theta_key": theta_key(theta),
                    "n_theory": float(row["n_theory"]),
                    "median_n_stop": float(row["median_n_stop"]),
                    "mean_n_stop": float(row["mean_n_stop"]),
                    "q25_n_stop": float(row["q25_n_stop"]),
                    "q75_n_stop": float(row["q75_n_stop"]),
                    "correctness": float(row["correctness"]),
                    "efficiency": float(row["efficiency"]),
                }
            )
    return rows


def row_lookup(rows, dist, batch_size, theta_key_name):
    for row in rows:
        if (
            row["dist"] == dist
            and row["batch_size"] == batch_size
            and row["theta_key"] == theta_key_name
        ):
            return row
    raise KeyError((dist, batch_size, theta_key_name))


def heatmap_data(rows, dist):
    corr = np.zeros((len(BATCH_SIZES), len(THETA_KEYS)))
    eff = np.zeros_like(corr)
    for i, batch_size in enumerate(BATCH_SIZES):
        for j, key in enumerate(THETA_KEYS):
            row = row_lookup(rows, dist, batch_size, key)
            corr[i, j] = row["correctness"]
            eff[i, j] = row["efficiency"]
    return corr, eff


def plot_combined_correctness(rows, dist_labels, out_name, title):
    fig, axes = plt.subplots(1, len(dist_labels), figsize=(5.1 * len(dist_labels), 4.8))
    if len(dist_labels) == 1:
        axes = [axes]

    for ax, (dist, label) in zip(axes, dist_labels.items()):
        corr, _ = heatmap_data(rows, dist)
        im = ax.imshow(corr, vmin=0, vmax=1, cmap="RdYlGn", origin="lower", aspect="auto")
        ax.set_xticks(range(len(THETA_KEYS)))
        ax.set_xticklabels(THETA_DISPLAY, fontsize=9)
        ax.set_yticks(range(len(BATCH_SIZES)))
        ax.set_yticklabels(BATCH_SIZES, fontsize=9)
        ax.set_xlabel("Stopping threshold")
        ax.set_title(label)
        for i in range(len(BATCH_SIZES)):
            for j in range(len(THETA_KEYS)):
                value = corr[i, j]
                ax.text(
                    j,
                    i,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="black",
                    path_effects=LABEL_OUTLINE,
                )
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    axes[0].set_ylabel("Packets per batch, increasing upward")
    fig.suptitle(title)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    out = os.path.join(RESULTS_DIR, out_name)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_individual_heatmaps(rows, dist_labels, prefix):
    paths = []
    for dist, label in dist_labels.items():
        corr, eff = heatmap_data(rows, dist)
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

        im0 = axes[0].imshow(corr, vmin=0, vmax=1, cmap="RdYlGn", origin="lower", aspect="auto")
        axes[0].set_title("Correctness")
        fig.colorbar(im0, ax=axes[0])

        im1 = axes[1].imshow(eff, cmap="YlOrRd", origin="lower", aspect="auto")
        axes[1].set_title("Efficiency")
        fig.colorbar(im1, ax=axes[1])

        for ax in axes:
            ax.set_xticks(range(len(THETA_KEYS)))
            ax.set_xticklabels(THETA_DISPLAY)
            ax.set_yticks(range(len(BATCH_SIZES)))
            ax.set_yticklabels(BATCH_SIZES)
            ax.set_xlabel("Stopping threshold")
            ax.set_ylabel("Packets per batch, increasing upward")

        for i in range(len(BATCH_SIZES)):
            for j in range(len(THETA_KEYS)):
                c = corr[i, j]
                axes[0].text(
                    j,
                    i,
                    f"{c:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="black",
                    path_effects=LABEL_OUTLINE,
                )
                axes[1].text(
                    j,
                    i,
                    f"{eff[i, j]:.0f}x",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="black",
                    path_effects=LABEL_OUTLINE,
                )

        fig.suptitle(f"{label}: correctness and efficiency")
        fig.tight_layout()
        out = os.path.join(RESULTS_DIR, f"heatmap_{prefix}_{dist}.png")
        fig.savefig(out, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths.append(out)
    return paths


def plot_n_stop_summary_all(rows):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    colors = plt.cm.plasma(np.linspace(0.08, 0.9, len(THETA_KEYS)))

    for ax, (dist, cfg) in zip(axes, CONTINUOUS_DISTS.items()):
        sub = [r for r in rows if r["dist"] == dist]
        for key, display, color in zip(THETA_KEYS, THETA_DISPLAY, colors):
            vals = [row_lookup(sub, dist, b, key) for b in BATCH_SIZES]
            med = np.array([v["median_n_stop"] for v in vals])
            q25 = np.array([v["q25_n_stop"] for v in vals])
            q75 = np.array([v["q75_n_stop"] for v in vals])
            ax.plot(BATCH_SIZES, med, marker="o", linewidth=2, color=color, label=display)
            ax.fill_between(BATCH_SIZES, q25, q75, color=color, alpha=0.12)

        ax.axhline(sub[0]["n_theory"], color="black", linestyle=":", linewidth=1.3)
        ax.set_title(cfg["label"])
        ax.set_xlabel("Packets per batch")
        ax.set_yscale("log")
        ax.grid(True, which="both", alpha=0.28)

    axes[0].set_ylabel("Total packets collected at stop")
    axes[0].legend(title="Threshold", fontsize=8, ncol=2)
    fig.suptitle("Continuous distributions: total packets collected before stopping")
    fig.tight_layout()
    out = os.path.join(RESULTS_DIR, "n_stop_summary_cont_all.png")
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_n_stop_b200(rows):
    batch_size = 200
    x = np.arange(len(THETA_KEYS))
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.4), sharey=True)
    y_max = 1.25 * max(
        row_lookup(rows, dist, batch_size, key)["q75_n_stop"]
        for dist in CONTINUOUS_DISTS
        for key in THETA_KEYS
    )

    for ax, (dist, cfg) in zip(axes, CONTINUOUS_DISTS.items()):
        vals = [row_lookup(rows, dist, batch_size, key) for key in THETA_KEYS]
        med = np.array([v["median_n_stop"] for v in vals])
        q25 = np.array([v["q25_n_stop"] for v in vals])
        q75 = np.array([v["q75_n_stop"] for v in vals])
        correctness = np.array([v["correctness"] for v in vals])

        ax.errorbar(
            x,
            med,
            yerr=[med - q25, q75 - med],
            marker="o",
            linewidth=2.4,
            capsize=4,
            color=cfg["color"],
        )
        for xi, yi, corr in zip(x, med, correctness):
            ax.text(xi, yi * 1.1, f"{corr:.2f}", ha="center", va="bottom", fontsize=9.5)

        ax.set_xticks(x)
        ax.set_xticklabels(THETA_DISPLAY)
        ax.set_xlabel("Stopping threshold")
        ax.set_title(cfg["label"])
        ax.set_ylim(0, y_max)
        ax.grid(True, alpha=0.28)

    axes[0].set_ylabel("Median total packets collected at stop")
    fig.suptitle("B=200 total packets needed to stop")
    fig.text(0.5, 0.01, "Numbers above points show correctness across 100 seeds.", ha="center")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    out = os.path.join(RESULTS_DIR, "n_stop_b200_continuous.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def true_continuous_masses(dist, params):
    if dist == "normal":
        pdf = stats.norm.pdf(GRID, loc=params["mean"], scale=math.sqrt(params["variance"]))
    elif dist == "lognormal":
        pdf = stats.lognorm.pdf(GRID, s=params["sigma"], scale=math.exp(params["mu"]))
    elif dist == "weibull":
        pdf = stats.weibull_min.pdf(GRID, c=params["shape"], scale=params["scale"])
    else:
        raise ValueError(dist)
    masses = pdf * BIN_WIDTH
    return masses / masses.sum()


def sample_continuous(dist, params, n, seed):
    rng = np.random.default_rng(seed)
    if dist == "normal":
        return rng.normal(params["mean"], math.sqrt(params["variance"]), size=n)
    if dist == "lognormal":
        return rng.lognormal(params["mu"], params["sigma"], size=n)
    if dist == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(dist)


def kde_masses(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    masses = kde(GRID) * BIN_WIDTH
    return masses / masses.sum()


def stop_continuous(dist, params, batch_size, theta, seed, max_samples):
    pool = sample_continuous(dist, params, max_samples, seed)
    true_m = true_continuous_masses(dist, params)
    n = batch_size
    f_prev = kde_masses(pool[:n])
    trace = [(n, tvd(f_prev, true_m), np.nan, f_prev)]
    stop = None

    while n + batch_size <= max_samples:
        n += batch_size
        f_cur = kde_masses(pool[:n])
        between = tvd(f_cur, f_prev)
        truth = tvd(f_cur, true_m)
        trace.append((n, truth, between, f_cur))
        if stop is None and between < theta:
            stop = {
                "n": n,
                "truth_tvd": truth,
                "between_tvd": between,
                "estimate": f_cur,
                "pool": pool,
            }
        f_prev = f_cur

    if stop is None:
        n, truth, between, estimate = trace[-1]
        stop = {
            "n": n,
            "truth_tvd": truth,
            "between_tvd": between,
            "estimate": estimate,
            "pool": pool,
        }
    return stop, trace


def plot_stopped_distribution_b200():
    batch_size = 200
    theta = DELTA / 6
    seed = 4
    max_samples = 12_000
    paths = []

    for dist, cfg in CONTINUOUS_DISTS.items():
        true_m = true_continuous_masses(dist, cfg["params"])
        stop, _ = stop_continuous(dist, cfg["params"], batch_size, theta, seed, max_samples)
        fig, ax = plt.subplots(figsize=(8.7, 5.6))

        ax.plot(GRID, true_m, color="black", linewidth=2.8, label="True distribution")
        ax.plot(GRID, stop["estimate"], color=cfg["color"], linewidth=2.8, label="Stopped KDE")
        ax.fill_between(GRID, stop["estimate"], color=cfg["color"], alpha=0.18)
        ax.set_xlim(*STOPPED_XLIMS[dist])
        ax.set_title(
            f"{cfg['label']} stopped reconstruction, B=200\n"
            f"stop n={stop['n']:,}, TVD={stop['truth_tvd']:.3f}, "
            r"$\theta=\delta/6$"
        )
        ax.set_xlabel("Delay on 1 ms grid")
        ax.set_ylabel("Probability mass")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right")

        out = os.path.join(RESULTS_DIR, f"stopped_distribution_{dist}_b200.png")
        fig.savefig(out, dpi=220, bbox_inches="tight")
        plt.close(fig)
        paths.append(out)

    return paths


def find_bad_seed(dist, params, max_samples):
    for seed in range(1, 101):
        stop, trace = stop_continuous(dist, params, 100, DELTA, seed, max_samples)
        if stop["truth_tvd"] > DELTA:
            return seed, stop, trace
    stop, trace = stop_continuous(dist, params, 100, DELTA, 1, max_samples)
    return 1, stop, trace


def plot_early_stop_traces():
    max_samples = 5_000
    fig, axes = plt.subplots(2, 3, figsize=(16, 8.4), sharex=False)

    for col, (dist, cfg) in enumerate(CONTINUOUS_DISTS.items()):
        seed, stop, trace = find_bad_seed(dist, cfg["params"], max_samples)
        ns = np.array([item[0] for item in trace])
        truth = np.array([item[1] for item in trace])
        between = np.array([item[2] for item in trace])

        axes[0, col].plot(ns, truth, marker="o", color=cfg["color"], linewidth=2)
        axes[0, col].axhline(DELTA, color="black", linestyle="--", linewidth=1.1)
        axes[0, col].scatter(
            [stop["n"]],
            [stop["truth_tvd"]],
            s=100,
            color=cfg["color"],
            edgecolor="black",
            zorder=5,
        )
        axes[0, col].set_title(f"{cfg['label']}, seed {seed}\nstop n={stop['n']:,}")
        axes[0, col].set_ylabel("TVD against truth")
        axes[0, col].grid(True, alpha=0.25)

        axes[1, col].plot(ns, between, marker="o", color=cfg["color"], linewidth=2)
        axes[1, col].axhline(DELTA, color="black", linestyle=":", linewidth=1.1)
        axes[1, col].scatter(
            [stop["n"]],
            [stop["between_tvd"]],
            s=100,
            color=cfg["color"],
            edgecolor="black",
            zorder=5,
        )
        axes[1, col].set_xlabel("Total packets collected")
        axes[1, col].set_ylabel("TVD to previous estimate")
        axes[1, col].grid(True, alpha=0.25)

    fig.suptitle("Continuing after an aggressive B=100, theta=delta stopping decision")
    fig.tight_layout()
    out = os.path.join(RESULTS_DIR, "early_stop_trace_cont_all.png")
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def format_duration(seconds):
    if seconds < 1e-6:
        return f"{seconds * 1e9:.0f} ns"
    if seconds < 1e-3:
        return f"{seconds * 1e6:.0f} us"
    if seconds < 1:
        return f"{seconds * 1e3:.1f} ms"
    return f"{seconds:.2f} s"


def plot_packet_timing_table():
    packet_bytes = 1500
    sample_counts = [100, 200, 500, 900, 1600, 3000, 6000, 10000]
    rates_gbps = [1, 10, 100]
    rows = []
    for n in sample_counts:
        row = [f"{n:,}"]
        for rate in rates_gbps:
            seconds = n * packet_bytes * 8 / (rate * 1e9)
            row.append(format_duration(seconds))
        rows.append(row)

    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=["Packets", "1 Gbit/s", "10 Gbit/s", "100 Gbit/s"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1.0, 1.45)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#e8eef7")
        elif row % 2 == 0:
            cell.set_facecolor("#f7f7f7")
    ax.set_title("Back-to-back collection time for 1500-byte packets", weight="bold", pad=12)
    out = os.path.join(RESULTS_DIR, "packet_timing_table.png")
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    cont_rows = load_rows("results_continuous.csv")
    disc_rows = load_rows("results_discrete.csv")

    paths = []
    paths.append(
        plot_combined_correctness(
            cont_rows,
            {k: v["label"] for k, v in CONTINUOUS_DISTS.items()},
            "correctness_grid_cont.png",
            "Continuous correctness with batch size increasing upwards",
        )
    )
    paths.append(
        plot_combined_correctness(
            disc_rows,
            DISCRETE_LABELS,
            "correctness_grid_disc.png",
            "Discrete correctness with batch size increasing upwards",
        )
    )
    paths.extend(
        plot_individual_heatmaps(
            cont_rows,
            {k: v["label"] for k, v in CONTINUOUS_DISTS.items()},
            "cont",
        )
    )
    paths.append(plot_n_stop_summary_all(cont_rows))
    paths.append(plot_n_stop_b200(cont_rows))
    paths.extend(plot_stopped_distribution_b200())
    paths.append(plot_early_stop_traces())
    paths.append(plot_packet_timing_table())

    print("Saved report adaptive plots:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
