"""
Plot empirical delay distributions from NS-3 simulation samples.

One subplot per distribution (normal, lognormal, weibull), each showing:
  - histogram of sampled delays
  - KDE estimate (what the monitor produces — no knowledge of underlying family)
  - theoretical PDF (ground truth, for comparison only)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import os

RESULTS_DIR = "../results"
OUTPUT_FILE = "../results/delay_distributions.png"

# distribution configurations matching the NS-3 simulation defaults
DISTRIBUTIONS = [
    {
        "name": "normal",
        "label": "Normal",
        "params": {"mean": 40.0, "variance": 4.0},
        "color": "#3498db",
    },
    {
        "name": "lognormal",
        "label": "Lognormal",
        "params": {"mu": 2.3, "sigma": 0.2},
        "color": "#e74c3c",
    },
    {
        "name": "weibull",
        "label": "Weibull",
        "params": {"scale": 10.0, "shape": 2.0},
        "color": "#2ecc71",
    },
]


def load_samples(dist_name):
    filepath = os.path.join(RESULTS_DIR, f"delay_samples_{dist_name}.csv")
    df = pd.read_csv(filepath)
    return df["delay_ms"].values


def theoretical_pdf(dist_config, x):
    name = dist_config["name"]
    p = dist_config["params"]

    if name == "normal":
        return stats.norm.pdf(x, loc=p["mean"], scale=np.sqrt(p["variance"]))

    elif name == "lognormal":
        # scipy lognorm: shape=sigma, scale=exp(mu)
        return stats.lognorm.pdf(x, s=p["sigma"], scale=np.exp(p["mu"]))

    elif name == "weibull":
        # scipy weibull_min: c=shape, scale=scale
        return stats.weibull_min.pdf(x, c=p["shape"], scale=p["scale"])

    return np.zeros_like(x)


def param_label(dist_config):
    name = dist_config["name"]
    p = dist_config["params"]

    if name == "normal":
        return f"mean={p['mean']}, variance={p['variance']}"
    elif name == "lognormal":
        return f"mu={p['mu']}, sigma={p['sigma']}"
    elif name == "weibull":
        return f"scale={p['scale']}, shape={p['shape']}"
    return ""


def plot_all(distributions):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Delay samples, KDE estimate, and theoretical PDF", fontsize=13)

    for ax, dist_config in zip(axes, distributions):
        samples = load_samples(dist_config["name"])
        color = dist_config["color"]

        # x range with a small margin so the curves don't get clipped at the edges
        margin = (samples.max() - samples.min()) * 0.05
        x = np.linspace(samples.min() - margin, samples.max() + margin, 500)

        # histogram of raw samples (normalised to density)
        ax.hist(
            samples,
            bins=40,
            density=True,
            alpha=0.4,
            color=color,
            edgecolor="white",
            label=f"Samples (n={len(samples)})",
        )

        # KDE estimate — distribution-agnostic, bandwidth chosen by Scott's rule
        kde = stats.gaussian_kde(samples, bw_method="scott")
        ax.plot(x, kde(x), color=color, linewidth=2.0, label="KDE estimate")

        # theoretical PDF — ground truth for comparison only, not available to the monitor
        pdf = theoretical_pdf(dist_config, x)
        ax.plot(x, pdf, color="black", linewidth=1.8, linestyle="--", label="Theoretical PDF")

        ax.set_title(f"{dist_config['label']}\n{param_label(dist_config)}", fontsize=10)
        ax.set_xlabel("Delay (ms)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_FILE, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUTPUT_FILE}")
    plt.close()


if __name__ == "__main__":
    plot_all(DISTRIBUTIONS)
