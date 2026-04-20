#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Realistic-mode discrete experiment with multiple random seeds.
# Sampled delay is a floor; packet is sent over the wire; receiver records
# actual end-to-end delay.  linkDelay=1ns and linkDataRate=1Gbps keep
# network overhead sub-millisecond so it rounds away in the analysis.
# Skips files that already exist so interrupted runs can be resumed.
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
RESULTS_DIR="delay-monitoring/results/sample-complexity/discrete/realistic/seeded"
RESULTS_RELPATH="../delay-monitoring/results/sample-complexity/discrete/realistic/seeded"
QUEUE_SIZE=50  # DropTail queue depth in packets

mkdir -p "$RESULTS_DIR"

SEEDS=($(seq 1 100))

# --- Binomial(20, 0.5) ---

BINOMIAL_SIZES=(480 960 2400 4800 9599 19197 38393)
total_b=$(( ${#BINOMIAL_SIZES[@]} * ${#SEEDS[@]} ))
count=0

echo "=== Binomial(20, 0.5) — ${#SEEDS[@]} seeds ==="
for seed in "${SEEDS[@]}"; do
    for n in "${BINOMIAL_SIZES[@]}"; do
        count=$(( count + 1 ))
        output="${RESULTS_RELPATH}/delay_samples_binomial_${n}_seed${seed}.csv"

        if [ -f "${RESULTS_DIR}/delay_samples_binomial_${n}_seed${seed}.csv" ]; then
            echo "  [${count}/${total_b}] skip (exists): binomial n=${n} seed=${seed}"
            continue
        fi

        echo "  [${count}/${total_b}] dist=binomial  n=${n}  seed=${seed}"

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
            --RngRun=${seed} \
            --outputFile=${output}" 2>/dev/null)
    done
done

# --- Zipf(N=20, alpha=1.5) ---

ZIPF_SIZES=(460 920 2300 4599 9199 18397 36793)
total_z=$(( ${#ZIPF_SIZES[@]} * ${#SEEDS[@]} ))
count=0

echo ""
echo "=== Zipf(N=20, alpha=1.5) — ${#SEEDS[@]} seeds ==="
for seed in "${SEEDS[@]}"; do
    for n in "${ZIPF_SIZES[@]}"; do
        count=$(( count + 1 ))
        output="${RESULTS_RELPATH}/delay_samples_zipf_${n}_seed${seed}.csv"

        if [ -f "${RESULTS_DIR}/delay_samples_zipf_${n}_seed${seed}.csv" ]; then
            echo "  [${count}/${total_z}] skip (exists): zipf n=${n} seed=${seed}"
            continue
        fi

        echo "  [${count}/${total_z}] dist=zipf  n=${n}  seed=${seed}"

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
            --RngRun=${seed} \
            --outputFile=${output}" 2>/dev/null)
    done
done

# --- Piecewise (irregular multi-modal PMF over {1,...,20}) ---

PIECEWISE_SIZES=(460 920 2300 4599 9199 18397 36793)
total_p=$(( ${#PIECEWISE_SIZES[@]} * ${#SEEDS[@]} ))
count=0

echo ""
echo "=== Piecewise (irregular multi-modal, k=20) — ${#SEEDS[@]} seeds ==="
for seed in "${SEEDS[@]}"; do
    for n in "${PIECEWISE_SIZES[@]}"; do
        count=$(( count + 1 ))
        output="${RESULTS_RELPATH}/delay_samples_piecewise_${n}_seed${seed}.csv"

        if [ -f "${RESULTS_DIR}/delay_samples_piecewise_${n}_seed${seed}.csv" ]; then
            echo "  [${count}/${total_p}] skip (exists): piecewise n=${n} seed=${seed}"
            continue
        fi

        echo "  [${count}/${total_p}] dist=piecewise  n=${n}  seed=${seed}"

        (cd "$NS3_DIR" && ./ns3 run \
            "scratch/delay-monitoring/single-hop-underlying-network \
            --realisticMode=true \
            --linkDelay=1ns \
            --linkDataRate=1Gbps \
            --queueSize=${QUEUE_SIZE} \
            --delayDist=piecewise \
            --numPackets=${n} \
            --RngRun=${seed} \
            --outputFile=${output}" 2>/dev/null)
    done
done

echo ""
echo "Done. Results written to ${RESULTS_DIR}/"
