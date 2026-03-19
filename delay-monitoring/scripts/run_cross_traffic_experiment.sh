#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Cross-traffic experiment.
#
# The underlying delay is sampled from a parametric distribution
# (Normal, Lognormal, Weibull) — same as in the load-change experiment.
# A second OnOff UDP sender generates cross-traffic at controlled fractions
# of link capacity, causing real DropTail queuing.
#
# The receiver measures total end-to-end delay via DelayProbeTag:
#
#     E2E = base_delay (sampled from dist) + propagation + queuing
#
# As cross-traffic increases, the observed distribution shifts right.
# No queueing-theory assumptions — purely empirical measurement.
#
# Distribution base parameters (same as load-change experiment):
#   Normal    : mean=10ms, variance=1ms^2
#   Lognormal : mu=1.5, sigma=0.3
#   Weibull   : scale=5ms, shape=2.0
#
# Cross-traffic utilisation levels: 0%, 20%, 40%, 60%, 80%
# (0% = baseline — pure underlying distribution, no queuing added)
#
# Link: 10 Mbps, 2 ms propagation delay, DropTail queue
# Probe: n_theory=61199 packets, 10ms mean interval (probe util ≈ 0.08%)
#
# Results: delay-monitoring/results/cross-traffic/{dist}/ct_XX/delay_samples.csv

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/cross-traffic"
BASE_RELPATH="../delay-monitoring/results/cross-traffic"

N_THEORY=61199
LINK_DATA_RATE="10Mbps"
LINK_DELAY="2ms"
INTERVAL_MEAN=10.0   # ms — probe util: 1024*8/(10ms*10Mbps) ≈ 0.08% (negligible)

# base distribution parameters (same as load-change experiment)
NORMAL_MEAN=10.0
NORMAL_VAR=1.0
LN_MU=1.5
LN_SIGMA=0.3
WB_SCALE=5.0
WB_SHAPE=2.0

DISTS=("normal" "lognormal" "weibull")
CT_LEVELS=("0.0" "0.2" "0.4" "0.6" "0.8")
CT_LABELS=("ct_00" "ct_20" "ct_40" "ct_60" "ct_80")

mkdir -p "$BASE_DIR"

total=$(( ${#DISTS[@]} * ${#CT_LEVELS[@]} ))
count=0

echo "Cross-traffic experiment"
echo "  Link        : ${LINK_DATA_RATE}, propagation delay ${LINK_DELAY}"
echo "  n_theory    : ${N_THEORY}"
echo "  Utilisation : ${CT_LEVELS[*]}"
echo "  Dists       : ${DISTS[*]}"
echo ""

for dist in "${DISTS[@]}"; do
    mkdir -p "${BASE_DIR}/${dist}"
    echo "=== distribution: ${dist} ==="

    for i in "${!CT_LEVELS[@]}"; do
        ct="${CT_LEVELS[$i]}"
        label="${CT_LABELS[$i]}"

        ct_dir="${BASE_DIR}/${dist}/${label}"
        ct_relpath="${BASE_RELPATH}/${dist}/${label}"
        mkdir -p "$ct_dir"

        count=$(( count + 1 ))
        echo "  [${count}/${total}] ${dist} crossTrafficRate=${ct}"

        if [ "$dist" = "normal" ]; then
            dist_args="--delayDist=normal --normal_mean=${NORMAL_MEAN} --normal_variance=${NORMAL_VAR}"
        elif [ "$dist" = "lognormal" ]; then
            dist_args="--delayDist=lognormal --lognormal_mu=${LN_MU} --lognormal_sigma=${LN_SIGMA}"
        elif [ "$dist" = "weibull" ]; then
            dist_args="--delayDist=weibull --weibull_scale=${WB_SCALE} --weibull_shape=${WB_SHAPE}"
        fi

        (cd "$NS3_DIR" && ./ns3 run \
            "scratch/delay-monitoring/single-hop-underlying-network \
            ${dist_args} \
            --crossTrafficMode=true \
            --crossTrafficRate=${ct} \
            --linkDataRate=${LINK_DATA_RATE} \
            --linkDelay=${LINK_DELAY} \
            --numPackets=${N_THEORY} \
            --intervalMean=${INTERVAL_MEAN} \
            --lossRate=0.0 \
            --outputFile=${ct_relpath}/delay_samples.csv" 2>/dev/null)
    done
    echo ""
done

echo "Done. Results written to ${BASE_DIR}/"
