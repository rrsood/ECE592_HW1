#!/usr/bin/env python3
"""Validate and execute a randomized ECE 592 associativity/conflict plan."""

import argparse
import csv
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
    "plot_index",
    "conflict_line_count",
    "conflict_stride_bytes",
    "point_seed",
]


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
    if parsed < 0:
        raise ValueError("negative integer in {}".format(field_name))
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
                raise ValueError("invalid or duplicate plan key: {!r}".format(key))
            metadata[key] = value
        else:
            raise ValueError("plan has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError("unexpected plan columns: {!r}".format(
                reader.fieldnames))

        found_end = False
        for record in reader:
            if record[EXPECTED_COLUMNS[0]] == "data_end":
                if any(record[column] not in (None, "")
                       for column in EXPECTED_COLUMNS[1:]):
                    raise ValueError("malformed data_end row")
                found_end = True
                break

            row = {column: parse_decimal(record[column], "plan " + column)
                   for column in EXPECTED_COLUMNS}
            rows.append(row)

        if not found_end:
            raise ValueError("plan has no data_end marker")
        if any(line.strip() for line in stream):
            raise ValueError("unexpected content after data_end")

    required_keys = {
        "ece592_conflict_plan_version",
        "generator",
        "sweep",
        "line_counts",
        "conflict_stride_bytes_values",
        "unique_line_count_count",
        "unique_conflict_stride_count",
        "trial_count",
        "plan_seed",
        "plan_row_count",
    }
    missing = required_keys.difference(metadata)
    if missing:
        raise ValueError("missing plan keys: {}".format(
            ", ".join(sorted(missing))))
    if metadata["ece592_conflict_plan_version"] != "1":
        raise ValueError("unsupported conflict plan version")

    numeric_metadata = {}
    for key in required_keys.difference({
            "ece592_conflict_plan_version",
            "generator",
            "sweep",
            "line_counts",
            "conflict_stride_bytes_values",
    }):
        numeric_metadata[key] = parse_decimal(metadata[key], "plan " + key)

    if numeric_metadata["plan_row_count"] != len(rows):
        raise ValueError("plan row count does not match metadata")
    if not rows:
        raise ValueError("plan contains no rows")

    seen_trial_execution = set()
    seen_trial_plot = set()
    seen_line_counts = set()
    seen_strides = set()
    for expected_global_index, row in enumerate(rows):
        if row["global_execution_index"] != expected_global_index:
            raise ValueError("global execution indices are not sequential")
        if row["conflict_line_count"] < 2:
            raise ValueError("conflict line count must be at least 2")
        if (row["conflict_stride_bytes"] < 8 or
                row["conflict_stride_bytes"] % 8 != 0):
            raise ValueError("invalid conflict stride")

        trial_execution = (row["trial"], row["trial_execution_index"])
        trial_plot = (row["trial"], row["plot_index"])
        if trial_execution in seen_trial_execution or trial_plot in seen_trial_plot:
            raise ValueError("duplicate trial execution or plot index")
        seen_trial_execution.add(trial_execution)
        seen_trial_plot.add(trial_plot)
        seen_line_counts.add(row["conflict_line_count"])
        seen_strides.add(row["conflict_stride_bytes"])

    if numeric_metadata["unique_line_count_count"] != len(seen_line_counts):
        raise ValueError("unique line-count count does not match rows")
    if numeric_metadata["unique_conflict_stride_count"] != len(seen_strides):
        raise ValueError("unique stride count does not match rows")

    return metadata, numeric_metadata, rows


def read_build_command(path):
    with open(path, "r", encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    if len(lines) != 1:
        raise ValueError("build command file must contain exactly one line")
    return single_line(lines[0], "build command")


def output_filename(machine, row):
    return (
        "{}_conflict_trial{:03d}_exec{:04d}_plot{:04d}_"
        "lines{:04d}_stride{:020d}_seed{:020d}.tsv"
        .format(machine, row["trial"], row["trial_execution_index"],
                row["plot_index"], row["conflict_line_count"],
                row["conflict_stride_bytes"], row["point_seed"]))


def benchmark_command(arguments, build_command, row, output_path):
    full_traversal_batches = (
        row["conflict_line_count"] + arguments.batch - 1) // arguments.batch
    warmup_batches = max(arguments.warmup, full_traversal_batches)
    return [
        arguments.benchmark,
        "--mode", "conflict",
        "--cpu", str(arguments.cpu),
        "--lines", str(row["conflict_line_count"]),
        "--conflict-stride", str(row["conflict_stride_bytes"]),
        "--batch", str(arguments.batch),
        "--warmup", str(warmup_batches),
        "--samples", str(arguments.samples),
        "--seed", str(row["point_seed"]),
        "--experiment", arguments.experiment,
        "--output", output_path,
        "--build-command", build_command,
        "--smt-siblings-idle", arguments.smt_siblings_idle,
        "--environment-variables", arguments.environment_variables,
    ]


def write_manifest_header(stream):
    stream.write(
        "global_execution_index\ttrial\ttrial_execution_index\tplot_index\t"
        "conflict_line_count\tconflict_stride_bytes\tpoint_seed\t"
        "output_filename\tstatus\treturn_code\n")
    stream.flush()
    os.fsync(stream.fileno())


def append_manifest_row(stream, row, filename, status, return_code):
    values = [
        row["global_execution_index"],
        row["trial"],
        row["trial_execution_index"],
        row["plot_index"],
        row["conflict_line_count"],
        row["conflict_stride_bytes"],
        row["point_seed"],
        filename,
        status,
        return_code,
    ]
    stream.write("\t".join(str(value) for value in values) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def execute(arguments, plan_metadata, numeric_metadata, rows, build_command):
    del plan_metadata
    del numeric_metadata
    output_directory = os.path.abspath(arguments.output_directory)
    commands = []

    for row in rows:
        filename = output_filename(arguments.machine, row)
        output_path = os.path.join(output_directory, filename)
        commands.append((row, filename, benchmark_command(
            arguments, build_command, row, output_path)))

    if arguments.dry_run:
        for _, _, command in commands:
            print("DRY_RUN {}".format(" ".join(
                shlex.quote(argument) for argument in command)))
        print("plan_row_count={}".format(len(rows)))
        print("status=dry-run-ok")
        return 0

    os.mkdir(output_directory, 0o755)
    shutil.copyfile(arguments.plan,
                    os.path.join(output_directory, "conflict_plan.tsv"))
    shutil.copyfile(arguments.build_command_file,
                    os.path.join(output_directory, "build-command.txt"))

    manifest_path = os.path.join(output_directory, "execution_manifest.tsv")
    with open(manifest_path, "x", encoding="utf-8", newline="\n") as manifest:
        write_manifest_header(manifest)
        for row, filename, command in commands:
            completed = subprocess.run(command, check=False)
            if completed.returncode != 0:
                append_manifest_row(manifest, row, filename, "failed",
                                    completed.returncode)
                print("error: benchmark failed; partial run directory preserved",
                      file=sys.stderr)
                return completed.returncode or 1
            append_manifest_row(manifest, row, filename, "complete", 0)

    print("output_directory={}".format(output_directory))
    print("completed_plan_rows={}".format(len(rows)))
    print("status=ok")
    return 0


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Execute a validated associativity/conflict plan.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--build-command-file", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--cpu", required=True, type=nonnegative_integer)
    parser.add_argument("--batch", required=True, type=positive_integer)
    parser.add_argument(
        "--warmup", required=True, type=nonnegative_integer,
        help=("minimum warm-up batch count; each point is automatically "
              "increased to cover at least one complete conflict cycle"))
    parser.add_argument("--samples", required=True, type=positive_integer)
    parser.add_argument("--smt-siblings-idle", required=True,
                        choices=("yes", "no", "not-applicable"))
    parser.add_argument("--environment-variables", required=True)
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
        parser.error("--machine may contain only letters, digits, dot, dash, underscore")
    try:
        single_line(arguments.experiment, "experiment")
        single_line(arguments.environment_variables, "environment variables")
    except ValueError as error:
        parser.error(str(error))
    if not arguments.dry_run and os.path.exists(arguments.output_directory):
        parser.error("--output-directory must not already exist")
    parent = os.path.dirname(os.path.abspath(arguments.output_directory))
    if not arguments.dry_run and not os.path.isdir(parent):
        parser.error("parent of --output-directory must already exist")

    return arguments


def main():
    arguments = parse_arguments()
    try:
        plan_metadata, numeric_metadata, rows = read_plan(arguments.plan)
        build_command = read_build_command(arguments.build_command_file)
        return execute(arguments, plan_metadata, numeric_metadata, rows,
                       build_command)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
