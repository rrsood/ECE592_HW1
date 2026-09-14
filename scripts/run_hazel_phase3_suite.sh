#!/bin/bash
# Run the complete timing-only Phase-I suite plus the software-only estimator
# on one bound Hazel compute CPU. This script must be launched by Slurm/srun.
set -euo pipefail

usage() {
  echo "usage: $0 --constraint NAME --generation NAME [--freeze-directory DIR --freeze-commit HASH | --unfrozen-run] --result-root DIR [--stage all|capacity|line-size|associativity|inclusion|eviction|software] [--conflict-strides CSV]" >&2
  exit 2
}

constraint=
generation=
freeze_directory=
freeze_commit=
result_root=
unfrozen_run=false
stage=all
conflict_strides=4096,8192,16384,32768,65536,131072,262144,524288,1048576
while [ "$#" -gt 0 ]; do
  case "$1" in
    --constraint) constraint=${2-}; shift 2 ;;
    --generation) generation=${2-}; shift 2 ;;
    --freeze-directory) freeze_directory=${2-}; shift 2 ;;
    --freeze-commit) freeze_commit=${2-}; shift 2 ;;
    --result-root) result_root=${2-}; shift 2 ;;
    --unfrozen-run) unfrozen_run=true; shift ;;
    --stage) stage=${2-}; shift 2 ;;
    --conflict-strides) conflict_strides=${2-}; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$constraint" ] && [ -n "$generation" ] && [ -n "$result_root" ] || usage
case "$stage" in
  all|capacity|line-size|associativity|inclusion|eviction|software) ;;
  *) usage ;;
esac
case "$conflict_strides" in
  ''|*[!0-9,]*) usage ;;
esac
if [ "$unfrozen_run" = false ]; then
  [ -n "$freeze_directory" ] && [ -n "$freeze_commit" ] || usage
fi

: "${SLURM_JOB_ID:?This benchmark must run inside a Slurm allocation}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
host=$(hostname -s)
case "$host" in
  login*|hazel-login*|*login*)
    echo "error: refusing to benchmark on a login node: $host" >&2
    exit 1
    ;;
esac

repo=$(git rev-parse --show-toplevel)
cd "$repo"
if [ "$unfrozen_run" = true ]; then
  freeze_status=not_frozen_at_run_time
  freeze_commit=not_available
else
  python3 scripts/verify_phase3_freeze.py \
    --freeze-directory "$freeze_directory" \
    --freeze-commit "$freeze_commit"
  freeze_status=verified_committed_freeze
fi

allowed_list=$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status)
cpu_token=${allowed_list%%,*}
cpu=${cpu_token%%-*}
case "$cpu" in
  ''|*[!0-9]*) echo "error: cannot derive bound logical CPU from $allowed_list" >&2; exit 1 ;;
esac

stage_token=$(printf '%s' "$stage" | tr '-' '_')
run_id="${constraint}_${stage_token}_${SLURM_JOB_ID}"
scratch_root=${SLURM_TMPDIR:-${TMPDIR:-/tmp}}
work="${scratch_root}/ece592_phase3_${run_id}"
case "$result_root" in
  /*) result_base=$result_root ;;
  *) result_base="${repo}/${result_root}" ;;
esac
mkdir -p "$result_base"
result="${result_base}/${run_id}"
[ ! -e "$result" ] || { echo "error: result directory already exists: $result" >&2; exit 1; }
mkdir -p "$work" "$result" "$work/plans" "$work/raw" "$work/processed" "$work/plots"

status=failed
finish() {
  rc=$?
  {
    echo "completion_status=$status"
    echo "return_code=$rc"
    echo "completion_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$result/job_metadata.tsv"
  if [ -d "$work/plans" ]; then cp -a "$work/plans" "$result/" 2>/dev/null || true; fi
  if [ -d "$work/processed" ]; then cp -a "$work/processed" "$result/" 2>/dev/null || true; fi
  if [ -d "$work/plots" ]; then cp -a "$work/plots" "$result/" 2>/dev/null || true; fi
  exit "$rc"
}
trap finish EXIT

{
  echo "ece592_hazel_phase3_job_metadata_version=1"
  echo "constraint=$constraint"
  echo "generation=$generation"
  echo "suite_stage=$stage"
  echo "conflict_strides=$conflict_strides"
  echo "slurm_job_id=$SLURM_JOB_ID"
  echo "slurm_job_name=${SLURM_JOB_NAME-unknown}"
  echo "slurm_node_list=${SLURM_JOB_NODELIST-unknown}"
  echo "hostname=$(hostname -f 2>/dev/null || hostname)"
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "benchmark_git_commit=$(git rev-parse HEAD)"
  echo "prediction_freeze_commit=$freeze_commit"
  echo "prediction_freeze_status=$freeze_status"
  echo "logical_cpu=$cpu"
  echo "allowed_cpu_list=$allowed_list"
  echo "physical_core_id=$(cat /sys/devices/system/cpu/cpu${cpu}/topology/core_id)"
  echo "physical_package_id=$(cat /sys/devices/system/cpu/cpu${cpu}/topology/physical_package_id)"
  echo "numa_node=$(ls -d /sys/devices/system/cpu/cpu${cpu}/node* 2>/dev/null | sed -n '1s/.*node//p')"
  echo "cpu_model=$(grep -m1 -E 'model name|Hardware|Processor' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
  echo "kernel=$(uname -a)"
  echo "compiler=$(gcc --version | head -n1)"
  echo "samples_per_point=1000000"
  echo "scratch_root=$scratch_root"
  echo "raw_storage=node_scratch_then_lossless_tar_gzip"
  echo "cache_labels_assigned_by_runner=false"
} > "$result/job_metadata.tsv"
lscpu -e=CPU,CORE,SOCKET,NODE > "$result/lscpu_topology.txt"

exe="$work/cache_bench"
bash scripts/build_phase1.sh "$exe" > "$result/build.log"
cp "${exe}.build-command.txt" "$result/build-command.txt"
objdump -d -S "$exe" > "$result/cache_bench.source.dis"
if [ "$(uname -m)" = x86_64 ]; then
  objdump -d -Mintel "$exe" > "$result/cache_bench.intel.dis"
fi
environment="Phase III Hazel timing-only held-out run; Slurm job ${SLURM_JOB_ID}; constraint ${constraint}; bound CPU ${cpu}"
smt=not-applicable
samples=1000000

if [ "$stage" = all ] || [ "$stage" = capacity ]; then
mkdir -p "$work/raw/capacity" "$work/processed/capacity" "$work/plots/capacity"
python3 scripts/generate_capacity_plan.py \
  --min-bytes 4096 --max-bytes 268435456 --points-per-octave 4 \
  --trials 2 --seed 81592 --node-spacing-bytes 8 --node-bytes 8 \
  --output "$work/plans/capacity_coarse.tsv"
for traversal in randomized sequential; do
  run_dir="$work/raw/capacity/coarse_${traversal}"
  python3 scripts/run_capacity_plan.py \
    --plan "$work/plans/capacity_coarse.tsv" --benchmark "$exe" \
    --build-command-file "${exe}.build-command.txt" --output-directory "$run_dir" \
    --machine "$constraint" --experiment "hazel-phase3-capacity-coarse-${traversal}" \
    --cpu "$cpu" --batch 256 --warmup 1000 --samples "$samples" \
    --traversal "$traversal" --smt-siblings-idle "$smt" \
    --environment-variables "$environment"
  python3 scripts/process_capacity_run.py --run-directory "$run_dir" \
    --output "$work/processed/capacity/coarse_${traversal}.tsv"
done
python3 scripts/analyze_capacity_transitions.py \
  --input "$work/processed/capacity/coarse_randomized.tsv" \
  --output "$work/processed/capacity/coarse_transitions.tsv"
python3 scripts/generate_dense_capacity_plan.py \
  --transitions "$work/processed/capacity/coarse_transitions.tsv" \
  --top-k 6 --padding-factor 1.25 --points-per-octave 8 --trials 2 \
  --seed 82592 --node-spacing-bytes 8 --node-bytes 8 \
  --output "$work/plans/capacity_dense.tsv"
python3 scripts/run_capacity_plan.py \
  --plan "$work/plans/capacity_dense.tsv" --benchmark "$exe" \
  --build-command-file "${exe}.build-command.txt" \
  --output-directory "$work/raw/capacity/dense_randomized" \
  --machine "$constraint" --experiment hazel-phase3-capacity-dense-randomized \
  --cpu "$cpu" --batch 256 --warmup 1000 --samples "$samples" \
  --traversal randomized --smt-siblings-idle "$smt" \
  --environment-variables "$environment"
python3 scripts/process_capacity_run.py \
  --run-directory "$work/raw/capacity/dense_randomized" \
  --output "$work/processed/capacity/dense_randomized.tsv"
python3 scripts/analyze_capacity_transitions.py \
  --input "$work/processed/capacity/dense_randomized.tsv" \
  --output "$work/processed/capacity/dense_transitions.tsv"
python3 scripts/compare_capacity_candidates.py \
  --coarse "$work/processed/capacity/coarse_transitions.tsv" \
  --dense "$work/processed/capacity/dense_transitions.tsv" --top-count 6 \
  --output "$work/processed/capacity/candidate_comparison.tsv"
python3 scripts/make_capacity_evidence_summary.py \
  --candidate-comparison "$work/processed/capacity/candidate_comparison.tsv" \
  --top-count 4 --output "$work/processed/capacity/evidence_summary.tsv"

mkdir -p "$work/processed/latency" "$work/plots/latency"
python3 scripts/select_latency_points.py \
  --processed-capacity "$work/processed/capacity/dense_randomized.tsv" \
  --capacity-evidence "$work/processed/capacity/evidence_summary.tsv" \
  --top-count 4 --output "$work/processed/latency/hit_representatives.tsv"
python3 scripts/make_miss_latency_evidence.py \
  --latency-representatives "$work/processed/latency/hit_representatives.tsv" \
  --output "$work/processed/latency/miss_next_level_evidence.tsv"
fi

if [ "$stage" = all ] || [ "$stage" = line-size ]; then
mkdir -p "$work/raw/line_size" "$work/processed/line_size" "$work/plots/line_size"
python3 scripts/generate_spatial_plan.py \
  --region-count 4099 --region-spacing-bytes 512 \
  --probe-offsets 8,16,24,32,40,48,56,64,72,80,96,112,120,128,136,144,160,192,224,248,256,264,288,320,384,504 \
  --trials 2 --seed 83592 --output "$work/plans/line_size.tsv"
python3 scripts/run_spatial_plan.py \
  --plan "$work/plans/line_size.tsv" --benchmark "$exe" \
  --build-command-file "${exe}.build-command.txt" \
  --output-directory "$work/raw/line_size/spatial_randomized" \
  --machine "$constraint" --experiment hazel-phase3-line-size \
  --cpu "$cpu" --batch 256 --warmup 1000 --samples "$samples" \
  --smt-siblings-idle "$smt" --environment-variables "$environment"
python3 scripts/process_spatial_run.py \
  --run-directory "$work/raw/line_size/spatial_randomized" \
  --output "$work/processed/line_size/spatial_randomized.tsv"
fi

if [ "$stage" = all ] || [ "$stage" = associativity ]; then
mkdir -p "$work/raw/associativity" "$work/processed/associativity" "$work/plots/associativity"
python3 scripts/generate_conflict_plan.py \
  --conflict-strides "$conflict_strides" \
  --line-counts 2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32 \
  --trials 2 --seed 84592 --output "$work/plans/associativity.tsv"
python3 scripts/run_conflict_plan.py \
  --plan "$work/plans/associativity.tsv" --benchmark "$exe" \
  --build-command-file "${exe}.build-command.txt" \
  --output-directory "$work/raw/associativity/conflict_randomized" \
  --machine "$constraint" --experiment hazel-phase3-associativity \
  --cpu "$cpu" --batch 256 --warmup 1000 --samples "$samples" \
  --smt-siblings-idle "$smt" --environment-variables "$environment"
python3 scripts/process_conflict_run.py \
  --run-directory "$work/raw/associativity/conflict_randomized" \
  --output "$work/processed/associativity/conflict_randomized.tsv"
fi

if [ "$stage" = all ] || [ "$stage" = inclusion ]; then
mkdir -p "$work/raw/inclusion" "$work/processed/inclusion" "$work/plots/inclusion"
python3 scripts/generate_inclusion_plan.py \
  --probe-nodes 2048,8192,32768,131072,524288 \
  --pressure-nodes 4096,32768,262144,2097152,8388608 \
  --node-spacing 8 --probe-batch 256 --pressure-batch 4096 \
  --trials 2 --seed 85592 --output "$work/plans/inclusion.tsv"
python3 scripts/run_inclusion_plan.py \
  --plan "$work/plans/inclusion.tsv" --benchmark "$exe" \
  --build-command-file "${exe}.build-command.txt" \
  --output-directory "$work/raw/inclusion/reuse_randomized" \
  --machine "$constraint" --experiment hazel-phase3-inclusion-reuse \
  --cpu "$cpu" --warmup 1000 --samples "$samples" \
  --smt-siblings-idle "$smt" --environment-variables "$environment"
python3 scripts/process_inclusion_run.py \
  --run-directory "$work/raw/inclusion/reuse_randomized" \
  --output "$work/processed/inclusion/reuse_randomized.tsv"
fi

if [ "$stage" = all ] || [ "$stage" = eviction ]; then
mkdir -p "$work/raw/eviction" "$work/processed/eviction" "$work/plots/eviction"
offset_set() {
  awk -v start="$1" -v count="$2" -v stride="$3" 'BEGIN { for (i=0;i<count;i++) printf "%s%d", (i ? "," : ""), (start+i)*stride }'
}
target_a=$(offset_set 0 8 65536)
target_b=$(offset_set 0 8 65536 | awk -F, 'BEGIN {OFS=","} {for(i=1;i<=NF;i++)$i+=32768; print}')
pressure_small=$(offset_set 8 1025 65536)
pressure_large=$(offset_set 8 4096 65536)
python3 scripts/generate_eviction_plan.py \
  --target-offset-sets "${target_a};${target_b}" \
  --pressure-offset-sets "${pressure_small};${pressure_large}" \
  --trials 2 --seed 86592 --output "$work/plans/eviction.tsv"
python3 scripts/run_eviction_plan.py \
  --plan "$work/plans/eviction.tsv" --benchmark "$exe" \
  --build-command-file "${exe}.build-command.txt" \
  --output-directory "$work/raw/eviction/cross_level_randomized" \
  --machine "$constraint" --experiment hazel-phase3-cross-level-eviction \
  --cpu "$cpu" --warmup 1000 --samples "$samples" \
  --smt-siblings-idle "$smt" --environment-variables "$environment"
python3 scripts/process_eviction_run.py \
  --run-directory "$work/raw/eviction/cross_level_randomized" \
  --output "$work/processed/eviction/cross_level_randomized.tsv"
fi

if [ "$stage" = all ] || [ "$stage" = software ]; then
mkdir -p "$work/raw/software_hit_rate" "$work/processed/software_hit_rate"
for specification in "l1_resident 2048 87592" "standardized_8mib 1048576 88592" "nonresident_256mib 33554432 89592"; do
  set -- $specification
  "$exe" --mode capacity --cpu "$cpu" --nodes "$2" --spacing 8 \
    --traversal randomized --batch 8 --warmup 1000 --samples "$samples" \
    --seed "$3" --experiment "hazel-phase3-software-residency-$1" \
    --output "$work/raw/software_hit_rate/$1.tsv" \
    --build-command "$(cat "${exe}.build-command.txt")" \
    --smt-siblings-idle "$smt" --environment-variables "$environment"
done
for target in l1_resident standardized_8mib nonresident_256mib; do
  python3 software_hit_rate/estimate_hit_rate.py \
    --hit-calibration "$work/raw/software_hit_rate/l1_resident.tsv" \
    --miss-calibration "$work/raw/software_hit_rate/nonresident_256mib.tsv" \
    --target "$work/raw/software_hit_rate/${target}.tsv" \
    --output "$work/processed/software_hit_rate/${target}.tsv"
done
fi

if command -v gnuplot >/dev/null 2>&1; then
  if [ "$stage" = all ] || [ "$stage" = capacity ]; then
    python3 scripts/plot_capacity_curve.py --input "$work/processed/capacity/coarse_randomized.tsv" --output "$work/plots/capacity/coarse_randomized.pdf"
    python3 scripts/plot_capacity_curve.py --input "$work/processed/capacity/dense_randomized.tsv" --output "$work/plots/capacity/dense_randomized.pdf"
    python3 scripts/plot_capacity_prefetch_control.py --randomized "$work/processed/capacity/coarse_randomized.tsv" --sequential "$work/processed/capacity/coarse_sequential.tsv" --output "$work/plots/capacity/prefetch_control.pdf"
    python3 scripts/plot_latency_boxplots.py --input "$work/processed/latency/hit_representatives.tsv" --output "$work/plots/latency/hit_representatives.pdf"
  fi
  if [ "$stage" = all ] || [ "$stage" = line-size ]; then
    python3 scripts/plot_spatial_curve.py --input "$work/processed/line_size/spatial_randomized.tsv" --output "$work/plots/line_size/spatial_randomized.pdf"
  fi
  if [ "$stage" = all ] || [ "$stage" = associativity ]; then
    python3 scripts/plot_conflict_curve.py --input "$work/processed/associativity/conflict_randomized.tsv" --output "$work/plots/associativity/conflict_randomized.pdf"
  fi
  if [ "$stage" = all ] || [ "$stage" = inclusion ]; then
    python3 scripts/plot_inclusion_curve.py --input "$work/processed/inclusion/reuse_randomized.tsv" --output "$work/plots/inclusion/reuse_randomized.pdf"
  fi
  if [ "$stage" = all ] || [ "$stage" = eviction ]; then
    python3 scripts/plot_eviction_evidence.py --input "$work/processed/eviction/cross_level_randomized.tsv" --output "$work/plots/eviction/cross_level_randomized.pdf"
  fi
else
  echo "plot_status=deferred_gnuplot_not_available" >> "$result/job_metadata.tsv"
fi

tar -C "$work" -czf "$result/raw_timing_samples.tar.gz" raw
sha256sum "$result/raw_timing_samples.tar.gz" > "$result/raw_timing_samples.tar.gz.sha256"
status=ok
echo "status=ok"
