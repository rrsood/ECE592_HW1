#!/usr/bin/env python3
"""Generate one guarded Slurm job script per live Hazel constraint."""

import argparse
import csv
import hashlib
import os
import stat
import sys


def read_targets(path):
    with open(path, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"constraint", "generation"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("target table is missing required columns")
        return list(reader)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", required=True)
    parser.add_argument("--visible-constraints", required=True,
                        help="comma-separated constraints observed with live si/sinfo")
    parser.add_argument("--availability-file", required=True,
                        help="saved live si/sinfo output used to select constraints")
    freeze = parser.add_mutually_exclusive_group(required=True)
    freeze.add_argument("--freeze-commit")
    freeze.add_argument("--unfrozen-run", action="store_true")
    parser.add_argument("--freeze-directory")
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--result-root", default="phase3/results",
                        help="persistent result directory, absolute or relative to repository")
    parser.add_argument("--account", default="ece592f26")
    parser.add_argument("--partition",
                        help="optional Slurm partition override")
    parser.add_argument("--time", default="12:00:00")
    parser.add_argument("--memory", default="8G")
    parser.add_argument("--staged", action="store_true",
                        help="generate QOS-friendly independent stage jobs")
    args = parser.parse_args()
    if os.path.exists(args.output_directory):
        parser.error("--output-directory must not already exist")
    if not os.path.isfile(args.availability_file):
        parser.error("--availability-file must name saved live scheduler output")
    if args.freeze_commit and not args.freeze_directory:
        parser.error("--freeze-directory is required with --freeze-commit")
    visible = {item.strip() for item in args.visible_constraints.split(",")
               if item.strip()}
    targets = read_targets(args.targets)
    known = {row["constraint"] for row in targets}
    unknown = visible.difference(known)
    if unknown:
        parser.error("unknown visible constraints: {}".format(", ".join(sorted(unknown))))
    selected = [row for row in targets if row["constraint"] in visible]
    if not selected:
        parser.error("no target constraints selected")
    os.makedirs(args.output_directory)
    stages = [
        ("capacity", None),
        ("line-size", None),
        ("associativity-a", "4096,8192,16384"),
        ("associativity-b", "32768,65536,131072"),
        ("associativity-c", "262144,524288,1048576"),
        ("inclusion", None),
        ("eviction", None),
        ("software", None),
    ] if args.staged else [("all", None)]
    generated = []
    for row in selected:
        constraint = row["constraint"]
        for stage_name, stage_strides in stages:
            runner_stage = "associativity" if stage_strides else stage_name
            suffix = "_{}".format(stage_name.replace("-", "_")) if args.staged else ""
            path = os.path.join(
                args.output_directory,
                "hazel_{}{}.sbatch".format(constraint, suffix))
            generated.append(path)
            write_job(path, args, row, constraint, stage_name,
                      runner_stage, stage_strides)
    print("output_directory={}".format(args.output_directory))
    print("generated_job_count={}".format(len(generated)))
    print("constraints={}".format(",".join(row["constraint"] for row in selected)))
    print("staged={}".format(str(args.staged).lower()))
    print("status=ok")
    return 0


def write_job(path, args, row, constraint, stage_name,
              runner_stage, stage_strides):
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("#!/bin/bash\n")
        job_stage = stage_name.replace("associativity", "assoc").replace("-", "")
        stream.write("#SBATCH --job-name=ece592_{}_{}\n".format(
            constraint, job_stage))
        stream.write("#SBATCH --output=phase3/slurm_logs/%x_%j.out\n")
        stream.write("#SBATCH --error=phase3/slurm_logs/%x_%j.err\n")
        stream.write("#SBATCH --account={}\n".format(args.account))
        stream.write("#SBATCH --ntasks=1\n")
        stream.write("#SBATCH --cpus-per-task=1\n")
        stream.write("#SBATCH --mem={}\n".format(args.memory))
        stream.write("#SBATCH --time={}\n".format(args.time))
        if args.partition:
            stream.write("#SBATCH --partition={}\n".format(args.partition))
        stream.write("#SBATCH --constraint={}\n".format(constraint))
        stream.write("set -euo pipefail\n")
        stream.write("# scheduler_availability_file={}\n".format(
            args.availability_file))
        stream.write("# scheduler_availability_sha256={}\n".format(
            sha256_file(args.availability_file)))
        stream.write("repo=${SLURM_SUBMIT_DIR:?submit from repository root}\n")
        stream.write("cd \"$repo\"\n")
        stream.write("mkdir -p phase3/slurm_logs phase3/results\n")
        stream.write("srun --cpu-bind=verbose,cores --cpus-per-task=1 "
                     "bash scripts/run_hazel_phase3_suite.sh \\\n")
        stream.write("  --constraint {} \\\n".format(constraint))
        stream.write("  --generation {} \\\n".format(repr(row["generation"])))
        stream.write("  --stage {} \\\n".format(runner_stage))
        if stage_strides:
            stream.write("  --conflict-strides {} \\\n".format(stage_strides))
        if args.unfrozen_run:
            stream.write("  --unfrozen-run \\\n")
        else:
            stream.write("  --freeze-directory {} \\\n".format(
                repr(args.freeze_directory)))
            stream.write("  --freeze-commit {} \\\n".format(
                repr(args.freeze_commit)))
        stream.write("  --result-root {}\n".format(repr(args.result_root)))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        sys.exit(1)
