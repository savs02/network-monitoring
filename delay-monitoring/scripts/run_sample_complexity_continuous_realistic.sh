#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Realistic-mode continuous experiment (single seed).
# Distributions: Lognormal(mu=2.3, sigma=0.2), Normal(mean=40, var=4),
#                Weibull(scale=10, shape=2).
#
# Sampled delay is a floor; packet is sent over the wire; receiver records
# actual end-to-end delay via DelayProbeTag.
# linkDelay=1ns and linkDataRate=1Gbps keep network overhead sub-millisecond.
#
# n_theory = ceil((k + ln(1/epsilon)) / delta^2)
#   k=150 bins (0-150ms at 1ms), epsilon=0.05, delta=0.05 => n_theory = 61199
#   Sample sizes: n/4=15299  n/2=30599  n=61199  2n=122398

set -e

NS3_DIR="ns-3.46"
RESULTS_DIR="delay-monitoring/results/sample-complexity/continuous/realistic/single_seed"
RESULTS_RELPATH="../delay-monitoring/results/sample-complexity/continuous/realistic/single_seed"
QUEUE_SIZE=50

mkdir -p "$RESULTS_DIR"

DISTRIBUTIONS=("lognormal" "normal" "weibull")
SAMPLE_SIZES=(3060 6120 15299 30599 61199 122398 244796)

total=$(( ${#DISTRIBUTIONS[@]} * ${#SAMPLE_SIZES[@]} ))
count=0

for dist in "${DISTRIBUTIONS[@]}"; do
    for n in "${SAMPLE_SIZES[@]}"; do
        count=$(( count + 1 ))
        output="${RESULTS_RELPATH}/delay_samples_${dist}_${n}.csv"
        echo "[${count}/${total}] dist=${dist}  n=${n}"

        (cd "$NS3_DIR" && ./ns3 run \
            "scratch/delay-monitoring/single-hop-underlying-network \
            --realisticMode=true \
            --linkDelay=1ns \
            --linkDataRate=1Gbps \
            --queueSize=${QUEUE_SIZE} \
            --delayDist=${dist} \
            --numPackets=${n} \
            --outputFile=${output}" 2>/dev/null)
    done
done

echo "Done. Results written to ${RESULTS_DIR}/"
