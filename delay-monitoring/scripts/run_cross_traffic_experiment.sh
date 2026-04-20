#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Cross-traffic experiment — 0% to 200% utilisation in 10% steps.
#
# A probe sender applies a base delay sampled from the underlying distribution
# (Normal, Lognormal, Weibull) before transmitting each packet.  A second
# OnOff UDP sender injects background traffic at a controlled fraction of link
# capacity.  The receiver measures actual end-to-end delay via DelayProbeTag:
#
#     E2E = base_delay (sampled from dist) + propagation + queuing
#
# The monitor is unaware of the cross-traffic load.  The goal is to observe
# how the delay distribution shifts as load increases, and use those shifts
# to estimate the point of link saturation.
#
# Above 100% utilisation the DropTail queue saturates: probe packets begin to
# be dropped and only a fraction of transmitted packets are received.
#
# Distribution base parameters:
#   Normal    : mean=10ms, variance=1ms^2
#   Lognormal : mu=1.5, sigma=0.3
#   Weibull   : scale=5ms, shape=2.0
#
# Cross-traffic: 0% to 200% in 10% steps (21 levels)
# Link: 10 Mbps, 2 ms propagation delay, DropTail queue (50 packets)
# Probe: n_theory=61199 packets, 10ms mean interval (probe util ~0.08%)
#
# Results: delay-monitoring/results/cross-traffic/{dist}/ct_XXX/delay_samples.csv

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/cross-traffic"
BASE_RELPATH="../delay-monitoring/results/cross-traffic"

N_THEORY=61199
LINK_DATA_RATE="10Mbps"
LINK_DELAY="2ms"
QUEUE_SIZE=50
INTERVAL_MEAN=10.0

NORMAL_MEAN=10.0
NORMAL_VAR=1.0
LN_MU=1.5
LN_SIGMA=0.3
WB_SCALE=5.0
WB_SHAPE=2.0

DISTS=("normal" "lognormal" "weibull")

# 0% to 200% in 10% steps — hardcoded to avoid bash 3.x compatibility issues
CT_RATES=(0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0 1.1 1.2 1.3 1.4 1.5 1.6 1.7 1.8 1.9 2.0)
CT_LABELS=(ct_000 ct_010 ct_020 ct_030 ct_040 ct_050 ct_060 ct_070 ct_080 ct_090 ct_100 ct_110 ct_120 ct_130 ct_140 ct_150 ct_160 ct_170 ct_180 ct_190 ct_200)

mkdir -p "$BASE_DIR"

total=$(( ${#DISTS[@]} * ${#CT_RATES[@]} ))
count=0

echo "Cross-traffic experiment — 0% to 200% in 10% steps"
echo "  Link        : ${LINK_DATA_RATE}, propagation ${LINK_DELAY}, queue ${QUEUE_SIZE}p"
echo "  n_theory    : ${N_THEORY}"
echo "  Levels      : ${#CT_RATES[@]}  (${CT_LABELS[0]} .. ${CT_LABELS[20]})"
echo "  Dists       : ${DISTS[*]}"
echo ""

for dist in "${DISTS[@]}"; do
    mkdir -p "${BASE_DIR}/${dist}"
    echo "=== distribution: ${dist} ==="

    if [ "$dist" = "normal" ]; then
        dist_args="--delayDist=normal --normal_mean=${NORMAL_MEAN} --normal_variance=${NORMAL_VAR}"
    elif [ "$dist" = "lognormal" ]; then
        dist_args="--delayDist=lognormal --lognormal_mu=${LN_MU} --lognormal_sigma=${LN_SIGMA}"
    elif [ "$dist" = "weibull" ]; then
        dist_args="--delayDist=weibull --weibull_scale=${WB_SCALE} --weibull_shape=${WB_SHAPE}"
    fi

    for i in "${!CT_RATES[@]}"; do
        ct="${CT_RATES[$i]}"
        label="${CT_LABELS[$i]}"

        ct_dir="${BASE_DIR}/${dist}/${label}"
        ct_relpath="${BASE_RELPATH}/${dist}/${label}"
        mkdir -p "$ct_dir"

        count=$(( count + 1 ))
        echo "  [${count}/${total}] ${dist}  crossTrafficRate=${ct}  (${label})"

        (cd "$NS3_DIR" && ./ns3 run \
            "scratch/delay-monitoring/single-hop-underlying-network \
            ${dist_args} \
            --crossTrafficMode=true \
            --crossTrafficRate=${ct} \
            --linkDataRate=${LINK_DATA_RATE} \
            --linkDelay=${LINK_DELAY} \
            --queueSize=${QUEUE_SIZE} \
            --numPackets=${N_THEORY} \
            --intervalMean=${INTERVAL_MEAN} \
            --lossRate=0.0 \
            --outputFile=${ct_relpath}/delay_samples.csv" 2>/dev/null)
    done
    echo ""
done

echo "Done. Results written to ${BASE_DIR}/"
