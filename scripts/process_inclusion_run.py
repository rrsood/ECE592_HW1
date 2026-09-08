#!/usr/bin/env python3
"""Validate and summarize every point in a completed inclusion/reuse sweep."""

import argparse
import csv
import hashlib
import os
import platform
import shlex
import sys

import run_inclusion_plan
import summarize_raw


MANIFEST_COLUMNS = [
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
    "output_filename",
    "status",
    "return_code",
]

RAW_DATA_COLUMNS = (
    "sample_index",
    "probe_before_raw_ticks",
    "pressure_raw_ticks",
    "probe_after_raw_ticks",
    "timer_overhead_raw_ticks",
)

POINT_COLUMNS = [
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
    "raw_filename",
    "raw_sha256",
    "traversal",
    "timer_unit",
    "timed_sample_count",
    "warmup_batch_count",
]

STATISTIC_NAMES = (
    "count",
    "mean",
    "population_stddev",
    "minimum",
    "p05",
    "q1",
    "median",
    "q3",
    "p95",
    "maximum",
    "lower_outlier_fence",
    "upper_outlier_fence",
    "outlier_count",
)

COMMON_RAW_KEYS = (
    "experiment_name",
    "hostname",
    "kernel_release",
    "isa",
    "cpu_model",
    "cpu_model_source",
    "page_size_bytes",
    "logical_cpu",
    "affinity_cpu_list",
    "affinity_allowed_cpu_count",
    "physical_core_id",
    "physical_package_id",
    "topology_id_source",
    "numa_node",
    "thread_siblings_list",
    "compiler_version",
    "compiler_flags",
    "git_commit",
    "build_command",
    "environment_variables",
    "locality_method",
    "smt_siblings_idle",
    "timer_name",
    "timer_unit",
    "timer_frequency_hz",
    "timer_frequency_hz_valid",
    "traversal",
    "random_seed_applicable",
    "allocation_alignment_bytes",
    "timed_sample_count",
    "probe_accesses_per_sample",
    "pressure_accesses_per_sample",
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
            if None in record:
                raise ValueError("execution-manifest row has extra fields")
            row = {}
            for key in MANIFEST_COLUMNS[:10]:
                row[key] = parse_decimal(record[key], "manifest " + key)
            row["output_filename"] = record["output_filename"]
            row["status"] = record["status"]
            row["return_code"] = parse_decimal(
                record["return_code"], "manifest return_code")
            rows.append(row)
    if not rows:
        raise ValueError("execution manifest contains no rows")
    return rows


def validate_manifest(plan_rows, manifest_rows):
    if len(manifest_rows) != len(plan_rows):
        raise ValueError(
            "manifest has {} rows but plan requires {}".format(
                len(manifest_rows), len(plan_rows)))

    seen_filenames = set()
    for plan_row, manifest_row in zip(plan_rows, manifest_rows):
        for field in run_inclusion_plan.EXPECTED_COLUMNS:
            if manifest_row[field] != plan_row[field]:
                raise ValueError(
                    "manifest/plan mismatch at global index {} for {}".format(
                        plan_row["global_execution_index"], field))
        if manifest_row["status"] != "complete" or manifest_row["return_code"] != 0:
            raise ValueError(
                "inclusion sweep is not complete at global index {}".format(
                    plan_row["global_execution_index"]))
        filename = manifest_row["output_filename"]
        if (not filename or os.path.basename(filename) != filename or
                filename in seen_filenames):
            raise ValueError("unsafe or duplicate raw output filename")
        seen_filenames.add(filename)


def read_inclusion_raw(path):
    metadata = {}
    probe_before = []
    pressure = []
    probe_after = []
    overhead = []

    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid metadata line: {!r}".format(line))
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("invalid or duplicate metadata key: {!r}".format(key))
            metadata[key] = value
        else:
            raise ValueError("raw file has no data_begin marker")

        heading = tuple(stream.readline().rstrip("\r\n").split("\t"))
        if heading != RAW_DATA_COLUMNS:
            raise ValueError("unexpected raw-data columns: {!r}".format(heading))

        found_end = False
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_end":
                found_end = True
                break
            fields = line.split("\t")
            if len(fields) != len(RAW_DATA_COLUMNS):
                raise ValueError("malformed raw-data row")
            try:
                sample_index, before_value, pressure_value, after_value, overhead_value = (
                    int(field, 10) for field in fields)
            except ValueError as error:
                raise ValueError("non-integer raw-data row") from error
            expected_index = len(probe_before)
            if sample_index != expected_index:
                raise ValueError(
                    "sample index {} found where {} was expected".format(
                        sample_index, expected_index))
            if min(before_value, pressure_value, after_value, overhead_value) < 0:
                raise ValueError("negative timer value in raw data")
            probe_before.append(before_value)
            pressure.append(pressure_value)
            probe_after.append(after_value)
            overhead.append(overhead_value)

        if not found_end:
            raise ValueError("raw file has no data_end marker")
        if any(line.strip() for line in stream):
            raise ValueError("unexpected content after data_end")

    required_metadata = {
        "ece592_raw_format_version",
        "output_filename",
        "hostname",
        "timer_unit",
        "timed_sample_count",
        "probe_accesses_per_sample",
        "pressure_accesses_per_sample",
        "traversal",
        "random_seed",
    }
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("missing raw metadata: {}".format(
            ", ".join(sorted(missing))))
    if metadata["ece592_raw_format_version"] != "1":
        raise ValueError("unsupported raw format version")
    declared_count = parse_decimal(
        metadata["timed_sample_count"], "raw timed_sample_count")
    if declared_count != len(probe_before):
        raise ValueError("declared sample count does not match row count")
    if declared_count < 1_000_000:
        raise ValueError("raw file has fewer than 1000000 timed samples")

    return metadata, probe_before, pressure, probe_after, overhead


def require_raw_integer(metadata, key, expected):
    if key not in metadata:
        raise ValueError("raw file is missing {}".format(key))
    actual = parse_decimal(metadata[key], "raw " + key)
    if actual != expected:
        raise ValueError(
            "raw {}={} does not match expected {}".format(
                key, actual, expected))


def validate_raw_point(metadata, plan_row, raw_filename, build_command):
    if os.path.basename(metadata["output_filename"]) != raw_filename:
        raise ValueError("raw output_filename does not match manifest")
    require_raw_integer(metadata, "probe_node_count",
                        plan_row["probe_node_count"])
    require_raw_integer(metadata, "pressure_node_count",
                        plan_row["pressure_node_count"])
    require_raw_integer(metadata, "node_spacing_bytes",
                        plan_row["node_spacing_bytes"])
    require_raw_integer(metadata, "probe_accesses_per_sample",
                        plan_row["probe_accesses_per_sample"])
    require_raw_integer(metadata, "pressure_accesses_per_sample",
                        plan_row["pressure_accesses_per_sample"])
    require_raw_integer(metadata, "random_seed", plan_row["point_seed"])

    for key in COMMON_RAW_KEYS:
        if key not in metadata:
            raise ValueError("raw file is missing common metadata {}".format(key))
    if metadata["traversal"] != "randomized-inclusion-probe-pressure-probe":
        raise ValueError("unsupported raw traversal: {}".format(
            metadata["traversal"]))
    if metadata["random_seed_applicable"] != "true":
        raise ValueError("random_seed_applicable must be true")
    if metadata["build_command"] != build_command:
        raise ValueError("raw build_command does not match build-command.txt")


def stable_common_metadata(first_metadata, metadata, global_index):
    if first_metadata is None:
        return {key: metadata[key] for key in COMMON_RAW_KEYS}
    for key in COMMON_RAW_KEYS:
        if metadata[key] != first_metadata[key]:
            raise ValueError(
                "raw common metadata {} changed at global index {}".format(
                    key, global_index))
    return first_metadata


def format_value(value):
    if isinstance(value, float):
        return "{:.17g}".format(value)
    return str(value)


def statistic_columns(prefix):
    return [prefix + "_" + name for name in STATISTIC_NAMES]


def flatten_statistics(row, prefix, statistics):
    for name in STATISTIC_NAMES:
        row[prefix + "_" + name] = statistics[name]


def process_points(run_directory, plan_rows, manifest_rows, build_command):
    processed_rows = []
    common_metadata = None

    for plan_row, manifest_row in zip(plan_rows, manifest_rows):
        raw_filename = manifest_row["output_filename"]
        raw_path = os.path.join(run_directory, raw_filename)
        if not os.path.isfile(raw_path):
            raise ValueError("missing raw file: {}".format(raw_filename))
        raw_digest = sha256_file(raw_path)
        metadata, probe_before, pressure, probe_after, overhead = (
            read_inclusion_raw(raw_path))
        validate_raw_point(metadata, plan_row, raw_filename, build_command)
        common_metadata = stable_common_metadata(
            common_metadata, metadata, plan_row["global_execution_index"])

        before_stats = summarize_raw.scaled_distribution(
            summarize_raw.distribution(probe_before),
            plan_row["probe_accesses_per_sample"])
        pressure_stats = summarize_raw.scaled_distribution(
            summarize_raw.distribution(pressure),
            plan_row["pressure_accesses_per_sample"])
        after_stats = summarize_raw.scaled_distribution(
            summarize_raw.distribution(probe_after),
            plan_row["probe_accesses_per_sample"])
        overhead_stats = summarize_raw.distribution(overhead)

        before_median = before_stats["median"]
        after_median = after_stats["median"]
        row = {
            "global_execution_index": plan_row["global_execution_index"],
            "trial": plan_row["trial"],
            "trial_execution_index": plan_row["trial_execution_index"],
            "plot_index": plan_row["plot_index"],
            "probe_node_count": plan_row["probe_node_count"],
            "pressure_node_count": plan_row["pressure_node_count"],
            "node_spacing_bytes": plan_row["node_spacing_bytes"],
            "probe_accesses_per_sample":
                plan_row["probe_accesses_per_sample"],
            "pressure_accesses_per_sample":
                plan_row["pressure_accesses_per_sample"],
            "point_seed": plan_row["point_seed"],
            "raw_filename": raw_filename,
            "raw_sha256": raw_digest,
            "traversal": metadata["traversal"],
            "timer_unit": metadata["timer_unit"],
            "timed_sample_count": len(probe_before),
            "warmup_batch_count": parse_decimal(
                metadata["warmup_batch_count"], "raw warmup_batch_count"),
            "probe_after_minus_before_median_ticks_per_access":
                after_median - before_median,
            "probe_after_divided_by_before_median_ratio":
                after_median / before_median if before_median > 0.0 else 0.0,
        }
        flatten_statistics(
            row, "probe_before_raw_ticks_per_access_unadjusted", before_stats)
        flatten_statistics(
            row, "pressure_raw_ticks_per_access_unadjusted", pressure_stats)
        flatten_statistics(
            row, "probe_after_raw_ticks_per_access_unadjusted", after_stats)
        flatten_statistics(row, "timer_overhead_raw_ticks", overhead_stats)
        processed_rows.append(row)

    processed_rows.sort(key=lambda row: (
        row["trial"], row["probe_node_count"], row["pressure_node_count"],
        row["global_execution_index"]))
    return common_metadata, processed_rows


def processing_command():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_processed(path, run_directory, plan_path, manifest_path,
                    build_command_path, plan_metadata, common_metadata, rows):
    columns = list(POINT_COLUMNS)
    columns.extend([
        "probe_after_minus_before_median_ticks_per_access",
        "probe_after_divided_by_before_median_ratio",
    ])
    columns.extend(statistic_columns(
        "probe_before_raw_ticks_per_access_unadjusted"))
    columns.extend(statistic_columns(
        "pressure_raw_ticks_per_access_unadjusted"))
    columns.extend(statistic_columns(
        "probe_after_raw_ticks_per_access_unadjusted"))
    columns.extend(statistic_columns("timer_overhead_raw_ticks"))

    created = False
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write("ece592_inclusion_processed_format_version=1\n")
            stream.write("summary_purpose=8.2.7_inclusion_exclusion_behavior\n")
            stream.write("source_run_directory={}\n".format(run_directory))
            stream.write("source_inclusion_plan_sha256={}\n".format(
                sha256_file(plan_path)))
            stream.write("source_execution_manifest_sha256={}\n".format(
                sha256_file(manifest_path)))
            stream.write("source_build_command_sha256={}\n".format(
                sha256_file(build_command_path)))
            for key, value in plan_metadata.items():
                stream.write("source_plan_{}={}\n".format(key, value))
            for key in COMMON_RAW_KEYS:
                stream.write("source_raw_{}={}\n".format(
                    key, common_metadata[key]))
            stream.write("processing_script={}\n".format(
                os.path.abspath(__file__)))
            stream.write("processing_command={}\n".format(
                processing_command()))
            stream.write("processing_working_directory={}\n".format(os.getcwd()))
            stream.write("python_version={}\n".format(platform.python_version()))
            stream.write("standard_deviation_definition=population\n")
            stream.write("quantile_method=linear interpolation at (n-1)*p\n")
            stream.write(
                "outlier_rule=values outside Q1-1.5*IQR or Q3+1.5*IQR\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write("cache_inclusion_labels_assigned=false\n")
            stream.write("processed_point_count={}\n".format(len(rows)))
            stream.write("row_order=trial then probe_node_count then pressure_node_count\n")
            stream.write("data_begin\n")
            stream.write("\t".join(columns) + "\n")
            for row in rows:
                stream.write("\t".join(
                    format_value(row[column]) for column in columns) + "\n")
            stream.write("data_end\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize a completed inclusion/reuse run directory."))
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    arguments.run_directory = os.path.abspath(arguments.run_directory)
    if not os.path.isdir(arguments.run_directory):
        parser.error("--run-directory must name an existing directory")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    output_parent = os.path.dirname(os.path.abspath(arguments.output))
    if not os.path.isdir(output_parent):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    plan_path = os.path.join(arguments.run_directory, "inclusion_plan.tsv")
    manifest_path = os.path.join(
        arguments.run_directory, "execution_manifest.tsv")
    build_command_path = os.path.join(arguments.run_directory,
                                      "build-command.txt")

    try:
        for path in (plan_path, manifest_path, build_command_path):
            if not os.path.isfile(path):
                raise ValueError("required run artifact is missing: {}".format(
                    os.path.basename(path)))
        plan_metadata, plan_rows = run_inclusion_plan.read_plan(plan_path)
        build_command = run_inclusion_plan.read_build_command(
            build_command_path)
        manifest_rows = read_manifest(manifest_path)
        validate_manifest(plan_rows, manifest_rows)
        common_metadata, processed_rows = process_points(
            arguments.run_directory, plan_rows, manifest_rows, build_command)
        write_processed(
            arguments.output, arguments.run_directory, plan_path,
            manifest_path, build_command_path, plan_metadata, common_metadata,
            processed_rows)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("run_directory={}".format(arguments.run_directory))
    print("output_filename={}".format(arguments.output))
    print("validated_point_count={}".format(len(processed_rows)))
    print("timer_overhead_subtracted=false")
    print("cache_inclusion_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
