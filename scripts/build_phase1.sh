#!/usr/bin/env bash

set -euo pipefail

usage() {
    echo "usage: $0 <absolute-output-executable>" >&2
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

script_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "${script_directory}/.." && pwd)
output_path=$1

if [[ ${output_path} != /* ]]; then
    echo "error: output executable path must be absolute" >&2
    exit 2
fi

output_directory=$(dirname -- "${output_path}")
build_command_path="${output_path}.build-command.txt"

if [[ ! -d "${output_directory}" ]]; then
    echo "error: output directory does not exist: ${output_directory}" >&2
    exit 1
fi

architecture=$(uname -m)
case "${architecture}" in
    x86_64)
        timer_source=main_code/x86_64/timer_x86_64.c
        ;;
    aarch64)
        timer_source=main_code/aarch64/timer_aarch64.c
        ;;
    *)
        echo "error: unsupported architecture: ${architecture}" >&2
        exit 1
        ;;
esac

cd -- "${repository_root}"

git_commit=$(git rev-parse --verify HEAD)
source_state=${git_commit}
if [[ -n $(git status --porcelain -- main_code scripts) ]]; then
    source_state="${git_commit}-dirty"
fi

compiler_flags=(
    -O0
    -g
    -std=c11
    -Wall
    -Wextra
    -Wpedantic
    -Werror
    -fno-omit-frame-pointer
)

common_sources=(
    main_code/common/cache_bench.c
    main_code/common/raw_output.c
    main_code/common/measurement.c
    main_code/common/pointer_chase.c
    main_code/common/metadata_linux.c
    main_code/common/affinity_linux.c
)

flags_text="${compiler_flags[*]}"
compile_command=(
    gcc
    "${compiler_flags[@]}"
    "-DECE592_BUILD_FLAGS=\"${flags_text}\""
    "-DECE592_GIT_COMMIT=\"${source_state}\""
    -I main_code/common
    "${common_sources[@]}"
    "${timer_source}"
    -o "${output_path}"
)

printf -v escaped_repository_root '%q' "${repository_root}"
printf -v escaped_compile_command '%q ' "${compile_command[@]}"
escaped_compile_command=${escaped_compile_command% }
recorded_build_command="cd -- ${escaped_repository_root} && ${escaped_compile_command}"

"${compile_command[@]}"

temporary_command_path=$(mktemp "${output_directory}/.ece592-build-command.XXXXXX")
cleanup_temporary_file() {
    if [[ -n ${temporary_command_path:-} && -e ${temporary_command_path} ]]; then
        rm -f -- "${temporary_command_path}"
    fi
}
trap cleanup_temporary_file EXIT

printf '%s\n' "${recorded_build_command}" > "${temporary_command_path}"
mv -f -- "${temporary_command_path}" "${build_command_path}"
temporary_command_path=
trap - EXIT

echo "architecture=${architecture}"
echo "timer_source=${timer_source}"
echo "source_state=${source_state}"
echo "output_executable=${output_path}"
echo "build_command_file=${build_command_path}"
echo "status=ok"
