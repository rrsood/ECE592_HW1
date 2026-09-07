#!/usr/bin/env python3
"""Validate an ECE 592 raw file and calculate required distribution statistics."""

import argparse
import bisect
import hashlib
import math
import os
import platform
import shlex
import sys


EXPECTED_COLUMNS = (
    "sample_index",
    "elapsed_raw_ticks",
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


def read_raw(path):
    metadata = {}
    elapsed = []
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

        heading = stream.readline().rstrip("\r\n").split("\t")
        if tuple(heading) != EXPECTED_COLUMNS:
            raise ValueError("unexpected raw-data columns: {!r}".format(heading))

        found_end = False
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_end":
                found_end = True
                break

            fields = line.split("\t")
            if len(fields) != 3:
                raise ValueError("malformed raw-data row")
            try:
                sample_index, elapsed_value, overhead_value = (
                    int(field, 10) for field in fields)
            except ValueError as error:
                raise ValueError("non-integer raw-data row") from error

            expected_index = len(elapsed)
            if sample_index != expected_index:
                raise ValueError(
                    "sample index {} found where {} was expected".format(
                        sample_index, expected_index))
            if elapsed_value < 0 or overhead_value < 0:
                raise ValueError("negative timer value in raw data")

            elapsed.append(elapsed_value)
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
        "dependent_accesses_per_sample",
        "traversal",
        "random_seed",
    }
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("missing raw metadata: {}".format(
            ", ".join(sorted(missing))))
    if metadata["ece592_raw_format_version"] != "1":
        raise ValueError("unsupported raw format version")

    try:
        declared_count = int(metadata["timed_sample_count"], 10)
        accesses_per_sample = int(
            metadata["dependent_accesses_per_sample"], 10)
    except ValueError as error:
        raise ValueError("invalid numeric raw metadata") from error
    if declared_count != len(elapsed):
        raise ValueError(
            "declared sample count {} does not match {} rows".format(
                declared_count, len(elapsed)))
    if declared_count < 1_000_000:
        raise ValueError("raw file has fewer than 1000000 timed samples")
    if accesses_per_sample <= 0:
        raise ValueError("dependent access count must be positive")

    return metadata, accesses_per_sample, elapsed, overhead


def quantile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    fraction = position - lower_index
    return (sorted_values[lower_index] * (1.0 - fraction) +
            sorted_values[upper_index] * fraction)


def distribution(values):
    count = 0
    mean = 0.0
    second_moment = 0.0

    for value in values:
        count += 1
        delta = value - mean
        mean += delta / count
        second_moment += delta * (value - mean)

    sorted_values = sorted(values)
    q1 = quantile(sorted_values, 0.25)
    q3 = quantile(sorted_values, 0.75)
    interquartile_range = q3 - q1
    lower_fence = q1 - 1.5 * interquartile_range
    upper_fence = q3 + 1.5 * interquartile_range
    below = bisect.bisect_left(sorted_values, lower_fence)
    above = count - bisect.bisect_right(sorted_values, upper_fence)

    return {
        "count": count,
        "mean": mean,
        "population_stddev": math.sqrt(second_moment / count),
        "minimum": float(sorted_values[0]),
        "p05": quantile(sorted_values, 0.05),
        "q1": q1,
        "median": quantile(sorted_values, 0.50),
        "q3": q3,
        "p95": quantile(sorted_values, 0.95),
        "maximum": float(sorted_values[-1]),
        "lower_outlier_fence": lower_fence,
        "upper_outlier_fence": upper_fence,
        "outlier_count": below + above,
    }


def scaled_distribution(statistics, divisor):
    scaled = dict(statistics)
    for key in (
            "mean", "population_stddev", "minimum", "p05", "q1",
            "median", "q3", "p95", "maximum", "lower_outlier_fence",
            "upper_outlier_fence"):
        scaled[key] = statistics[key] / divisor
    return scaled


def reconstruct_command():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_summary(path, raw_path, raw_digest, metadata, accesses_per_sample,
                  elapsed_statistics, overhead_statistics):
    per_access_statistics = scaled_distribution(
        elapsed_statistics, accesses_per_sample)
    metric_order = (
        "count", "mean", "population_stddev", "minimum", "p05", "q1",
        "median", "q3", "p95", "maximum", "lower_outlier_fence",
        "upper_outlier_fence", "outlier_count")

    with open(path, "x", encoding="ascii", newline="\n") as stream:
        stream.write("ece592_summary_format_version=1\n")
        stream.write("source_raw_file={}\n".format(os.path.abspath(raw_path)))
        stream.write("source_raw_sha256={}\n".format(raw_digest))
        for key, value in metadata.items():
            stream.write("source_{}={}\n".format(key, value))
        stream.write("dependent_accesses_per_sample={}\n".format(
            accesses_per_sample))
        stream.write("processing_command={}\n".format(reconstruct_command()))
        stream.write("processing_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("standard_deviation_definition=population\n")
        stream.write("quantile_method=linear interpolation at (n-1)*p\n")
        stream.write("outlier_rule=values outside Q1-1.5*IQR or Q3+1.5*IQR\n")
        stream.write("timer_overhead_subtracted=false\n")
        stream.write("data_begin\n")
        stream.write("metric\t" + "\t".join(metric_order) + "\n")

        metric_rows = (
            ("elapsed_batch_raw_ticks", elapsed_statistics),
            ("elapsed_raw_ticks_per_access_unadjusted", per_access_statistics),
            ("timer_overhead_raw_ticks", overhead_statistics),
        )
        for metric_name, statistics in metric_rows:
            values = []
            for key in metric_order:
                value = statistics[key]
                if isinstance(value, float):
                    values.append("{:.17g}".format(value))
                else:
                    values.append(str(value))
            stream.write(metric_name + "\t" + "\t".join(values) + "\n")

        stream.write("data_end\n")
        stream.flush()
        os.fsync(stream.fileno())


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Validate and summarize one complete ECE 592 raw file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if not os.path.isfile(arguments.input):
        parser.error("--input must name an existing raw file")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    output_parent = os.path.dirname(os.path.abspath(arguments.output))
    if not os.path.isdir(output_parent):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        raw_digest = sha256_file(arguments.input)
        metadata, accesses_per_sample, elapsed, overhead = read_raw(
            arguments.input)
        elapsed_statistics = distribution(elapsed)
        overhead_statistics = distribution(overhead)
        write_summary(arguments.output, arguments.input, raw_digest, metadata,
                      accesses_per_sample, elapsed_statistics,
                      overhead_statistics)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("input_filename={}".format(arguments.input))
    print("output_filename={}".format(arguments.output))
    print("validated_sample_count={}".format(len(elapsed)))
    print("timer_overhead_subtracted=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
