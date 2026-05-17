# Profiler

Profiler is the implementation used for my MEng Computer Science final year project at UCL. The project studies passive network monitoring through delay distribution analysis. Given packet delay observations at the endpoint, Profiler reconstructs the path delay distribution and evaluates when the distributional response indicates a capacity boundary.

The repository contains the NS-3 simulations, Python analysis code, and dissertation figures used for the evaluation. It is intended to be readable by a dissertation reviewer as well as runnable by someone who wants to reproduce the main experiments.

## Project Context

Profiler is evaluated through a staged set of controlled experiments. A sender transmits packets to a receiver over one or more point-to-point links. The simulator samples per-packet delay from a chosen distribution, while the monitoring code only sees observed delays. The monitor does not receive the name or parameters of the distribution. This makes the reconstruction distribution agnostic.

The current experiments focus on lognormal, Weibull, and normal continuous delay distributions, plus finite-support binomial, Zipfian, and piecewise distributions for the statistical reconstruction checks. Accuracy is mainly measured with total variation distance, with related scripts for other distance measures and diagnostic plots.

## Report Alignment

The README follows the submitted dissertation PDF dated 17 May 2026. The main numbers used by the code paths below are:

```text
Total variation distance target: 0.05
Success probability target: 0.95
Discrete n_theory values: binomial 8,920, Zipfian 8,520, piecewise 8,520
Continuous n_theory value: 60,520 on a 1 ms grid from 0 ms to 150 ms
Continuous sample grid: 500, 1,000, 2,000, 5,000, 10,000, 20,000, 50,000, 60,520
Adaptive stopping operating point: batch size 200 and threshold delta / 6
Constant-rate single-link boundary: 0.925 load-grid point
Endpoint cross-traffic loss in the constant-rate single-link run: 0.950 median load ratio
Bursty average-load boundary: 0.475 median load ratio
Multi-hop constant-rate boundary: 0.925 median load ratio across two to ten hops
Multi-path modal result: upper-mode response recovers the 0.925 grid point
```

Profiler does not claim to measure exact physical capacity. The reported 0.925 boundary is the first satisfying point on the tested load grid under the report's queue model, traffic model, estimator, and decision rule.

## Repository Layout

```text
.
├── delay-monitoring/
│   ├── analysis/              Python experiment and plotting scripts
│   ├── foundations/           Single-hop NS-3 model and monitoring support
│   ├── multihop_scratch/      Multi-hop NS-3 capacity model
│   ├── results/               Selected summary data and generated figures
│   ├── scripts/               Longer NS-3 batch-run helpers
│   └── underlying_network_data/
├── ns-3.46/                   NS-3 checkout used by the project
└── report/                    Dissertation source and figures
```

The large raw experiment trees are not meant to live in Git. The repository keeps the code, report source, selected summary CSV files, and figures needed to inspect the dissertation results.

## Requirements

The code was developed with NS-3.46 and Python 3. The Python scripts use NumPy, SciPy, pandas, matplotlib, and seaborn. The NS-3 checkout is included in this workspace.

From the repository root, set up a Python environment with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r delay-monitoring/analysis/requirements.txt
```

If `requirements.txt` is empty in your copy, install the analysis dependencies directly:

```bash
pip install numpy scipy pandas matplotlib seaborn
```

## NS-3 Setup

The NS-3 scratch directory must point at the project simulations. The expected links are:

```text
ns-3.46/scratch/delay-monitoring -> delay-monitoring/foundations
ns-3.46/scratch/delay-monitoring-multihop -> delay-monitoring/multihop_scratch
```

Create or refresh them from the repository root:

```bash
ln -sfn ../../delay-monitoring/foundations ns-3.46/scratch/delay-monitoring
ln -sfn ../../delay-monitoring/multihop_scratch ns-3.46/scratch/delay-monitoring-multihop
```

Build the two simulation targets:

```bash
rm -rf ns-3.46/cmake-cache ns-3.46/build
cd ns-3.46
./ns3 configure --disable-examples --disable-tests
./ns3 build scratch/delay-monitoring/single-hop-underlying-network
./ns3 build scratch/delay-monitoring-multihop/multi-hop-capacity-network
cd ..
```

The `rm -rf` line removes generated NS-3 cache directories. It is useful if CMake reports that the cache was created in a different checkout path.

## Quick Reviewer Checks

These commands are intended as lightweight checks. They write only to `/tmp`, so they do not add new result files to the repository.

Compile the Python analysis scripts:

```bash
python3 -m compileall -q delay-monitoring/analysis
```

Run a tiny single-hop NS-3 simulation:

```bash
cd ns-3.46
./ns3 run --no-build --quiet "scratch/delay-monitoring/single-hop-underlying-network --delayDist=normal --normal_mean=10 --normal_variance=4 --numPackets=25 --outputFile=/tmp/profiler-normal-smoke.csv"
cd ..
```

This smoke run uses `--no-build` so it does not regenerate NS-3 build files while reviewing the repository.

Run a tiny observable-capacity experiment and place its output in `/tmp`:

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

Generate the statistical sample-complexity report figures into `/tmp`:

```bash
MPLCONFIGDIR=/tmp/profiler-matplotlib \
python3 delay-monitoring/analysis/statistical_sample_complexity_report.py \
  --results-dir /tmp/profiler-statistical-report
```

The last command is computational rather than simulator-heavy. It may take a few minutes because it repeats the statistical sampling used for the dissertation figures.

## Reproducing Main Results

The dissertation figures were produced from a mixture of NS-3 simulation outputs and pure Python statistical experiments.

The statistical sample-complexity figures in Chapter 4 can be regenerated with:

```bash
python3 delay-monitoring/analysis/statistical_sample_complexity_report.py
```

By default this writes to:

```text
delay-monitoring/results/statistical-sample-complexity-report/
```

This script uses the report's finite-domain reference counts: 8,920 for binomial, 8,520 for Zipfian and piecewise, and 60,520 for the continuous one millisecond grid.

For a single-link observable-capacity run, use:

```bash
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology single \
  --results-dir delay-monitoring/results/observable-capacity-single-100-seed \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8
```

For a multi-hop run, use:

```bash
python3 delay-monitoring/analysis/observable_capacity_experiments.py \
  --topology multi \
  --cross-traffic-scope path \
  --results-dir delay-monitoring/results/observable-capacity-multi-100-seed \
  --seed-start 1 \
  --seed-end 100 \
  --workers 8
```

These full runs produce many raw CSV files. For review, the quick checks above are usually the better way to confirm that the code path works.

The saved dissertation figures report that TVD response rate selects the 0.925 load-grid point in the constant-rate single-link run and remains at that grid point across the two to ten hop path-wide multi-hop runs. The bursty run reports a lower average-load boundary because the on-period sending rate is twice the swept average.

## What To Commit

Commit source code, report text, configuration files, summary CSV files, and final figures that are referenced by the dissertation.

Do not commit NS-3 build products or full raw experiment trees. In particular, leave these out of normal Git commits:

```text
ns-3.46/build/
ns-3.46/cmake-cache/
delay-monitoring/results/**/raw/
delay-monitoring/results/**/processed/
```

Large raw outputs should be archived outside the Git repository, for example in institutional storage, cloud storage, or a release archive.

## Useful Entry Points

The most relevant files for a reviewer are:

```text
delay-monitoring/foundations/single-hop-underlying-network.cc
delay-monitoring/multihop_scratch/multi-hop-capacity-network.cc
delay-monitoring/analysis/observable_capacity_experiments.py
delay-monitoring/analysis/distributional_capacity_response.py
delay-monitoring/analysis/statistical_sample_complexity_report.py
report/main.tex
```

Together, these files show the simulator model, the endpoint-visible monitoring pipeline, the statistical reconstruction baseline, and the dissertation write-up.
