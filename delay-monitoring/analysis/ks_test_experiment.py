"""
KS test p-value evolution with sample size.

For each distribution, draws samples at increasing n across 30 independent
seeds and runs three statistical tests:

  1. One-sample KS test (continuous)
     scipy.stats.kstest(samples, true_cdf)
     H0: samples come from the true distribution.
     Since samples DO come from the true distribution, p-values should be
     approximately Uniform(0,1) for all n.  Any systematic deviation would
     indicate a defect in the sampling or test implementation.

  2. Two-sample KS test — KDE quality (continuous)
     Fits a KDE to the n training samples, draws n_ref samples from it,
     and runs ks_2samp(kde_samples, reference_true_samples).
     H0: KDE samples and true-distribution samples come from the same
     distribution.  At small n the KDE may be over-smoothed and the test
     may reject; at large n the KDE converges and the test should pass.

  3. Chi-squared goodness-of-fit (discrete)
     Bins samples into 1ms bins and compares observed counts to expected
     counts from the true PMF.  Bins with expected count < 5 are merged.
     H0: histogram matches the true PMF.

Plots:
  ks_statistic_vs_n.png      — KS D statistic vs n, all distributions
  ks_pvalue_boxplots.png     — p-value distributions (box plots) vs n
  ks_kde_quality_vs_n.png    — 2-sample KS p-value (KDE vs truth) vs n
  pass_rate_vs_n.png         — fraction of seeds passing each test vs n
  chisq_pvalue_boxplots.png  — chi-squared p-value distributions vs n

Results saved to: results/ks-test-experiment/
"""

import os
import shutil
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/ks-test-experiment")

SAMPLE_SIZES = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
SEEDS        = list(range(1, 31))
ALPHA        = 0.05

BIN_SIZE_CHI = 1.0   # ms; for chi-squared
GRID_MAX     = 150.0
N_REF        = 5000  # reference sample size for 2-sample KS

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


# ============================================================
# helpers
# ============================================================

def get_scipy_dist(dist_name, params):
    if dist_name == "normal":
        return stats.norm(loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min(c=params["shape"], scale=params["scale"])
    raise ValueError(dist_name)


def sample_distribution(dist_name, params, n, rng):
    if dist_name == "normal":
        return rng.normal(loc=params["mean"], scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(dist_name)


def chi_squared_test(samples, dist_obj, n):
    """
    Chi-squared goodness-of-fit on 1ms bins.
    Bins with expected count < 5 are merged into adjacent bins so that the
    test statistic is valid.  Returns (statistic, p-value) or (nan, nan)
    if fewer than 2 usable bins remain.
    """
    edges    = np.arange(0.0, GRID_MAX + BIN_SIZE_CHI, BIN_SIZE_CHI)
    expected = np.diff(dist_obj.cdf(edges)) * n
    observed, _ = np.histogram(samples, bins=edges)

    # Merge bins where expected < 5
    obs_merged, exp_merged = [], []
    obs_acc, exp_acc = 0.0, 0.0
    for o, e in zip(observed, expected):
        obs_acc += o
        exp_acc += e
        if exp_acc >= 5.0:
            obs_merged.append(obs_acc)
            exp_merged.append(exp_acc)
            obs_acc, exp_acc = 0.0, 0.0
    # absorb any remainder into the last bin
    if obs_merged and exp_acc > 0:
        obs_merged[-1] += obs_acc
        exp_merged[-1] += exp_acc

    if len(obs_merged) < 2:
        return np.nan, np.nan

    stat, p = stats.chisquare(np.array(obs_merged), f_exp=np.array(exp_merged))
    return stat, p


# ============================================================
# experiments
# ============================================================

def run_experiments():
    """
    Returns results[dist_name] = {
        'ks1_d':    {n: [D values across seeds]},
        'ks1_p':    {n: [p values across seeds]},
        'ks2_p':    {n: [p values — 2-sample KDE quality test]},
        'chi_p':    {n: [p values — chi-squared discrete test]},
    }
    """
    results = {}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        print(f"\n--- {dist_config['label']} ---")
        params   = dist_config["params"]
        dist_obj = get_scipy_dist(dist_name, params)

        # Fixed reference sample for the 2-sample KDE test
        ref_rng    = np.random.default_rng(0)
        ref_samples = sample_distribution(dist_name, params, N_REF, ref_rng)

        ks1_d = {n: [] for n in SAMPLE_SIZES}
        ks1_p = {n: [] for n in SAMPLE_SIZES}
        ks2_p = {n: [] for n in SAMPLE_SIZES}
        chi_p = {n: [] for n in SAMPLE_SIZES}

        for n in SAMPLE_SIZES:
            for seed in SEEDS:
                rng     = np.random.default_rng(seed)
                samples = sample_distribution(dist_name, params, n, rng)

                # Test 1 — 1-sample KS: raw samples vs true CDF
                d_stat, p1 = stats.kstest(samples, dist_obj.cdf)
                ks1_d[n].append(d_stat)
                ks1_p[n].append(p1)

                # Test 2 — 2-sample KS: KDE samples vs reference true samples
                kde        = stats.gaussian_kde(samples, bw_method="scott")
                kde_samp   = kde.resample(N_REF, seed=seed)[0]
                _, p2      = stats.ks_2samp(kde_samp, ref_samples)
                ks2_p[n].append(p2)

                # Test 3 — chi-squared on 1ms histogram
                _, pchi = chi_squared_test(samples, dist_obj, n)
                chi_p[n].append(pchi)

            pass1 = np.mean(np.array(ks1_p[n]) > ALPHA)
            pass2 = np.mean(np.array(ks2_p[n]) > ALPHA)
            pchi_clean = [v for v in chi_p[n] if not np.isnan(v)]
            pass3 = np.mean(np.array(pchi_clean) > ALPHA) if pchi_clean else np.nan
            print(
                f"  n={n:>7,}  "
                f"KS1 D={np.median(ks1_d[n]):.4f}  "
                f"KS1 pass={pass1*100:.0f}%  "
                f"KS2 pass={pass2*100:.0f}%  "
                f"chi2 pass={pass3*100:.0f}%" if not np.isnan(pass3) else
                f"  n={n:>7,}  "
                f"KS1 D={np.median(ks1_d[n]):.4f}  "
                f"KS1 pass={pass1*100:.0f}%  "
                f"KS2 pass={pass2*100:.0f}%  "
                f"chi2 pass=n/a"
            )

        results[dist_name] = {
            "ks1_d": ks1_d, "ks1_p": ks1_p,
            "ks2_p": ks2_p, "chi_p": chi_p,
        }

    return results


# ============================================================
# plots
# ============================================================

def _box_axes(ax, data_by_n, color, y_ref=ALPHA, ref_label=None):
    """Draw box plots at each sample size with a horizontal reference line."""
    data = [data_by_n[n] for n in SAMPLE_SIZES]
    ax.boxplot(
        data,
        positions=range(len(SAMPLE_SIZES)),
        widths=0.5,
        patch_artist=True,
        boxprops=dict(facecolor=color, alpha=0.45),
        medianprops=dict(color="black", linewidth=2),
        flierprops=dict(marker="o", markersize=2.5, alpha=0.35),
        whiskerprops=dict(linewidth=1.2),
        capprops=dict(linewidth=1.2),
    )
    if y_ref is not None:
        ax.axhline(y=y_ref, color="red", linestyle="--", linewidth=1.5,
                   label=ref_label or f"α = {y_ref}")
    ax.set_xticks(range(len(SAMPLE_SIZES)))
    ax.set_xticklabels([f"{n:,}" for n in SAMPLE_SIZES],
                       rotation=40, ha="right", fontsize=7)
    ax.set_xlabel("n")
    ax.grid(True, alpha=0.25, axis="y")


def plot_ks_statistic(results):
    """KS D statistic vs n — median and IQR, all distributions on one axes."""
    fig, ax = plt.subplots(figsize=(9, 6))

    n_fine = np.logspace(
        np.log10(SAMPLE_SIZES[0]), np.log10(SAMPLE_SIZES[-1]), 300
    )
    d_crit = 1.36 / np.sqrt(n_fine)  # critical value at α = 0.05 (large-n approx)
    ax.plot(n_fine, d_crit, "--", color="black", linewidth=1.8, alpha=0.7,
            label=f"Critical value α = {ALPHA}  (≈ 1.36 / √n)")

    for dist_name, dist_config in DISTRIBUTIONS.items():
        ks1_d   = results[dist_name]["ks1_d"]
        medians = [np.median(ks1_d[n]) for n in SAMPLE_SIZES]
        q25     = [np.percentile(ks1_d[n], 25) for n in SAMPLE_SIZES]
        q75     = [np.percentile(ks1_d[n], 75) for n in SAMPLE_SIZES]

        ax.fill_between(SAMPLE_SIZES, q25, q75,
                        color=dist_config["color"], alpha=0.18)
        ax.plot(SAMPLE_SIZES, medians, "o-",
                color=dist_config["color"], linewidth=2, markersize=6,
                label=dist_config["label"])

    ax.set_xscale("log")
    ax.set_xlabel("Number of samples (n)")
    ax.set_ylabel("KS statistic D")
    ax.set_title(
        "One-sample KS statistic vs sample size\n"
        "D decreases as ~1/√n.  Values above the dashed line reject H₀."
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "ks_statistic_vs_n.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_ks1_pvalue_boxplots(results):
    """Box plots of 1-sample KS p-values vs n, one panel per distribution."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    fig.suptitle(
        f"One-sample KS test p-values vs n  |  {len(SEEDS)} seeds\n"
        "H₀: samples come from the true distribution.  "
        "Under H₀ p ~ Uniform(0,1); ~95% should exceed 0.05.",
        fontsize=11,
    )
    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        _box_axes(ax, results[dist_name]["ks1_p"], dist_config["color"],
                  y_ref=ALPHA, ref_label=f"α = {ALPHA}")
        ax.axhline(y=0.5, color="grey", linestyle=":", linewidth=1.0, alpha=0.6,
                   label="p = 0.5 (expected median)")
        ax.set_ylabel("KS p-value" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=8)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "ks_pvalue_boxplots.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_ks_kde_quality(results):
    """
    Two-sample KS p-value (KDE samples vs N_REF true samples) vs n.
    Low p-value means the KDE is not yet close to the true distribution.
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    fig.suptitle(
        f"Two-sample KS test: KDE samples vs {N_REF:,} true samples  |  {len(SEEDS)} seeds\n"
        "Tests whether the KDE correctly reproduces the true distribution.  "
        "Higher p-value = better KDE fit.",
        fontsize=11,
    )
    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        _box_axes(ax, results[dist_name]["ks2_p"], dist_config["color"],
                  y_ref=ALPHA, ref_label=f"α = {ALPHA}")
        ax.set_ylabel("2-sample KS p-value" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=8)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "ks_kde_quality_vs_n.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_pass_rate(results):
    """
    Fraction of seeds passing each test (p > alpha) vs n.
    Expected under H₀: ~95% for all n.
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        f"Test pass rate (fraction of seeds with p > {ALPHA}) vs n\n"
        f"Expected under H₀ (samples from true distribution): {(1-ALPHA)*100:.0f}%",
        fontsize=12,
    )

    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        col = dist_config["color"]

        rate_ks1 = [np.mean(np.array(results[dist_name]["ks1_p"][n]) > ALPHA)
                    for n in SAMPLE_SIZES]
        rate_ks2 = [np.mean(np.array(results[dist_name]["ks2_p"][n]) > ALPHA)
                    for n in SAMPLE_SIZES]
        chi_vals = [results[dist_name]["chi_p"][n] for n in SAMPLE_SIZES]
        rate_chi = [
            np.nanmean(np.array(v) > ALPHA) if any(not np.isnan(x) for x in v) else np.nan
            for v in chi_vals
        ]

        ax.plot(SAMPLE_SIZES, rate_ks1, "o-", color="#3498db",
                linewidth=2, markersize=6, label="1-sample KS (continuous)")
        ax.plot(SAMPLE_SIZES, rate_ks2, "s-", color="#e74c3c",
                linewidth=2, markersize=6, label="2-sample KS (KDE quality)")
        ax.plot(SAMPLE_SIZES, rate_chi, "^-", color="#f39c12",
                linewidth=2, markersize=6, label="Chi-squared (discrete, 1ms)")

        ax.axhline(y=1 - ALPHA, color="black", linestyle="--", linewidth=1.5,
                   label=f"Expected {(1-ALPHA)*100:.0f}%")
        ax.set_xscale("log")
        ax.set_ylim(-0.05, 1.10)
        ax.set_xlabel("Number of samples (n)")
        ax.set_ylabel("Pass rate" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "pass_rate_vs_n.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_chisq_pvalue_boxplots(results):
    """Box plots of chi-squared p-values vs n, one panel per distribution."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    fig.suptitle(
        f"Chi-squared goodness-of-fit p-values vs n  |  {BIN_SIZE_CHI}ms bins  |  "
        f"{len(SEEDS)} seeds\n"
        "H₀: histogram matches the true PMF.  Bins with expected count < 5 are merged.",
        fontsize=11,
    )
    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        # Replace nan with a sentinel so boxplot can still run
        data = []
        for n in SAMPLE_SIZES:
            clean = [v for v in results[dist_name]["chi_p"][n] if not np.isnan(v)]
            data.append(clean if clean else [np.nan])

        _box_axes(ax, {n: data[i] for i, n in enumerate(SAMPLE_SIZES)},
                  dist_config["color"],
                  y_ref=ALPHA, ref_label=f"α = {ALPHA}")
        ax.set_ylabel("Chi-squared p-value" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=8)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "chisq_pvalue_boxplots.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ============================================================
# main
# ============================================================

if __name__ == "__main__":
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR)

    print("KS test p-value evolution experiment")
    print(f"  Distributions : {list(DISTRIBUTIONS.keys())}")
    print(f"  Sample sizes  : {SAMPLE_SIZES}")
    print(f"  Seeds         : {len(SEEDS)}")
    print(f"  Alpha         : {ALPHA}")
    print(f"  N_ref (2-samp): {N_REF:,}")
    print()

    results = run_experiments()

    print("\nGenerating plots ...")
    plot_ks_statistic(results)
    plot_ks1_pvalue_boxplots(results)
    plot_ks_kde_quality(results)
    plot_pass_rate(results)
    plot_chisq_pvalue_boxplots(results)

    print("\nDone.")
