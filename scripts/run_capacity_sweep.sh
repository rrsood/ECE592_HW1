#!/usr/bin/env bash
# =============================================================================
# run_capacity_sweep.sh
#
# Collects the Experiment 1 (cache levels / capacity) dataset for one machine.
#
# ECE 592 Homework I -- Phase I (timing only).
#
# WHAT IT DOES
#   1. Records the machine environment (Phase-I-safe commands only).
#   2. Characterizes the empty timer bracket.
#   3. Sweeps working-set size across a log-spaced grid, running BOTH the
#      randomized traversal (primary) and the sequential traversal (prefetcher
#      control) at every point.
#   4. Writes one gzip-compressed raw CSV plus one .meta file per run, and a
#      machine-readable manifest.json describing the whole sweep.
#
# SPEC REQUIREMENTS THIS SCRIPT IMPLEMENTS
#   - "collect at least 1,000,000 timed samples" per x-axis point  (SAMPLES)
#   - "Sweep working-set size from much smaller than expected L1 to much larger
#      than LLC, initially by powers of two and then densely around each
#      observed transition"                                        (grid + DENSE)
#   - "randomize the order of tested sizes/strides across trials to reduce drift
#      and prefetcher artifacts"                                   (point shuffle)
#   - "compare at least one regular/sequential traversal against a randomized
#      dependent traversal as a prefetcher sanity check"           (both modes)
#   - "Bind the benchmark to one logical CPU and record CPU, core, socket/
#      package, and NUMA node"                                     (taskset + manifest)
#   - "Raw data may be losslessly compressed"                      (gzip)
#   - "Record the environment"                                     (record_environment.sh)
#
# USAGE
#   ./run_capacity_sweep.sh <machine_name> <logical_cpu> <output_root> [mode]
#
#     machine_name   e.g. sunbird        (names the output directory)
#     logical_cpu    e.g. 4              (taskset target; pick an idle core
#                                         whose SMT sibling is also idle)
#     output_root    e.g. data_raw       (per spec section 14 layout)
#     mode           coarse | dense | full     (default: coarse)
#                      coarse = 2 points/octave, for the first pass
#                      dense  = 8 points/octave over ranges named in DENSE_RANGES
#                      full   = coarse grid plus the dense ranges
#
# TYPICAL WORKFLOW
#   # pass 1: locate the boundaries approximately
#   ./run_capacity_sweep.sh sunbird 4 data_raw coarse
#   # inspect the plot, then edit DENSE_RANGES below to bracket each observed
#   # step, and:
#   ./run_capacity_sweep.sh sunbird 4 data_raw dense
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------
MACHINE="${1:?usage: $0 <machine_name> <logical_cpu> <output_root> [mode]}"
CPU="${2:?missing logical_cpu}"
OUT_ROOT="${3:?missing output_root}"
MODE="${4:-coarse}"

# -----------------------------------------------------------------------------
# Tunable parameters
# -----------------------------------------------------------------------------

# Samples per x-axis point. The spec REQUIRES >= 1,000,000.
# Override for smoke tests only, and never for reported data.
SAMPLES="${SAMPLES:-1000000}"

# Dependent loads timed per sample (batching, Pillar 3).
#
# Choosing N -- the tradeoff the spec describes as "large enough that timer/
# fence overhead and counter resolution are small relative to the total
# interval, while preserving the cache state you intend to measure":
#   - The empty bracket costs ~40-70 TSC ticks (measure it; timer_overhead.c
#     writes the distribution). At N=1000 that is <0.07 ticks/access, about 1.5%
#     of a ~4-tick L1 hit and invisible against DRAM.
#   - Total accesses per point = N * SAMPLES = 1e9. At an L1-resident ~4 ticks
#     that is a few seconds; at a DRAM-resident ~250 ticks roughly 2 minutes on
#     a ~2 GHz part. Budget accordingly: the DRAM-side points dominate runtime.
#   - N may exceed the node count; the chase simply laps the ring, which is
#     exactly the steady state we want to measure.
NPB="${NPB:-1000}"

# RNG seed for the shuffle. Recorded in every manifest; keep it FIXED across a
# machine's runs so the traversal order is reproducible, and record any change.
SEED="${SEED:-20260904}"

# Node spacing in bytes.
#
# IMPORTANT: this is provisional on the first pass. The capacity result is only
# calibrated once spacing == the measured line size B (see the footprint
# discussion in cache_bench.c section 3). Workflow:
#   pass 1: run with SPACING=64 (a common value, explicitly provisional)
#   then:   run the line-size experiment to measure B
#   pass 2: re-run this sweep with SPACING=B -- those are the REPORTED numbers
# The manifest records which pass a dataset came from.
SPACING="${SPACING:-64}"

# Sweep bounds. Must span "much smaller than expected L1 to much larger than
# LLC". 4 KiB to 512 MiB is deliberately generous at both ends.
MIN_BYTES="${MIN_BYTES:-4096}"
MAX_BYTES="${MAX_BYTES:-536870912}"

# Points per octave (a doubling) for the coarse grid.
COARSE_PER_OCTAVE="${COARSE_PER_OCTAVE:-2}"

# Points per octave for dense sampling near a suspected boundary.
DENSE_PER_OCTAVE="${DENSE_PER_OCTAVE:-8}"

# Ranges to sample densely, as "low_bytes:high_bytes" pairs.
# EDIT THIS after the coarse pass to bracket each observed step. The defaults
# bracket generic regions and are intentionally NOT tuned to any known machine.
DENSE_RANGES="${DENSE_RANGES:-16384:131072 131072:2097152 2097152:33554432}"

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BIN_DIR="$OUT_ROOT/$MACHINE/build"
EXP_DIR="$OUT_ROOT/$MACHINE/capacity/raw"
mkdir -p "$BIN_DIR" "$EXP_DIR"

BENCH="$BIN_DIR/cache_bench"
OVERHEAD="$BIN_DIR/timer_overhead"

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"

# -----------------------------------------------------------------------------
# Preflight
# -----------------------------------------------------------------------------
command -v taskset >/dev/null 2>&1 || {
    echo "ERROR: taskset not found. CPU pinning is mandatory per the spec." >&2
    exit 1
}

if [ "$SAMPLES" -lt 1000000 ]; then
    echo "WARNING: SAMPLES=$SAMPLES is below the spec-required 1,000,000." >&2
    echo "         Acceptable for a smoke test ONLY -- never for reported data." >&2
fi

# Build if the binaries are missing or older than their sources.
if [ ! -x "$BENCH" ] || [ "$REPO_ROOT/main_code/x86_64/cache_bench.c" -nt "$BENCH" ]; then
    echo "Building benchmarks ..."
    "$SCRIPT_DIR/build.sh" "$REPO_ROOT/main_code/x86_64" "$BIN_DIR"
fi

# -----------------------------------------------------------------------------
# 1. Record the environment (Phase-I-safe commands only)
# -----------------------------------------------------------------------------
echo "== Recording environment =="
"$SCRIPT_DIR/record_environment.sh" "$OUT_ROOT/$MACHINE/environment_$TIMESTAMP.txt"

# Capture the topology row for the pinned CPU, so core/socket/NUMA land in the
# manifest as the spec requires ("record CPU, core, socket/package, and NUMA
# node"). Field-restricted lscpu -- no cache columns.
TOPO_ROW="$(lscpu -e=CPU,CORE,SOCKET,NODE 2>/dev/null | awk -v c="$CPU" 'NR>1 && $1==c {print}')"
CORE_ID="$(echo   "$TOPO_ROW" | awk '{print $2}')"
SOCKET_ID="$(echo "$TOPO_ROW" | awk '{print $3}')"
NUMA_ID="$(echo   "$TOPO_ROW" | awk '{print $4}')"

# Identify SMT siblings of the pinned core, so the report can state whether they
# were idle (spec: "report whether SMT siblings or other users may have
# interfered").
SMT_SIBLINGS="$(lscpu -e=CPU,CORE 2>/dev/null \
                | awk -v k="$CORE_ID" 'NR>1 && $2==k {printf "%s ", $1}')"

echo "  pinned CPU=$CPU core=$CORE_ID socket=$SOCKET_ID numa=$NUMA_ID"
echo "  SMT siblings on this core: ${SMT_SIBLINGS:-unknown}"

# -----------------------------------------------------------------------------
# 2. Characterize the empty timer bracket
# -----------------------------------------------------------------------------
echo "== Measuring empty timer bracket =="
taskset -c "$CPU" "$OVERHEAD" "$SAMPLES" \
    2> "$EXP_DIR/timer_overhead_${MACHINE}_${TIMESTAMP}.meta" \
    | gzip -9 > "$EXP_DIR/timer_overhead_${MACHINE}_${TIMESTAMP}.csv.gz"

# -----------------------------------------------------------------------------
# 3. Build the sweep grid
# -----------------------------------------------------------------------------
# Log-spaced points, each snapped DOWN to a multiple of SPACING so cache_bench's
# divisibility check passes and the x-axis label equals the traversed footprint.
# Duplicates (which log spacing can produce at small sizes) are removed.
gen_grid() {
    local lo="$1" hi="$2" per_octave="$3"
    python3 - "$lo" "$hi" "$per_octave" "$SPACING" <<'PYEOF'
import sys, math
lo, hi, per_oct, spacing = (int(x) for x in sys.argv[1:5])
n_oct = math.log2(hi / lo)
n_pts = max(1, int(round(n_oct * per_oct)))
out = []
for i in range(n_pts + 1):
    v = lo * (2.0 ** (i * n_oct / n_pts))
    v = int(v) // spacing * spacing        # snap DOWN to a spacing multiple
    if v >= spacing * 2:                   # need >= 2 nodes to form a cycle
        out.append(v)
for v in sorted(set(out)):
    print(v)
PYEOF
}

POINTS=""
case "$MODE" in
    coarse)
        POINTS="$(gen_grid "$MIN_BYTES" "$MAX_BYTES" "$COARSE_PER_OCTAVE")"
        ;;
    dense)
        for range in $DENSE_RANGES; do
            lo="${range%%:*}"; hi="${range##*:}"
            POINTS="$POINTS
$(gen_grid "$lo" "$hi" "$DENSE_PER_OCTAVE")"
        done
        ;;
    full)
        POINTS="$(gen_grid "$MIN_BYTES" "$MAX_BYTES" "$COARSE_PER_OCTAVE")"
        for range in $DENSE_RANGES; do
            lo="${range%%:*}"; hi="${range##*:}"
            POINTS="$POINTS
$(gen_grid "$lo" "$hi" "$DENSE_PER_OCTAVE")"
        done
        ;;
    *)
        echo "ERROR: unknown mode '$MODE' (expected coarse|dense|full)" >&2
        exit 1
        ;;
esac

POINTS="$(echo "$POINTS" | grep -v '^$' | sort -n -u)"
N_POINTS="$(echo "$POINTS" | wc -l)"
echo "== Sweep grid: $N_POINTS points, mode=$MODE, spacing=${SPACING}B =="

# -----------------------------------------------------------------------------
# 4. Build the run list and SHUFFLE it
# -----------------------------------------------------------------------------
# Spec: "when feasible, randomize the order of tested sizes/strides across
# trials to reduce drift and prefetcher artifacts."
#
# Why this matters: if points ran in ascending size order, any slow drift in
# machine conditions (another user's job starting, thermal changes, DVFS
# residency shifting) would correlate with working-set size and could masquerade
# as a capacity step. Randomizing the execution order decorrelates drift from
# the x-axis, so such an artifact shows up as scatter rather than a fake edge.
RUNLIST=""
for ws in $POINTS; do
    RUNLIST="$RUNLIST$ws 0"$'\n'      # 0 = randomized traversal (primary)
    RUNLIST="$RUNLIST$ws 1"$'\n'      # 1 = sequential traversal (control)
done
RUNLIST="$(echo "$RUNLIST" | grep -v '^$' | shuf --random-source=<(yes "$SEED"))"

TOTAL_RUNS="$(echo "$RUNLIST" | wc -l)"
echo "== $TOTAL_RUNS runs queued (each point x2 traversal modes), order shuffled =="

# -----------------------------------------------------------------------------
# 5. Execute
# -----------------------------------------------------------------------------
RUN_IDX=0
SWEEP_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

while read -r ws seq; do
    RUN_IDX=$((RUN_IDX + 1))
    [ -z "$ws" ] && continue

    if [ "$seq" -eq 0 ]; then order="rand"; else order="seq"; fi
    stem="capacity_ws${ws}_sp${SPACING}_${order}_${MACHINE}_${TIMESTAMP}"

    printf "[%3d/%3d] ws=%-11s order=%-4s ... " "$RUN_IDX" "$TOTAL_RUNS" "$ws" "$order"
    t0=$(date +%s)

    # taskset pins the process to one logical CPU. The first-touch memset inside
    # cache_bench then runs already-pinned, so pages land on the local NUMA node.
    taskset -c "$CPU" "$BENCH" "$ws" "$SPACING" "$NPB" "$SAMPLES" "$SEED" "$seq" \
        2> "$EXP_DIR/$stem.meta" \
        | gzip -9 > "$EXP_DIR/$stem.csv.gz"

    t1=$(date +%s)
    echo "done ($((t1 - t0))s)"
done <<< "$RUNLIST"

SWEEP_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# -----------------------------------------------------------------------------
# 6. Write the sweep manifest
# -----------------------------------------------------------------------------
# Machine-readable record tying every raw file to the exact conditions that
# produced it. Per-run details live in each .meta file (auto-emitted by the
# benchmark); this manifest describes the sweep as a whole.
GIT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo 'not_a_git_repo')"
GIT_DIRTY="$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | wc -l)"

cat > "$EXP_DIR/manifest_${TIMESTAMP}.json" <<EOF
{
  "machine": "$MACHINE",
  "experiment": "capacity",
  "sweep_mode": "$MODE",
  "phase": "I_timing_only",

  "pinning": {
    "logical_cpu": $CPU,
    "core": "${CORE_ID:-unknown}",
    "socket": "${SOCKET_ID:-unknown}",
    "numa_node": "${NUMA_ID:-unknown}",
    "smt_siblings": "${SMT_SIBLINGS:-unknown}",
    "method": "taskset -c $CPU"
  },

  "parameters": {
    "node_spacing_bytes": $SPACING,
    "spacing_is_provisional": "TRUE until the line-size experiment confirms B; re-run with SPACING=B for reported values",
    "N_per_batch": $NPB,
    "samples_per_point": $SAMPLES,
    "seed": $SEED,
    "min_bytes": $MIN_BYTES,
    "max_bytes": $MAX_BYTES,
    "num_points": $N_POINTS,
    "total_runs": $TOTAL_RUNS,
    "traversal_modes": ["randomized_primary", "sequential_control"],
    "run_order": "shuffled (seed $SEED) to decorrelate drift from working-set size"
  },

  "timing": {
    "timer_method": "lfence;rdtscp;lfence / rdtscp;lfence",
    "units": "TSC ticks (NOT core clock cycles)",
    "empty_bracket_dataset": "timer_overhead_${MACHINE}_${TIMESTAMP}.csv.gz",
    "overhead_handling": "characterized, NOT subtracted; amortized by batching"
  },

  "memory": {
    "locality_method": "first-touch memset after taskset pinning",
    "buffer_alignment_bytes": 4096,
    "kernel_type": "read-only dependent pointer chase"
  },

  "build": {
    "compiler": "$(gcc --version | head -1)",
    "flags": "-O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer",
    "build_log": "../../build/build_log.txt",
    "disassembly": "../../build/critical_loop_chase.asm"
  },

  "provenance": {
    "git_commit": "$GIT_COMMIT",
    "git_uncommitted_files": $GIT_DIRTY,
    "sweep_start_utc": "$SWEEP_START",
    "sweep_end_utc": "$SWEEP_END",
    "environment_record": "../../environment_$TIMESTAMP.txt",
    "raw_file_pattern": "capacity_ws<BYTES>_sp<SPACING>_<rand|seq>_${MACHINE}_${TIMESTAMP}.csv.gz",
    "excluded_runs": []
  }
}
EOF

echo
echo "== Sweep complete =="
echo "  Raw data: $EXP_DIR"
echo "  Manifest: $EXP_DIR/manifest_${TIMESTAMP}.json"
echo
echo "Next: process and plot with"
echo "  python3 scripts/process_capacity.py $EXP_DIR $OUT_ROOT/$MACHINE/capacity/processed"
echo "  python3 scripts/plot_capacity.py $OUT_ROOT/$MACHINE/capacity/processed plots/"
