"""
Report figures for the statistical sample-complexity evaluation.

This script samples directly from the distributions used in the first
evaluation section. It avoids the network simulator on purpose: this part of
the dissertation checks the statistical reconstruction question before any
topology-specific effects are introduced.
"""

import argparse
import csv
import math
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/profiler-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(
    SCRIPT_DIR, "../results/statistical-sample-complexity-report"
)

EPSILON = 0.05
DELTA = 0.05
DISCRETE_N_THEORY = {
    "binomial": 9599,
    "zipf": 9199,
    "piecewise": 9199,
}
CONTINUOUS_N_THEORY = 60520
GRID_MAX = 150.0
BIN_WIDTH = 1.0
BIN_EDGES = np.arange(0.0, GRID_MAX + BIN_WIDTH, BIN_WIDTH)
BIN_CENTRES = 0.5 * (BIN_EDGES[:-1] + BIN_EDGES[1:])
K_CONT = len(BIN_CENTRES)

DISCRETE_SEEDS = range(1, 101)
CONTINUOUS_SEEDS = range(1, 31)

DISCRETE_DISTS = {
    "binomial": {
        "label": "Binomial",
        "support": np.arange(0, 21),
        "pmf": lambda x: stats.binom.pmf(x, n=20, p=0.5),
        "sample": lambda rng, n: rng.binomial(20, 0.5, size=n),
        "color": "#8e44ad",
    },
    "zipf": {
        "label": "Zipfian",
        "support": np.arange(1, 21),
        "pmf": lambda x: x ** (-1.5) / np.sum(np.arange(1, 21) ** (-1.5)),
        "sample": None,
        "color": "#d35400",
    },
    "piecewise": {
        "label": "Piecewise",
        "support": np.arange(1, 21),
        "pmf": lambda x: np.array(
            [
                0.12,
                0.02,
                0.08,
                0.01,
                0.10,
                0.03,
                0.07,
                0.12,
                0.02,
                0.09,
                0.01,
                0.08,
                0.04,
                0.06,
                0.02,
                0.05,
                0.02,
                0.04,
                0.01,
                0.01,
            ]
        ),
        "sample": None,
        "color": "#229954",
    },
}

CONTINUOUS_DISTS = {
    "normal": {
        "label": "Normal",
        "dist": stats.norm(loc=40.0, scale=2.0),
        "sample": lambda rng, n: rng.normal(loc=40.0, scale=2.0, size=n),
        "color": "#2874a6",
    },
    "lognormal": {
        "label": "Lognormal",
        "dist": stats.lognorm(s=0.2, scale=math.exp(2.3)),
        "sample": lambda rng, n: rng.lognormal(mean=2.3, sigma=0.2, size=n),
        "color": "#c0392b",
    },
    "weibull": {
        "label": "Weibull",
        "dist": stats.weibull_min(c=2.0, scale=10.0),
        "sample": lambda rng, n: 10.0 * rng.weibull(2.0, size=n),
        "color": "#d68910",
    },
}


def finite_bound(k):
    return math.ceil((k + math.log(1.0 / EPSILON)) / (DELTA**2))


def bound_curve(k, ns):
    ns = np.asarray(ns, dtype=float)
    return np.minimum(1.0, np.sqrt((k + math.log(1.0 / EPSILON)) / ns))


def reference_bound_curve(n_theory, ns):
    ns = np.asarray(ns, dtype=float)
    return np.minimum(1.0, DELTA * np.sqrt(n_theory / ns))


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def empirical_discrete_pmf(samples, support):
    offset = int(support[0])
    indices = np.asarray(samples, dtype=int) - offset
    counts = np.bincount(indices, minlength=len(support))[: len(support)].astype(float)
    return counts / counts.sum()


def empirical_continuous_pmf(samples):
    counts, _ = np.histogram(samples, bins=BIN_EDGES)
    return counts / counts.sum()


def kde_grid_pmf(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    masses = kde(BIN_CENTRES) * BIN_WIDTH
    return masses / masses.sum()


def true_continuous_pmf(cfg):
    masses = np.diff(cfg["dist"].cdf(BIN_EDGES))
    return masses / masses.sum()


def zipf_sample(rng, n):
    support = DISCRETE_DISTS["zipf"]["support"]
    probs = DISCRETE_DISTS["zipf"]["pmf"](support)
    return rng.choice(support, size=n, p=probs)


def piecewise_sample(rng, n):
    support = DISCRETE_DISTS["piecewise"]["support"]
    probs = DISCRETE_DISTS["piecewise"]["pmf"](support)
    return rng.choice(support, size=n, p=probs)


DISCRETE_DISTS["zipf"]["sample"] = zipf_sample
DISCRETE_DISTS["piecewise"]["sample"] = piecewise_sample


def median_iqr(values_by_n, ns):
    med = np.array([np.median(values_by_n[n]) for n in ns])
    q25 = np.array([np.percentile(values_by_n[n], 25) for n in ns])
    q75 = np.array([np.percentile(values_by_n[n], 75) for n in ns])
    return med, q25, q75


def plot_true_shapes():
    fig, axes = plt.subplots(2, 3, figsize=(14, 7))

    for ax, (name, cfg) in zip(axes[0], DISCRETE_DISTS.items()):
        support = cfg["support"]
        probs = cfg["pmf"](support)
        ax.bar(support, probs, color=cfg["color"], alpha=0.75)
        ax.set_title(cfg["label"])
        ax.set_xlabel("Delay value")
        ax.set_ylabel("Probability")
        ax.grid(True, alpha=0.25, axis="y")

    x = np.linspace(0.0, 70.0, 800)
    for ax, (name, cfg) in zip(axes[1], CONTINUOUS_DISTS.items()):
        ax.plot(x, cfg["dist"].pdf(x), color=cfg["color"], linewidth=2)
        ax.set_title(cfg["label"])
        ax.set_xlabel("Delay value")
        ax.set_ylabel("Density")
        ax.grid(True, alpha=0.25)

    fig.suptitle("Ground-truth distributions used in the sample-complexity evaluation")
    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "statistical_distribution_shapes.png")
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()
    return out


def run_discrete():
    ns_by_dist = {
        "binomial": [480, 960, 2400, 4800, 9599, 19197, 38393],
        "zipf": [460, 920, 2300, 4599, 9199, 18397, 36793],
        "piecewise": [460, 920, 2300, 4599, 9199, 18397, 36793],
    }
    results = {}

    for name, cfg in DISCRETE_DISTS.items():
        support = cfg["support"]
        true_p = cfg["pmf"](support)
        values_by_n = {n: [] for n in ns_by_dist[name]}

        for n in ns_by_dist[name]:
            for seed in DISCRETE_SEEDS:
                rng = np.random.default_rng(seed)
                samples = cfg["sample"](rng, n)
                emp = empirical_discrete_pmf(samples, support)
                values_by_n[n].append(tvd(true_p, emp))

        results[name] = {
            "ns": ns_by_dist[name],
            "values": values_by_n,
            "k": len(support),
            "n_theory": DISCRETE_N_THEORY[name],
        }

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (name, cfg) in zip(axes, DISCRETE_DISTS.items()):
        ns = results[name]["ns"]
        med, q25, q75 = median_iqr(results[name]["values"], ns)
        k = results[name]["k"]
        n_theory = results[name]["n_theory"]
        curve_x = np.logspace(math.log10(min(ns)), math.log10(max(ns)), 250)

        ax.fill_between(ns, q25, q75, color=cfg["color"], alpha=0.18)
        ax.plot(ns, med, marker="o", color=cfg["color"], linewidth=2, label="Median TVD")
        ax.plot(
            curve_x,
            reference_bound_curve(n_theory, curve_x),
            "k--",
            linewidth=1.3,
            label="Theory curve",
        )
        ax.axhline(DELTA, color="#555555", linestyle=":", linewidth=1.2, label="Target")
        ax.axvline(n_theory, color="#922b21", linestyle=":", linewidth=1.2)
        ax.set_xscale("log")
        ax.set_title(f"{cfg['label']}, k={k}")
        ax.set_xlabel("Samples n")
        ax.grid(True, alpha=0.25, which="both")
        ax.text(
            0.03,
            0.92,
            f"$n_{{theory}}$ = {n_theory:,}",
            transform=ax.transAxes,
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
    axes[0].set_ylabel("Total variation distance")
    axes[0].legend(fontsize=8, loc="upper right")
    fig.suptitle("Discrete distributions: TVD against true PMF as samples increase")
    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "statistical_discrete_tvd_vs_n.png")
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (name, cfg) in zip(axes, DISCRETE_DISTS.items()):
        ns = results[name]["ns"]
        worst = np.array([np.max(results[name]["values"][n]) for n in ns])
        best = np.array([np.min(results[name]["values"][n]) for n in ns])
        k = results[name]["k"]
        n_theory = results[name]["n_theory"]
        curve_x = np.logspace(math.log10(min(ns)), math.log10(max(ns)), 250)

        ax.fill_between(ns, best, worst, color=cfg["color"], alpha=0.14)
        ax.plot(
            ns,
            worst,
            marker="o",
            color=cfg["color"],
            linewidth=2,
            label="Worst-case TVD",
        )
        ax.plot(
            curve_x,
            reference_bound_curve(n_theory, curve_x),
            "k--",
            linewidth=1.3,
            label="Theory curve",
        )
        ax.axhline(DELTA, color="#555555", linestyle=":", linewidth=1.2, label="Target")
        ax.axvline(n_theory, color="#922b21", linestyle=":", linewidth=1.2)
        ax.set_xscale("log")
        ax.set_title(f"{cfg['label']}, k={k}")
        ax.set_xlabel("Samples n")
        ax.grid(True, alpha=0.25, which="both")
        ax.text(
            0.03,
            0.92,
            f"$n_{{theory}}$ = {n_theory:,}",
            transform=ax.transAxes,
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
    axes[0].set_ylabel("Total variation distance")
    axes[0].legend(fontsize=8, loc="upper right")
    fig.suptitle("Discrete distributions: worst-case TVD against true PMF as samples increase")
    plt.tight_layout()
    worst_out = os.path.join(RESULTS_DIR, "statistical_discrete_worst_tvd_vs_n.png")
    plt.savefig(worst_out, dpi=180, bbox_inches="tight")
    plt.close()

    separate_worst_outs = []
    for name, cfg in DISCRETE_DISTS.items():
        ns = results[name]["ns"]
        worst = np.array([np.max(results[name]["values"][n]) for n in ns])
        best = np.array([np.min(results[name]["values"][n]) for n in ns])
        k = results[name]["k"]
        n_theory = results[name]["n_theory"]
        curve_x = np.logspace(math.log10(min(ns)), math.log10(max(ns)), 250)

        fig, ax = plt.subplots(figsize=(6.2, 4.6))
        ax.fill_between(ns, best, worst, color=cfg["color"], alpha=0.14)
        ax.plot(
            ns,
            worst,
            marker="o",
            color=cfg["color"],
            linewidth=2,
            label="Worst-case TVD",
        )
        ax.plot(
            curve_x,
            reference_bound_curve(n_theory, curve_x),
            "k--",
            linewidth=1.3,
            label="Theory curve",
        )
        ax.axhline(DELTA, color="#555555", linestyle=":", linewidth=1.2, label="Target")
        ax.axvline(n_theory, color="#922b21", linestyle=":", linewidth=1.2)
        ax.set_xscale("log")
        ax.set_title(f"{cfg['label']}, k={k}")
        ax.set_xlabel("Samples n")
        ax.set_ylabel("Total variation distance")
        ax.grid(True, alpha=0.25, which="both")
        ax.text(
            0.03,
            0.92,
            f"$n_{{theory}}$ = {n_theory:,}",
            transform=ax.transAxes,
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
        ax.legend(fontsize=8, loc="upper right")
        plt.tight_layout()
        separate_out = os.path.join(
            RESULTS_DIR,
            f"statistical_discrete_worst_tvd_vs_n_{name}.png",
        )
        plt.savefig(separate_out, dpi=180, bbox_inches="tight")
        plt.close()
        separate_worst_outs.append(separate_out)

    return results, out, worst_out, separate_worst_outs


def run_continuous():
    ns = sorted({500, 1000, 2000, 5000, 10000, 20000, 50000, CONTINUOUS_N_THEORY, 61199})
    results = {}

    for name, cfg in CONTINUOUS_DISTS.items():
        true_p = true_continuous_pmf(cfg)
        pmf_by_n = {n: [] for n in ns}
        kde_by_n = {n: [] for n in ns}
        gap_by_n = {n: [] for n in ns}

        for n in ns:
            for seed in CONTINUOUS_SEEDS:
                rng = np.random.default_rng(seed)
                samples = cfg["sample"](rng, n)
                emp = empirical_continuous_pmf(samples)
                kde = kde_grid_pmf(samples)
                pmf_by_n[n].append(tvd(true_p, emp))
                kde_by_n[n].append(tvd(true_p, kde))
                gap_by_n[n].append(tvd(emp, kde))

        results[name] = {
            "ns": ns,
            "pmf": pmf_by_n,
            "kde": kde_by_n,
            "gap": gap_by_n,
            "k": K_CONT,
            "n_theory": CONTINUOUS_N_THEORY,
        }

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (name, cfg) in zip(axes, CONTINUOUS_DISTS.items()):
        res = results[name]
        med_pmf, q25_pmf, q75_pmf = median_iqr(res["pmf"], ns)
        med_kde, q25_kde, q75_kde = median_iqr(res["kde"], ns)
        curve_x = np.logspace(math.log10(min(ns)), math.log10(max(ns)), 250)

        ax.fill_between(ns, q25_pmf, q75_pmf, color="#7f8c8d", alpha=0.16)
        ax.plot(ns, med_pmf, marker="s", color="#566573", linewidth=1.8, label="PMF")
        ax.fill_between(ns, q25_kde, q75_kde, color=cfg["color"], alpha=0.16)
        ax.plot(ns, med_kde, marker="o", color=cfg["color"], linewidth=2, label="KDE")
        ax.plot(
            curve_x,
            reference_bound_curve(res["n_theory"], curve_x),
            "k--",
            linewidth=1.3,
            label="PMF theory",
        )
        ax.axhline(DELTA, color="#555555", linestyle=":", linewidth=1.2, label="Target")
        ax.axvline(res["n_theory"], color="#922b21", linestyle=":", linewidth=1.2)
        ax.set_xscale("log")
        ax.set_title(cfg["label"])
        ax.set_xlabel("Samples n")
        ax.grid(True, alpha=0.25, which="both")
        ax.text(
            0.03,
            0.92,
            f"$n_{{theory}}$ = {res['n_theory']:,}",
            transform=ax.transAxes,
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
    axes[0].set_ylabel("Total variation distance")
    axes[0].legend(fontsize=8, loc="upper right")
    fig.suptitle("Continuous distributions: PMF and KDE accuracy on a 1 ms grid")
    plt.tight_layout()
    out_accuracy = os.path.join(RESULTS_DIR, "statistical_continuous_tvd_vs_n.png")
    plt.savefig(out_accuracy, dpi=180, bbox_inches="tight")
    plt.close()

    separate_accuracy_outs = []
    separate_worst_outs = []
    for name, cfg in CONTINUOUS_DISTS.items():
        res = results[name]
        med_pmf, q25_pmf, q75_pmf = median_iqr(res["pmf"], ns)
        med_kde, q25_kde, q75_kde = median_iqr(res["kde"], ns)
        curve_x = np.logspace(math.log10(min(ns)), math.log10(max(ns)), 250)

        fig, ax = plt.subplots(figsize=(6.2, 4.6))
        ax.fill_between(ns, q25_pmf, q75_pmf, color="#7f8c8d", alpha=0.16)
        ax.plot(ns, med_pmf, marker="s", color="#566573", linewidth=1.8, label="PMF")
        ax.fill_between(ns, q25_kde, q75_kde, color=cfg["color"], alpha=0.16)
        ax.plot(ns, med_kde, marker="o", color=cfg["color"], linewidth=2, label="KDE")
        ax.plot(
            curve_x,
            reference_bound_curve(res["n_theory"], curve_x),
            "k--",
            linewidth=1.3,
            label="PMF theory",
        )
        ax.axhline(DELTA, color="#555555", linestyle=":", linewidth=1.2, label="Target")
        ax.axvline(res["n_theory"], color="#922b21", linestyle=":", linewidth=1.2)
        ax.set_xscale("log")
        ax.set_title(cfg["label"])
        ax.set_xlabel("Samples n")
        ax.set_ylabel("Total variation distance")
        ax.grid(True, alpha=0.25, which="both")
        ax.text(
            0.03,
            0.92,
            f"$n_{{theory}}$ = {res['n_theory']:,}",
            transform=ax.transAxes,
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
        ax.legend(fontsize=8, loc="upper right")
        plt.tight_layout()
        separate_out = os.path.join(
            RESULTS_DIR,
            f"statistical_continuous_tvd_vs_n_{name}_60520.png",
        )
        plt.savefig(separate_out, dpi=180, bbox_inches="tight")
        plt.close()
        separate_accuracy_outs.append(separate_out)

        worst_pmf = np.array([np.max(res["pmf"][n]) for n in ns])
        best_pmf = np.array([np.min(res["pmf"][n]) for n in ns])
        worst_kde = np.array([np.max(res["kde"][n]) for n in ns])
        best_kde = np.array([np.min(res["kde"][n]) for n in ns])

        fig, ax = plt.subplots(figsize=(6.2, 4.6))
        ax.fill_between(ns, best_pmf, worst_pmf, color="#7f8c8d", alpha=0.14)
        ax.plot(
            ns,
            worst_pmf,
            marker="s",
            color="#566573",
            linewidth=1.8,
            label="Worst-case PMF",
        )
        ax.fill_between(ns, best_kde, worst_kde, color=cfg["color"], alpha=0.14)
        ax.plot(
            ns,
            worst_kde,
            marker="o",
            color=cfg["color"],
            linewidth=2,
            label="Worst-case KDE",
        )
        ax.plot(
            curve_x,
            reference_bound_curve(res["n_theory"], curve_x),
            "k--",
            linewidth=1.3,
            label="PMF theory",
        )
        ax.axhline(DELTA, color="#555555", linestyle=":", linewidth=1.2, label="Target")
        ax.axvline(res["n_theory"], color="#922b21", linestyle=":", linewidth=1.2)
        ax.set_xscale("log")
        ax.set_title(cfg["label"])
        ax.set_xlabel("Samples n")
        ax.set_ylabel("Total variation distance")
        ax.grid(True, alpha=0.25, which="both")
        ax.text(
            0.03,
            0.92,
            f"$n_{{theory}}$ = {res['n_theory']:,}",
            transform=ax.transAxes,
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )
        ax.legend(fontsize=8, loc="upper right")
        plt.tight_layout()
        worst_out = os.path.join(
            RESULTS_DIR,
            f"statistical_continuous_worst_tvd_vs_n_{name}_60520.png",
        )
        plt.savefig(worst_out, dpi=180, bbox_inches="tight")
        plt.close()
        separate_worst_outs.append(worst_out)

    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    for name, cfg in CONTINUOUS_DISTS.items():
        med, q25, q75 = median_iqr(results[name]["gap"], ns)
        ax.fill_between(ns, q25, q75, color=cfg["color"], alpha=0.13)
        ax.plot(ns, med, marker="o", color=cfg["color"], linewidth=2, label=cfg["label"])
    ax.set_xscale("log")
    ax.set_xlabel("Samples n")
    ax.set_ylabel("TVD between empirical PMF and KDE")
    ax.set_title("KDE and empirical PMF disagreement on the 1 ms grid")
    ax.grid(True, alpha=0.25, which="both")
    ax.legend(fontsize=9)
    plt.tight_layout()
    out_gap = os.path.join(RESULTS_DIR, "statistical_continuous_kde_pmf_gap.png")
    plt.savefig(out_gap, dpi=180, bbox_inches="tight")
    plt.close()
    return results, out_accuracy, out_gap, separate_accuracy_outs, separate_worst_outs


def write_summary(discrete_results, continuous_results):
    out = os.path.join(RESULTS_DIR, "statistical_sample_complexity_summary.csv")
    with open(out, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "family",
                "distribution",
                "estimator",
                "k",
                "n_theory",
                "n",
                "median_tvd",
                "q25_tvd",
                "q75_tvd",
            ]
        )
        for name, res in discrete_results.items():
            for n in res["ns"]:
                values = res["values"][n]
                writer.writerow(
                    [
                        "discrete",
                        name,
                        "pmf",
                        res["k"],
                        res["n_theory"],
                        n,
                        np.median(values),
                        np.percentile(values, 25),
                        np.percentile(values, 75),
                    ]
                )
        for name, res in continuous_results.items():
            for estimator in ("pmf", "kde", "gap"):
                for n in res["ns"]:
                    values = res[estimator][n]
                    writer.writerow(
                        [
                            "continuous",
                            name,
                            estimator,
                            res["k"],
                            res["n_theory"],
                            n,
                            np.median(values),
                            np.percentile(values, 25),
                            np.percentile(values, 75),
                        ]
                    )
    return out


def print_key_numbers(discrete_results, continuous_results):
    print("Discrete at n_theory")
    for name, res in discrete_results.items():
        n = res["n_theory"]
        values = res["values"][n]
        print(
            f"  {name:<10} k={res['k']:>3} n_theory={n:>6,} "
            f"median={np.median(values):.4f} "
            f"iqr=[{np.percentile(values, 25):.4f}, {np.percentile(values, 75):.4f}]"
        )

    print("\nContinuous at n_theory")
    for name, res in continuous_results.items():
        n = res["n_theory"]
        pmf = res["pmf"][n]
        kde = res["kde"][n]
        gap = res["gap"][n]
        print(
            f"  {name:<10} k={res['k']:>3} n_theory={n:>6,} "
            f"PMF={np.median(pmf):.4f} KDE={np.median(kde):.4f} "
            f"gap={np.median(gap):.4f}"
        )


def main():
    global RESULTS_DIR

    parser = argparse.ArgumentParser(
        description="Generate the statistical sample-complexity report figures."
    )
    parser.add_argument(
        "--results-dir",
        default=RESULTS_DIR,
        help="Directory for generated figures and the summary CSV.",
    )
    args = parser.parse_args()

    RESULTS_DIR = args.results_dir
    os.makedirs(RESULTS_DIR, exist_ok=True)
    shape_plot = plot_true_shapes()
    discrete_results, discrete_plot, discrete_worst_plot, discrete_worst_separate = run_discrete()
    (
        continuous_results,
        continuous_plot,
        gap_plot,
        continuous_separate,
        continuous_worst_separate,
    ) = run_continuous()
    summary = write_summary(discrete_results, continuous_results)

    print_key_numbers(discrete_results, continuous_results)
    print("\nSaved figures")
    for path in (
        shape_plot,
        discrete_plot,
        discrete_worst_plot,
        *discrete_worst_separate,
        continuous_plot,
        *continuous_separate,
        *continuous_worst_separate,
        gap_plot,
        summary,
    ):
        print(f"  {path}")


if __name__ == "__main__":
    main()
