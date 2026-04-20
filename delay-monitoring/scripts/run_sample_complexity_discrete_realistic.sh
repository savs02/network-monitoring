#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Realistic-mode discrete experiment: same three distributions as the
# theoretical discrete experiment, but each packet is sent over the wire
# and the receiver records the actual end-to-end delay.
#
# The sampled delay is a floor — the packet takes at least that long, but
# real link propagation and transmission time are added on top.  To keep
# that overhead sub-millisecond (so it rounds away in the analysis), we
# use linkDelay=1ns and linkDataRate=1Gbps.
#
# Sample sizes are identical to the theoretical discrete experiment.

set -e

NS3_DIR="ns-3.46"
RESULTS_DIR="delay-monitoring/results/sample-complexity/discrete/realistic/single_seed"
RESULTS_RELPATH="../delay-monitoring/results/sample-complexity/discrete/realistic/single_seed"
QUEUE_SIZE=50  # DropTail queue depth in packets

mkdir -p "$RESULTS_DIR"

# --- Binomial(20, 0.5) ---

BINOMIAL_SIZES=(480 960 2400 4800 9599 19197 38393)
total_b=${#BINOMIAL_SIZES[@]}
count=0

echo "=== Binomial(20, 0.5) ==="
for n in "${BINOMIAL_SIZES[@]}"; do
    count=$(( count + 1 ))
    output="${RESULTS_RELPATH}/delay_samples_binomial_${n}.csv"
    echo "  [${count}/${total_b}] dist=binomial  n=${n}"

    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --realisticMode=true \
        --linkDelay=1ns \
        --linkDataRate=1Gbps \
        --queueSize=${QUEUE_SIZE} \
        --delayDist=binomial \
        --binomial_trials=20 \
        --binomial_prob=0.5 \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

# --- Zipf(N=20, alpha=1.5) ---

ZIPF_SIZES=(460 920 2300 4599 9199 18397 36793)
total_z=${#ZIPF_SIZES[@]}
count=0

echo ""
echo "=== Zipf(N=20, alpha=1.5) ==="
for n in "${ZIPF_SIZES[@]}"; do
    count=$(( count + 1 ))
    output="${RESULTS_RELPATH}/delay_samples_zipf_${n}.csv"
    echo "  [${count}/${total_z}] dist=zipf  n=${n}"

    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --realisticMode=true \
        --linkDelay=1ns \
        --linkDataRate=1Gbps \
        --queueSize=${QUEUE_SIZE} \
        --delayDist=zipf \
        --zipf_n=20 \
        --zipf_alpha=1.5 \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

# --- Piecewise (irregular multi-modal PMF over {1,...,20}) ---

PIECEWISE_SIZES=(460 920 2300 4599 9199 18397 36793)
total_p=${#PIECEWISE_SIZES[@]}
count=0

echo ""
echo "=== Piecewise (irregular multi-modal, k=20) ==="
for n in "${PIECEWISE_SIZES[@]}"; do
    count=$(( count + 1 ))
    output="${RESULTS_RELPATH}/delay_samples_piecewise_${n}.csv"
    echo "  [${count}/${total_p}] dist=piecewise  n=${n}"

    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --realisticMode=true \
        --linkDelay=1ns \
        --linkDataRate=1Gbps \
        --queueSize=${QUEUE_SIZE} \
        --delayDist=piecewise \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

echo ""
echo "Done. Results written to ${RESULTS_DIR}/"
