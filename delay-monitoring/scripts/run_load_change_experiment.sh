#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Load change experiment.
#
# Models increasing link utilisation by scaling the mean of the existing
# delay distributions (Normal, Lognormal, Weibull) using the M/M/1
# mean-delay formula:
#
#     mean(rho) = base_mean / (1 - rho)
#
# Three load windows are simulated for each distribution:
#   before : rho = 0.1  (low load  — baseline)
#   during : rho = 0.5  (mid load  — load is ramping up)
#   after  : rho = 0.8  (high load — congested)
#
# The monitor collects n_theory = 61,199 packets per window (the
# theoretical sample bound at k=150, epsilon=0.05, delta=0.05).
#
# Distribution base parameters (chosen so all means stay within 150ms grid):
#   Normal    : base_mean = 10 ms,  variance = 1 ms^2  (fixed)
#   Lognormal : base mu   = 1.5,    sigma    = 0.3     (fixed)
#                 -> mean(rho) achieved by adjusting mu: mu(rho) = mu_0 + ln(1/(1-rho))
#   Weibull   : base_scale= 5  ms,  shape    = 2.0     (fixed)
#                 -> mean(rho) achieved by scaling: scale(rho) = base_scale / (1-rho)
#
# Resulting means:
#   rho=0.1:  Normal=11.1ms  Lognormal=5.3ms  Weibull=4.9ms
#   rho=0.5:  Normal=20ms    Lognormal=9.5ms  Weibull=8.9ms
#   rho=0.8:  Normal=50ms    Lognormal=23.6ms Weibull=22.1ms
#
# Packet loss is disabled for this experiment.
# Results: delay-monitoring/results/load-change/

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/load-change"
BASE_RELPATH="../delay-monitoring/results/load-change"

N_THEORY=61199

LOAD_LEVELS=("0.1" "0.5" "0.8")
LOAD_LABELS=("before" "during" "after")

# base parameters at rho -> 0
BASE_NORMAL_MEAN=10.0
BASE_NORMAL_VAR=1.0

BASE_LN_MU=1.5
BASE_LN_SIGMA=0.3

BASE_WB_SCALE=5.0
BASE_WB_SHAPE=2.0

mkdir -p "$BASE_DIR"

total=$(( ${#LOAD_LEVELS[@]} * 3 ))  # 3 distributions
count=0

echo "Load change experiment"
echo "  Windows: before(rho=0.1)  during(rho=0.5)  after(rho=0.8)"
echo "  n_theory = ${N_THEORY} per window"
echo ""

for i in "${!LOAD_LEVELS[@]}"; do
    rho="${LOAD_LEVELS[$i]}"
    label="${LOAD_LABELS[$i]}"

    window_dir="${BASE_DIR}/${label}"
    window_relpath="${BASE_RELPATH}/${label}"
    mkdir -p "$window_dir"

    echo "=== ${label} (rho=${rho}) ==="

    # ---- Normal ----
    normal_mean=$(python3 -c "print(f'{$BASE_NORMAL_MEAN / (1 - $rho):.4f}')")
    count=$(( count + 1 ))
    echo "  [${count}/${total}] normal  mean=${normal_mean}ms"
    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --delayDist=normal \
        --normal_mean=${normal_mean} \
        --normal_variance=${BASE_NORMAL_VAR} \
        --numPackets=${N_THEORY} \
        --lossRate=0.0 \
        --outputFile=${window_relpath}/delay_samples_normal_${N_THEORY}.csv" 2>/dev/null)

    # ---- Lognormal ----
    # mean of Lognormal = exp(mu + sigma^2/2), so mu(rho) = ln(base_mean/(1-rho)) - sigma^2/2
    # equivalently: mu(rho) = mu_0 + ln(1/(1-rho))
    ln_mu=$(python3 -c "import math; print(f'{$BASE_LN_MU + math.log(1/(1-$rho)):.4f}')")
    count=$(( count + 1 ))
    echo "  [${count}/${total}] lognormal  mu=${ln_mu}"
    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --delayDist=lognormal \
        --lognormal_mu=${ln_mu} \
        --lognormal_sigma=${BASE_LN_SIGMA} \
        --numPackets=${N_THEORY} \
        --lossRate=0.0 \
        --outputFile=${window_relpath}/delay_samples_lognormal_${N_THEORY}.csv" 2>/dev/null)

    # ---- Weibull ----
    wb_scale=$(python3 -c "print(f'{$BASE_WB_SCALE / (1 - $rho):.4f}')")
    count=$(( count + 1 ))
    echo "  [${count}/${total}] weibull  scale=${wb_scale}ms"
    (cd "$NS3_DIR" && ./ns3 run \
        "scratch/delay-monitoring/single-hop-underlying-network \
        --delayDist=weibull \
        --weibull_scale=${wb_scale} \
        --weibull_shape=${BASE_WB_SHAPE} \
        --numPackets=${N_THEORY} \
        --lossRate=0.0 \
        --outputFile=${window_relpath}/delay_samples_weibull_${N_THEORY}.csv" 2>/dev/null)

    echo ""
done

echo "Done. Results written to ${BASE_DIR}/"
