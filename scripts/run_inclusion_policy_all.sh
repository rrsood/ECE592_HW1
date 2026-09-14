#!/usr/bin/env bash
#
# One command that takes a machine from nothing to finished inclusion/exclusion
# evidence: build, generate the plan, collect the data, process it, and plot it.
#
# Everything it writes lands under the repository's data_raw/, data_processed/
# and plots/ trees in the layout the handout asks for:
#
#   data_raw/<machine>/inclusion_policy/raw/<run directory>/
#   data_processed/<machine>/inclusion_policy/<machine>_inclusion_policy.tsv
#   plots/<machine>/<machine>_inclusion_policy_*.pdf
#
# Example:
#
#   scripts/run_inclusion_policy_all.sh \
#       --machine sunbird --cpu 4 --helper-cpus 6,8 \
#       --line-bytes 64 --l1-bytes 32768 --l2-bytes 262144 \
#       --llc-bytes 31457280 \
#       --smt-siblings-idle yes --trials 2 --seed 592
#
# Re-running after an interruption: pass --resume with the same arguments and
# the same seed.  Completed plan rows are skipped.

set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
usage: run_inclusion_policy_all.sh --machine NAME --cpu N --helper-cpus LIST
                                   --line-bytes N --l1-bytes N --l2-bytes N
                                   --llc-bytes N --smt-siblings-idle VALUE
                                   [--trials N] [--seed N] [--samples N]
                                   [--accesses-per-sample N]
                                   [--environment-variables TEXT]
                                   [--no-compress] [--resume] [--dry-run]
                                   [--allow-remote-package]
                                   [--allow-unknown-topology]

All four cache sizes are the team's own Phase-I timing-only inferences, in
bytes.  --helper-cpus is a comma separated list of logical CPUs that share the
LLC with --cpu but sit on different physical cores.
USAGE
}

machine=""
cpu=""
helper_cpus=""
line_bytes=""
l1_bytes=""
l2_bytes=""
llc_bytes=""
smt_siblings_idle=""
trials=2
seed=592
samples=1000000
accesses_per_sample=1
environment_variables="none set beyond the login defaults"
compress="--compress"
resume=""
dry_run=""
extra_flags=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --machine) machine=$2; shift 2 ;;
        --cpu) cpu=$2; shift 2 ;;
        --helper-cpus) helper_cpus=$2; shift 2 ;;
        --line-bytes) line_bytes=$2; shift 2 ;;
        --l1-bytes) l1_bytes=$2; shift 2 ;;
        --l2-bytes) l2_bytes=$2; shift 2 ;;
        --llc-bytes) llc_bytes=$2; shift 2 ;;
        --smt-siblings-idle) smt_siblings_idle=$2; shift 2 ;;
        --trials) trials=$2; shift 2 ;;
        --seed) seed=$2; shift 2 ;;
        --samples) samples=$2; shift 2 ;;
        --accesses-per-sample) accesses_per_sample=$2; shift 2 ;;
        --environment-variables) environment_variables=$2; shift 2 ;;
        --no-compress) compress=""; shift ;;
        --resume) resume="--resume"; shift ;;
        --dry-run) dry_run="--dry-run"; shift ;;
        --allow-remote-package) extra_flags+=("--allow-remote-package"); shift ;;
        --allow-unknown-topology) extra_flags+=("--allow-unknown-topology"); shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

for required in machine cpu helper_cpus line_bytes l1_bytes l2_bytes \
                llc_bytes smt_siblings_idle; do
    if [[ -z ${!required} ]]; then
        echo "error: --${required//_/-} is required" >&2
        usage
        exit 2
    fi
done

script_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "${script_directory}/.." && pwd)
cd -- "${repository_root}"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
run_name="${machine}_inclusion_policy_${stamp}"

build_directory="${repository_root}/build"
raw_root="${repository_root}/data_raw/${machine}/inclusion_policy/raw"
processed_root="${repository_root}/data_processed/${machine}/inclusion_policy"
plot_root="${repository_root}/plots/${machine}"

mkdir -p "${build_directory}" "${raw_root}" "${processed_root}" "${plot_root}"

executable="${build_directory}/inclusion_policy_bench"
plan_path="${raw_root}/${run_name}_plan.tsv"
run_directory="${raw_root}/${run_name}"
processed_path="${processed_root}/${run_name}.tsv"
plot_prefix="${plot_root}/${run_name}"

echo "=== step 1/5: build ==="
"${script_directory}/build_inclusion_policy.sh" "${executable}"

echo "=== step 2/5: generate plan ==="
if [[ -f ${plan_path} && -n ${resume} ]]; then
    echo "reusing existing plan: ${plan_path}"
else
    python3 "${script_directory}/generate_inclusion_policy_plan.py" \
        --line-bytes "${line_bytes}" \
        --l1-bytes "${l1_bytes}" \
        --l2-bytes "${l2_bytes}" \
        --llc-bytes "${llc_bytes}" \
        --helper-cpus "${helper_cpus}" \
        --accesses-per-sample "${accesses_per_sample}" \
        --samples "${samples}" \
        --trials "${trials}" \
        --seed "${seed}" \
        --output "${plan_path}"
fi

echo "=== step 3/5: collect ==="
python3 "${script_directory}/run_inclusion_policy_plan.py" \
    --plan "${plan_path}" \
    --benchmark "${executable}" \
    --build-command-file "${executable}.build-command.txt" \
    --output-directory "${run_directory}" \
    --machine "${machine}" \
    --experiment "inclusion-policy-phase1" \
    --cpu "${cpu}" \
    --samples "${samples}" \
    --smt-siblings-idle "${smt_siblings_idle}" \
    --environment-variables "${environment_variables}" \
    ${compress} ${resume} ${dry_run} \
    ${extra_flags[@]+"${extra_flags[@]}"}

if [[ -n ${dry_run} ]]; then
    echo "status=dry-run-complete"
    exit 0
fi

echo "=== step 4/5: process ==="
python3 "${script_directory}/process_inclusion_policy_run.py" \
    --run-directory "${run_directory}" \
    --output "${processed_path}"

echo "=== step 5/5: plot ==="
python3 "${script_directory}/plot_inclusion_policy_curve.py" \
    --input "${processed_path}" \
    --output-prefix "${plot_prefix}" \
    --machine "${machine}" \
    --llc-bytes "${llc_bytes}" \
    --l1-bytes "${l1_bytes}" \
    --l2-bytes "${l2_bytes}"

echo
echo "run_directory=${run_directory}"
echo "processed_file=${processed_path}"
echo "plot_prefix=${plot_prefix}"
echo "status=ok"
