"""
PMF vs KDE comparison — estimator differences across bin sizes.

Compares the histogram (PMF) and kernel density estimate (KDE) as
reconstruction methods, measuring how closely each approximates the true
distribution, how much they disagree with each other, and whether the
disagreement is statistically significant.

For each (distribution, sample size, bin size), the following are recorded:

  TVD(true, KDE)     KDE accuracy against ground truth
  TVD(true, PMF)     PMF accuracy against ground truth
  TVD(KDE,  PMF)     direct divergence between the two estimators

  KS 2-sample        n resamples from KDE vs n resamples from PMF;
                     tests whether the two estimators are statistically
                     indistinguishable as n grows
  Pearson chi-sq     PMF bin counts (observed) vs KDE-predicted bin
                     probabilities * n (expected); tests consistency
                     of the PMF with what the KDE implies

Plots produced:
  tvd_convergence_{dist}.png       TVD vs n for KDE and PMF, per distribution
                                   2x2 grid, one panel per bin size
  estimator_gap_all_dists.png      TVD(KDE, PMF) vs n, all distributions
  visual_comparison_{dist}.png     true PDF, KDE curve, and PMF bars at key n
  kde_advantage_ratio.png          PMF TVD / KDE TVD ratio across n
  stat_tests_{dist}.png            KS and chi-sq p-values vs n, 2x2 per dist
  pass_rate_kde_vs_pmf.png         fraction of seeds with p > 0.05 for
                                   both tests, 2x3 grid

Results saved to: results/pmf-kde-comparison/
"""

import os
import shutil
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/pmf-kde-comparison")

SAMPLE_SIZES    = [200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
SEEDS           = list(range(1, 21))
VISUAL_N_VALUES = [200, 1000, 5000, 20000]
BIN_SIZES       = [1, 2, 5, 10]   # ms
GRID_MAX        = 150.0
ALPHA           = 0.05

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

BIN_COLORS   = {1: "#2196F3", 2: "#FF9800", 5: "#4CAF50", 10: "#E91E63"}
BIN_MARKERS  = {1: "o", 2: "s", 5: "^", 10: "D"}


# ============================================================
# helpers — distributions
# ============================================================

def sample_distribution(dist_name, params, n, rng):
    if dist_name == "normal":
        return rng.normal(loc=params["mean"], scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(dist_name)


def get_scipy_dist(dist_name, params):
    if dist_name == "normal":
        return stats.norm(loc=params["mean"], scale=np.sqrt(params["variance"]))
    elif dist_name == "lognormal":
        return stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))
    elif dist_name == "weibull":
        return stats.weibull_min(c=params["shape"], scale=params["scale"])
    raise ValueError(dist_name)


def param_str(dist_name, params):
    if dist_name == "normal":
        return f"μ = {params['mean']}, σ² = {params['variance']}"
    elif dist_name == "lognormal":
        return f"μ = {params['mu']}, σ = {params['sigma']}"
    elif dist_name == "weibull":
        return f"scale = {params['scale']}, shape = {params['shape']}"
    return ""


# ============================================================
# helpers — estimators
# ============================================================

def true_pmf(dist_name, params, bin_size):
    """True probability masses via CDF differences, normalised."""
    edges  = np.arange(0.0, GRID_MAX + bin_size, bin_size)
    d      = get_scipy_dist(dist_name, params)
    masses = np.diff(d.cdf(edges))
    return masses / masses.sum()


def kde_pmf(samples, bin_size):
    """
    KDE integrated exactly over each bin using Gaussian CDF differences.
    Mass in bin [a,b] = mean_j( Phi((b-xj)/h) - Phi((a-xj)/h) ).
    """
    edges  = np.arange(0.0, GRID_MAX + bin_size, bin_size)
    kde    = stats.gaussian_kde(samples, bw_method="scott")
    h      = kde.factor * np.std(samples, ddof=1)
    left   = edges[:-1]
    right  = edges[1:]
    masses = np.mean(
        stats.norm.cdf(right, loc=samples[:, None], scale=h)
        - stats.norm.cdf(left,  loc=samples[:, None], scale=h),
        axis=0,
    )
    s = masses.sum()
    return masses / s if s > 0 else masses


def empirical_pmf(samples, bin_size):
    """Raw histogram PMF on coarse bins, normalised."""
    k   = int(GRID_MAX / bin_size)
    idx = np.clip(np.floor(samples / bin_size).astype(int), 0, k - 1)
    counts = np.bincount(idx, minlength=k).astype(float)
    total  = counts.sum()
    return counts / total if total > 0 else counts


def empirical_counts(samples, bin_size):
    """Raw integer bin counts (not normalised)."""
    k   = int(GRID_MAX / bin_size)
    idx = np.clip(np.floor(samples / bin_size).astype(int), 0, k - 1)
    return np.bincount(idx, minlength=k)


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


# ============================================================
# helpers — statistical tests (KDE vs PMF directly)
# ============================================================

def ks_kde_vs_pmf(kde_obj, pmf_probs, bin_size, n, seed):
    """
    2-sample KS test between n resamples from the KDE and n resamples from
    the PMF (drawn as a discrete distribution over bin centres).
    Tests whether the two estimators are statistically indistinguishable.
    """
    rng_k = np.random.default_rng(seed + 10000)
    rng_p = np.random.default_rng(seed + 20000)

    np.random.seed(int(seed) + 10000)
    kde_samples = kde_obj.resample(n)[0]

    k            = int(GRID_MAX / bin_size)
    bin_centres  = (np.arange(k) + 0.5) * bin_size
    # Guard against all-zero pmf (shouldn't happen, but be safe)
    p = pmf_probs.copy()
    s = p.sum()
    if s == 0:
        return np.nan, np.nan
    p = p / s
    pmf_samples = rng_p.choice(bin_centres, size=n, p=p)

    stat, pval = stats.ks_2samp(kde_samples, pmf_samples)
    return float(stat), float(pval)


def chisq_kde_vs_pmf(observed_counts, kde_probs):
    """
    Pearson chi-squared: observed bin counts (from PMF) vs expected counts
    predicted by the KDE (kde_probs * n).

    Bins where expected < 5 are merged with their neighbour to avoid
    inflated chi-squared statistics from sparse cells.

    Returns (stat, pval) or (nan, nan) if there are fewer than 2 bins.
    """
    n        = observed_counts.sum()
    expected = kde_probs * n

    # Merge bins with expected < 5
    obs_m = []
    exp_m = []
    obs_acc = 0.0
    exp_acc = 0.0
    for o, e in zip(observed_counts.astype(float), expected):
        obs_acc += o
        exp_acc += e
        if exp_acc >= 5.0:
            obs_m.append(obs_acc)
            exp_m.append(exp_acc)
            obs_acc = 0.0
            exp_acc = 0.0
    # Absorb any leftover into the last bin
    if obs_m:
        obs_m[-1] += obs_acc
        exp_m[-1] += exp_acc
    else:
        obs_m = [obs_acc]
        exp_m = [exp_acc]

    if len(obs_m) < 2:
        return np.nan, np.nan

    obs_arr = np.array(obs_m)
    exp_arr = np.array(exp_m)
    # Renormalise expected to same sum as observed (chisquare requires this)
    exp_arr = exp_arr * (obs_arr.sum() / exp_arr.sum())

    stat, pval = stats.chisquare(f_obs=obs_arr, f_exp=exp_arr)
    return float(stat), float(pval)


# ============================================================
# experiments
# ============================================================

def run_experiments():
    """
    Returns:
        results[dist_name][bin_size] = {
            'kde':      {n: [tvd(true, kde), ...]},
            'pmf':      {n: [tvd(true, pmf), ...]},
            'gap':      {n: [tvd(kde,  pmf), ...]},
            'ks_stat':  {n: [...]},
            'ks_pval':  {n: [...]},
            'cs_stat':  {n: [...]},
            'cs_pval':  {n: [...]},
        }
        visual_samples[dist_name][n] = samples array (seed=1)
    """
    results        = {}
    visual_samples = {}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        print(f"\n--- {dist_config['label']} ---")
        params = dist_config["params"]
        results[dist_name]        = {}
        visual_samples[dist_name] = {}

        for bin_size in BIN_SIZES:
            true_m = true_pmf(dist_name, params, bin_size)

            store = {
                key: {n: [] for n in SAMPLE_SIZES}
                for key in ("kde", "pmf", "gap", "ks_stat", "ks_pval", "cs_stat", "cs_pval")
            }

            for n in SAMPLE_SIZES:
                for seed in SEEDS:
                    rng     = np.random.default_rng(seed)
                    samples = sample_distribution(dist_name, params, n, rng)

                    if seed == 1 and bin_size == BIN_SIZES[0] and n in VISUAL_N_VALUES:
                        visual_samples[dist_name][n] = samples

                    kde_obj  = stats.gaussian_kde(samples, bw_method="scott")
                    kde_m    = kde_pmf(samples, bin_size)
                    pmf_m    = empirical_pmf(samples, bin_size)
                    counts   = empirical_counts(samples, bin_size)

                    store["kde"][n].append(tvd(true_m, kde_m))
                    store["pmf"][n].append(tvd(true_m, pmf_m))
                    store["gap"][n].append(tvd(kde_m, pmf_m))

                    ks_s, ks_p = ks_kde_vs_pmf(kde_obj, pmf_m, bin_size, n, seed)
                    store["ks_stat"][n].append(ks_s)
                    store["ks_pval"][n].append(ks_p)

                    cs_s, cs_p = chisq_kde_vs_pmf(counts, kde_m)
                    store["cs_stat"][n].append(cs_s)
                    store["cs_pval"][n].append(cs_p)

                if bin_size == 1:
                    ks_pass  = np.mean([v > ALPHA for v in store["ks_pval"][n] if not np.isnan(v)])
                    cs_pass  = np.mean([v > ALPHA for v in store["cs_pval"][n] if not np.isnan(v)])
                    print(
                        f"  bin=1ms  n={n:>7,}  "
                        f"KDE={np.median(store['kde'][n]):.5f}  "
                        f"PMF={np.median(store['pmf'][n]):.5f}  "
                        f"gap={np.median(store['gap'][n]):.5f}  "
                        f"KS_pass={ks_pass:.0%}  χ²_pass={cs_pass:.0%}"
                    )

            results[dist_name][bin_size] = store

    return results, visual_samples


# ============================================================
# plots — TVD (existing)
# ============================================================

def plot_tvd_convergence(results):
    for dist_name, dist_config in DISTRIBUTIONS.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"{dist_config['label']} — TVD convergence: KDE vs PMF\n"
            f"{param_str(dist_name, dist_config['params'])}  |  {len(SEEDS)} seeds",
            fontsize=12,
        )

        for ax, bin_size in zip(axes.flatten(), BIN_SIZES):
            r = results[dist_name][bin_size]

            for key, col, ls, mk, lab in (
                ("kde", "#3498db", "-",  "o", "KDE"),
                ("pmf", "#e74c3c", "--", "s", "PMF"),
            ):
                meds = [np.median(r[key][n]) for n in SAMPLE_SIZES]
                q25  = [np.percentile(r[key][n], 25) for n in SAMPLE_SIZES]
                q75  = [np.percentile(r[key][n], 75) for n in SAMPLE_SIZES]
                ax.fill_between(SAMPLE_SIZES, q25, q75, color=col, alpha=0.15)
                ax.plot(SAMPLE_SIZES, meds, marker=mk, linestyle=ls, color=col,
                        linewidth=2, markersize=6, label=lab)

            ax.axhline(y=0.05, color="grey", linestyle=":", linewidth=1.2,
                       label="TVD = 0.05")
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("Number of samples (n)")
            ax.set_ylabel("TVD vs true distribution")
            ax.set_title(f"{bin_size} ms bins")
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3, which="both")

        plt.tight_layout()
        out = os.path.join(RESULTS_DIR, f"tvd_convergence_{dist_name}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")


def plot_estimator_gap(results):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        "Estimator disagreement: TVD(KDE, PMF) vs n\n"
        "Both estimators converge to the truth; their disagreement decreases with n.  "
        "Larger bins reduce the gap faster.",
        fontsize=12,
    )

    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        for bin_size in BIN_SIZES:
            r    = results[dist_name][bin_size]
            meds = [np.median(r["gap"][n]) for n in SAMPLE_SIZES]
            q25  = [np.percentile(r["gap"][n], 25) for n in SAMPLE_SIZES]
            q75  = [np.percentile(r["gap"][n], 75) for n in SAMPLE_SIZES]
            col  = BIN_COLORS[bin_size]
            mk   = BIN_MARKERS[bin_size]

            ax.fill_between(SAMPLE_SIZES, q25, q75, color=col, alpha=0.12)
            ax.plot(SAMPLE_SIZES, meds, marker=mk, linestyle="-", color=col,
                    linewidth=2, markersize=6, label=f"{bin_size} ms bins")

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Number of samples (n)")
        ax.set_ylabel("TVD(KDE, PMF)" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "estimator_gap_all_dists.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_visual_comparison(visual_samples):
    bin_size_vis = BIN_SIZES[0]

    for dist_name, dist_config in DISTRIBUTIONS.items():
        params   = dist_config["params"]
        d_obj    = get_scipy_dist(dist_name, params)
        xmin     = max(0.0, d_obj.ppf(0.0005))
        xmax     = d_obj.ppf(0.9995)
        x_fine   = np.linspace(xmin, xmax, 800)
        true_pdf = d_obj.pdf(x_fine)

        edges   = np.arange(0.0, GRID_MAX + bin_size_vis, bin_size_vis)
        centres = edges[:-1] + bin_size_vis / 2
        k       = len(centres)

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"{dist_config['label']} — Visual comparison: true PDF, KDE, PMF\n"
            f"{param_str(dist_name, params)}  |  {bin_size_vis} ms bins  |  seed 1",
            fontsize=12,
        )

        for ax, n in zip(axes.flatten(), VISUAL_N_VALUES):
            samples = visual_samples[dist_name][n]

            idx    = np.clip(np.floor(samples / bin_size_vis).astype(int), 0, k - 1)
            counts = np.bincount(idx, minlength=k).astype(float)
            pmf    = counts / counts.sum()
            density = pmf / bin_size_vis
            vis     = (centres >= xmin) & (centres <= xmax)
            ax.bar(centres[vis], density[vis], width=bin_size_vis * 0.85,
                   color="#FF9800", alpha=0.5, label="Empirical PMF")

            kde_obj = stats.gaussian_kde(samples, bw_method="scott")
            ax.plot(x_fine, kde_obj(x_fine), color="#9b59b6",
                    linewidth=2.0, label="KDE")

            ax.plot(x_fine, true_pdf, color="black",
                    linewidth=2.0, linestyle="--", label="True PDF")

            ax.set_xlim(xmin, xmax)
            ax.set_xlabel("Delay (ms)")
            ax.set_ylabel("Probability density")
            ax.set_title(f"n = {n:,}")
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        out = os.path.join(RESULTS_DIR, f"visual_comparison_{dist_name}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")


def plot_kde_advantage_ratio(results):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        "KDE advantage: TVD(true, PMF) / TVD(true, KDE)\n"
        "Ratio > 1 means KDE is more accurate.  Advantage is largest at small n.",
        fontsize=12,
    )

    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        for bin_size in BIN_SIZES:
            r      = results[dist_name][bin_size]
            ratios = []
            for n in SAMPLE_SIZES:
                kde_med = np.median(r["kde"][n])
                pmf_med = np.median(r["pmf"][n])
                ratios.append(pmf_med / kde_med if kde_med > 0 else np.nan)

            col = BIN_COLORS[bin_size]
            mk  = BIN_MARKERS[bin_size]
            ax.plot(SAMPLE_SIZES, ratios, marker=mk, linestyle="-", color=col,
                    linewidth=2, markersize=6, label=f"{bin_size} ms bins")

        ax.axhline(y=1.0, color="black", linestyle="--", linewidth=1.5,
                   label="ratio = 1 (equal accuracy)")
        ax.set_xscale("log")
        ax.set_xlabel("Number of samples (n)")
        ax.set_ylabel("TVD(PMF) / TVD(KDE)" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "kde_advantage_ratio.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ============================================================
# plots — statistical tests (new)
# ============================================================

def _plot_pval_panel(ax, results_bin, metric, label, color):
    """Draw median p-value + IQR band for one test on one axes."""
    pvals  = results_bin[metric]
    meds   = [np.nanmedian(pvals[n]) for n in SAMPLE_SIZES]
    q25    = [np.nanpercentile(pvals[n], 25) for n in SAMPLE_SIZES]
    q75    = [np.nanpercentile(pvals[n], 75) for n in SAMPLE_SIZES]

    ax.fill_between(SAMPLE_SIZES, q25, q75, color=color, alpha=0.15)
    ax.plot(SAMPLE_SIZES, meds, "o-", color=color,
            linewidth=2, markersize=6, label=label)


def plot_stat_tests_per_dist(results):
    """
    Per-distribution, 2x2 grid (one panel per bin size).
    Each panel shows the median p-value for the KS 2-sample test (KDE vs PMF)
    and the Pearson chi-squared test as a function of n.
    The alpha = 0.05 horizontal line marks the significance threshold.

    Large p-value means the two estimators are NOT statistically distinguishable
    — they are telling the same story about the distribution.
    """
    for dist_name, dist_config in DISTRIBUTIONS.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"{dist_config['label']} — Statistical tests: KDE vs PMF directly\n"
            f"{param_str(dist_name, dist_config['params'])}  |  {len(SEEDS)} seeds\n"
            "Large p-value = KDE and PMF are statistically indistinguishable",
            fontsize=11,
        )

        for ax, bin_size in zip(axes.flatten(), BIN_SIZES):
            r = results[dist_name][bin_size]

            _plot_pval_panel(ax, r, "ks_pval", "KS 2-sample", "#3498db")
            _plot_pval_panel(ax, r, "cs_pval", "Pearson χ²",  "#e74c3c")

            ax.axhline(y=ALPHA, color="black", linestyle="--", linewidth=1.2,
                       label=f"α = {ALPHA}")

            ax.set_xscale("log")
            ax.set_ylim(-0.02, 1.05)
            ax.set_xlabel("Number of samples (n)")
            ax.set_ylabel("p-value (median across seeds)")
            ax.set_title(f"{bin_size} ms bins")
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3, which="both")

        plt.tight_layout()
        out = os.path.join(RESULTS_DIR, f"stat_tests_{dist_name}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")


def plot_pass_rate(results):
    """
    2x3 grid: top row = KS 2-sample pass rate, bottom row = chi-sq pass rate.
    One column per distribution, one line per bin size.
    Pass rate = fraction of seeds where p > alpha.
    """
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(
        f"Pass rate (p > {ALPHA}): KDE vs PMF agreement as a function of n\n"
        "Top row: KS 2-sample (KDE resamples vs PMF resamples).  "
        "Bottom row: Pearson chi-squared (PMF counts vs KDE-expected counts).\n"
        "High pass rate = the two estimators are statistically consistent.",
        fontsize=11,
    )

    for col_idx, (dist_name, dist_config) in enumerate(DISTRIBUTIONS.items()):
        for row_idx, (metric, title) in enumerate(
            [("ks_pval", "KS 2-sample"), ("cs_pval", "Pearson χ²")]
        ):
            ax = axes[row_idx][col_idx]

            for bin_size in BIN_SIZES:
                r    = results[dist_name][bin_size]
                rate = [
                    np.mean([v > ALPHA for v in r[metric][n] if not np.isnan(v)])
                    for n in SAMPLE_SIZES
                ]
                col = BIN_COLORS[bin_size]
                mk  = BIN_MARKERS[bin_size]
                ax.plot(SAMPLE_SIZES, rate, marker=mk, linestyle="-", color=col,
                        linewidth=2, markersize=6, label=f"{bin_size} ms bins")

            ax.axhline(y=0.95, color="grey", linestyle=":", linewidth=1.0,
                       label="95% pass rate")
            ax.set_xscale("log")
            ax.set_ylim(-0.05, 1.08)
            ax.set_xlabel("Number of samples (n)")
            if col_idx == 0:
                ax.set_ylabel(f"{title}\nPass rate (fraction of seeds)")
            ax.set_title(dist_config["label"])
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "pass_rate_kde_vs_pmf.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_ks_stat_vs_n(results):
    """
    KS statistic (not p-value) vs n for all distributions, 1x3.
    Shows the raw divergence between KDE and PMF resamples on a log-log scale.
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        "KS 2-sample statistic (KDE vs PMF) vs n — log-log axes\n"
        "Statistic → 0 as both estimators converge to the truth",
        fontsize=12,
    )

    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        for bin_size in BIN_SIZES:
            r    = results[dist_name][bin_size]
            meds = [np.nanmedian(r["ks_stat"][n]) for n in SAMPLE_SIZES]
            q25  = [np.nanpercentile(r["ks_stat"][n], 25) for n in SAMPLE_SIZES]
            q75  = [np.nanpercentile(r["ks_stat"][n], 75) for n in SAMPLE_SIZES]
            col  = BIN_COLORS[bin_size]
            mk   = BIN_MARKERS[bin_size]

            ax.fill_between(SAMPLE_SIZES, q25, q75, color=col, alpha=0.12)
            ax.plot(SAMPLE_SIZES, meds, marker=mk, linestyle="-", color=col,
                    linewidth=2, markersize=6, label=f"{bin_size} ms bins")

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Number of samples (n)")
        ax.set_ylabel("KS statistic" if ax is axes[0] else "")
        ax.set_title(dist_config["label"])
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "ks_stat_kde_vs_pmf.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ============================================================
# console summary
# ============================================================

def print_summary(results):
    print("\n" + "=" * 90)
    print(f"Smallest n where pass rate >= 95% for BOTH tests (bin = 1ms)")
    print("=" * 90)
    print("Note: KS 2-sample compares continuous KDE resamples vs discrete PMF resamples.")
    print("      At large n it always detects this structural difference — low pass rate")
    print("      is expected and meaningful. Chi-sq tests bin-level agreement only.")
    print(f"{'Distribution':<14}  {'KS 2-sample':>14}  {'Pearson χ²':>14}")
    print("-" * 50)

    for dist_name, dist_config in DISTRIBUTIONS.items():
        r = results[dist_name][1]  # 1ms bins

        def first_n(metric):
            for n in SAMPLE_SIZES:
                vals = r[metric][n]
                rate = np.mean([v > ALPHA for v in vals if not np.isnan(v)])
                if rate >= 0.95:
                    return n
            return ">50,000"

        n_ks = first_n("ks_pval")
        n_cs = first_n("cs_pval")
        ks_str = f"{n_ks:,}" if isinstance(n_ks, int) else str(n_ks)
        cs_str = f"{n_cs:,}" if isinstance(n_cs, int) else str(n_cs)
        print(f"{dist_config['label']:<14}  {ks_str:>14}  {cs_str:>14}")


# ============================================================
# main
# ============================================================

if __name__ == "__main__":
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR)

    print("PMF vs KDE comparison experiment")
    print(f"  Distributions : {list(DISTRIBUTIONS.keys())}")
    print(f"  Sample sizes  : {SAMPLE_SIZES}")
    print(f"  Seeds         : {len(SEEDS)}")
    print(f"  Bin sizes     : {BIN_SIZES} ms")
    print(f"  Alpha         : {ALPHA}")
    print()

    results, visual_samples = run_experiments()

    print_summary(results)

    print("\nGenerating plots ...")
    plot_tvd_convergence(results)
    plot_estimator_gap(results)
    plot_visual_comparison(visual_samples)
    plot_kde_advantage_ratio(results)
    plot_stat_tests_per_dist(results)
    plot_pass_rate(results)
    plot_ks_stat_vs_n(results)

    print("\nDone.")
