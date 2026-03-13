#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Packet loss experiment.
#
# For each combination of (distribution, loss_rate, n_transmitted):
#   - runs the NS-3 simulation with --lossRate=p
#   - the simulator independently drops each packet with probability p
#     before recording it (models packets lost before reaching the monitor)
#   - the output CSV contains only the packets actually received by the monitor
#
# Loss rates:   0%, 10%, 25%, 50%, 75%
# Distributions: normal, lognormal, weibull
# n_transmitted: n/4, n/2, n, 2n  where n = n_theory for 1ms bins
#
# n_theory = ceil((k + log(1/epsilon)) / delta^2)
#          = ceil((150 + 2.9957) / 0.0025) = 61,199
# Sample sizes: 15299  30599  61199  122398

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/packet-loss"
BASE_RELPATH="../delay-monitoring/results/packet-loss"

DISTRIBUTIONS=("normal" "lognormal" "weibull")
LOSS_RATES=("0.0" "0.1" "0.25" "0.5" "0.75")
SAMPLE_SIZES=(15299 30599 61199 122398)

mkdir -p "$BASE_DIR"

total=$(( ${#DISTRIBUTIONS[@]} * ${#LOSS_RATES[@]} * ${#SAMPLE_SIZES[@]} ))
count=0

echo "Packet loss experiment"
echo "  Distributions : ${DISTRIBUTIONS[*]}"
echo "  Loss rates    : ${LOSS_RATES[*]}"
echo "  n_transmitted : ${SAMPLE_SIZES[*]}"
echo "  Total runs    : $total"
echo ""

for loss_rate in "${LOSS_RATES[@]}"; do

    # directory name: loss_0pct, loss_10pct, etc.
    loss_pct=$(python3 -c "print(int(float('$loss_rate') * 100))")
    loss_dir="${BASE_DIR}/loss_${loss_pct}pct"
    loss_relpath="${BASE_RELPATH}/loss_${loss_pct}pct"
    mkdir -p "$loss_dir"

    echo "=== loss_rate=${loss_rate} (${loss_pct}%) ==="

    for dist in "${DISTRIBUTIONS[@]}"; do
        for n in "${SAMPLE_SIZES[@]}"; do
            count=$(( count + 1 ))
            output="${loss_relpath}/delay_samples_${dist}_${n}.csv"
            echo "  [${count}/${total}] dist=${dist}  n=${n}  loss=${loss_rate}"

            (cd "$NS3_DIR" && ./ns3 run \
                "scratch/delay-monitoring/single-hop-underlying-network \
                --delayDist=${dist} \
                --numPackets=${n} \
                --lossRate=${loss_rate} \
                --outputFile=${output}" 2>/dev/null)
        done
    done
    echo ""
done

echo "Done. Results written to ${BASE_DIR}/"
