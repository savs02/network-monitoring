#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Multi-seed bin size experiment for continuous distributions.
# Extends run_bin_size_experiment.sh by varying --RngRun across 30 seeds.
#
# For each bin size, n_theory = ceil((k + log(1/epsilon)) / delta^2),
# and sample sizes n/4, n/2, n, 2n are derived from it.
#
# Output files: bin_{size}ms/delay_samples_{dist}_{n}_seed{seed}.csv
# Results go to: delay-monitoring/results/bin-size-experiment/bin_{size}ms/
#
# If a file already exists it is skipped, so interrupted runs can be resumed.

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/bin-size-experiment"
BASE_RELPATH="../delay-monitoring/results/bin-size-experiment"

DISTRIBUTIONS=("lognormal" "normal" "weibull")
BIN_SIZES=("1" "2" "5" "10")
SEEDS=($(seq 1 30))

GRID_MAX=150
EPSILON=0.05
DELTA=0.05

total=$(( ${#BIN_SIZES[@]} * ${#DISTRIBUTIONS[@]} * 5 * ${#SEEDS[@]} ))
count=0

for bin_size in "${BIN_SIZES[@]}"; do

    read -r k n1 n2 n3 n4 n5 < <(python3 -c "
import math
k        = int($GRID_MAX / $bin_size)
n_theory = math.ceil((k + math.log(1 / $EPSILON)) / ($DELTA ** 2))
print(k, n_theory // 4, n_theory // 2, n_theory, n_theory * 2, n_theory * 4)
")

    bin_dir="${BASE_DIR}/bin_${bin_size}ms"
    bin_relpath="${BASE_RELPATH}/bin_${bin_size}ms"
    mkdir -p "$bin_dir"

    echo ""
    echo "=== bin_size=${bin_size}ms  k=${k}  sample sizes: ${n1} ${n2} ${n3} ${n4} ${n5} ==="

    for seed in "${SEEDS[@]}"; do
        for dist in "${DISTRIBUTIONS[@]}"; do
            for n in "$n1" "$n2" "$n3" "$n4" "$n5"; do
                count=$(( count + 1 ))
                output="${bin_relpath}/delay_samples_${dist}_${n}_seed${seed}.csv"

                if [ -f "$output" ]; then
                    echo "  [${count}/${total}] skip (exists): ${output##*/}"
                    continue
                fi

                echo "  [${count}/${total}] dist=${dist}  n=${n}  seed=${seed}"

                (cd "$NS3_DIR" && ./ns3 run \
                    "scratch/delay-monitoring/single-hop-underlying-network \
                    --delayDist=${dist} \
                    --numPackets=${n} \
                    --RngRun=${seed} \
                    --outputFile=${output}" 2>/dev/null)
            done
        done
    done
done

echo ""
echo "Done. Results written to ${BASE_DIR}/"
