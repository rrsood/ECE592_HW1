#!/usr/bin/env python3
"""Validate and execute a randomized ECE 592 inclusion/reuse plan."""

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
    "probe_node_count",
    "pressure_node_count",
    "node_spacing_bytes",
    "probe_accesses_per_sample",
    "pressure_accesses_per_sample",
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
        "ece592_inclusion_plan_version",
        "generator",
        "sweep",
        "probe_node_counts",
        "pressure_node_counts",
        "node_spacing_bytes",
        "probe_accesses_per_sample",
        "pressure_accesses_per_sample",
        "unique_probe_node_count_count",
        "unique_pressure_node_count_count",
        "trial_count",
        "plan_seed",
        "plan_row_count",
    }
    missing = required_keys.difference(metadata)
    if missing:
        raise ValueError("missing plan keys: {}".format(
            ", ".join(sorted(missing))))
    if metadata["ece592_inclusion_plan_version"] != "1":
        raise ValueError("unsupported inclusion plan version")
    if parse_decimal(metadata["plan_row_count"], "plan_row_count") != len(rows):
        raise ValueError("plan row count does not match metadata")
    if not rows:
        raise ValueError("plan contains no rows")

    for expected_index, row in enumerate(rows):
        if row["global_execution_index"] != expected_index:
            raise ValueError("global execution indices are not sequential")
        if row["probe_node_count"] < 2 or row["pressure_node_count"] < 2:
            raise ValueError("node counts must be at least 2")
        if row["node_spacing_bytes"] < 8 or row["node_spacing_bytes"] % 8 != 0:
            raise ValueError("invalid node spacing")
        if row["probe_accesses_per_sample"] == 0:
            raise ValueError("probe batch cannot be zero")
        if row["pressure_accesses_per_sample"] == 0:
            raise ValueError("pressure batch cannot be zero")

    return metadata, rows


def read_build_command(path):
    with open(path, "r", encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    if len(lines) != 1:
        raise ValueError("build command file must contain exactly one line")
    return single_line(lines[0], "build command")


def output_filename(machine, row):
    return (
        "{}_inclusion_trial{:03d}_exec{:04d}_plot{:04d}_"
        "probe{:012d}_pressure{:012d}_seed{:020d}.tsv"
        .format(machine, row["trial"], row["trial_execution_index"],
                row["plot_index"], row["probe_node_count"],
                row["pressure_node_count"], row["point_seed"]))


def benchmark_command(arguments, build_command, row, output_path):
    probe_cycle_batches = (
        row["probe_node_count"] + row["probe_accesses_per_sample"] - 1) // row["probe_accesses_per_sample"]
    pressure_cycle_batches = (
        row["pressure_node_count"] + row["pressure_accesses_per_sample"] - 1) // row["pressure_accesses_per_sample"]
    warmup_batches = max(arguments.warmup, probe_cycle_batches,
                         pressure_cycle_batches)
    return [
        arguments.benchmark,
        "--mode", "inclusion",
        "--cpu", str(arguments.cpu),
        "--probe-nodes", str(row["probe_node_count"]),
        "--pressure-nodes", str(row["pressure_node_count"]),
        "--spacing", str(row["node_spacing_bytes"]),
        "--batch", str(row["probe_accesses_per_sample"]),
        "--pressure-batch", str(row["pressure_accesses_per_sample"]),
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
        "probe_node_count\tpressure_node_count\tnode_spacing_bytes\t"
        "probe_accesses_per_sample\tpressure_accesses_per_sample\t"
        "point_seed\toutput_filename\tstatus\treturn_code\n")
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
                    os.path.join(output_directory, "inclusion_plan.tsv"))
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
        description="Execute a validated inclusion/reuse plan.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--build-command-file", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--cpu", required=True, type=nonnegative_integer)
    parser.add_argument("--warmup", required=True, type=nonnegative_integer)
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
        _, rows = read_plan(arguments.plan)
        build_command = read_build_command(arguments.build_command_file)
        return execute(arguments, rows, build_command)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
