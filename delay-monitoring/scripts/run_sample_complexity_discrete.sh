#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Discrete experiment: Binomial(20, 0.5) delay distribution.
#
# Theoretical sample requirement:
#   k = N + 1 = 21  (support of Binomial(20, 0.5) is {0, 1, ..., 20})
#   n_theory = ceil((k + log(1/epsilon)) / delta^2)
#            = ceil((21 + 2.9957) / 0.0025) = 9599
#
# Sample sizes: n/4=2399, n/2=4799, n=9599, 2n=19198

set -e

NS3_DIR="ns-3.46"
RESULTS_DIR="delay-monitoring/results/sample-complexity-discrete"
RESULTS_RELPATH="../delay-monitoring/results/sample-complexity-discrete"

mkdir -p "$RESULTS_DIR"

SAMPLE_SIZES=(2399 4799 9599 19198)

total=${#SAMPLE_SIZES[@]}
count=0

for n in "${SAMPLE_SIZES[@]}"; do
    count=$(( count + 1 ))
    output="${RESULTS_RELPATH}/delay_samples_binomial_${n}.csv"
    echo "[${count}/${total}] dist=binomial  n=${n}"

    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --delayDist=binomial \
        --binomial_trials=20 \
        --binomial_prob=0.5 \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

echo "Done. Results written to ${RESULTS_DIR}/"
