"""
Summarise all sample-complexity experiment results into a single JSON file.

For each experiment (mode x domain x distribution x n x seed), computes TVD
and the KS statistic, then writes a compact summary that can be fed to an
external validator to sanity-check the results.

Output: delay-monitoring/results/summary.json

Usage (from network-monitoring/ repo root):
    delay-monitoring/analysis/venv/bin/python \
        delay-monitoring/analysis/summarise_results.py
"""

import json
import math
import os
import numpy as np
import pandas as pd
from scipy import stats

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
RESULTS_ROOT = os.path.join(SCRIPT_DIR, "../results/sample-complexity")
OUTPUT_PATH  = os.path.join(SCRIPT_DIR, "../results/summary.json")

# ---------------------------------------------------------------------------
# shared parameters
# ---------------------------------------------------------------------------

EPSILON  = 0.05
DELTA    = 0.05
SEEDS    = list(range(1, 101))

# Discrete bins / bin parameters
BIN_SIZE = 1.0
BIN_MAX  = 150.0
N_BINS   = int(BIN_MAX / BIN_SIZE)
BIN_EDGES = np.linspace(0.0, BIN_MAX, N_BINS + 1)

# ---------------------------------------------------------------------------
# experiment definitions
# ---------------------------------------------------------------------------

DISCRETE_DISTS = {
    "binomial": {
        "label":        "Binomial(N=20, p=0.5)",
        "support":      np.arange(0, 21),
        "support_str":  "{0, 1, ..., 20}",
        "k":            21,
        "params":       {"N": 20, "p": 0.5},
        "mean":         10.0,
        "variance":     5.0,
        "true_pmf":     lambda s: stats.binom.pmf(s, n=20, p=0.5),
        "true_pmf_values": {int(k): round(float(stats.binom.pmf(k, n=20, p=0.5)), 6)
                            for k in range(21)},
        "n_theory":     9599,
        "epsilon":      0.05,
        "delta":        0.05,
        "sample_sizes": [480, 960, 2400, 4800, 9599, 19197, 38393],
        "size_labels":  ["n/20", "n/10", "n/4", "n/2", "n", "2n", "4n"],
    },
    "zipf": {
        "label":        "Zipf(N=20, alpha=1.5)",
        "support":      np.arange(1, 21),
        "support_str":  "{1, 2, ..., 20}",
        "k":            20,
        "params":       {"N": 20, "alpha": 1.5},
        "true_pmf":     lambda s: stats.zipfian.pmf(s, a=1.5, n=20),
        "true_pmf_values": {int(k): round(float(stats.zipfian.pmf(k, a=1.5, n=20)), 6)
                            for k in range(1, 21)},
        "n_theory":     9199,
        "epsilon":      0.05,
        "delta":        0.05,
        "sample_sizes": [460, 920, 2300, 4599, 9199, 18397, 36793],
        "size_labels":  ["n/20", "n/10", "n/4", "n/2", "n", "2n", "4n"],
    },
    "piecewise": {
        "label":        "Piecewise (irregular multi-modal)",
        "support":      np.arange(1, 21),
        "support_str":  "{1, 2, ..., 20}",
        "k":            20,
        "params":       {},
        "true_pmf_values": {k+1: round(float(p), 6) for k, p in enumerate(
                            [0.12, 0.02, 0.08, 0.01, 0.10, 0.03, 0.07, 0.12, 0.02, 0.09,
                             0.01, 0.08, 0.04, 0.06, 0.02, 0.05, 0.02, 0.04, 0.01, 0.01])},
        "true_pmf":     lambda s: np.array([
                            0.12, 0.02, 0.08, 0.01, 0.10, 0.03, 0.07, 0.12, 0.02, 0.09,
                            0.01, 0.08, 0.04, 0.06, 0.02, 0.05, 0.02, 0.04, 0.01, 0.01
                        ]),
        "n_theory":     9199,
        "epsilon":      0.05,
        "delta":        0.05,
        "sample_sizes": [460, 920, 2300, 4599, 9199, 18397, 36793],
        "size_labels":  ["n/20", "n/10", "n/4", "n/2", "n", "2n", "4n"],
    },
}

CONTINUOUS_DISTS = {
    "lognormal": {
        "label":        "Lognormal(mu=2.3, sigma=0.2)",
        "params":       {"mu": 2.3, "sigma": 0.2},
        "mean_ms":      round(math.exp(2.3 + 0.5 * 0.2**2), 4),
        "scipy":        stats.lognorm(s=0.2, scale=math.exp(2.3)),
        "binning":      {"bin_size_ms": 1.0, "bin_max_ms": 150.0, "n_bins": 150},
        "n_theory":     61199,
        "epsilon":      0.05,
        "delta":        0.05,
        "sample_sizes": [3060, 6120, 15299, 30599, 61199, 122398, 244796],
        "size_labels":  ["n/20", "n/10", "n/4", "n/2", "n", "2n", "4n"],
    },
    "normal": {
        "label":        "Normal(mean=40, var=4)",
        "params":       {"mean": 40.0, "variance": 4.0, "std": 2.0},
        "mean_ms":      40.0,
        "scipy":        stats.norm(loc=40.0, scale=2.0),
        "binning":      {"bin_size_ms": 1.0, "bin_max_ms": 150.0, "n_bins": 150},
        "n_theory":     61199,
        "epsilon":      0.05,
        "delta":        0.05,
        "sample_sizes": [3060, 6120, 15299, 30599, 61199, 122398, 244796],
        "size_labels":  ["n/20", "n/10", "n/4", "n/2", "n", "2n", "4n"],
    },
    "weibull": {
        "label":        "Weibull(scale=10, shape=2)",
        "params":       {"scale": 10.0, "shape": 2.0},
        "mean_ms":      round(10.0 * math.gamma(1 + 1/2), 4),
        "scipy":        stats.weibull_min(c=2.0, scale=10.0),
        "binning":      {"bin_size_ms": 1.0, "bin_max_ms": 150.0, "n_bins": 150},
        "n_theory":     61199,
        "epsilon":      0.05,
        "delta":        0.05,
        "sample_sizes": [3060, 6120, 15299, 30599, 61199, 122398, 244796],
        "size_labels":  ["n/20", "n/10", "n/4", "n/2", "n", "2n", "4n"],
    },
}

# (mode, domain) -> results subdirectory
EXPERIMENTS = [
    ("theoretical", "discrete",   "discrete/theoretical/single_seed",  False),
    ("theoretical", "discrete",   "discrete/theoretical/seeded",        True),
    ("realistic",   "discrete",   "discrete/realistic/single_seed",     False),
    ("realistic",   "discrete",   "discrete/realistic/seeded",          True),
    ("realistic",   "continuous", "continuous/realistic/single_seed",   False),
    ("realistic",   "continuous", "continuous/realistic/seeded",        True),
]


# ---------------------------------------------------------------------------
# metric helpers
# ---------------------------------------------------------------------------

def discrete_tvd(samples, dist_cfg):
    support       = dist_cfg["support"]
    true_pmf_vals = dist_cfg["true_pmf"](support)
    counts = np.zeros(len(support))
    lo, hi = support[0], support[-1]
    for val in samples:
        if lo <= val <= hi:
            counts[val - lo] += 1
    total = counts.sum()
    emp = counts / total if total > 0 else counts
    return 0.5 * float(np.sum(np.abs(emp - true_pmf_vals)))


def continuous_tvd(samples, dist_cfg):
    cdf_vals = dist_cfg["scipy"].cdf(BIN_EDGES)
    true_probs = np.diff(cdf_vals)
    if true_probs.sum() > 0:
        true_probs = true_probs / true_probs.sum()
    counts, _ = np.histogram(samples, bins=BIN_EDGES)
    total = counts.sum()
    emp = counts / total if total > 0 else counts.astype(float)
    return 0.5 * float(np.sum(np.abs(emp - true_probs)))


def continuous_ks(samples, dist_cfg):
    return stats.kstest(samples, dist_cfg["scipy"].cdf).statistic


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def summarise():
    summary = {}

    for mode, domain, rel_path, seeded in EXPERIMENTS:
        results_dir = os.path.join(RESULTS_ROOT, rel_path)
        if not os.path.isdir(results_dir):
            print(f"  skip (no directory): {results_dir}")
            continue

        dists  = DISCRETE_DISTS if domain == "discrete" else CONTINUOUS_DISTS
        tvd_fn = discrete_tvd  if domain == "discrete" else continuous_tvd
        ks_fn  = None          if domain == "discrete" else continuous_ks

        for dist_name, dist_cfg in dists.items():
            key = f"{mode}__{domain}__{dist_name}"
            if key not in summary:
                dist_info = {
                    "label":        dist_cfg.get("label", dist_name),
                    "params":       dist_cfg.get("params", {}),
                    "n_theory":     dist_cfg["n_theory"],
                    "epsilon":      dist_cfg["epsilon"],
                    "delta":        dist_cfg["delta"],
                    "sample_sizes": dist_cfg["sample_sizes"],
                    "size_labels":  dist_cfg["size_labels"],
                }
                if domain == "discrete":
                    dist_info["support"]         = dist_cfg["support_str"]
                    dist_info["k"]               = dist_cfg["k"]
                    dist_info["true_pmf_values"] = dist_cfg["true_pmf_values"]
                else:
                    dist_info["binning"]  = dist_cfg["binning"]
                    dist_info["mean_ms"]  = dist_cfg["mean_ms"]

                summary[key] = {
                    "mode":        mode,
                    "domain":      domain,
                    "dist":        dist_name,
                    "dist_info":   dist_info,
                    "by_n":        {},
                }

            for n in dist_cfg["sample_sizes"]:
                if seeded:
                    tvd_vals = []
                    ks_vals  = []
                    for seed in SEEDS:
                        path = os.path.join(results_dir, f"delay_samples_{dist_name}_{n}_seed{seed}.csv")
                        if not os.path.isfile(path):
                            break
                        raw     = pd.read_csv(path)["delay_ms"].values
                        samples = np.round(raw).astype(int) if domain == "discrete" else raw
                        tvd_vals.append(tvd_fn(samples, dist_cfg))
                        if ks_fn is not None:
                            ks_vals.append(ks_fn(samples, dist_cfg))
                    if not tvd_vals:
                        continue
                    entry = {
                        "seeds":      len(tvd_vals),
                        "tvd_median": round(float(np.median(tvd_vals)), 6),
                        "tvd_mean":   round(float(np.mean(tvd_vals)), 6),
                        "tvd_min":    round(float(np.min(tvd_vals)), 6),
                        "tvd_max":    round(float(np.max(tvd_vals)), 6),
                    }
                    if ks_vals:
                        entry.update({
                            "ks_median": round(float(np.median(ks_vals)), 6),
                            "ks_mean":   round(float(np.mean(ks_vals)), 6),
                            "ks_min":    round(float(np.min(ks_vals)), 6),
                            "ks_max":    round(float(np.max(ks_vals)), 6),
                        })
                else:
                    path = os.path.join(results_dir, f"delay_samples_{dist_name}_{n}.csv")
                    if not os.path.isfile(path):
                        continue
                    raw     = pd.read_csv(path)["delay_ms"].values
                    samples = np.round(raw).astype(int) if domain == "discrete" else raw
                    entry = {
                        "seeds": 1,
                        "tvd":   round(float(tvd_fn(samples, dist_cfg)), 6),
                    }
                    if ks_fn is not None:
                        entry["ks"] = round(float(ks_fn(samples, dist_cfg)), 6)

                n_str = str(n)
                if n_str not in summary[key]["by_n"]:
                    summary[key]["by_n"][n_str] = {}

                sub_key = "seeded" if seeded else "single_seed"
                summary[key]["by_n"][n_str][sub_key] = entry

            print(f"  done: {key}  (seeded={seeded})")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary written to: {OUTPUT_PATH}")
    print(f"Total experiment keys: {len(summary)}")


if __name__ == "__main__":
    summarise()
