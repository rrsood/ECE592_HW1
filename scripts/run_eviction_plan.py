#!/usr/bin/env python3
"""Validate and execute a randomized ECE 592 eviction/reload plan."""

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
    "target_set_index",
    "pressure_set_index",
    "target_offsets_bytes",
    "pressure_offsets_bytes",
    "target_offset_count",
    "pressure_offset_count",
    "point_seed",
]


def positive_integer(text):
    value = int(text, 0)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def nonnegative_integer(text):
    value = int(text, 0)
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


def parse_offset_csv(text):
    values = []
    seen = set()
    for part in text.split(","):
        value = parse_decimal(part, "offset list")
        if value % 8 != 0 or value in seen:
            raise ValueError("bad offset list")
        seen.add(value)
        values.append(value)
    if len(values) < 2:
        raise ValueError("offset list must contain at least 2 values")
    return values


def read_plan(path):
    metadata = {}
    rows = []
    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid plan metadata line")
            key, value = line.split("=", 1)
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
                found_end = True
                break
            row = {}
            for column in EXPECTED_COLUMNS:
                if column.endswith("_bytes"):
                    row[column] = record[column]
                else:
                    row[column] = parse_decimal(record[column], column)
            targets = parse_offset_csv(row["target_offsets_bytes"])
            pressure = parse_offset_csv(row["pressure_offsets_bytes"])
            if len(targets) != row["target_offset_count"]:
                raise ValueError("target count mismatch in plan")
            if len(pressure) != row["pressure_offset_count"]:
                raise ValueError("pressure count mismatch in plan")
            if set(targets).intersection(pressure):
                raise ValueError("target and pressure offsets overlap")
            rows.append(row)
        if not found_end:
            raise ValueError("plan has no data_end marker")

    if metadata.get("ece592_eviction_plan_version") != "1":
        raise ValueError("unsupported eviction plan version")
    if parse_decimal(metadata.get("plan_row_count"), "plan_row_count") != len(rows):
        raise ValueError("plan row count does not match metadata")
    for expected_index, row in enumerate(rows):
        if row["global_execution_index"] != expected_index:
            raise ValueError("global execution indices are not sequential")
    return metadata, rows


def read_build_command(path):
    with open(path, "r", encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    if len(lines) != 1:
        raise ValueError("build command file must contain exactly one line")
    return single_line(lines[0], "build command")


def output_filename(machine, row):
    return (
        "{}_eviction_trial{:03d}_exec{:04d}_plot{:04d}_"
        "targets{:02d}_pressure{:04d}_seed{:020d}.tsv"
        .format(machine, row["trial"], row["trial_execution_index"],
                row["plot_index"], row["target_offset_count"],
                row["pressure_offset_count"], row["point_seed"]))


def benchmark_command(arguments, build_command, row, output_path):
    return [
        arguments.benchmark,
        "--mode", "eviction",
        "--cpu", str(arguments.cpu),
        "--target-offsets", row["target_offsets_bytes"],
        "--pressure-offsets", row["pressure_offsets_bytes"],
        "--batch", str(row["target_offset_count"]),
        "--warmup", str(arguments.warmup),
        "--samples", str(arguments.samples),
        "--seed", str(row["point_seed"]),
        "--experiment", arguments.experiment,
        "--output", output_path,
        "--build-command", build_command,
        "--smt-siblings-idle", arguments.smt_siblings_idle,
        "--environment-variables", arguments.environment_variables,
    ]


def write_manifest_header(stream):
    stream.write("\t".join(EXPECTED_COLUMNS + [
        "output_filename", "status", "return_code"]) + "\n")
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
                    os.path.join(output_directory, "eviction_plan.tsv"))
    shutil.copyfile(arguments.build_command_file,
                    os.path.join(output_directory, "build-command.txt"))
    with open(os.path.join(output_directory, "execution_manifest.tsv"),
              "x", encoding="utf-8", newline="\n") as manifest:
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
        description="Execute a validated eviction/reload plan.")
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
