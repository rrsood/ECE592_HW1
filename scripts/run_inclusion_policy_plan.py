#!/usr/bin/env python3
"""Validate and execute a randomized ECE 592 inclusion/exclusion plan.

Responsibilities, in order:

  1. Re-validate the plan file, so a hand-edited plan cannot be executed.
  2. Pre-flight the CPU topology: every helper CPU named in the plan must be a
     different physical core in the same package as the measuring CPU, because
     an SMT sibling shares L1D/L2 and a different package has a different LLC.
     Either mistake silently destroys the experiment, so it is checked before
     any data is collected rather than discovered during analysis.
  3. Run every plan row in the planned randomized order, one raw file per row.
  4. Record an execution manifest that ties each plan row to its raw file.
  5. Optionally gzip each raw file once it is written.  One million samples per
     point is roughly 25 MB of text and compresses by about 4x, which matters
     when eight machines have to be collected and copied before a deadline.

Only topology files are read, never cache-size files, so this stays inside the
Phase-I rules.
"""

import argparse
import csv
import gzip
import os
import re
import shlex
import shutil
import subprocess
import sys


MINIMUM_TIMED_SAMPLES = 1_000_000

EXPECTED_COLUMNS = [
    "global_execution_index",
    "trial",
    "trial_execution_index",
    "series_index",
    "plot_index",
    "target_bytes",
    "target_line_spacing_bytes",
    "pressure_source",
    "pressure_bytes",
    "pressure_line_spacing_bytes",
    "pressure_order",
    "pressure_passes",
    "helper_cpu",
    "accesses_per_sample",
    "point_seed",
]

INTEGER_COLUMNS = {
    "global_execution_index",
    "trial",
    "trial_execution_index",
    "series_index",
    "plot_index",
    "target_bytes",
    "target_line_spacing_bytes",
    "pressure_bytes",
    "pressure_line_spacing_bytes",
    "pressure_passes",
    "accesses_per_sample",
    "point_seed",
}

MANIFEST_COLUMNS = EXPECTED_COLUMNS + [
    "output_filename",
    "status",
    "return_code",
]

REQUIRED_PLAN_KEYS = {
    "ece592_inclusion_policy_plan_version",
    "generator",
    "measurement_goal",
    "inferred_line_bytes",
    "inferred_l1d_bytes",
    "inferred_l2_bytes",
    "inferred_llc_bytes",
    "accesses_per_sample",
    "pressure_passes",
    "pressure_order",
    "requested_samples_per_point",
    "unique_point_count",
    "series_count",
    "trial_count",
    "plan_seed",
    "plan_row_count",
}


def positive_integer(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def nonnegative_integer(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    if value < 0:
        raise argparse.ArgumentTypeError("value must be nonnegative")
    return value


def single_line(text, field_name):
    if not text or any(character in text for character in "\r\n\t"):
        raise ValueError("{} must be a nonempty single line".format(field_name))
    return text


def parse_decimal(value, field_name):
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid integer in {}".format(field_name)) from error
    return parsed


def read_plan(path):
    metadata = {}
    rows = []

    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid plan metadata line: {!r}".format(line))
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError(
                    "invalid or duplicate plan key: {!r}".format(key))
            metadata[key] = value
        else:
            raise ValueError("plan has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "unexpected plan columns: {!r}".format(reader.fieldnames))

        found_end = False
        for record in reader:
            if record[EXPECTED_COLUMNS[0]] == "data_end":
                found_end = True
                break
            row = {}
            for column in EXPECTED_COLUMNS:
                if column in INTEGER_COLUMNS:
                    row[column] = parse_decimal(record[column],
                                                "plan " + column)
                elif column == "helper_cpu":
                    row[column] = parse_decimal(record[column], "plan helper")
                else:
                    row[column] = record[column]
            rows.append(row)

        if not found_end:
            raise ValueError("plan has no data_end marker")
        if any(line.strip() for line in stream):
            raise ValueError("unexpected content after data_end")

    missing = REQUIRED_PLAN_KEYS.difference(metadata)
    if missing:
        raise ValueError("missing plan keys: {}".format(", ".join(
            sorted(missing))))
    if metadata["ece592_inclusion_policy_plan_version"] != "1":
        raise ValueError("unsupported inclusion policy plan version")
    if parse_decimal(metadata["plan_row_count"], "plan_row_count") != len(rows):
        raise ValueError("plan row count does not match metadata")
    if not rows:
        raise ValueError("plan contains no rows")

    for expected_index, row in enumerate(rows):
        if row["global_execution_index"] != expected_index:
            raise ValueError("global execution indices are not sequential")
        if row["pressure_source"] not in ("none", "self", "helper"):
            raise ValueError("invalid pressure source: {!r}".format(
                row["pressure_source"]))
        if row["pressure_order"] not in ("sequential", "randomized"):
            raise ValueError("invalid pressure order")
        line_bytes = row["target_line_spacing_bytes"]
        if line_bytes < 8 or line_bytes % 8 != 0:
            raise ValueError("invalid target line spacing")
        group = row["accesses_per_sample"]
        if group <= 0:
            raise ValueError("accesses_per_sample must be positive")
        target_nodes = row["target_bytes"] // line_bytes
        if target_nodes < 2 or target_nodes % group != 0:
            raise ValueError(
                "target footprint {} does not split evenly into groups of {}"
                .format(row["target_bytes"], group))
        if row["pressure_source"] == "none":
            if row["pressure_bytes"] != 0:
                raise ValueError("no-pressure row must have zero footprint")
        else:
            if row["pressure_bytes"] < 2 * row["pressure_line_spacing_bytes"]:
                raise ValueError("pressure footprint is too small")
            if row["pressure_passes"] <= 0:
                raise ValueError("pressure passes must be positive")
        if row["pressure_source"] == "helper" and row["helper_cpu"] < 0:
            raise ValueError("helper row needs a helper CPU")

    return metadata, rows


# --------------------------------------------------------------------------
# Phase-I-safe topology pre-flight
# --------------------------------------------------------------------------

def read_topology(logical_cpu, leaf):
    path = "/sys/devices/system/cpu/cpu{}/topology/{}".format(logical_cpu, leaf)
    try:
        with open(path, "r", encoding="ascii") as stream:
            return int(stream.read().strip())
    except (OSError, ValueError):
        return None


def describe_cpu(logical_cpu):
    return {
        "logical_cpu": logical_cpu,
        "core_id": read_topology(logical_cpu, "core_id"),
        "package_id": read_topology(logical_cpu, "physical_package_id"),
    }


def preflight_topology(arguments, rows):
    """Reject helper placements that cannot answer the inclusion question."""
    measuring = describe_cpu(arguments.cpu)
    helper_cpus = sorted({row["helper_cpu"] for row in rows
                          if row["pressure_source"] == "helper"})
    report = ["measuring_cpu={} core_id={} package_id={}".format(
        measuring["logical_cpu"], measuring["core_id"],
        measuring["package_id"])]
    problems = []

    for helper_cpu in helper_cpus:
        helper = describe_cpu(helper_cpu)
        same_package = (helper["package_id"] is not None and
                        helper["package_id"] == measuring["package_id"])
        smt_sibling = (same_package and helper["core_id"] is not None and
                       helper["core_id"] == measuring["core_id"])
        report.append(
            "helper_cpu={} core_id={} package_id={} same_package={} "
            "smt_sibling={}".format(
                helper_cpu, helper["core_id"], helper["package_id"],
                str(same_package).lower(), str(smt_sibling).lower()))
        if helper_cpu == arguments.cpu:
            problems.append(
                "helper CPU {} is the measuring CPU".format(helper_cpu))
        if smt_sibling and not arguments.allow_smt_sibling:
            problems.append(
                "helper CPU {} is an SMT sibling of the measuring CPU; it "
                "shares L1D/L2 so its pressure cannot isolate the shared "
                "cache (pass --allow-smt-sibling to run it as a deliberate "
                "control)".format(helper_cpu))
        topology_known = (helper["package_id"] is not None and
                          measuring["package_id"] is not None)
        if not topology_known:
            if not arguments.allow_unknown_topology:
                problems.append(
                    "topology IDs are unreadable for CPU {} or the measuring "
                    "CPU, so same-package placement cannot be verified (pass "
                    "--allow-unknown-topology to proceed and record the "
                    "limitation)".format(helper_cpu))
        elif not same_package and not arguments.allow_remote_package:
            problems.append(
                "helper CPU {} is in a different package from the measuring "
                "CPU; it drives a different LLC (pass "
                "--allow-remote-package to run it as a deliberate negative "
                "control)".format(helper_cpu))

    return report, problems


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------

def read_build_command(path):
    with open(path, "r", encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    if len(lines) != 1:
        raise ValueError("build command file must contain exactly one line")
    return single_line(lines[0], "build command")


def output_filename(machine, row):
    return (
        "{}_inclusionpolicy_trial{:03d}_exec{:04d}_series{:02d}_plot{:04d}_"
        "target{:010d}_{}_pressure{:012d}_helper{:03d}_seed{:020d}.tsv"
        .format(machine, row["trial"], row["trial_execution_index"],
                row["series_index"], row["plot_index"], row["target_bytes"],
                row["pressure_source"], row["pressure_bytes"],
                row["helper_cpu"] if row["helper_cpu"] >= 0 else 999,
                row["point_seed"]))


def benchmark_command(arguments, build_command, row, output_path):
    command = [
        arguments.benchmark,
        "--cpu", str(arguments.cpu),
        "--pressure-source", row["pressure_source"],
        "--target-bytes", str(row["target_bytes"]),
        "--target-spacing", str(row["target_line_spacing_bytes"]),
        "--accesses-per-sample", str(row["accesses_per_sample"]),
        "--samples", str(arguments.samples),
        "--warmup", str(arguments.warmup),
        "--seed", str(row["point_seed"]),
        "--experiment", arguments.experiment,
        "--output", output_path,
        "--build-command", build_command,
        "--smt-siblings-idle", arguments.smt_siblings_idle,
        "--environment-variables", arguments.environment_variables,
    ]
    if row["pressure_source"] != "none":
        command.extend([
            "--pressure-bytes", str(row["pressure_bytes"]),
            "--pressure-spacing", str(row["pressure_line_spacing_bytes"]),
            "--pressure-order", row["pressure_order"],
            "--pressure-passes", str(row["pressure_passes"]),
        ])
    if row["pressure_source"] == "helper":
        command.extend(["--helper-cpu", str(row["helper_cpu"])])
    if arguments.allow_smt_sibling:
        command.append("--allow-smt-sibling")
    return command


def compress_in_place(path):
    """Replace path with path + '.gz'; the raw text is fully recoverable."""
    compressed = path + ".gz"
    with open(path, "rb") as source:
        with gzip.open(compressed, "wb", compresslevel=6) as destination:
            shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
    os.replace(compressed, compressed)
    os.unlink(path)
    return os.path.basename(compressed)


def read_completed_indices(manifest_path):
    completed = set()
    if not os.path.isfile(manifest_path):
        return completed
    with open(manifest_path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        for record in reader:
            if record.get("status") == "complete":
                completed.add(int(record["global_execution_index"], 10))
    return completed


def write_manifest_header(stream):
    stream.write("\t".join(MANIFEST_COLUMNS) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def append_manifest_row(stream, row, filename, status, return_code):
    values = [row[column] for column in EXPECTED_COLUMNS]
    values.extend([filename, status, return_code])
    stream.write("\t".join(str(value) for value in values) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def execute(arguments, rows, build_command):
    output_directory = os.path.abspath(arguments.output_directory)
    commands = []
    for row in rows:
        filename = output_filename(arguments.machine, row)
        output_path = os.path.join(output_directory, filename)
        commands.append((row, filename, output_path, benchmark_command(
            arguments, build_command, row, output_path)))

    if arguments.dry_run:
        for _, _, _, command in commands:
            print("DRY_RUN {}".format(" ".join(
                shlex.quote(argument) for argument in command)))
        print("plan_row_count={}".format(len(rows)))
        print("status=dry-run-ok")
        return 0

    manifest_path = os.path.join(output_directory, "execution_manifest.tsv")
    completed = set()
    if os.path.isdir(output_directory):
        completed = read_completed_indices(manifest_path)
        manifest_mode = "a"
    else:
        os.mkdir(output_directory, 0o755)
        manifest_mode = "x"

    shutil.copyfile(arguments.plan,
                    os.path.join(output_directory,
                                 "inclusion_policy_plan.tsv"))
    shutil.copyfile(arguments.build_command_file,
                    os.path.join(output_directory, "build-command.txt"))

    executed = 0
    skipped = 0
    with open(manifest_path, manifest_mode, encoding="utf-8",
              newline="\n") as manifest:
        if manifest_mode == "x":
            write_manifest_header(manifest)
        for row, filename, output_path, command in commands:
            if row["global_execution_index"] in completed:
                skipped += 1
                continue
            completed_process = subprocess.run(command, check=False)
            if completed_process.returncode != 0:
                append_manifest_row(manifest, row, filename, "failed",
                                    completed_process.returncode)
                print("error: benchmark failed on global index {}; partial "
                      "run directory preserved, rerun with --resume".format(
                          row["global_execution_index"]), file=sys.stderr)
                return completed_process.returncode or 1
            stored = filename
            if arguments.compress:
                stored = compress_in_place(output_path)
            append_manifest_row(manifest, row, stored, "complete", 0)
            executed += 1

    print("output_directory={}".format(output_directory))
    print("executed_plan_rows={}".format(executed))
    print("skipped_completed_rows={}".format(skipped))
    print("raw_files_compressed={}".format(
        "true" if arguments.compress else "false"))
    print("status=ok")
    return 0


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Execute a validated inclusion/exclusion plan.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--build-command-file", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--cpu", required=True, type=nonnegative_integer,
                        help="Measuring logical CPU.")
    parser.add_argument("--warmup", type=nonnegative_integer, default=2,
                        help="Unrecorded rounds before sampling begins.")
    parser.add_argument("--samples", type=positive_integer,
                        default=MINIMUM_TIMED_SAMPLES)
    parser.add_argument("--smt-siblings-idle", required=True,
                        choices=("yes", "no", "not-applicable"))
    parser.add_argument("--environment-variables", required=True)
    parser.add_argument("--compress", action="store_true",
                        help="gzip each raw file after it is written.")
    parser.add_argument("--resume", action="store_true",
                        help="Reuse an existing run directory and skip rows "
                             "already marked complete in its manifest.")
    parser.add_argument("--allow-smt-sibling", action="store_true")
    parser.add_argument("--allow-remote-package", action="store_true")
    parser.add_argument("--allow-unknown-topology",
                        action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    if arguments.samples < MINIMUM_TIMED_SAMPLES:
        parser.error("--samples must be at least 1000000")
    if not os.path.isfile(arguments.plan):
        parser.error("--plan must name an existing file")
    if not os.path.isfile(arguments.benchmark) or not os.access(
            arguments.benchmark, os.X_OK):
        parser.error("--benchmark must name an executable file")
    if not os.path.isfile(arguments.build_command_file):
        parser.error("--build-command-file must name an existing file")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", arguments.machine):
        parser.error(
            "--machine may contain only letters, digits, dot, dash, underscore")
    try:
        single_line(arguments.experiment, "experiment")
        single_line(arguments.environment_variables, "environment variables")
    except ValueError as error:
        parser.error(str(error))
    if not arguments.dry_run and os.path.exists(arguments.output_directory):
        if not arguments.resume:
            parser.error("--output-directory must not already exist "
                         "(pass --resume to continue an interrupted run)")
        if not os.path.isdir(arguments.output_directory):
            parser.error("--output-directory exists but is not a directory")
    parent = os.path.dirname(os.path.abspath(arguments.output_directory))
    if not arguments.dry_run and not os.path.isdir(parent):
        parser.error("parent of --output-directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        _, rows = read_plan(arguments.plan)
        report, problems = preflight_topology(arguments, rows)
        for line in report:
            print(line)
        if problems:
            for problem in problems:
                print("error: {}".format(problem), file=sys.stderr)
            return 1
        build_command = read_build_command(arguments.build_command_file)
        return execute(arguments, rows, build_command)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
