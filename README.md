# Profiler

Profiler is the implementation used for my MEng Computer Science final year project at UCL. The project studies passive network monitoring through delay distribution analysis. Given packet delay observations at the endpoint, Profiler reconstructs the path delay distribution and evaluates when a distributional change becomes strong enough to identify a capacity boundary.

The repository contains the NS-3 simulations, Python analysis code, and dissertation figures used for the evaluation. It is intended to be readable by a dissertation reviewer as well as runnable by someone who wants to reproduce the main experiments.

## Project Context

The core setting is deliberately simple. A sender transmits packets to a receiver over one or more point-to-point links. The simulator samples per-packet delay from a chosen distribution, while the monitoring code only sees observed delays. The monitor does not receive the name or parameters of the distribution. This makes the reconstruction distribution agnostic.

The current experiments focus on three families: lognormal, Weibull, and normal. Accuracy is mainly measured with total variation distance, with related scripts for other distance measures and diagnostic plots.

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
cd ns-3.46
./ns3 build scratch/delay-monitoring/single-hop-underlying-network
./ns3 build scratch/delay-monitoring-multihop/multi-hop-capacity-network
cd ..
```

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

The statistical sample-complexity figures can be regenerated with:

```bash
python3 delay-monitoring/analysis/statistical_sample_complexity_report.py
```

By default this writes to:

```text
delay-monitoring/results/statistical-sample-complexity-report/
```

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
