# Profiler

Profiler is a passive network monitoring pipeline for detecting when a path approaches a capacity boundary from endpoint delay observations. It reconstructs non-parametric delay distributions from received packet samples, stops when the reconstruction is stable, and compares stopped distributions across offered-load conditions using total variation distance.

The monitor only uses receiver-side packet delays and the ordering of load conditions. The simulator knows the configured topology, delay family, random seed, and offered load, but those fields are used for experiment control and post-run scoring rather than for the monitoring decision.

## Repository Layout

```text
.
├── delay-monitoring/
│   ├── analysis/              Python experiment, analysis, and plotting scripts
│   ├── foundations/           Single-link NS-3 model and monitoring support
│   ├── multihop_scratch/      Multi-hop NS-3 capacity model
│   ├── results/               Selected summary data and generated figures
│   ├── scripts/               Batch helpers for earlier sample-complexity runs
│   └── underlying_network_data/
├── ns-3.46/                   Network Simulator 3 checkout used by Profiler
└── report/                    Report source and figures
```

## Requirements

Profiler uses Network Simulator 3 (NS-3) 3.46, C++, and Python 3. The Python analysis uses NumPy, SciPy, pandas, matplotlib, and seaborn.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install numpy scipy pandas matplotlib seaborn
pip install -r delay-monitoring/analysis/requirements.txt
```

## NS-3 Setup

The project simulations are exposed to NS-3 through scratch links:

```bash
ln -sfn ../../delay-monitoring/foundations ns-3.46/scratch/delay-monitoring
ln -sfn ../../delay-monitoring/multihop_scratch ns-3.46/scratch/delay-monitoring-multihop
```

Build the single-link and multi-hop simulation targets:

```bash
cd ns-3.46
./ns3 configure --disable-examples --disable-tests
./ns3 build scratch/delay-monitoring/single-hop-underlying-network
./ns3 build scratch/delay-monitoring-multihop/multi-hop-capacity-network
cd ..
```

If CMake reports that its cache was created in another checkout path, remove the generated NS-3 cache directories and rerun the build commands:

```bash
rm -rf ns-3.46/cmake-cache ns-3.46/build
```

## Quick Checks

These commands check the main code paths and write experiment output to `/tmp`.

Compile the Python analysis scripts:

```bash
python3 -m compileall -q delay-monitoring/analysis
```

Run a small single-link NS-3 simulation:

```bash
cd ns-3.46
./ns3 run --no-build --quiet "scratch/delay-monitoring/single-hop-underlying-network --delayDist=normal --normal_mean=10 --normal_variance=4 --numPackets=25 --outputFile=/tmp/profiler-normal-smoke.csv"
cd ..
```

Run a small observable-capacity analysis:

```bash
MPLCONFIGDIR=/tmp/profiler-matplotlib \
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology single \
  --results-dir /tmp/profiler-observable-smoke \
  --dists weibull \
  --seed-start 1 \
  --seed-end 1 \
  --workers 1 \
  --skip-ns3-build \
  --max-load-factor 0.10 \
  --load-step-fraction 0.05 \
  --max-packets-per-load 50 \
  --simulation-stop-time 2 \
  --quiet-progress
```

Regenerate the statistical sample-complexity figures into `/tmp`:

```bash
MPLCONFIGDIR=/tmp/profiler-matplotlib \
python3 delay-monitoring/analysis/statistical_sample_complexity_report.py \
  --results-dir /tmp/profiler-statistical-report
```

## Reproducing Main Results

The commands below regenerate the main result families. Commands that call NS-3 write raw simulation files under the supplied `--results-dir`; use a different directory if you want to keep several runs side by side.

### Statistical Reconstruction

```bash
python3 delay-monitoring/analysis/statistical_sample_complexity_report.py
```

This regenerates `delay-monitoring/results/statistical-sample-complexity-report/` using the sample counts used in the report: 8,920 for binomial, 8,520 for Zipfian and piecewise, and 60,520 for the continuous one millisecond grid.

### Adaptive Stopping

```bash
python3 delay-monitoring/analysis/adaptive_stopping_v2.py
python3 delay-monitoring/analysis/adaptive_stopping_report_plots.py
```

The first command runs the 100-seed stopping sweep. The second command derives the report plots from that sweep.

### Constant-Rate Single-Link Capacity

```bash
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology single \
  --results-dir delay-monitoring/results/observable-capacity-single-100-seed \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8
```

### Pareto On-Off Bursty Single-Link Capacity

```bash
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology single \
  --results-dir delay-monitoring/results/observable-capacity-single-bursty-pareto-100 \
  --scenario-label single_bursty_pareto \
  --cross-traffic-pattern bursty \
  --cross-traffic-on-time 'ns3::ParetoRandomVariable[Scale=0.02|Shape=1.5|Bound=0.5]' \
  --cross-traffic-off-time 'ns3::ParetoRandomVariable[Scale=0.02|Shape=1.5|Bound=0.5]' \
  --burst-rate-multiplier 2.0 \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8
```

### Uniform Multi-Hop Capacity

```bash
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology multi \
  --cross-traffic-scope path \
  --results-dir delay-monitoring/results/observable-capacity-multi-100-seed \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8
```

### Heterogeneous Five-Hop Capacity

```bash
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology multi \
  --hop-counts 5 \
  --capacity-mbps 10 \
  --link-data-rates 10Mbps,20Mbps,20Mbps,20Mbps,20Mbps \
  --bottleneck-hop 0 \
  --scenario-label heterogeneous_start \
  --results-dir delay-monitoring/results/observable-capacity-heterogeneous-start-100 \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8

python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology multi \
  --hop-counts 5 \
  --capacity-mbps 10 \
  --link-data-rates 20Mbps,20Mbps,10Mbps,20Mbps,20Mbps \
  --bottleneck-hop 2 \
  --scenario-label heterogeneous_middle \
  --results-dir delay-monitoring/results/observable-capacity-heterogeneous-middle-100 \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8

python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology multi \
  --hop-counts 5 \
  --capacity-mbps 10 \
  --link-data-rates 20Mbps,20Mbps,20Mbps,20Mbps,10Mbps \
  --bottleneck-hop 4 \
  --scenario-label heterogeneous_end \
  --results-dir delay-monitoring/results/observable-capacity-heterogeneous-end-100 \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8
```

### Capacity Figures From Saved Runs

```bash
python3 delay-monitoring/analysis/plot_observable_capacity_results.py \
  --single-dir delay-monitoring/results/observable-capacity-single-100-seed \
  --multi-dir delay-monitoring/results/observable-capacity-multi-100-seed \
  --out-dir report/figures/evaluation \
  --plot-hop 10

python3 delay-monitoring/analysis/capacity_robustness_plots.py \
  --bursty-dir delay-monitoring/results/observable-capacity-single-bursty-pareto-100 \
  --hetero-dir start=delay-monitoring/results/observable-capacity-heterogeneous-start-100 \
  --hetero-dir middle=delay-monitoring/results/observable-capacity-heterogeneous-middle-100 \
  --hetero-dir end=delay-monitoring/results/observable-capacity-heterogeneous-end-100 \
  --report-figures report/figures/evaluation \
  --summary-dir delay-monitoring/results/capacity-robustness-summary
```

### Multi-Path Modal Capacity

The multi-path analysis uses the stopped distributions from the constant-rate single-link run.

```bash
python3 delay-monitoring/analysis/multipath_bimodal_capacity.py \
  --single-results delay-monitoring/results/observable-capacity-single-100-seed \
  --results-dir delay-monitoring/results/multipath-bimodal-capacity \
  --upper-shares 0.10 0.25 0.50 0.75 \
  --upper-path-offset-ms 30

python3 delay-monitoring/analysis/multipath_offset_sensitivity.py \
  --single-results delay-monitoring/results/observable-capacity-single-100-seed \
  --results-dir delay-monitoring/results/multipath-offset-sensitivity \
  --upper-shares 0.10 0.25 0.50 0.75 \
  --offsets-ms 10 20 30 40 50
```

## Useful Entry Points

```text
delay-monitoring/foundations/single-hop-underlying-network.cc
delay-monitoring/multihop_scratch/multi-hop-capacity-network.cc
delay-monitoring/analysis/statistical_sample_complexity_report.py
delay-monitoring/analysis/adaptive_stopping_v2.py
delay-monitoring/analysis/adaptive_stopping_report_plots.py
delay-monitoring/analysis/observable_capacity_experiments.py
delay-monitoring/analysis/plot_observable_capacity_results.py
delay-monitoring/analysis/capacity_robustness_plots.py
delay-monitoring/analysis/multipath_bimodal_capacity.py
delay-monitoring/analysis/multipath_offset_sensitivity.py
report/main.tex
```
