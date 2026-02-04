import sys
import re
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import json

def parse_delays_from_log(log_file):
    # extract the sampled delays
    delays = []
    with open(log_file, 'r') as f:
        for line in f:
            match = re.search(r'sampled delay = ([\d.]+) ms', line)
            if match:
                delays.append(float(match.group(1)))
    return np.array(delays)

def save_delays_to_csv(delays, output_file):
    np.savetxt(output_file, delays, delimiter=',', header='delay_ms', comments='')
    print(f"Saved {len(delays)} delays to {output_file}")

def save_statistics_to_json(delays, dist_type, params, output_file):
    stats_dict = {
        'distribution': dist_type,
        'parameters': params,
        'num_samples': int(len(delays)),
        'statistics': {
            'mean': float(np.mean(delays)),
            'std': float(np.std(delays)),
            'min': float(np.min(delays)),
            'max': float(np.max(delays)),
            'median': float(np.median(delays)),
            'q25': float(np.percentile(delays, 25)),
            'q75': float(np.percentile(delays, 75))
        }
    }
    
    # add distribution-specific parameters
    if dist_type == "lognormal":
        log_delays = np.log(delays)
        mu = float(np.mean(log_delays))
        sigma = float(np.std(log_delays))
        stats_dict['lognormal_params'] = {
            'mu': mu,
            'sigma': sigma
        }
    elif dist_type == "weibull":
        # fit weibull to the data
        shape, loc, scale = stats.weibull_min.fit(delays, floc=0)
        stats_dict['weibull_params'] = {
            'shape': float(shape),
            'scale': float(scale)
        }
    elif dist_type == "normal":
        mean = float(np.mean(delays))
        variance = float(np.var(delays))
        stats_dict['normal_params'] = {
            'mean': mean,
            'variance': variance,
            'std': float(np.sqrt(variance))
        }
    
    with open(output_file, 'w') as f:
        json.dump(stats_dict, f, indent=2)
    print(f"Saved statistics to {output_file}")

def plot_distribution(delays, dist_type, params, output_file):
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # histogram
    ax = axes[0, 0]
    ax.hist(delays, bins=30, density=True, alpha=0.6, edgecolor='black', color='skyblue')
    ax.set_xlabel('Delay (ms)')
    ax.set_ylabel('Density')
    ax.set_title(f'Histogram of Sampled Delays\n{dist_type}')
    ax.grid(True, alpha=0.3)
    
    # add statistics text
    stats_text = f"n = {len(delays)}\nmean = {np.mean(delays):.2f} ms\nstd = {np.std(delays):.2f} ms"
    ax.text(0.95, 0.95, stats_text, transform=ax.transAxes, 
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # empirical CDF
    ax = axes[0, 1]
    sorted_delays = np.sort(delays)
    cdf = np.arange(1, len(sorted_delays) + 1) / len(sorted_delays)
    ax.plot(sorted_delays, cdf, linewidth=2)
    ax.set_xlabel('Delay (ms)')
    ax.set_ylabel('CDF')
    ax.set_title('Empirical Cumulative Distribution')
    ax.grid(True, alpha=0.3)
    
    # Time series
    ax = axes[1, 0]
    ax.plot(delays, linewidth=0.5, alpha=0.7)
    ax.axhline(y=np.mean(delays), color='r', linestyle='--', label=f'Mean = {np.mean(delays):.2f}')
    ax.set_xlabel('Packet Number')
    ax.set_ylabel('Delay (ms)')
    ax.set_title('Delay Time Series')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # box plot
    ax = axes[1, 1]
    ax.boxplot(delays, vert=True)
    ax.set_ylabel('Delay (ms)')
    ax.set_title('Delay Distribution Box Plot')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Saved plot to {output_file}")
    plt.close()

def main():
    if len(sys.argv) < 3:
        print("Usage: python extract_underlying_delays.py <ns3_log> <dist_type>")
        print("Example: python extract_underlying_delays.py ../underlying_network_data/output.log lognormal")
        sys.exit(1)
    
    log_file = sys.argv[1]
    dist_type = sys.argv[2]
    
    # output 
    import os
    log_dir = os.path.dirname(log_file)
    output_prefix = f"{log_dir}/{dist_type}_experiment"
    
    # parse delays
    print(f"Parsing delays from {log_file}...")
    delays = parse_delays_from_log(log_file)
    
    if len(delays) == 0:
        print("Error: No delays found in log file!")
        sys.exit(1)
    
    print(f"Extracted {len(delays)} delay samples")
    
    # infer parameters from the data
    params = {
        'inferred_mean': float(np.mean(delays)),
        'inferred_std': float(np.std(delays))
    }
    
    # save
    save_delays_to_csv(delays, f"{output_prefix}_delays.csv")
    save_statistics_to_json(delays, dist_type, params, f"{output_prefix}_stats.json")
    plot_distribution(delays, dist_type, params, f"{output_prefix}_plot.png")
    
    print("\nSummary:")
    print(f"  Distribution: {dist_type}")
    print(f"  Samples: {len(delays)}")
    print(f"  Mean: {np.mean(delays):.2f} ms")
    print(f"  Std: {np.std(delays):.2f} ms")
    print(f"  Range: [{np.min(delays):.2f}, {np.max(delays):.2f}] ms")
    
    # print distribution-specific parameters
    if dist_type == "lognormal":
        log_delays = np.log(delays)
        mu = np.mean(log_delays)
        sigma = np.std(log_delays)
        print(f"  LogNormal Mu (μ): {mu:.4f}")
        print(f"  LogNormal Sigma (σ): {sigma:.4f}")
    elif dist_type == "weibull":
        shape, loc, scale = stats.weibull_min.fit(delays, floc=0)
        print(f"  Weibull Shape (k): {shape:.4f}")
        print(f"  Weibull Scale (λ): {scale:.4f}")
    elif dist_type == "normal":
        mean = np.mean(delays)
        variance = np.var(delays)
        print(f"  Normal Mean (μ): {mean:.4f}")
        print(f"  Normal Variance (σ²): {variance:.4f}")
        print(f"  Normal Std (σ): {np.sqrt(variance):.4f}")

if __name__ == "__main__":
    main()