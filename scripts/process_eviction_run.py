#!/usr/bin/env python3
"""Validate and summarize every point in a completed eviction/reload sweep."""

import argparse
import csv
import hashlib
import os
import platform
import shlex
import sys

import run_eviction_plan
import summarize_raw


MANIFEST_COLUMNS = run_eviction_plan.EXPECTED_COLUMNS + [
    "output_filename", "status", "return_code"]
RAW_COLUMNS = (
    "sample_index",
    "baseline_raw_ticks",
    "after_pressure_raw_ticks",
    "timer_overhead_raw_ticks",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def parse_decimal(value, field_name):
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid integer in {}".format(field_name)) from error
    if parsed < 0:
        raise ValueError("negative integer in {}".format(field_name))
    return parsed


def read_manifest(path):
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != MANIFEST_COLUMNS:
            raise ValueError("unexpected execution-manifest columns")
        for record in reader:
            row = {}
            for column in run_eviction_plan.EXPECTED_COLUMNS:
                if column.endswith("_bytes"):
                    row[column] = record[column]
                else:
                    row[column] = parse_decimal(record[column], column)
            row["output_filename"] = record["output_filename"]
            row["status"] = record["status"]
            row["return_code"] = parse_decimal(record["return_code"],
                                               "return_code")
            rows.append(row)
    return rows


def validate_manifest(plan_rows, manifest_rows):
    if len(manifest_rows) != len(plan_rows):
        raise ValueError("manifest has {} rows but plan requires {}".format(
            len(manifest_rows), len(plan_rows)))
    seen = set()
    for plan_row, manifest_row in zip(plan_rows, manifest_rows):
        for field in run_eviction_plan.EXPECTED_COLUMNS:
            if manifest_row[field] != plan_row[field]:
                raise ValueError("manifest/plan mismatch for {}".format(field))
        if manifest_row["status"] != "complete" or manifest_row["return_code"] != 0:
            raise ValueError("eviction run is incomplete")
        filename = manifest_row["output_filename"]
        if os.path.basename(filename) != filename or filename in seen:
            raise ValueError("unsafe or duplicate raw filename")
        seen.add(filename)


def read_raw(path):
    metadata = {}
    baseline = []
    after_pressure = []
    overhead = []
    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid raw metadata line")
            key, value = line.split("=", 1)
            if key in metadata:
                raise ValueError("duplicate raw metadata key")
            metadata[key] = value
        else:
            raise ValueError("raw file has no data_begin marker")
        heading = tuple(stream.readline().rstrip("\r\n").split("\t"))
        if heading != RAW_COLUMNS:
            raise ValueError("unexpected raw-data columns: {!r}".format(heading))
        found_end = False
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_end":
                found_end = True
                break
            fields = line.split("\t")
            if len(fields) != len(RAW_COLUMNS):
                raise ValueError("malformed raw row")
            sample, before, after, timer = (int(field, 10) for field in fields)
            if sample != len(baseline):
                raise ValueError("sample index gap in raw data")
            baseline.append(before)
            after_pressure.append(after)
            overhead.append(timer)
        if not found_end:
            raise ValueError("raw file has no data_end marker")
    required = {
        "ece592_raw_format_version",
        "traversal",
        "random_seed",
        "target_reloads_per_sample",
        "timed_sample_count",
    }
    missing = required.difference(metadata)
    if missing:
        raise ValueError("missing raw metadata: {}".format(
            ", ".join(sorted(missing))))
    if metadata["traversal"] != "randomized-cross-level-eviction-probe":
        raise ValueError("raw file is not corrected eviction-probe data")
    declared = parse_decimal(metadata["timed_sample_count"],
                             "timed_sample_count")
    if declared != len(baseline) or declared < 1_000_000:
        raise ValueError("raw sample count is invalid")
    return metadata, baseline, after_pressure, overhead


def fmt(value):
    return "{:.17g}".format(value) if isinstance(value, float) else str(value)


def write_output(path, run_directory, plan_sha, rows):
    columns = [
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
        "raw_filename",
        "raw_sha256",
        "timer_unit",
        "target_reloads_per_sample",
        "baseline_median_ticks_per_target",
        "after_pressure_median_ticks_per_target",
        "delta_median_ticks_per_target",
        "ratio_after_to_baseline",
        "baseline_p95_ticks_per_target",
        "after_pressure_p95_ticks_per_target",
        "overhead_median_raw_ticks",
    ]
    with open(path, "x", encoding="ascii", newline="\n") as stream:
        stream.write("ece592_eviction_processed_format_version=1\n")
        stream.write("summary_purpose=8.2.7_cross_level_eviction_behavior\n")
        stream.write("source_run_directory={}\n".format(
            os.path.abspath(run_directory)))
        stream.write("source_eviction_plan_sha256={}\n".format(plan_sha))
        stream.write("processing_command={}\n".format(
            " ".join(shlex.quote(argument) for argument in sys.argv)))
        stream.write("processing_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("timer_overhead_subtracted=false\n")
        stream.write("cache_policy_labels_assigned=false\n")
        stream.write("data_begin\n")
        stream.write("\t".join(columns) + "\n")
        for row in rows:
            stream.write("\t".join(fmt(row[column]) for column in columns) + "\n")
        stream.write("data_end\n")
        stream.flush()
        os.fsync(stream.fileno())


def process(run_directory):
    plan_path = os.path.join(run_directory, "eviction_plan.tsv")
    manifest_path = os.path.join(run_directory, "execution_manifest.tsv")
    _, plan_rows = run_eviction_plan.read_plan(plan_path)
    manifest_rows = read_manifest(manifest_path)
    validate_manifest(plan_rows, manifest_rows)
    processed = []
    for manifest_row in manifest_rows:
        raw_path = os.path.join(run_directory, manifest_row["output_filename"])
        metadata, baseline, after_pressure, overhead = read_raw(raw_path)
        reloads = parse_decimal(metadata["target_reloads_per_sample"],
                                "target_reloads_per_sample")
        baseline_stats = summarize_raw.distribution(baseline)
        after_stats = summarize_raw.distribution(after_pressure)
        overhead_stats = summarize_raw.distribution(overhead)
        baseline_median = baseline_stats["median"] / reloads
        after_median = after_stats["median"] / reloads
        row = dict(manifest_row)
        row["raw_filename"] = manifest_row["output_filename"]
        row["raw_sha256"] = sha256_file(raw_path)
        row["timer_unit"] = metadata["timer_unit"]
        row["target_reloads_per_sample"] = reloads
        row["baseline_median_ticks_per_target"] = baseline_median
        row["after_pressure_median_ticks_per_target"] = after_median
        row["delta_median_ticks_per_target"] = after_median - baseline_median
        row["ratio_after_to_baseline"] = (
            after_median / baseline_median if baseline_median != 0 else 0.0)
        row["baseline_p95_ticks_per_target"] = baseline_stats["p95"] / reloads
        row["after_pressure_p95_ticks_per_target"] = after_stats["p95"] / reloads
        row["overhead_median_raw_ticks"] = overhead_stats["median"]
        processed.append(row)
    return processed, sha256_file(plan_path), len(plan_rows)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Process a completed eviction/reload run directory.")
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.run_directory):
        parser.error("--run-directory must name an existing directory")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(arguments.output))
    if not os.path.isdir(parent):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        rows, plan_sha, count = process(arguments.run_directory)
        write_output(arguments.output, arguments.run_directory, plan_sha, rows)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    print("run_directory={}".format(os.path.abspath(arguments.run_directory)))
    print("output_filename={}".format(arguments.output))
    print("validated_point_count={}".format(count))
    print("timer_overhead_subtracted=false")
    print("cache_policy_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
