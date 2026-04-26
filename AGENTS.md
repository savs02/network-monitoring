# network-monitoring — FYP Context

## Project

Final Year Project (MEng Computer Science, UCL). Passive network monitoring via delay distribution analysis. The core idea is that a monitoring mechanism observes packet delays passively and attempts to reconstruct the underlying delay distribution of a network path — without active probing or per-packet tracking across nodes.

Supervised by Dr. Stefano Vissicchio and Prof. Mark Handley.

This project is being developed toward publication (HotNets-style paper, 6 pages).

---

## The Simple Network Case

The current experimental focus is a two-node, one-link topology in NS-3. Node A sends packets to Node B over a point-to-point link. The link delay is sampled from a chosen distribution on a per-packet basis. This is the ground truth setup used to validate the monitoring approach.

NS-3 version: 3.46. Simulations live in `scratch/` with a symlink from the repo's `experiments/` directory.

---

## Underlying Distributions

The experimenter sets the underlying delay distribution when running the simulation. The three families used are:

- **Lognormal** — parameterised by mu and sigma (log-space parameters)
- **Weibull** — parameterised by scale and shape
- **Normal** — parameterised by mean and variance

The monitoring mechanism does not know which family generated the data. It sees only the observed delays and must reconstruct the distribution without that prior knowledge. This distribution-agnostic property is a core strength of the approach.

The experimenter knows the ground truth and uses it to validate reconstruction accuracy, typically via total variation distance (TVD).

---

## The Non-Binning Approach

The current primary focus. The monitoring mechanism observes per-packet delays directly (not aggregated into time bins). The research question is about sample complexity: how many samples are needed to reconstruct the delay distribution to within a given TVD tolerance, with high probability?

This connects to statistical learning theory results on empirical distribution convergence. The non-binning case is the clean baseline — direct observation, no information loss from aggregation.

---

## Repo Structure

```
network-monitoring/
├── delay-monitoring/
│   ├── experiments/          # NS-3 C++ simulation code
│   ├── analysis/             # Python analysis scripts
│   ├── underlying_network_data/  # Ground truth validation outputs
│   └── results/              # Monitoring mechanism outputs
└── ns-3.46/                  # NS-3 installation (adjacent or symlinked)
```

`underlying_network_data/` is for validating the NS-3 setup (i.e., confirming the sampled delays match the configured distribution). `results/` is for outputs from the monitoring mechanism itself.

---

## Key Metrics

- **TVD (Total Variation Distance)** — primary accuracy metric for distribution reconstruction
- **KL divergence** and **Wasserstein distance** — secondary metrics

---

## Writing Conventions

All written outputs (paper, dissertation, comments) follow these rules strictly:

- No em dashes
- No colons in section/subsection headings
- No abbreviations on first use without expansion
- British English spelling
- No AI-sounding phrasing — natural, direct academic prose
- No bullet points in prose sections
