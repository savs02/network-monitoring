"""
Bin resolution experiment — theoretical sample complexity.

Investigates how the number of histogram bins k (controlled by bin size)
affects the theoretical sample requirement n_theory, and how n_theory and
the accuracy target delta are coupled.

Discrete PMF bound:   n = ceil((k + log(1/epsilon)) / delta^2)
Continuous KDE bound: n = ceil(K * log(1/epsilon) / delta^2)

A finer bin size increases k linearly, which increases n_theory.
Halving delta quadruples n_theory — the 1/delta^2 coupling.

Bin sizes tested: 0.1 ms to 50 ms (k from 1500 down to 3).

Plots:
  n_theory_vs_k.png       — n_theory vs k for each delta (log-log)
  n_theory_vs_delta.png   — n_theory vs delta for each bin size (coupling)
  n_theory_heatmap.png    — 2D heatmap: log10(n_theory) over (bin_size x delta)

Results saved to: results/bin-resolution-experiment/
"""

import math
import os
import shutil
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "../results/bin-resolution-experiment")

EPSILON  = 0.05
GRID_MAX = 150.0  # ms

# Bin sizes: very fine to very coarse
BIN_SIZES        = [0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50]
# Grid resolutions for the continuous KDE bound
GRID_RESOLUTIONS = [0.1, 0.25, 0.5, 1, 2, 5, 10]
# Accuracy targets
DELTAS = [0.01, 0.02, 0.03, 0.04, 0.05]

DELTA_COLORS = {
    0.01: "#c0392b",
    0.02: "#e67e22",
    0.03: "#f39c12",
    0.04: "#27ae60",
    0.05: "#2980b9",
}


# ============================================================
# theoretical bounds
# ============================================================

def k_bins(bin_size):
    return int(GRID_MAX / bin_size)


def n_discrete(delta, bin_size):
    k = k_bins(bin_size)
    return math.ceil((k + math.log(1.0 / EPSILON)) / delta ** 2)


def n_continuous(delta, grid_res):
    K = int(GRID_MAX / grid_res)
    return math.ceil(K * math.log(1.0 / EPSILON) / delta ** 2)


# ============================================================
# plots
# ============================================================

def plot_n_theory_vs_k():
    """log-log plot: n_theory vs k for each delta — discrete PMF bound."""
    k_vals = [k_bins(b) for b in BIN_SIZES]

    fig, ax = plt.subplots(figsize=(9, 6))

    for delta in DELTAS:
        ns = [n_discrete(delta, b) for b in BIN_SIZES]
        ax.plot(k_vals, ns, "o-",
                color=DELTA_COLORS[delta], linewidth=2, markersize=7,
                label=f"δ = {delta}")

    # Asymptotic slope-1 reference: n ∝ k
    k_ref   = np.array([k_vals[0], k_vals[-1]], dtype=float)
    n_ref   = k_ref / DELTAS[0] ** 2
    ax.plot(k_ref, n_ref, "k:", linewidth=1.2, alpha=0.5, label="slope 1 (n ∝ k)")

    # Secondary x-axis showing bin sizes
    ax2 = ax.twiny()
    ax2.set_xscale("log")
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(k_vals)
    ax2.set_xticklabels([f"{b}ms" for b in BIN_SIZES], fontsize=8, rotation=45)
    ax2.set_xlabel("Bin size (ms)")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Number of bins (k)")
    ax.set_ylabel("Theoretical n required")
    ax.set_title(
        "Discrete PMF: theoretical n vs number of bins k\n"
        r"$n = \lceil (k + \log(1/\varepsilon)) / \delta^2 \rceil$"
        f",  ε = {EPSILON}"
    )
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "n_theory_vs_k.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_n_theory_vs_delta():
    """
    Two-panel: n_theory vs delta for each bin size / grid resolution.
    Left: discrete PMF.  Right: continuous KDE.
    Shows the 1/delta^2 coupling explicitly.
    """
    cmap       = plt.cm.viridis
    delta_fine = np.linspace(0.005, 0.06, 500)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        r"Theoretical sample requirement vs accuracy target $\delta$"
        "\n"
        r"Halving $\delta$ quadruples n — the $1/\delta^2$ coupling is identical"
        " across all bin sizes",
        fontsize=12,
    )

    # --- left: discrete PMF ---
    ax   = axes[0]
    cols = cmap(np.linspace(0.1, 0.9, len(BIN_SIZES)))
    for bin_size, col in zip(BIN_SIZES, cols):
        k  = k_bins(bin_size)
        ns = [(k + math.log(1.0 / EPSILON)) / d ** 2 for d in delta_fine]
        ax.plot(delta_fine, ns, color=col, linewidth=2,
                label=f"{bin_size} ms  (k = {k})")

    for d in DELTAS:
        ax.axvline(x=d, color="grey", linestyle=":", linewidth=0.8, alpha=0.5)

    ax.set_yscale("log")
    ax.set_xlabel("Accuracy target (δ)")
    ax.set_ylabel("Theoretical n required")
    ax.set_title(r"Discrete PMF: $n = (k + \log(1/\varepsilon))\,/\,\delta^2$")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3, which="both")

    # --- right: continuous KDE ---
    ax   = axes[1]
    cols = cmap(np.linspace(0.1, 0.9, len(GRID_RESOLUTIONS)))
    for gr, col in zip(GRID_RESOLUTIONS, cols):
        K  = int(GRID_MAX / gr)
        ns = [K * math.log(1.0 / EPSILON) / d ** 2 for d in delta_fine]
        ax.plot(delta_fine, ns, color=col, linewidth=2,
                label=f"{gr} ms grid  (K = {K})")

    for d in DELTAS:
        ax.axvline(x=d, color="grey", linestyle=":", linewidth=0.8, alpha=0.5)

    ax.set_yscale("log")
    ax.set_xlabel("Accuracy target (δ)")
    ax.set_ylabel("Theoretical n required")
    ax.set_title(r"Continuous KDE: $n = K\,\log(1/\varepsilon)\,/\,\delta^2$")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "n_theory_vs_delta.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_n_theory_heatmap():
    """2D heatmap: log10(n_theory) as a function of (bin_size, delta)."""
    delta_vals = np.linspace(0.01, 0.05, 80)
    k_vals     = [k_bins(b) for b in BIN_SIZES]

    grid = np.zeros((len(BIN_SIZES), len(delta_vals)))
    for i, b in enumerate(BIN_SIZES):
        k = k_bins(b)
        for j, d in enumerate(delta_vals):
            grid[i, j] = math.log10(
                math.ceil((k + math.log(1.0 / EPSILON)) / d ** 2)
            )

    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(
        grid, aspect="auto", origin="lower",
        extent=[delta_vals[0], delta_vals[-1], -0.5, len(BIN_SIZES) - 0.5],
        cmap="plasma", interpolation="bilinear",
    )
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("log₁₀(n_theory)")

    # Contour lines at round powers of 10
    X, Y = np.meshgrid(delta_vals, np.arange(len(BIN_SIZES)))
    levels = [3, 4, 5, 6, 7]
    cs = ax.contour(X, Y, grid, levels=levels,
                    colors="white", linewidths=1.2, alpha=0.8)
    ax.clabel(cs, fmt={l: f"10^{l}" for l in levels},
              fontsize=9, colors="white")

    ax.set_yticks(range(len(BIN_SIZES)))
    ax.set_yticklabels([f"{b} ms  (k = {k_bins(b)})" for b in BIN_SIZES])
    ax.set_xlabel("Accuracy target (δ)")
    ax.set_ylabel("Bin size")
    ax.set_title(
        r"Discrete PMF: $n = \lceil (k + \log(1/\varepsilon)) / \delta^2 \rceil$"
        f"   (ε = {EPSILON})\n"
        "Colour = log₁₀(n_theory) — fine bins and tight tolerances both drive n up"
    )

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "n_theory_heatmap.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ============================================================
# console summary
# ============================================================

def print_tables():
    w = 12

    print("\n" + "=" * 80)
    print(f"Discrete PMF bound — n = ceil((k + log(1/ε)) / δ²),  ε = {EPSILON}")
    print("=" * 80)
    header = f"{'Bin size':>10}  {'k':>5}" + "".join(
        f"  {'δ='+str(d):>{w}}" for d in DELTAS
    )
    print(header)
    print("-" * len(header))
    for b in BIN_SIZES:
        k   = k_bins(b)
        row = f"{str(b)+'ms':>10}  {k:>5}"
        for d in DELTAS:
            row += f"  {n_discrete(d, b):>{w},}"
        print(row)

    print("\n" + "=" * 80)
    print(f"Continuous KDE bound — n = ceil(K · log(1/ε) / δ²),  ε = {EPSILON}")
    print("=" * 80)
    header = f"{'Grid res':>10}  {'K':>5}" + "".join(
        f"  {'δ='+str(d):>{w}}" for d in DELTAS
    )
    print(header)
    print("-" * len(header))
    for gr in GRID_RESOLUTIONS:
        K   = int(GRID_MAX / gr)
        row = f"{str(gr)+'ms':>10}  {K:>5}"
        for d in DELTAS:
            row += f"  {n_continuous(d, gr):>{w},}"
        print(row)


# ============================================================
# main
# ============================================================

if __name__ == "__main__":
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR)

    print("Bin resolution experiment — theoretical sample complexity")
    print(f"  Bin sizes      : {BIN_SIZES} ms")
    print(f"  Grid res (KDE) : {GRID_RESOLUTIONS} ms")
    print(f"  Delta range    : {DELTAS}")
    print(f"  Epsilon        : {EPSILON}")
    print()

    print_tables()

    print("\nGenerating plots ...")
    plot_n_theory_vs_k()
    plot_n_theory_vs_delta()
    plot_n_theory_heatmap()

    print("\nDone.")
