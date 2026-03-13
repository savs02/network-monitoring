#!/bin/bash
#
# Run from: network-monitoring/ (repo root)
#
# Runs the sample complexity experiment for each bin size in BIN_SIZES.
# For each bin size, n_theory = ceil((k + log(1/epsilon)) / delta^2) is
# recomputed (k = GRID_MAX / bin_size), and samples sizes n/4, n/2, n, 2n
# are derived from it.
#
# Results go to: delay-monitoring/results/bin-size-experiment/bin_{size}ms/

set -e

NS3_DIR="ns-3.46"
BASE_DIR="delay-monitoring/results/bin-size-experiment"
BASE_RELPATH="../delay-monitoring/results/bin-size-experiment"

DISTRIBUTIONS=("lognormal" "normal" "weibull")
BIN_SIZES=("1" "2" "5" "10")

GRID_MAX=150
EPSILON=0.05
DELTA=0.05

# count total runs up front for progress display
total=$(( ${#BIN_SIZES[@]} * ${#DISTRIBUTIONS[@]} * 4 ))
count=0

for bin_size in "${BIN_SIZES[@]}"; do

    # compute k and the four sample sizes using python
    read -r k n1 n2 n3 n4 < <(python3 -c "
import math
k        = int($GRID_MAX / $bin_size)
n_theory = math.ceil((k + math.log(1 / $EPSILON)) / ($DELTA ** 2))
print(k, n_theory // 4, n_theory // 2, n_theory, n_theory * 2)
")

    bin_dir="${BASE_DIR}/bin_${bin_size}ms"
    bin_relpath="${BASE_RELPATH}/bin_${bin_size}ms"
    mkdir -p "$bin_dir"

    echo ""
    echo "=== bin_size=${bin_size}ms  k=${k}  sample sizes: ${n1} ${n2} ${n3} ${n4} ==="

    for dist in "${DISTRIBUTIONS[@]}"; do
        for n in "$n1" "$n2" "$n3" "$n4"; do
            count=$(( count + 1 ))
            output="${bin_relpath}/delay_samples_${dist}_${n}.csv"
            echo "  [${count}/${total}] dist=${dist}  n=${n}"

            (cd "$NS3_DIR" && ./ns3 run \
                "scratch/delay-monitoring/single-hop-underlying-network \
                --delayDist=${dist} \
                --numPackets=${n} \
                --outputFile=${output}" 2>/dev/null)
        done
    done
done

echo ""
echo "Done. Results written to ${BASE_DIR}/"
