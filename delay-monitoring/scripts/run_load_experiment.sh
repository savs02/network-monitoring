#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Load / remaining-capacity experiment.
#
# Models a single-hop link under increasing utilisation using an M/M/1
# queuing model.  The sojourn time of a packet in an M/M/1 queue is
# exponentially distributed with mean:
#
#     mean_delay = base_delay / (1 - rho)
#
# where rho is the link utilisation (0 = idle, 1 = fully loaded) and
# base_delay is the mean delay at very low load (service time).
#
# The monitor collects n_theory packets at each load level — the same
# theoretical sample bound established in earlier experiments — and
# builds an empirical delay distribution.  From the observed mean the
# monitor estimates:
#
#     rho_est        = 1 - base_delay / mean_observed
#     remaining_cap  = link_capacity * (1 - rho_est)
#
# Packet loss is disabled (lossRate=0) for this experiment.
#
# Parameters
#   base_delay  = 5 ms   (mean delay at rho -> 0, i.e. the service time)
#   rho levels  = 0.1  0.2  0.4  0.6  0.8
#   mean delays = 5.56 6.25 8.33 12.5 25.0  ms
#   n_theory    = 61199  (k=150, epsilon=0.05, delta=0.05)
#
# Results: delay-monitoring/results/load-experiment/load_{rho}/

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/load-experiment"
BASE_RELPATH="../delay-monitoring/results/load-experiment"

BASE_DELAY=5.0          # ms — service time / low-load mean
N_THEORY=61199          # packets to transmit per load level

LOAD_LEVELS=("0.1" "0.2" "0.4" "0.6" "0.8")

mkdir -p "$BASE_DIR"

total=${#LOAD_LEVELS[@]}
count=0

echo "Load / remaining-capacity experiment"
echo "  base_delay = ${BASE_DELAY} ms"
echo "  n_theory   = ${N_THEORY}"
echo "  rho levels : ${LOAD_LEVELS[*]}"
echo ""

for rho in "${LOAD_LEVELS[@]}"; do

    # compute mean delay for this utilisation: base / (1 - rho)
    mean_delay=$(python3 -c "print(f'{$BASE_DELAY / (1 - $rho):.4f}')")

    load_tag=$(echo "$rho" | tr '.' '_')   # e.g. 0.1 -> 0_1
    load_dir="${BASE_DIR}/load_${load_tag}"
    load_relpath="${BASE_RELPATH}/load_${load_tag}"
    mkdir -p "$load_dir"

    count=$(( count + 1 ))
    echo "[${count}/${total}] rho=${rho}  mean_delay=${mean_delay}ms  n=${N_THEORY}"

    output="${load_relpath}/delay_samples_${N_THEORY}.csv"

    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --delayDist=exponential \
        --exponential_mean=${mean_delay} \
        --numPackets=${N_THEORY} \
        --lossRate=0.0 \
        --outputFile=${output}" 2>/dev/null)
done

echo ""
echo "Done. Results written to ${BASE_DIR}/"
