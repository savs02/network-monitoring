#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Detection pipeline experiment — before / detection / reconstruction.
#
# Each run produces a single continuous sample stream:
#   Phase 1 (before)     : N_BEFORE probe packets, no cross-traffic
#   Phase 2 (after change): N_AFTER probe packets, cross-traffic active
#
# The cross-traffic sender starts at CHANGE_TIME seconds, which is set
# comfortably after the expected arrival of N_BEFORE packets at the
# configured mean inter-packet interval of INTERVAL_MEAN ms.
#
# The analysis script (detection_experiment.py) splits the output at
# index N_BEFORE: samples before that index build the reference PMF;
# samples from that index onward are streamed through the identity tester.
#
# Distributions : normal, lognormal, weibull
# CT levels     : 20%, 40%, 60%, 80%
# Output        : results/detection-changeover/{dist}/ct_{XX}/delay_samples.csv

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/detection-changeover"
BASE_RELPATH="../delay-monitoring/results/detection-changeover"

DISTRIBUTIONS=("normal" "lognormal" "weibull")
CT_RATES=("0.2" "0.4" "0.6" "0.8")
CT_LABELS=("ct_20" "ct_40" "ct_60" "ct_80")

# sample counts — must match detection_experiment.py
N_BEFORE=61199
N_AFTER=61199
N_TOTAL=$(( N_BEFORE + N_AFTER ))

# inter-packet interval (ms) — exponential mean
INTERVAL_MEAN=1.0

QUEUE_SIZE=50  # DropTail queue depth in packets

# cross-traffic starts after expected arrival of N_BEFORE packets,
# with a 10% buffer to absorb randomness in the exponential intervals
CHANGE_TIME=$(python3 -c "
n = $N_BEFORE
interval_ms = $INTERVAL_MEAN
buffer = 1.10
print(f'{n * interval_ms / 1000.0 * buffer:.1f}')
")

echo "==================================================================="
echo "Detection changeover experiment"
echo "==================================================================="
echo "  N_BEFORE    : ${N_BEFORE}"
echo "  N_AFTER     : ${N_AFTER}"
echo "  N_TOTAL     : ${N_TOTAL}"
echo "  CHANGE_TIME : ${CHANGE_TIME}s"
echo "  Distributions: ${DISTRIBUTIONS[*]}"
echo "  CT levels    : ${CT_LABELS[*]}"
echo "==================================================================="

total=$(( ${#DISTRIBUTIONS[@]} * ${#CT_RATES[@]} ))
count=0

for dist in "${DISTRIBUTIONS[@]}"; do
    for i in "${!CT_RATES[@]}"; do
        ct_rate="${CT_RATES[$i]}"
        ct_label="${CT_LABELS[$i]}"
        count=$(( count + 1 ))

        out_dir="${BASE_DIR}/${dist}/${ct_label}"
        out_relpath="${BASE_RELPATH}/${dist}/${ct_label}"
        mkdir -p "$out_dir"

        output="${out_relpath}/delay_samples.csv"

        if [ -f "$output" ]; then
            echo "  [${count}/${total}] skip (exists): ${dist}/${ct_label}"
            continue
        fi

        echo "  [${count}/${total}] dist=${dist}  CT=${ct_label}  change_time=${CHANGE_TIME}s"

        (cd "$NS3_DIR" && ./ns3 run \
            "scratch/delay-monitoring/single-hop-underlying-network \
            --delayDist=${dist} \
            --numPackets=${N_TOTAL} \
            --crossTrafficMode=true \
            --crossTrafficRate=${ct_rate} \
            --crossTrafficStartTime=${CHANGE_TIME} \
            --queueSize=${QUEUE_SIZE} \
            --outputFile=${output}" 2>/dev/null)
    done
done

echo ""
echo "Done. Results written to ${BASE_DIR}/"
