#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Discrete experiment: Binomial(20, 0.5), Zipf(N=20, alpha=1.5), and Piecewise.
#
# Theoretical sample requirement for each:
#   Binomial: k = N + 1 = 21  (support {0, ..., 20})
#     n_theory = ceil((21 + ln(1/0.05)) / 0.05^2) = 9599
#     Sample sizes: 2400  4800  9599  19197  38393
#
#   Zipf: k = N = 20  (support {1, ..., 20})
#     n_theory = ceil((20 + ln(1/0.05)) / 0.05^2) = 9199
#     Sample sizes: 2300  4599  9199  18397  36793
#
#   Piecewise: k = 20  (support {1, ..., 20})
#     n_theory = ceil((20 + ln(1/0.05)) / 0.05^2) = 9199
#     Sample sizes: 2300  4599  9199  18397  36793

set -e

NS3_DIR="ns-3.46"
RESULTS_DIR="delay-monitoring/results/sample-complexity-discrete"
RESULTS_RELPATH="../delay-monitoring/results/sample-complexity-discrete"

mkdir -p "$RESULTS_DIR"

# --- Binomial(20, 0.5) ---

BINOMIAL_SIZES=(2400 4800 9599 19197 38393)
total_b=${#BINOMIAL_SIZES[@]}
count=0

echo "=== Binomial(20, 0.5) ==="
for n in "${BINOMIAL_SIZES[@]}"; do
    count=$(( count + 1 ))
    output="${RESULTS_RELPATH}/delay_samples_binomial_${n}.csv"
    echo "  [${count}/${total_b}] dist=binomial  n=${n}"

    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --delayDist=binomial \
        --binomial_trials=20 \
        --binomial_prob=0.5 \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

# --- Zipf(N=20, alpha=1.5) ---

ZIPF_SIZES=(2300 4599 9199 18397 36793)
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
        --delayDist=zipf \
        --zipf_n=20 \
        --zipf_alpha=1.5 \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

# --- Piecewise (irregular multi-modal PMF over {1,...,20}) ---

PIECEWISE_SIZES=(2300 4599 9199 18397 36793)
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
        --delayDist=piecewise \
        --numPackets=${n} \
        --outputFile=${output}" 2>/dev/null)
done

echo ""
echo "Done. Results written to ${RESULTS_DIR}/"
