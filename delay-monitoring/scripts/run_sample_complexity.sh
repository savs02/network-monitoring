#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Sample sizes are derived from the theoretical bound:
#   n_theory = ceil((k + log(1/epsilon)) / delta^2)
#   k=150 bins (0-150ms at 1ms), epsilon=0.05, delta=0.05 => n_theory = 61199
#
# We test n/4, n/2, n, and 2n to bracket the theoretical requirement.

set -e

NS3_DIR="ns-3.46"
RESULTS_DIR="delay-monitoring/results/sample-complexity"
RESULTS_RELPATH="../delay-monitoring/results/sample-complexity"

mkdir -p "$RESULTS_DIR"

DISTRIBUTIONS=("lognormal" "normal" "weibull")
SAMPLE_SIZES=(15299 30599 61199 122398)

total=$(( ${#DISTRIBUTIONS[@]} * ${#SAMPLE_SIZES[@]} ))
count=0

for dist in "${DISTRIBUTIONS[@]}"; do
    for n in "${SAMPLE_SIZES[@]}"; do
        count=$(( count + 1 ))
        output="${RESULTS_RELPATH}/delay_samples_${dist}_${n}.csv"
        echo "[${count}/${total}] dist=${dist}  n=${n}"

        (cd "$NS3_DIR" && ./ns3 run \
            "scratch/delay-monitoring/single-hop-underlying-network \
            --delayDist=${dist} \
            --numPackets=${n} \
            --outputFile=${output}" 2>/dev/null)
    done
done

echo "Done. Results written to ${RESULTS_DIR}/"
