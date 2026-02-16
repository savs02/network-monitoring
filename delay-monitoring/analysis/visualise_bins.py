"""
Reconstruct delay distribution from ingress/egress bin counts using EM algorithm.

Model: E[t] = sum_d (I[t-d] * D[d])  -- egress is convolution of ingress with delay
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import sys

def load_bin_data(filepath):
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found")
        return None
    return pd.read_csv(filepath)

def estimate_rough_delay(ingress_counts, egress_counts):
    """Use cross-correlation to get a rough delay estimate for initialization."""
    # Normalize
    ing = ingress_counts - ingress_counts.mean()
    egr = egress_counts - egress_counts.mean()
    
    # Cross-correlation
    correlation = np.correlate(egr, ing, mode='full')
    lags = np.arange(-len(ing) + 1, len(egr))
    
    # Find peak in positive lag region (delay should be positive)
    positive_mask = lags >= 0
    positive_lags = lags[positive_mask]
    positive_corr = correlation[positive_mask]
    
    if len(positive_corr) > 0:
        best_lag = positive_lags[np.argmax(positive_corr)]
        return max(0, best_lag)
    return 0

def em_delay_estimation(ingress_counts, egress_counts, bin_width, max_delay_bins=20, max_iter=200, tol=1e-6):
    """
    Estimate delay distribution using Expectation-Maximization.
    
    Model: E[t] = sum_d I[t-d] * D[d]
    
    E-step: Compute P(packet in egress bin t came from ingress bin t-d)
    M-step: Update delay distribution based on expected assignments
    
    Parameters:
    - ingress_counts: array of packet counts per bin at ingress
    - egress_counts: array of packet counts per bin at egress
    - bin_width: width of each bin in ms
    - max_delay_bins: maximum delay to consider (in bins)
    - max_iter: maximum EM iterations
    - tol: convergence tolerance
    
    Returns:
    - D: estimated delay distribution
    - delays_ms: corresponding delay values in ms
    - ll_history: log-likelihood at each iteration
    """
    n_bins = len(ingress_counts)
    
    # Get rough delay estimate from cross-correlation
    rough_delay_bins = estimate_rough_delay(ingress_counts, egress_counts)
    rough_delay_bins = min(rough_delay_bins, max_delay_bins - 1)
    print(f"  Rough delay estimate from cross-correlation: {rough_delay_bins} bins ({rough_delay_bins * bin_width}ms)")
    
    # Initialize delay distribution with Gaussian centered at rough estimate
    D = np.zeros(max_delay_bins)
    init_std = max(2, max_delay_bins / 10)  # spread of initial guess
    for d in range(max_delay_bins):
        D[d] = np.exp(-0.5 * ((d - rough_delay_bins) / init_std) ** 2)
    D = D / D.sum()
    
    ll_history = []
    
    for iteration in range(max_iter):
        # E-step: compute responsibilities
        # gamma[t, d] = P(egress packet in bin t came from ingress bin t-d | D)
        gamma = np.zeros((n_bins, max_delay_bins))
        
        for t in range(n_bins):
            for d in range(max_delay_bins):
                source_bin = t - d
                if 0 <= source_bin < n_bins and ingress_counts[source_bin] > 0:
                    gamma[t, d] = ingress_counts[source_bin] * D[d]
            
            # Normalize
            row_sum = gamma[t].sum()
            if row_sum > 0:
                gamma[t] /= row_sum
        
        # M-step: update delay distribution
        D_new = np.zeros(max_delay_bins)
        
        for d in range(max_delay_bins):
            for t in range(n_bins):
                D_new[d] += egress_counts[t] * gamma[t, d]
        
        # Normalize
        total = D_new.sum()
        if total > 0:
            D_new /= total
        else:
            print(f"Warning: D_new sum is zero at iteration {iteration}")
            break
        
        # Compute log-likelihood
        ll = 0
        for t in range(n_bins):
            if egress_counts[t] > 0:
                expected = 0
                for d in range(max_delay_bins):
                    source_bin = t - d
                    if 0 <= source_bin < n_bins:
                        expected += ingress_counts[source_bin] * D_new[d]
                if expected > 0:
                    ll += egress_counts[t] * np.log(expected)
        ll_history.append(ll)
        
        # Check convergence
        diff = np.abs(D_new - D).max()
        if diff < tol:
            print(f"  Converged at iteration {iteration}")
            break
        
        D = D_new.copy()
        
        if iteration % 50 == 0:
            print(f"  Iteration {iteration}: max diff = {diff:.6f}")
    
    delays_ms = np.arange(max_delay_bins) * bin_width
    
    return D, delays_ms, ll_history

def reconstruct_delay_distribution(ingress_df, egress_df, max_delay_ms=100):
    """
    Main function to reconstruct delay distribution using EM.
    """
    if ingress_df is None or egress_df is None:
        return None, None, None, None, None
    
    ingress_counts = ingress_df['packet_count'].values.astype(float)
    egress_counts = egress_df['packet_count'].values.astype(float)
    
    bin_width = ingress_df['bin_start_ms'].iloc[1] - ingress_df['bin_start_ms'].iloc[0] if len(ingress_df) > 1 else 10
    
    # Find where data exists
    ingress_nonzero = np.where(ingress_counts > 0)[0]
    egress_nonzero = np.where(egress_counts > 0)[0]
    
    if len(ingress_nonzero) == 0 or len(egress_nonzero) == 0:
        print("No packets found")
        return None, None, bin_width, None, None
    
    print(f"Ingress data: bins {ingress_nonzero.min()} to {ingress_nonzero.max()}")
    print(f"Egress data: bins {egress_nonzero.min()} to {egress_nonzero.max()}")
    print(f"Total ingress packets: {ingress_counts.sum():.0f}")
    print(f"Total egress packets: {egress_counts.sum():.0f}")
    
    # Trim to data region with padding for max delay
    max_delay_bins = int(max_delay_ms / bin_width) + 1
    start_idx = max(0, ingress_nonzero.min() - max_delay_bins)
    end_idx = min(len(ingress_counts), egress_nonzero.max() + max_delay_bins)
    
    ingress_trimmed = ingress_counts[start_idx:end_idx]
    egress_trimmed = egress_counts[start_idx:end_idx]
    
    print(f"Using bins {start_idx} to {end_idx} ({len(ingress_trimmed)} bins)")
    print(f"Max delay: {max_delay_bins} bins ({max_delay_ms}ms)")
    
    # Run EM
    D, delays_ms, ll_history = em_delay_estimation(
        ingress_trimmed,
        egress_trimmed,
        bin_width,
        max_delay_bins=max_delay_bins,
        max_iter=200
    )
    
    # Find peak
    peak_idx = np.argmax(D)
    peak_delay = delays_ms[peak_idx]
    
    return D, delays_ms, bin_width, peak_delay, ll_history

def plot_delay_distribution(D, delays_ms, bin_width, peak_delay, ll_history, title, axes, color, expected_mean=None, expected_std=None):
    """Plot the estimated delay distribution and convergence."""
    
    ax1, ax2 = axes
    
    if D is None or delays_ms is None:
        ax1.text(0.5, 0.5, 'Could not estimate', ha='center', va='center', transform=ax1.transAxes)
        ax1.set_title(title)
        return None
    
    # Find significant range
    threshold = 0.001 * D.max() if D.max() > 0 else 0
    significant = D > threshold
    if significant.any():
        last_sig = np.where(significant)[0][-1]
        plot_range = min(last_sig + 3, len(D))
    else:
        plot_range = len(D)
    
    # Plot delay distribution
    ax1.bar(delays_ms[:plot_range], D[:plot_range], 
            width=bin_width*0.8, color=color, edgecolor='black', alpha=0.7)
    ax1.set_xlabel('Delay (ms)')
    ax1.set_ylabel('Probability')
    ax1.set_title(title)
    ax1.grid(True, alpha=0.3)
    
    # Calculate statistics
    mean_delay = np.sum(delays_ms * D)
    variance = np.sum(D * (delays_ms - mean_delay)**2)
    std_delay = np.sqrt(variance)
    
    ax1.axvline(x=peak_delay, color='red', linestyle='--', linewidth=2, label=f'Peak: {peak_delay:.1f}ms')
    ax1.axvline(x=mean_delay, color='orange', linestyle=':', linewidth=2, label=f'Mean: {mean_delay:.1f}ms')
    
    # Plot expected distribution if provided
    if expected_mean is not None and expected_std is not None:
        ax1.axvline(x=expected_mean, color='green', linestyle='-', linewidth=2, alpha=0.7, label=f'Expected: {expected_mean:.1f}ms')
    
    ax1.legend()
    
    stats_text = f'Peak: {peak_delay:.2f}ms\nMean: {mean_delay:.2f}ms\nStd: {std_delay:.2f}ms'
    ax1.text(0.95, 0.95, stats_text, transform=ax1.transAxes, ha='right', va='top', fontsize=9,
             bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
    
    # Plot convergence
    if ll_history and len(ll_history) > 1:
        ax2.plot(ll_history, color=color, linewidth=2)
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Log-Likelihood')
        ax2.set_title('EM Convergence')
        ax2.grid(True, alpha=0.3)
    
    return {'peak': peak_delay, 'mean': mean_delay, 'std': std_delay}

def main():
    results_dir = "../results"
    output_dir = "../results"
    
    if len(sys.argv) > 1:
        results_dir = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    
    print(f"Loading bin data from: {results_dir}")
    print("=" * 60)
    
    # Load data
    ingress_aligned = load_bin_data(os.path.join(results_dir, 'ingress_bins_aligned.csv'))
    ingress_shifted = load_bin_data(os.path.join(results_dir, 'ingress_bins_shifted.csv'))
    egress_aligned = load_bin_data(os.path.join(results_dir, 'egress_bins_aligned.csv'))
    egress_shifted = load_bin_data(os.path.join(results_dir, 'egress_bins_shifted.csv'))
    
    for name, df in [('ingress_aligned', ingress_aligned), ('ingress_shifted', ingress_shifted),
                     ('egress_aligned', egress_aligned), ('egress_shifted', egress_shifted)]:
        if df is not None:
            total = df['packet_count'].sum()
            nonzero = (df['packet_count'] > 0).sum()
            print(f"{name}: {total} packets in {nonzero} non-empty bins")
    
    # Get bin width
    bin_width = 10.0
    if ingress_aligned is not None and len(ingress_aligned) > 1:
        bin_width = ingress_aligned['bin_start_ms'].iloc[1] - ingress_aligned['bin_start_ms'].iloc[0]
    
    # Reconstruct using EM
    print("\n" + "=" * 60)
    print("ALIGNED BINS - EM Estimation")
    print("=" * 60)
    result_aligned = reconstruct_delay_distribution(ingress_aligned, egress_aligned)
    D_aligned, delays_aligned, _, peak_aligned, ll_aligned = result_aligned if result_aligned[0] is not None else (None, None, None, None, None)
    
    print("\n" + "=" * 60)
    print("SHIFTED BINS - EM Estimation")
    print("=" * 60)
    result_shifted = reconstruct_delay_distribution(ingress_shifted, egress_shifted)
    D_shifted, delays_shifted, _, peak_shifted, ll_shifted = result_shifted if result_shifted[0] is not None else (None, None, None, None, None)
    
    # Expected values (can be passed as args later)
    expected_mean = 10.0
    expected_std = 2.0
    
    # Plot results
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Delay Distribution Estimation using EM (bin width = {bin_width}ms)', 
                 fontsize=14, fontweight='bold')
    
    stats_aligned = plot_delay_distribution(
        D_aligned, delays_aligned, bin_width, peak_aligned, ll_aligned,
        'Aligned Bins - Delay Distribution', 
        [axes[0, 0], axes[1, 0]], '#3498db',
        expected_mean=expected_mean, expected_std=expected_std
    )
    
    stats_shifted = plot_delay_distribution(
        D_shifted, delays_shifted, bin_width, peak_shifted, ll_shifted,
        'Shifted Bins - Delay Distribution', 
        [axes[0, 1], axes[1, 1]], '#e74c3c',
        expected_mean=expected_mean, expected_std=expected_std
    )
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'em_delay_distribution.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nSaved: {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("EM DELAY ESTIMATION SUMMARY")
    print("=" * 60)
    if stats_aligned:
        print(f"Aligned bins  - Peak: {stats_aligned['peak']:.2f}ms, Mean: {stats_aligned['mean']:.2f}ms, Std: {stats_aligned['std']:.2f}ms")
    if stats_shifted:
        print(f"Shifted bins  - Peak: {stats_shifted['peak']:.2f}ms, Mean: {stats_shifted['mean']:.2f}ms, Std: {stats_shifted['std']:.2f}ms")
    
    # Expected values for reference
    print("\n--- Expected (for lognormal mu=2.3, sigma=0.2) ---")
    expected_mean_ln = np.exp(2.3 + 0.2**2 / 2)
    expected_std_ln = expected_mean_ln * np.sqrt(np.exp(0.2**2) - 1)
    print(f"Expected Mean: {expected_mean_ln:.2f}ms, Std: {expected_std_ln:.2f}ms")
    
    print("\n--- Expected (for normal mean=10, var=4) ---")
    print(f"Expected Mean: 10.00ms, Std: 2.00ms")
    
    print("\nDone!")

if __name__ == "__main__":
    main()