"""
KS test p-value evolution — connecting statistical tests to TVD = 0.05.

For each distribution, four tests are run at each sample size across 20 seeds:

  (a) 1-sample KS (continuous)
      kstest(samples, true_cdf)
      H0: samples come from the true distribution.
      Since they do, p-values should be ~Uniform(0,1) for all n.
      Pass rate should sit at ~95% throughout.

  (b) 2-sample KS — KDE quality (continuous)
      Fits KDE to the n training samples; draws N_REF samples from the KDE;
      runs ks_2samp(kde_samples, reference_true_samples).
      H0: the KDE faithfully reproduces the true distribution.
      At small n the KDE is over-smoothed and the test may reject.
      At large n the KDE converges and should consistently pass.

  (c) Chi-squared goodness-of-fit (discrete)
      Bins samples into BIN_SIZE_CHI ms bins; compares observed counts to
      expected counts from the true PMF.  Bins with expected count < 5 are
      merged before testing.
      H0: the histogram matches the true PMF.

  (d) 2-sample Anderson-Darling — KDE tail quality (continuous)
      anderson_ksamp([kde_samples, reference_true_samples])
      More sensitive than the KS test to differences in the distribution tails.

A vertical dashed line is drawn on every plot at n*, the smallest sample
size where the median TVD drops below 0.05 (the practical accuracy target).
This connects each test's pass/fail outcome directly to the TVD threshold.

TVD is computed using:
  Continuous: KDE on 1ms grid vs true PDF masses
  Discrete:   Empirical PMF at BIN_SIZE_CHI ms bins vs true PMF

Results saved to: results/ks-experiment/
Clears the directory on each run.
"""

import os
import shutil
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/ks-experiment")

# ============================================================
# parameters
# ============================================================

SAMPLE_SIZES  = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
SEEDS         = list(range(1, 21))   # 20 seeds per (distribution, n)
ALPHA         = 0.05                 # significance level for all tests
TVD_TARGET    = 0.05                 # fixed accuracy target for n* marker
N_REF         = 5000                 # reference sample size for 2-sample tests
BIN_SIZE_CHI  = 1.0                  # ms; bin size for chi-squared and discrete TVD
GRID_MAX      = 150.0
BIN_WIDTH_KDE = 1.0                  # ms; fine grid for KDE TVD
GRID_KDE      = np.arange(BIN_WIDTH_KDE / 2, GRID_MAX, BIN_WIDTH_KDE)
K_KDE         = len(GRID_KDE)

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
        return rng.normal(loc=params["mean"],
                          scale=np.sqrt(params["variance"]), size=n)
    elif dist_name == "lognormal":
        return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], size=n)
    raise ValueError(dist_name)


def param_str(dist_name, params):
    if dist_name == "normal":
        return f"μ={params['mean']}, σ²={params['variance']}"
    elif dist_name == "lognormal":
        return f"μ={params['mu']}, σ={params['sigma']}"
    elif dist_name == "weibull":
        return f"scale={params['scale']}, shape={params['shape']}"
    return ""


# TVD helpers
def true_masses_kde_grid(dist_name, params):
    d   = get_scipy_dist(dist_name, params)
    pdf = d.pdf(GRID_KDE)
    m   = pdf * BIN_WIDTH_KDE
    return m / m.sum()


def kde_masses_on_grid(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    m   = kde(GRID_KDE) * BIN_WIDTH_KDE
    return m / m.sum()


def true_pmf_coarse(dist_name, params):
    d     = get_scipy_dist(dist_name, params)
    edges = np.arange(0.0, GRID_MAX + BIN_SIZE_CHI, BIN_SIZE_CHI)
    m     = np.diff(d.cdf(edges))
    return m / m.sum()


def empirical_pmf_coarse(samples):
    k   = int(GRID_MAX / BIN_SIZE_CHI)
    idx = np.clip(np.floor(samples / BIN_SIZE_CHI).astype(int), 0, k - 1)
    c   = np.bincount(idx, minlength=k).astype(float)
    return c / c.sum() if c.sum() > 0 else c


def tvd(p, q):
    return 0.5 * float(np.sum(np.abs(p - q)))


def chi_squared_test(samples, dist_obj, n):
    """Chi-squared with bin merging for expected counts < 5."""
    edges    = np.arange(0.0, GRID_MAX + BIN_SIZE_CHI, BIN_SIZE_CHI)
    expected = np.diff(dist_obj.cdf(edges)) * n
    observed, _ = np.histogram(samples, bins=edges)

    obs_m, exp_m = [], []
    oa, ea = 0.0, 0.0
    for o, e in zip(observed, expected):
        oa += o; ea += e
        if ea >= 5.0:
            obs_m.append(oa); exp_m.append(ea)
            oa, ea = 0.0, 0.0
    if obs_m and ea > 0:
        obs_m[-1] += oa; exp_m[-1] += ea

    if len(obs_m) < 2:
        return np.nan, np.nan
    stat, p = stats.chisquare(np.array(obs_m), f_exp=np.array(exp_m))
    return stat, p


def find_n_star(tvds_by_n, target=TVD_TARGET):
    """Smallest n where median TVD <= target, else None."""
    for n in SAMPLE_SIZES:
        if np.median(tvds_by_n[n]) <= target:
            return n
    return None


# ============================================================
# experiments
# ============================================================

def run_experiments():
    """
    Returns results[dist_name] = {
        "ks1_p":   {n: [p values]},      # 1-sample KS
        "ks2_p":   {n: [p values]},      # 2-sample KS (KDE quality)
        "chi_p":   {n: [p values]},      # chi-squared
        "ad_p":    {n: [p values]},      # 2-sample Anderson-Darling
        "ks1_d":   {n: [D statistics]},  # KS D statistic
        "tvd_kde": {n: [TVD values]},    # KDE TVD for n* computation
        "tvd_pmf": {n: [TVD values]},    # PMF TVD for n* computation
    }
    """
    results = {}

    for dist_name, dist_config in DISTRIBUTIONS.items():
        print(f"\n--- {dist_config['label']} ---")
        params   = dist_config["params"]
        dist_obj = get_scipy_dist(dist_name, params)

        true_cont = true_masses_kde_grid(dist_name, params)
        true_disc = true_pmf_coarse(dist_name, params)

        ref_rng     = np.random.default_rng(0)
        ref_samples = sample_distribution(dist_name, params, N_REF, ref_rng)

        ks1_p = {n: [] for n in SAMPLE_SIZES}
        ks1_d = {n: [] for n in SAMPLE_SIZES}
        ks2_p = {n: [] for n in SAMPLE_SIZES}
        chi_p = {n: [] for n in SAMPLE_SIZES}
        ad_p  = {n: [] for n in SAMPLE_SIZES}
        tvd_kde = {n: [] for n in SAMPLE_SIZES}
        tvd_pmf = {n: [] for n in SAMPLE_SIZES}

        for n in SAMPLE_SIZES:
            for seed in SEEDS:
                rng     = np.random.default_rng(seed)
                samples = sample_distribution(dist_name, params, n, rng)

                # (a) 1-sample KS
                d_stat, p1 = stats.kstest(samples, dist_obj.cdf)
                ks1_d[n].append(d_stat)
                ks1_p[n].append(p1)

                # (b) 2-sample KS — KDE quality
                kde      = stats.gaussian_kde(samples, bw_method="scott")
                kde_samp = kde.resample(N_REF, seed=seed)[0]
                _, p2    = stats.ks_2samp(kde_samp, ref_samples)
                ks2_p[n].append(p2)

                # (c) chi-squared
                _, pchi = chi_squared_test(samples, dist_obj, n)
                chi_p[n].append(pchi if not np.isnan(pchi) else np.nan)

                # (d) 2-sample Anderson-Darling — KDE quality
                try:
                    ad_res = stats.anderson_ksamp([kde_samp, ref_samples])
                    ad_p[n].append(float(ad_res.pvalue))
                except Exception:
                    ad_p[n].append(np.nan)

                # TVD
                tvd_kde[n].append(tvd(true_cont, kde_masses_on_grid(samples)))
                tvd_pmf[n].append(tvd(true_disc, empirical_pmf_coarse(samples)))

            pass1 = np.mean(np.array(ks1_p[n]) > ALPHA) * 100
            pass2 = np.mean(np.array(ks2_p[n]) > ALPHA) * 100
            chi_clean = [v for v in chi_p[n] if not np.isnan(v)]
            pass3 = (np.mean(np.array(chi_clean) > ALPHA) * 100
                     if chi_clean else float("nan"))
            ad_clean = [v for v in ad_p[n] if not np.isnan(v)]
            pass4 = (np.mean(np.array(ad_clean) > ALPHA) * 100
                     if ad_clean else float("nan"))
            print(
                f"  n={n:>6,}  "
                f"KS1={pass1:.0f}%  KS2={pass2:.0f}%  "
                f"χ²={pass3:.0f}%  AD={pass4:.0f}%  "
                f"TVD_kde={np.median(tvd_kde[n]):.4f}  "
                f"TVD_pmf={np.median(tvd_pmf[n]):.4f}"
            )

        results[dist_name] = {
            "ks1_p": ks1_p, "ks1_d": ks1_d,
            "ks2_p": ks2_p, "chi_p": chi_p, "ad_p": ad_p,
            "tvd_kde": tvd_kde, "tvd_pmf": tvd_pmf,
        }

    return results


# ============================================================
# plotting helpers
# ============================================================

def _line_plot(ax, data_by_n, color, label, clean_nan=False):
    """Median + IQR band as a line, skipping nan entries."""
    xs, meds, q25s, q75s = [], [], [], []
    for n in SAMPLE_SIZES:
        vals = data_by_n[n]
        if clean_nan:
            vals = [v for v in vals if not np.isnan(v)]
        if not vals:
            continue
        xs.append(n)
        meds.append(np.median(vals))
        q25s.append(np.percentile(vals, 25))
        q75s.append(np.percentile(vals, 75))

    if xs:
        ax.fill_between(xs, q25s, q75s, color=color, alpha=0.18)
        ax.plot(xs, meds, "o-", color=color, linewidth=2.5,
                markersize=7, markeredgecolor="white",
                markeredgewidth=0.7, label=label)


def _decorate(ax, n_star=None, n_star_label="n* (TVD≤0.05)",
              y_ref=ALPHA, y_label=f"α = {ALPHA}"):
    """Add significance line, optional n* marker, and grid."""
    ax.axhline(y=y_ref, color="red", linestyle="--",
               linewidth=1.8, label=y_label)
    if n_star is not None:
        ax.axvline(x=n_star, color="black", linestyle=":",
                   linewidth=1.8, label=n_star_label)
    ax.set_xscale("log")
    ax.set_ylim(-0.03, 1.08)
    ax.set_xlabel("Number of samples (n)", fontsize=10)
    ax.set_ylabel("p-value", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, which="both")


# ============================================================
# plots
# ============================================================

def plot_pvalue_per_dist(results):
    """
    Per-distribution 2×2 grid:
      Top-left:     1-sample KS p-value vs n  (continuous baseline)
      Top-right:    2-sample KS p-value vs n  (KDE quality, continuous)
      Bottom-left:  Chi-squared p-value vs n  (discrete)
      Bottom-right: 2-sample Anderson-Darling p-value vs n  (tail test)

    Vertical dashed line marks n* where median TVD first drops to 0.05.
    """
    for dist_name, dist_config in DISTRIBUTIONS.items():
        r   = results[dist_name]
        col = dist_config["color"]

        n_star_kde = find_n_star(r["tvd_kde"])
        n_star_pmf = find_n_star(r["tvd_pmf"])

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"{dist_config['label']} — p-value evolution vs n  "
            f"({len(SEEDS)} seeds)\n"
            f"{param_str(dist_name, dist_config['params'])}  |  "
            f"Vertical line: n* where median TVD ≤ {TVD_TARGET}  |  "
            f"n*_KDE = {n_star_kde:,}   n*_PMF = {n_star_pmf:,}",
            fontsize=11,
        )

        # top-left: 1-sample KS
        ax = axes[0, 0]
        _line_plot(ax, r["ks1_p"], col, "Median p-value (1-sample KS)")
        _decorate(ax, n_star_kde,
                  n_star_label=f"n*_KDE = {n_star_kde:,}")
        ax.set_title("1-sample KS test (continuous)\n"
                     "H₀: samples come from the true distribution\n"
                     "Expected: p ≈ Uniform(0,1) — flat ~0.5 with wide IQR",
                     fontsize=9)

        # top-right: 2-sample KS (KDE quality)
        ax = axes[0, 1]
        _line_plot(ax, r["ks2_p"], col, "Median p-value (2-sample KS)")
        _decorate(ax, n_star_kde,
                  n_star_label=f"n*_KDE = {n_star_kde:,}")
        ax.set_title("2-sample KS: KDE samples vs reference (continuous)\n"
                     "H₀: KDE faithfully reproduces the true distribution\n"
                     "Low p at small n = KDE not yet accurate",
                     fontsize=9)

        # bottom-left: chi-squared
        ax = axes[1, 0]
        _line_plot(ax, r["chi_p"], col, "Median p-value (chi-squared)",
                   clean_nan=True)
        _decorate(ax, n_star_pmf,
                  n_star_label=f"n*_PMF = {n_star_pmf:,}")
        ax.set_title(f"Chi-squared goodness-of-fit (discrete, {BIN_SIZE_CHI}ms bins)\n"
                     "H₀: histogram matches the true PMF\n"
                     "At very small n, sparse bins make the test unreliable",
                     fontsize=9)

        # bottom-right: 2-sample Anderson-Darling
        ax = axes[1, 1]
        _line_plot(ax, r["ad_p"], col, "Median p-value (2-sample AD)",
                   clean_nan=True)
        _decorate(ax, n_star_kde,
                  n_star_label=f"n*_KDE = {n_star_kde:,}")
        ax.set_title("2-sample Anderson-Darling: KDE vs reference (continuous)\n"
                     "More sensitive to tail differences than the KS test\n"
                     "Low p at small n = tail behaviour not yet matched",
                     fontsize=9)

        plt.tight_layout()
        out = os.path.join(RESULTS_DIR, f"pvalue_vs_n_{dist_name}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")


def plot_pass_rate(results):
    """
    1×3 grid (one panel per distribution).
    Each panel shows the fraction of seeds where each test passes (p > α).
    Expected baseline under H₀: 1 - α = 95%.
    Vertical lines at n*_KDE and n*_PMF.
    """
    fig, axes = plt.subplots(1, 3, figsize=(20, 6), sharey=True)
    fig.suptitle(
        f"Test pass rate (fraction of seeds with p > {ALPHA}) vs n  |  "
        f"{len(SEEDS)} seeds\n"
        "Expected under H₀: ~95%  |  "
        "Vertical lines: n* where median TVD ≤ 0.05 "
        "(dashed = KDE / dotted = PMF)",
        fontsize=12,
    )

    test_styles = [
        ("ks1_p",  "#3498db", "o-",  "1-sample KS (continuous baseline)"),
        ("ks2_p",  "#e74c3c", "s-",  "2-sample KS: KDE quality"),
        ("chi_p",  "#f39c12", "^-",  f"Chi-squared (discrete, {BIN_SIZE_CHI}ms)"),
        ("ad_p",   "#9b59b6", "D-",  "2-sample Anderson-Darling: KDE tails"),
    ]

    for ax, (dist_name, dist_config) in zip(axes, DISTRIBUTIONS.items()):
        r = results[dist_name]
        n_star_kde = find_n_star(r["tvd_kde"])
        n_star_pmf = find_n_star(r["tvd_pmf"])

        for key, col, mk, label in test_styles:
            rates = []
            for n in SAMPLE_SIZES:
                vals = [v for v in r[key][n] if not np.isnan(v)]
                rates.append(np.mean(np.array(vals) > ALPHA) if vals else np.nan)
            ax.plot(SAMPLE_SIZES, rates, mk, color=col,
                    linewidth=2.5, markersize=8,
                    markeredgecolor="white", markeredgewidth=0.7,
                    label=label)

        # Expected 95% line
        ax.axhline(y=1 - ALPHA, color="black", linestyle="--",
                   linewidth=2, label=f"Expected {(1-ALPHA)*100:.0f}% (H₀)")

        # n* markers
        if n_star_kde:
            ax.axvline(x=n_star_kde, color="black", linestyle="--",
                       linewidth=1.5,
                       label=f"n*_KDE = {n_star_kde:,}")
        if n_star_pmf:
            ax.axvline(x=n_star_pmf, color="black", linestyle=":",
                       linewidth=1.8,
                       label=f"n*_PMF = {n_star_pmf:,}")

        ax.set_xscale("log")
        ax.set_ylim(-0.05, 1.12)
        ax.set_xlabel("Number of samples (n)", fontsize=11)
        if ax is axes[0]:
            ax.set_ylabel("Fraction passing", fontsize=11)
        ax.set_title(
            f"{dist_config['label']}\n"
            f"{param_str(dist_name, dist_config['params'])}",
            fontsize=11,
        )
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "pass_rate_vs_n.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_ks_statistic(results):
    """
    KS D statistic (1-sample) vs n — all distributions on one log-log plot.
    Theoretical critical value at α = 0.05 overlaid as a dashed curve.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    n_fine = np.logspace(
        np.log10(SAMPLE_SIZES[0]), np.log10(SAMPLE_SIZES[-1]), 300
    )
    d_crit = 1.36 / np.sqrt(n_fine)
    ax.plot(n_fine, d_crit, "--", color="black", linewidth=2,
            alpha=0.7, label=f"Critical value at α = {ALPHA}  (≈ 1.36 / √n)")

    for dist_name, dist_config in DISTRIBUTIONS.items():
        ks1_d = results[dist_name]["ks1_d"]
        meds  = [np.median(ks1_d[n]) for n in SAMPLE_SIZES]
        q25   = [np.percentile(ks1_d[n], 25) for n in SAMPLE_SIZES]
        q75   = [np.percentile(ks1_d[n], 75) for n in SAMPLE_SIZES]

        ax.fill_between(SAMPLE_SIZES, q25, q75,
                        color=dist_config["color"], alpha=0.15)
        ax.plot(SAMPLE_SIZES, meds, "o-",
                color=dist_config["color"], linewidth=2.5, markersize=8,
                markeredgecolor="white", markeredgewidth=0.7,
                label=dist_config["label"])

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Number of samples (n)", fontsize=12)
    ax.set_ylabel("KS statistic D (log scale)", fontsize=12)
    ax.set_title(
        "1-sample KS statistic vs n (log–log)  |  "
        f"{len(SEEDS)} seeds, median + IQR\n"
        "D decreases as ~1/√n.  Values above the dashed line reject H₀.",
        fontsize=11,
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "ks_statistic_vs_n.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_tvd_vs_n(results):
    """
    TVD vs n for both KDE and PMF, all distributions on one panel each.
    Shows the context for the n* vertical line used throughout the other plots.
    Log-log axes.
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        f"TVD vs n — context for the n* = {TVD_TARGET} threshold marker\n"
        f"{len(SEEDS)} seeds, median + IQR  |  "
        "Dashed line: TVD = 0.05 target",
        fontsize=12,
    )

    for ax, method_key, method_title in [
        (axes[0], "tvd_kde", "Continuous (KDE, 1ms grid)"),
        (axes[1], "tvd_pmf", f"Discrete (PMF, {BIN_SIZE_CHI}ms bins)"),
    ]:
        for dist_name, dist_config in DISTRIBUTIONS.items():
            r    = results[dist_name][method_key]
            meds = [np.median(r[n]) for n in SAMPLE_SIZES]
            q25  = [max(np.percentile(r[n], 25), 1e-4) for n in SAMPLE_SIZES]
            q75  = [np.percentile(r[n], 75) for n in SAMPLE_SIZES]

            ax.fill_between(SAMPLE_SIZES, q25, q75,
                            color=dist_config["color"], alpha=0.15)
            ax.plot(SAMPLE_SIZES, meds, "o-",
                    color=dist_config["color"], linewidth=2.5, markersize=8,
                    markeredgecolor="white", markeredgewidth=0.7,
                    label=dist_config["label"])

        ax.axhline(y=TVD_TARGET, color="black", linestyle="--",
                   linewidth=2, label=f"TVD = {TVD_TARGET}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Number of samples (n)", fontsize=11)
        ax.set_ylabel("TVD (log scale)", fontsize=11)
        ax.set_title(method_title, fontsize=11)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "tvd_vs_n_context.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ============================================================
# console summary
# ============================================================

def print_summary(results):
    print("\n" + "=" * 85)
    print(f"n* — smallest n where median TVD ≤ {TVD_TARGET}")
    print("=" * 85)
    print(f"{'Distribution':<15}  {'n*_KDE':>10}  {'n*_PMF':>10}")
    print("-" * 40)
    for dist_name, dist_config in DISTRIBUTIONS.items():
        r = results[dist_name]
        k = find_n_star(r["tvd_kde"])
        p = find_n_star(r["tvd_pmf"])
        print(f"{dist_config['label']:<15}  "
              f"{(str(k)+','  if k else '>20k'):>10}  "
              f"{(str(p)+','  if p else '>20k'):>10}")

    print("\n" + "=" * 85)
    print(f"Pass rate at n* — fraction of seeds with p > {ALPHA} at n*_KDE")
    print("=" * 85)
    for dist_name, dist_config in DISTRIBUTIONS.items():
        r   = results[dist_name]
        n   = find_n_star(r["tvd_kde"])
        if n is None:
            print(f"{dist_config['label']}: n* not reached")
            continue
        p_ks1  = np.mean(np.array(r["ks1_p"][n])  > ALPHA) * 100
        p_ks2  = np.mean(np.array(r["ks2_p"][n])  > ALPHA) * 100
        p_chi  = np.mean([v for v in r["chi_p"][n] if not np.isnan(v)] > np.array(ALPHA)) * 100
        p_ad   = np.mean([v for v in r["ad_p"][n]  if not np.isnan(v)] > np.array(ALPHA)) * 100
        print(f"{dist_config['label']:<15}  n*={n:>6,}  "
              f"KS1={p_ks1:.0f}%  KS2={p_ks2:.0f}%  "
              f"χ²={p_chi:.0f}%  AD={p_ad:.0f}%")


# ============================================================
# main
# ============================================================

if __name__ == "__main__":
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR)

    print("KS test p-value evolution — TVD = 0.05 threshold")
    print(f"  Distributions : {list(DISTRIBUTIONS.keys())}")
    print(f"  Sample sizes  : {SAMPLE_SIZES}")
    print(f"  Seeds         : {len(SEEDS)}")
    print(f"  Alpha         : {ALPHA}")
    print(f"  TVD target    : {TVD_TARGET}")
    print(f"  N_ref         : {N_REF:,}")
    print()

    results = run_experiments()
    print_summary(results)

    print("\nGenerating plots ...")
    plot_tvd_vs_n(results)
    plot_ks_statistic(results)
    plot_pvalue_per_dist(results)
    plot_pass_rate(results)

    print("\nDone.")
