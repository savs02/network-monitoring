"""
Adaptive stopping diagnostics.

This script adds the extra plots suggested by the evaluation notes:

  1. total packets collected before stopping, as a function of packets per batch;
  2. a packet-count to transmission-time reference table;
  3. a continued trace after the stopping point, showing why small batches can
     stop too early.

The plots use the same distributions, estimators, and stopping rule as
adaptive_stopping_v2.py, but avoid pandas so they can run in the base analysis
environment.
"""

import csv
import math
import os

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
V2_RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/adaptive-stopping-v2")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/adaptive-stopping-diagnostics")

DELTA = 0.05
EPSILON = 0.05

BATCH_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000]
THETA_LABELS = ["delta/6", "delta/5", "delta/4", "delta/3", "delta/2", "delta"]
THETA_DISPLAY = {
    "delta/6": r"$\delta/6$",
    "delta/5": r"$\delta/5$",
    "delta/4": r"$\delta/4$",
    "delta/3": r"$\delta/3$",
    "delta/2": r"$\delta/2$",
    "delta": r"$\delta$",
}
THETA_VALUE = {
    "delta/6": DELTA / 6,
    "delta/5": DELTA / 5,
    "delta/4": DELTA / 4,
    "delta/3": DELTA / 3,
    "delta/2": DELTA / 2,
    "delta": DELTA,
}

GRID_MAX = 150.0
BIN_WIDTH = 1.0
GRID = np.arange(BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)
K = len(GRID)
N_THEORY_CONT = math.ceil(K * math.log(1.0 / EPSILON) / DELTA**2)

NORMAL_PARAMS = {"mean": 40.0, "variance": 4.0}


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def true_normal_masses():
    pdf = stats.norm.pdf(
        GRID,
        loc=NORMAL_PARAMS["mean"],
        scale=np.sqrt(NORMAL_PARAMS["variance"]),
    )
    masses = pdf * BIN_WIDTH
    return masses / masses.sum()


def sample_normal(n, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(
        loc=NORMAL_PARAMS["mean"],
        scale=np.sqrt(NORMAL_PARAMS["variance"]),
        size=n,
    )


def kde_estimate(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    masses = kde(GRID) * BIN_WIDTH
    return masses / masses.sum()


def normal_trace(pool, batch_size, theta, max_samples):
    true_m = true_normal_masses()
    ns = []
    true_tvds = []
    between_tvds = []
    stop_n = None
    stop_true_tvd = None

    n = batch_size
    f_prev = kde_estimate(pool[:n])
    ns.append(n)
    true_tvds.append(tvd(f_prev, true_m))
    between_tvds.append(np.nan)

    while n + batch_size <= max_samples:
        n += batch_size
        f_cur = kde_estimate(pool[:n])
        between = tvd(f_cur, f_prev)
        current_true = tvd(f_cur, true_m)

        ns.append(n)
        true_tvds.append(current_true)
        between_tvds.append(between)

        if stop_n is None and between < theta:
            stop_n = n
            stop_true_tvd = current_true

        f_prev = f_cur

    return {
        "n": np.array(ns),
        "true_tvd": np.array(true_tvds),
        "between_tvd": np.array(between_tvds),
        "stop_n": stop_n,
        "stop_true_tvd": stop_true_tvd,
    }


def load_summary_csv(filename):
    path = os.path.join(V2_RESULTS_DIR, filename)
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            normalised = dict(row)
            normalised["theta_label"] = (
                normalised["theta_label"]
                .replace("\u03b4", "delta")
                .replace(" ", "")
            )
            for key in [
                "batch_size",
                "median_n_stop",
                "q25_n_stop",
                "q75_n_stop",
                "n_theory",
                "correctness",
                "efficiency",
            ]:
                normalised[key] = float(normalised[key])
            rows.append(normalised)
    return rows


def plot_n_stop_summary(rows, dist_name, title, out_name):
    sub = [r for r in rows if r["dist"] == dist_name]
    colors = plt.cm.plasma(np.linspace(0.05, 0.9, len(THETA_LABELS)))

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for theta_label, color in zip(THETA_LABELS, colors):
        vals = sorted(
            [r for r in sub if r["theta_label"] == theta_label],
            key=lambda r: r["batch_size"],
        )
        x = np.array([r["batch_size"] for r in vals])
        med = np.array([r["median_n_stop"] for r in vals])
        q25 = np.array([r["q25_n_stop"] for r in vals])
        q75 = np.array([r["q75_n_stop"] for r in vals])
        ax.plot(
            x,
            med,
            marker="o",
            linewidth=2,
            color=color,
            label=THETA_DISPLAY[theta_label],
        )
        ax.fill_between(x, q25, q75, color=color, alpha=0.12)

    if sub:
        n_theory = sub[0]["n_theory"]
        ax.axhline(
            n_theory,
            color="black",
            linestyle=":",
            linewidth=1.5,
            label=f"theory = {n_theory:,.0f}",
        )

    ax.set_xlabel("Packets per batch")
    ax.set_ylabel("Total packets collected at stop")
    ax.set_title(title)
    ax.set_yscale("log")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(title="Stopping threshold", fontsize=8, ncol=2)
    fig.tight_layout()

    out = os.path.join(RESULTS_DIR, out_name)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


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
    sample_counts = [100, 200, 500, 1000, 2000, 3000]
    rates_gbps = [1, 10, 100]

    rows = []
    for n in sample_counts:
        row = [f"{n:,}"]
        for rate in rates_gbps:
            seconds = n * packet_bytes * 8 / (rate * 1e9)
            row.append(format_duration(seconds))
        rows.append(row)

    columns = ["Packets", "1 Gbit/s", "10 Gbit/s", "100 Gbit/s"]

    fig, ax = plt.subplots(figsize=(8.5, 3.2))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=columns,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.55)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#e8eef7")
        elif row % 2 == 0:
            cell.set_facecolor("#f7f7f7")
    ax.set_title(
        "Back-to-back collection time for 1500-byte packets",
        fontsize=12,
        weight="bold",
        pad=14,
    )

    out = os.path.join(RESULTS_DIR, "packet_timing_table.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def find_early_stop_seed():
    max_samples = 5000
    for seed in range(1, 101):
        pool = sample_normal(max_samples, seed)
        trace = normal_trace(pool, batch_size=100, theta=DELTA, max_samples=max_samples)
        if trace["stop_true_tvd"] is not None and trace["stop_true_tvd"] > DELTA:
            return seed
    return 1


def plot_early_stop_trace():
    max_samples = 5000
    seed = find_early_stop_seed()
    pool = sample_normal(max_samples, seed)

    configs = [
        (100, "delta", "#e74c3c", "B=100, theta=delta"),
        (100, "delta/6", "#8e44ad", "B=100, theta=delta/6"),
        (200, "delta/6", "#2980b9", "B=200, theta=delta/6"),
        (500, "delta/6", "#27ae60", "B=500, theta=delta/6"),
    ]

    traces = []
    for batch_size, theta_label, color, label in configs:
        traces.append(
            (
                normal_trace(
                    pool,
                    batch_size=batch_size,
                    theta=THETA_VALUE[theta_label],
                    max_samples=max_samples,
                ),
                theta_label,
                color,
                label,
            )
        )

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    for trace, theta_label, color, label in traces:
        axes[0].plot(
            trace["n"],
            trace["true_tvd"],
            marker="o",
            linewidth=2,
            color=color,
            label=label,
        )
        if trace["stop_n"] is not None:
            axes[0].scatter(
                [trace["stop_n"]],
                [trace["stop_true_tvd"]],
                s=110,
                color=color,
                edgecolor="black",
                zorder=5,
            )
            axes[0].annotate(
                f"stop {trace['stop_n']}",
                (trace["stop_n"], trace["stop_true_tvd"]),
                textcoords="offset points",
                xytext=(6, 7),
                fontsize=8,
            )

        axes[1].plot(
            trace["n"],
            trace["between_tvd"],
            marker="o",
            linewidth=2,
            color=color,
            label=label,
        )
        axes[1].axhline(
            THETA_VALUE[theta_label],
            color=color,
            linestyle=":",
            linewidth=1,
            alpha=0.8,
        )

    axes[0].axhline(DELTA, color="black", linestyle="--", linewidth=1.2, label="target TVD")
    axes[0].set_ylabel("TVD against truth")
    axes[0].set_title(
        f"Continuing after the stopping point, normal distribution, seed {seed}"
    )
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=8, ncol=2)

    axes[1].set_ylabel("TVD to previous estimate")
    axes[1].set_xlabel("Total packets collected")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(fontsize=8, ncol=2)

    fig.tight_layout()
    out = os.path.join(RESULTS_DIR, "early_stop_trace_normal.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    cont_rows = load_summary_csv("results_continuous.csv")
    disc_rows = load_summary_csv("results_discrete.csv")

    plot_n_stop_summary(
        cont_rows,
        "normal",
        "Normal distribution: total packets collected before stopping",
        "n_stop_summary_cont_normal.png",
    )
    plot_n_stop_summary(
        disc_rows,
        "piecewise",
        "Piecewise distribution: total packets collected before stopping",
        "n_stop_summary_disc_piecewise.png",
    )
    plot_packet_timing_table()
    plot_early_stop_trace()


if __name__ == "__main__":
    main()
