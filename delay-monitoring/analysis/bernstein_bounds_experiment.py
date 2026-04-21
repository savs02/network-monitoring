"""
Bernstein bounds experiment.

Compares three sample complexity bounds for TVD estimation:

  1. Hoeffding (current bound in the codebase):
       n_hoeff(δ) = K · ln(1/ε) / δ²
     This is the worst-case concentration bound, treating each bin as if
     its variance is 1/4 (the maximum for a Bernoulli variable).

  2. Bernstein — oracle:
       Uses the true PMF to compute σ²_max = max_j p_j(1 - p_j), the
       maximum per-bin Bernoulli variance.  The Hoeffding bound implicitly
       assumes worst-case variance 1/4 for every bin; Bernstein replaces
       this with the actual σ²_max.
       n_bern_oracle(δ) = (4 · σ²_max) · n_hoeff(δ)
     Since σ²_max ≤ 1/4 always, this is always at least as good as
     Hoeffding.  For concentrated distributions σ²_max << 1/4 gives a
     genuine reduction.

  3. Bernstein — empirical (adaptive):
       Uses n_pilot = 300 samples to estimate σ²_max from the data, then
       applies the same formula.  This is the practical version that does
       not need the true distribution.
       n_bern_emp(δ) = (4 · σ̂²_max) · n_hoeff(δ)

  4. Empirical requirement (from running experiments):
       Smallest n such that the median TVD over 100 seeds falls below δ.

Derivation note:
  The Hoeffding-based code bound n_hoeff = K · ln(1/ε) / δ² treats each
  of the K bins as if the per-bin estimator has worst-case Bernoulli
  variance 1/4.  Replacing 1/4 with the actual σ²_max gives the Bernstein
  correction factor of (4 · σ²_max).

  Important caveat: a naive union-bound-per-bin Bernstein derivation
  would use t = 2δ/K per bin (the per-bin error budget), which gives a
  formula with K² in the numerator and is strictly WORSE than the
  code's bound for large K.  That formula is therefore NOT used here.
  The comparison n_bern = (4 · σ²_max) · n_hoeff is the correct
  apples-to-apples Bernstein correction of the existing bound.

Plots:
  bound_comparison_*.png  — four curves (Hoeffding, Bernstein oracle, Bernstein
                            empirical, empirical requirement) vs δ, per distribution
  improvement_ratio_*.png — ratio n_hoeff / n_bern and n_hoeff / n_empirical vs δ
  sigma_profile_*.png     — per-bin variance profile of each distribution
  summary_bar_*.png       — bar chart at δ=0.05 comparing all four bounds
"""

import math, os
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/bernstein-bounds")

# ── parameters ────────────────────────────────────────────────────────────────

EPSILON  = 0.05
N_PILOT  = 300       # samples used to estimate σ²_max in the empirical Bernstein
N_SEEDS  = 100       # seeds for empirical requirement and pilot estimation
DELTAS   = np.array([0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10])
DELTA_MAIN = 0.05    # reference delta for bar charts and profiles

GRID_MAX  = 150.0
BIN_WIDTH = 1.0
GRID      = np.arange(BIN_WIDTH / 2, GRID_MAX, BIN_WIDTH)
K         = len(GRID)

SAMPLE_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000,
                7500, 10000, 15000, 20000, 30000, 50000]

CONTINUOUS_DISTS = {
    "normal":    {"label": "Normal(40, 4)",       "params": {"mean": 40.0, "variance": 4.0}, "color": "#3498db"},
    "lognormal": {"label": "Lognormal(2.3, 0.2)", "params": {"mu": 2.3, "sigma": 0.2},       "color": "#e74c3c"},
    "weibull":   {"label": "Weibull(10, 2)",       "params": {"scale": 10.0, "shape": 2.0},   "color": "#2ecc71"},
}

DISCRETE_DISTS = {
    "binomial": {
        "label": "Binomial(N=20, p=0.5)", "color": "#9b59b6",
        "support": np.arange(0, 21), "k": 21,
        "true_pmf": stats.binom.pmf(np.arange(0, 21), n=20, p=0.5),
    },
    "zipf": {
        "label": "Zipf(N=20, α=1.5)", "color": "#e67e22",
        "support": np.arange(1, 21), "k": 20,
        "true_pmf": stats.zipfian.pmf(np.arange(1, 21), a=1.5, n=20),
    },
    "piecewise": {
        "label": "Piecewise (multi-modal)", "color": "#27ae60",
        "support": np.arange(1, 21), "k": 20,
        "true_pmf": np.array([
            0.12, 0.02, 0.08, 0.01, 0.10, 0.03, 0.07, 0.12, 0.02, 0.09,
            0.01, 0.08, 0.04, 0.06, 0.02, 0.05, 0.02, 0.04, 0.01, 0.01,
        ]),
    },
}

# ── helpers ───────────────────────────────────────────────────────────────────

def tvd(p, q):
    return 0.5 * np.sum(np.abs(p - q))

def _to_masses(pdf_values):
    m = pdf_values * BIN_WIDTH
    return m / m.sum()

def true_cont_pmf(dist_name, params):
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
        return rng.normal(params["mean"], np.sqrt(params["variance"]), n)
    elif dist_name == "lognormal":
        return rng.lognormal(params["mu"], params["sigma"], n)
    elif dist_name == "weibull":
        return params["scale"] * rng.weibull(params["shape"], n)
    raise ValueError(dist_name)

def kde_masses(samples):
    kde = stats.gaussian_kde(samples, bw_method="scott")
    m   = kde(GRID) * BIN_WIDTH
    return m / m.sum()

def empirical_pmf(samples, support):
    counts = np.array([(samples == v).sum() for v in support], dtype=float)
    s = counts.sum()
    return counts / s if s > 0 else np.ones(len(support)) / len(support)

# ── bound calculations ────────────────────────────────────────────────────────

def n_hoeffding(delta, k=K):
    """Hoeffding-based bound: n = K * ln(1/eps) / delta^2."""
    return math.ceil(k * math.log(1.0 / EPSILON) / delta ** 2)

def bernstein_n_approx(delta, sigma2_max, k=K):
    """
    Bernstein correction to the Hoeffding bound:
      n_bern = 4 * sigma2_max * n_hoeff(delta, k)
    The factor 4*sigma2_max replaces the implicit worst-case variance assumption
    (1/4) in the Hoeffding bound, giving a reduction of 1/(4*sigma2_max).
    """
    return math.ceil(4 * sigma2_max * n_hoeffding(delta, k))

def sigma2_max_from_pmf(pmf):
    """Per-bin Bernoulli variance; return max and profile."""
    variances = pmf * (1 - pmf)
    return float(np.max(variances)), variances

def sigma2_max_empirical(dist_name, params_or_cfg, n_pilot, seed, is_continuous):
    """Estimate sigma2_max from n_pilot samples (the adaptive Bernstein approach)."""
    rng = np.random.default_rng(seed)
    if is_continuous:
        samples = sample_continuous(dist_name, params_or_cfg, n_pilot, rng)
        est_pmf = kde_masses(samples)
    else:
        support = params_or_cfg["support"]
        true_m  = params_or_cfg["true_pmf"]
        samples = rng.choice(support, size=n_pilot, p=true_m)
        est_pmf = empirical_pmf(samples, support)
    _, variances = sigma2_max_from_pmf(est_pmf)
    return float(np.max(variances))

# ── empirical requirement ─────────────────────────────────────────────────────

def empirical_requirement(dist_name, params_or_cfg, delta, is_continuous):
    """
    Smallest n in SAMPLE_SIZES such that median TVD over N_SEEDS seeds <= delta.
    Returns None if not achieved within SAMPLE_SIZES.
    """
    if is_continuous:
        true_m = true_cont_pmf(dist_name, params_or_cfg)
    else:
        true_m  = params_or_cfg["true_pmf"]
        support = params_or_cfg["support"]

    for n in SAMPLE_SIZES:
        tvds = []
        for seed in range(N_SEEDS):
            rng = np.random.default_rng(seed)
            if is_continuous:
                samples = sample_continuous(dist_name, params_or_cfg, n, rng)
                est     = kde_masses(samples)
            else:
                samples = rng.choice(support, size=n, p=true_m)
                est     = empirical_pmf(samples, support)
            tvds.append(tvd(est, true_m))
        if np.median(tvds) <= delta:
            return n
    return SAMPLE_SIZES[-1]   # cap


# ── pilot σ²_max estimation ───────────────────────────────────────────────────

def mean_empirical_sigma2(dist_name, params_or_cfg, is_continuous):
    """Average σ²_max over N_SEEDS pilot estimates."""
    estimates = [
        sigma2_max_empirical(dist_name, params_or_cfg, N_PILOT, seed, is_continuous)
        for seed in range(N_SEEDS)
    ]
    return float(np.mean(estimates)), float(np.std(estimates))


# ── plotting ──────────────────────────────────────────────────────────────────

def plot_bound_comparison(dist_name, label, color, sigma2_true, sigma2_emp_mean,
                          emp_reqs, is_continuous, suffix):
    """
    Four curves vs delta:
      - Hoeffding
      - Bernstein oracle (true σ²_max)
      - Bernstein pilot (estimated σ²_max from n_pilot samples)
      - Empirical requirement (dots)
    """
    k = K if is_continuous else (21 if dist_name == "binomial" else 20)

    n_hoeff    = [n_hoeffding(d, k)                      for d in DELTAS]
    n_b_oracle = [bernstein_n_approx(d, sigma2_true)     for d in DELTAS]
    n_b_pilot  = [bernstein_n_approx(d, sigma2_emp_mean) for d in DELTAS]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # left: absolute sample sizes
    ax = axes[0]
    ax.semilogy(DELTAS, n_hoeff,    "k-",  linewidth=2,   label="Hoeffding (current bound)")
    ax.semilogy(DELTAS, n_b_oracle, "b--", linewidth=1.8,
                label=f"Bernstein oracle (σ²_max={sigma2_true:.4f})")
    ax.semilogy(DELTAS, n_b_pilot,  "c--", linewidth=1.5,
                label=f"Bernstein pilot (σ̂²_max≈{sigma2_emp_mean:.4f}, n_pilot={N_PILOT})")
    ax.scatter(DELTAS, emp_reqs, color="red", s=50, zorder=5,
               label="Empirical requirement (median ≤ δ)")
    ax.axvline(DELTA_MAIN, color="grey", linestyle=":", linewidth=1.0)
    ax.set_xlabel("TVD target δ"); ax.set_ylabel("Sample size n")
    ax.set_title("Sample size bounds vs δ")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3, which="both")

    # right: improvement ratio over Hoeffding
    ratio_boracle = np.array(n_hoeff) / np.array(n_b_oracle)
    ratio_bpilot  = np.array(n_hoeff) / np.array(n_b_pilot)
    ratio_emp     = np.array(n_hoeff) / np.array(emp_reqs)

    ax2 = axes[1]
    ax2.plot(DELTAS, ratio_boracle, "b--", linewidth=1.8, label="Hoeff / Bernstein oracle")
    ax2.plot(DELTAS, ratio_bpilot,  "c--", linewidth=1.5, label="Hoeff / Bernstein pilot")
    ax2.scatter(DELTAS, ratio_emp, color="red", s=50, zorder=5, label="Hoeff / Empirical req")
    ax2.axhline(1, color="grey", linestyle=":", linewidth=1.0, label="Ratio = 1")
    ax2.set_xlabel("TVD target δ"); ax2.set_ylabel("Improvement ratio")
    ax2.set_title("How much tighter is each bound over Hoeffding?")
    ax2.legend(fontsize=8); ax2.grid(True, alpha=0.3)

    fig.suptitle(f"{label} — bound comparison\n"
                 f"K={k}, ε={EPSILON}, σ²_max(true)={sigma2_true:.4f}", fontsize=11, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"bound_comparison_{suffix}_{dist_name}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  Saved: {path}")


def plot_sigma_profile(dist_name, label, true_pmf, variances, is_continuous, suffix):
    """Bar chart of per-bin variance σ²_j = p_j(1 - p_j) across bins."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    if is_continuous:
        x = GRID
        axes[0].bar(x, true_pmf, width=BIN_WIDTH * 0.9, color="#3498db", alpha=0.7)
        axes[0].set_xlabel("Delay (ms)")
    else:
        x = np.arange(len(true_pmf))
        axes[0].bar(x, true_pmf, color="#3498db", alpha=0.7)
        axes[0].set_xlabel("Outcome index")
    axes[0].set_ylabel("Probability mass")
    axes[0].set_title("True PMF")
    axes[0].grid(True, alpha=0.3, axis="y")

    worstcase = 0.25 * np.ones_like(variances)
    if is_continuous:
        axes[1].bar(x, variances, width=BIN_WIDTH * 0.9, color="#e74c3c", alpha=0.7,
                    label="Bernstein σ²_j = p_j(1-p_j)")
        axes[1].axhline(0.25, color="black", linestyle="--", linewidth=1.2,
                        label="Hoeffding worst-case σ² = 0.25")
        axes[1].set_xlabel("Delay (ms)")
    else:
        axes[1].bar(x, variances, color="#e74c3c", alpha=0.7,
                    label="Bernstein σ²_j")
        axes[1].axhline(0.25, color="black", linestyle="--", linewidth=1.2,
                        label="Hoeffding worst-case = 0.25")
        axes[1].set_xlabel("Outcome index")
    axes[1].set_ylabel("Bin variance σ²_j")
    axes[1].set_title(f"Per-bin variance  (max = {np.max(variances):.4f}, "
                      f"Hoeffding assumes 0.25)")
    axes[1].legend(fontsize=9); axes[1].grid(True, alpha=0.3, axis="y")

    fig.suptitle(f"{label} — bin variance profile", fontsize=11, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"sigma_profile_{suffix}_{dist_name}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  Saved: {path}")


def plot_summary_bar(all_info, suffix):
    """
    Bar chart at delta=DELTA_MAIN: four bounds side by side per distribution.
    """
    dists  = [d["name"]  for d in all_info]
    labels = [d["label"] for d in all_info]

    n_hoeff    = [d["n_hoeff_main"]    for d in all_info]
    n_boracle  = [d["n_boracle_main"]  for d in all_info]
    n_bpilot   = [d["n_bpilot_main"]  for d in all_info]
    n_emp_req  = [d["n_emp_req_main"]  for d in all_info]

    x   = np.arange(len(dists))
    w   = 0.18
    fig, ax = plt.subplots(figsize=(max(10, 3 * len(dists)), 6))

    ax.bar(x - 1.5*w, n_hoeff,   width=w, color="#2c3e50", alpha=0.85, label="Hoeffding")
    ax.bar(x - 0.5*w, n_boracle, width=w, color="#2980b9", alpha=0.85, label="Bernstein oracle (true σ²)")
    ax.bar(x + 0.5*w, n_bpilot,  width=w, color="#3498db", alpha=0.70, label=f"Bernstein pilot ({N_PILOT} samples)")
    ax.bar(x + 1.5*w, n_emp_req, width=w, color="#e74c3c", alpha=0.85, label="Empirical requirement")

    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Sample size n"); ax.set_yscale("log")
    ax.set_title(f"Sample complexity comparison at δ={DELTA_MAIN}, ε={EPSILON}\n"
                 f"How much does Bernstein improve over Hoeffding, and does it close the gap?",
                 fontsize=11)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3, axis="y", which="both")

    # annotate improvement ratios
    for i, d in enumerate(all_info):
        ratio_b = d["n_hoeff_main"] / d["n_boracle_main"]
        ratio_e = d["n_hoeff_main"] / d["n_emp_req_main"]
        ax.text(i - 0.5*w, d["n_boracle_main"] * 1.3, f"{ratio_b:.1f}×",
                ha="center", va="bottom", fontsize=8, color="#2980b9")
        ax.text(i + 1.5*w, d["n_emp_req_main"] * 1.3, f"{ratio_e:.0f}×",
                ha="center", va="bottom", fontsize=8, color="#e74c3c")

    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"summary_bar_{suffix}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  Saved: {path}")


def plot_gap_analysis(all_info, suffix):
    """
    For each distribution: Bernstein improvement (Hoeff/Bern) and empirical improvement
    (Hoeff/Emp) across delta values.  Shows that Bernstein narrows the gap but not fully.
    """
    nd = len(all_info)
    fig, axes = plt.subplots(1, nd, figsize=(5 * nd, 5), sharey=True)
    if nd == 1: axes = [axes]

    for ax, d in zip(axes, all_info):
        ax.plot(DELTAS, d["ratio_boracle"], "b--", linewidth=2,   label="Hoeff / Bernstein oracle")
        ax.plot(DELTAS, d["ratio_bpilot"],  "c--", linewidth=1.5, label="Hoeff / Bernstein pilot")
        ax.scatter(DELTAS, d["ratio_emp"], color="red", s=60, zorder=5,
                   label="Hoeff / Empirical req")
        ax.fill_between(DELTAS, d["ratio_boracle"], d["ratio_emp"],
                        alpha=0.1, color="red", label="Gap Bernstein cannot explain")
        ax.set_xlabel("TVD target δ"); ax.set_title(d["label"])
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
        ax.axhline(1, color="grey", linestyle=":", linewidth=0.8)

    axes[0].set_ylabel("Improvement ratio over Hoeffding")
    fig.suptitle(f"Residual gap after Bernstein correction — {suffix}\n"
                 f"Shaded region is the gap that Bernstein leaves unexplained",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, f"gap_analysis_{suffix}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  Saved: {path}")


# ── run ───────────────────────────────────────────────────────────────────────

def run_for_dist_set(dist_dict, is_continuous, suffix):
    all_info = []
    k_default = K if is_continuous else None

    for dist_name, cfg in dist_dict.items():
        params_or_cfg = cfg["params"] if is_continuous else cfg
        k = K if is_continuous else cfg["k"]
        print(f"\n  {cfg['label']}")

        # true PMF and variance profile
        if is_continuous:
            true_pmf = true_cont_pmf(dist_name, cfg["params"])
        else:
            true_pmf = cfg["true_pmf"]
        sigma2_max_true, variances = sigma2_max_from_pmf(true_pmf)
        print(f"    σ²_max (oracle) = {sigma2_max_true:.5f}  "
              f"(Hoeffding assumes 0.25, Bernstein improvement ≈ {1/(4*sigma2_max_true):.1f}×)")

        # empirical sigma2 estimate
        sigma2_emp_mean, sigma2_emp_std = mean_empirical_sigma2(dist_name, params_or_cfg, is_continuous)
        print(f"    σ²_max (pilot, {N_PILOT} samples) = {sigma2_emp_mean:.5f} ± {sigma2_emp_std:.5f}")

        # per-delta analysis
        emp_reqs       = []
        ratio_boracle  = []
        ratio_bpilot   = []
        ratio_emp_list = []

        for delta in DELTAS:
            nh  = n_hoeffding(delta, k)
            nbo = bernstein_n_approx(delta, sigma2_max_true, k)
            nbp = bernstein_n_approx(delta, sigma2_emp_mean, k)
            er  = empirical_requirement(dist_name, params_or_cfg, delta, is_continuous)
            emp_reqs.append(er)
            ratio_boracle.append(nh / nbo)
            ratio_bpilot.append(nh / nbp)
            ratio_emp_list.append(nh / er)
            print(f"    δ={delta:.3f}  n_hoeff={nh:>7,}  n_bern_oracle={nbo:>7,}  "
                  f"n_emp_req={er:>7,}  ratio_bern={nh/nbo:.2f}×  ratio_emp={nh/er:.0f}×")

        # values at DELTA_MAIN
        idx_main    = list(DELTAS).index(DELTA_MAIN)
        nh_main      = n_hoeffding(DELTA_MAIN, k)
        nbo_main     = bernstein_n_approx(DELTA_MAIN, sigma2_max_true, k)
        nbpilot_main = bernstein_n_approx(DELTA_MAIN, sigma2_emp_mean, k)

        all_info.append({
            "name":           dist_name,
            "label":          cfg["label"],
            "sigma2_true":    sigma2_max_true,
            "sigma2_emp":     sigma2_emp_mean,
            "true_pmf":       true_pmf,
            "variances":      variances,
            "emp_reqs":       emp_reqs,
            "ratio_boracle":  ratio_boracle,
            "ratio_bpilot":   ratio_bpilot,
            "ratio_emp":      ratio_emp_list,
            "n_hoeff_main":   nh_main,
            "n_boracle_main": nbo_main,
            "n_bpilot_main":  nbpilot_main,
            "n_emp_req_main": emp_reqs[idx_main],
        })

        plot_bound_comparison(dist_name, cfg["label"], cfg["color"],
                              sigma2_max_true, sigma2_emp_mean, emp_reqs,
                              is_continuous, suffix)
        plot_sigma_profile(dist_name, cfg["label"], true_pmf, variances,
                           is_continuous, suffix)

    # summary plots across all distributions
    plot_summary_bar(all_info, suffix)
    plot_gap_analysis(all_info, suffix)
    return all_info


if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Bernstein bounds experiment")
    print(f"  ε={EPSILON}  δ sweep={list(DELTAS)}  pilot n={N_PILOT}  seeds={N_SEEDS}")
    print(f"  K (continuous grid) = {K}")
    print()

    print("── Continuous ─────────────────────────────────────────────────────")
    run_for_dist_set(CONTINUOUS_DISTS, is_continuous=True, suffix="cont")

    print("\n── Discrete ───────────────────────────────────────────────────────")
    run_for_dist_set(DISCRETE_DISTS, is_continuous=False, suffix="disc")

    print("\nDone. Results in:", RESULTS_DIR)
