#!/usr/bin/env python3
"""Validate and summarize every point in a completed inclusion/exclusion sweep.

Input  : the run directory produced by run_inclusion_policy_plan.py
Output : one processed TSV with one row per measured point

For each point this computes the full distribution (count, mean, population
standard deviation, min, p05, Q1, median, Q3, p95, max, Tukey fences, outlier
count) of three quantities, using exactly the definitions in summarize_raw.py
so the numbers are comparable with the rest of the Phase-I suite:

  baseline_raw_ticks        the target reload while it is still private
                            resident, measured immediately before the pressure
  after_pressure_raw_ticks  the identical addresses reloaded in the identical
                            order immediately after the pressure episode
  timer_overhead_raw_ticks  empty start/stop pairs, so fence and timer cost is
                            characterized instead of blindly subtracted

DERIVED QUANTITY: EVICTION PROBABILITY
--------------------------------------------------------------------------
The inference does not depend on any absolute latency number.  Each point
carries its own calibration: the baseline samples are the private-hit class,
measured on the same core, in the same round, through the same code path, so
every constant additive cost (loop overhead at -O0, LFENCE/RDTSCP overhead)
appears in both conditions and cancels in the comparison.

The classification threshold is a high quantile of that point's own baseline
distribution, by default the 99.9th percentile:

    threshold            = baseline quantile at 1 - false_positive_rate
    eviction probability = fraction of after-pressure samples above it

Setting the threshold this way fixes the classifier's false-positive rate by
construction, so the reported eviction probability is directly interpretable
and no latency number has to be chosen by hand.  The empirical false-positive
rate is recomputed from the baseline itself and reported, as a check that the
rule behaved as designed.

The suite's usual Tukey fence (Q3 + 1.5 x IQR) is also reported as a secondary
threshold, but it is not used for the primary number: when the private-hit
distribution is very tight the interquartile range collapses to zero, the
fence degenerates onto the median, and the rule misclassifies a large part of
the hit mode.  That failure mode is worth stating in the report, because a
tight hit distribution is the good case, not the bad one.

No policy label is assigned here.  That is left to the analyst, using the
inference rule documented in docs/INCLUSION_POLICY_EXPERIMENT.md.
"""

import argparse
import bisect
import csv
import gzip
import hashlib
import math
import os
import platform
import shlex
import sys
from array import array


EXPECTED_RAW_COLUMNS = (
    "sample_index",
    "baseline_raw_ticks",
    "after_pressure_raw_ticks",
    "timer_overhead_raw_ticks",
)

PLAN_COLUMNS = [
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

MANIFEST_COLUMNS = PLAN_COLUMNS + ["output_filename", "status", "return_code"]

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

# Raw-header keys copied verbatim into the processed row so every figure is
# traceable to the machine and build that produced it.
CARRIED_RAW_KEYS = (
    "experiment_name",
    "hostname",
    "kernel_release",
    "isa",
    "cpu_model",
    "page_size_bytes",
    "logical_cpu",
    "affinity_cpu_list",
    "physical_core_id",
    "physical_package_id",
    "numa_node",
    "thread_siblings_list",
    "compiler_version",
    "compiler_flags",
    "git_commit",
    "smt_siblings_idle",
    "timer_name",
    "timer_unit",
    "timer_frequency_hz_valid",
    "target_bytes",
    "target_line_spacing_bytes",
    "target_node_count",
    "pressure_source",
    "pressure_bytes",
    "pressure_node_count",
    "pressure_order",
    "pressure_passes_per_round",
    "pressure_pass_count",
    "helper_pass_count",
    "measuring_logical_cpu",
    "measuring_physical_core_id",
    "measuring_physical_package_id",
    "helper_used",
    "helper_logical_cpu",
    "helper_physical_core_id",
    "helper_physical_package_id",
    "helper_same_package",
    "helper_is_smt_sibling",
    "timed_sample_count",
    "round_count",
    "samples_per_round",
    "accesses_per_sample",
    "warmup_round_count",
    "random_seed",
)

DERIVED_COLUMNS = [
    "requested_false_positive_rate",
    "eviction_threshold_ticks",
    "after_pressure_above_threshold_count",
    "eviction_probability",
    "baseline_above_threshold_fraction",
    "threshold_is_confident",
    "tukey_fence_threshold_ticks",
    "eviction_probability_tukey_fence",
    "delta_median_ticks",
    "baseline_median_ticks_per_access",
    "after_pressure_median_ticks_per_access",
    "delta_median_ticks_per_access",
    "separation_ratio_median",
]

# The empirical false-positive rate should not exceed the requested rate by
# more than this factor; if it does, the threshold is sitting inside the hit
# mode and the point cannot support a confident classification.
FALSE_POSITIVE_TOLERANCE_FACTOR = 3.0
DEFAULT_FALSE_POSITIVE_RATE = 0.001


# --------------------------------------------------------------------------
# Statistics (identical definitions to summarize_raw.py)
# --------------------------------------------------------------------------

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
    }, sorted_values


def fraction_above(sorted_values, threshold):
    above = len(sorted_values) - bisect.bisect_right(sorted_values, threshold)
    return above, above / float(len(sorted_values))


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_maybe_compressed(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="ascii", newline="")
    return open(path, "r", encoding="ascii", newline="")


def read_raw(path):
    """Return (metadata, baseline, after_pressure, overhead) as int arrays."""
    metadata = {}
    baseline = array("q")
    after_pressure = array("q")
    overhead = array("q")

    with open_maybe_compressed(path) as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid metadata line: {!r}".format(line))
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError(
                    "invalid or duplicate metadata key: {!r}".format(key))
            metadata[key] = value
        else:
            raise ValueError("raw file has no data_begin marker")

        heading = stream.readline().rstrip("\r\n").split("\t")
        if tuple(heading) != EXPECTED_RAW_COLUMNS:
            raise ValueError("unexpected raw-data columns: {!r}".format(heading))

        found_end = False
        expected_index = 0
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_end":
                found_end = True
                break
            fields = line.split("\t")
            if len(fields) != 4:
                raise ValueError("malformed raw-data row")
            index = int(fields[0], 10)
            if index != expected_index:
                raise ValueError(
                    "sample index {} found where {} was expected".format(
                        index, expected_index))
            first = int(fields[1], 10)
            second = int(fields[2], 10)
            third = int(fields[3], 10)
            if first < 0 or second < 0 or third < 0:
                raise ValueError("negative timer value in raw data")
            baseline.append(first)
            after_pressure.append(second)
            overhead.append(third)
            expected_index += 1

        if not found_end:
            raise ValueError("raw file has no data_end marker")

    return metadata, baseline, after_pressure, overhead


def read_tsv_block(path, expected_columns, integer_columns):
    metadata = {}
    rows = []
    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid metadata line: {!r}".format(line))
            key, value = line.split("=", 1)
            metadata[key] = value
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != expected_columns:
            raise ValueError("unexpected columns in {}: {!r}".format(
                path, reader.fieldnames))
        for record in reader:
            if record[expected_columns[0]] == "data_end":
                break
            row = {}
            for column in expected_columns:
                value = record[column]
                row[column] = (int(value, 10) if column in integer_columns
                               else value)
            rows.append(row)
    return metadata, rows


def read_manifest(path):
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != MANIFEST_COLUMNS:
            raise ValueError("unexpected manifest columns: {!r}".format(
                reader.fieldnames))
        integer_columns = set(PLAN_COLUMNS) - {"pressure_source",
                                               "pressure_order"}
        for record in reader:
            row = {}
            for column in MANIFEST_COLUMNS:
                value = record[column]
                if column in integer_columns or column == "return_code":
                    row[column] = int(value, 10)
                else:
                    row[column] = value
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_raw_against_plan(metadata, row, raw_filename):
    """Every plan parameter must appear unchanged in the raw file header."""
    checks = {
        "target_bytes": row["target_bytes"],
        "target_line_spacing_bytes": row["target_line_spacing_bytes"],
        "accesses_per_sample": row["accesses_per_sample"],
        "random_seed": row["point_seed"],
    }
    for key, expected in checks.items():
        if key not in metadata:
            raise ValueError("{}: raw file is missing {}".format(
                raw_filename, key))
        if int(metadata[key], 10) != expected:
            raise ValueError(
                "{}: {} is {} but the plan requested {}".format(
                    raw_filename, key, metadata[key], expected))
    if metadata.get("pressure_source") != row["pressure_source"]:
        raise ValueError("{}: pressure source does not match the plan".format(
            raw_filename))
    if row["pressure_source"] != "none":
        if int(metadata["pressure_bytes"], 10) != row["pressure_bytes"]:
            raise ValueError("{}: pressure footprint does not match".format(
                raw_filename))
    if row["pressure_source"] == "helper":
        if int(metadata["helper_logical_cpu"], 10) != row["helper_cpu"]:
            raise ValueError("{}: helper CPU does not match the plan".format(
                raw_filename))
        if metadata.get("helper_used") != "true":
            raise ValueError("{}: helper was not used".format(raw_filename))
        if int(metadata["helper_pass_count"], 10) <= 0:
            raise ValueError(
                "{}: helper completed no pressure passes".format(raw_filename))
    if int(metadata["timed_sample_count"], 10) < 1000000:
        raise ValueError("{}: fewer than one million timed samples".format(
            raw_filename))
    if metadata.get("cache_policy_labels_assigned") != "false":
        raise ValueError("{}: unexpected policy label in raw data".format(
            raw_filename))


# --------------------------------------------------------------------------
# Processing
# --------------------------------------------------------------------------

def statistic_columns(prefix):
    return ["{}_{}".format(prefix, name) for name in STATISTIC_NAMES]


def flatten_statistics(row, prefix, statistics):
    for name in STATISTIC_NAMES:
        row["{}_{}".format(prefix, name)] = statistics[name]


def format_value(value):
    if isinstance(value, float):
        return "{:.17g}".format(value)
    return str(value)


def process_points(run_directory, manifest_rows, false_positive_rate):
    processed = []
    for manifest_row in manifest_rows:
        if manifest_row["status"] != "complete":
            raise ValueError("manifest row {} is not complete".format(
                manifest_row["global_execution_index"]))
        raw_path = os.path.join(run_directory, manifest_row["output_filename"])
        if not os.path.isfile(raw_path):
            raise ValueError("missing raw file: {}".format(raw_path))

        metadata, baseline, after_pressure, overhead = read_raw(raw_path)
        validate_raw_against_plan(metadata, manifest_row,
                                  manifest_row["output_filename"])

        baseline_statistics, baseline_sorted = distribution(baseline)
        after_statistics, after_sorted = distribution(after_pressure)
        overhead_statistics, _ = distribution(overhead)

        threshold = quantile(baseline_sorted, 1.0 - false_positive_rate)
        above_count, eviction_probability = fraction_above(after_sorted,
                                                           threshold)
        _, false_positive = fraction_above(baseline_sorted, threshold)
        tukey_threshold = baseline_statistics["upper_outlier_fence"]
        _, eviction_probability_tukey = fraction_above(after_sorted,
                                                       tukey_threshold)
        group = manifest_row["accesses_per_sample"]

        row = {}
        for column in PLAN_COLUMNS:
            row[column] = manifest_row[column]
        row["raw_filename"] = manifest_row["output_filename"]
        row["raw_sha256"] = sha256_file(raw_path)
        for key in CARRIED_RAW_KEYS:
            row["raw_" + key] = metadata.get(key, "unavailable")

        flatten_statistics(row, "baseline_ticks", baseline_statistics)
        flatten_statistics(row, "after_pressure_ticks", after_statistics)
        flatten_statistics(row, "overhead_ticks", overhead_statistics)

        row["requested_false_positive_rate"] = false_positive_rate
        row["eviction_threshold_ticks"] = threshold
        row["after_pressure_above_threshold_count"] = above_count
        row["eviction_probability"] = eviction_probability
        row["baseline_above_threshold_fraction"] = false_positive
        row["threshold_is_confident"] = str(
            false_positive <= false_positive_rate *
            FALSE_POSITIVE_TOLERANCE_FACTOR).lower()
        row["tukey_fence_threshold_ticks"] = tukey_threshold
        row["eviction_probability_tukey_fence"] = eviction_probability_tukey
        row["delta_median_ticks"] = (after_statistics["median"] -
                                     baseline_statistics["median"])
        row["baseline_median_ticks_per_access"] = (
            baseline_statistics["median"] / group)
        row["after_pressure_median_ticks_per_access"] = (
            after_statistics["median"] / group)
        row["delta_median_ticks_per_access"] = (
            row["delta_median_ticks"] / group)
        row["separation_ratio_median"] = (
            after_statistics["median"] / baseline_statistics["median"]
            if baseline_statistics["median"] > 0 else float("nan"))

        processed.append(row)

    processed.sort(key=lambda item: (item["trial"], item["series_index"],
                                     item["pressure_bytes"]))
    return processed


def write_processed(path, run_directory, rows):
    columns = list(PLAN_COLUMNS)
    columns.extend(["raw_filename", "raw_sha256"])
    columns.extend("raw_" + key for key in CARRIED_RAW_KEYS)
    columns.extend(statistic_columns("baseline_ticks"))
    columns.extend(statistic_columns("after_pressure_ticks"))
    columns.extend(statistic_columns("overhead_ticks"))
    columns.extend(DERIVED_COLUMNS)

    created = False
    try:
        with open(path, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_inclusion_policy_processed_version=1\n")
            stream.write(
                "summary_purpose=8.2.7_inclusion_exclusion_behavior\n")
            stream.write("source_run_directory={}\n".format(
                os.path.abspath(run_directory)))
            stream.write("processing_script={}\n".format(
                os.path.basename(__file__)))
            stream.write("processing_command={}\n".format(" ".join(
                shlex.quote(argument) for argument in sys.argv)))
            stream.write("processing_working_directory={}\n".format(
                os.getcwd()))
            stream.write("python_version={}\n".format(
                platform.python_version()))
            stream.write("standard_deviation_definition=population\n")
            stream.write("quantile_method=linear interpolation at (n-1)*p\n")
            stream.write(
                "outlier_definition=outside q1-1.5*iqr and q3+1.5*iqr\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write(
                "eviction_threshold_rule=quantile of the same point's baseline "
                "distribution at 1-false_positive_rate\n")
            stream.write(
                "eviction_probability=fraction of after-pressure samples "
                "above that threshold\n")
            stream.write("cache_policy_labels_assigned=false\n")
            stream.write("processed_point_count={}\n".format(len(rows)))
            stream.write(
                "row_order=trial then series_index then pressure_bytes\n")
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
        description="Summarize a completed inclusion/exclusion sweep.")
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--false-positive-rate", type=float,
                        default=DEFAULT_FALSE_POSITIVE_RATE,
                        help="Baseline quantile used as the "
                             "classification threshold is "
                             "1 - this value.")
    arguments = parser.parse_args()
    if not 0.0 < arguments.false_positive_rate < 0.5:
        parser.error("--false-positive-rate must be in (0, 0.5)")
    if not os.path.isdir(arguments.run_directory):
        parser.error("--run-directory must name an existing directory")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(arguments.output))
    if not os.path.isdir(parent):
        parser.error("parent of --output must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    manifest_path = os.path.join(arguments.run_directory,
                                 "execution_manifest.tsv")
    try:
        manifest_rows = read_manifest(manifest_path)
        rows = process_points(arguments.run_directory, manifest_rows,
                              arguments.false_positive_rate)
        write_processed(arguments.output, arguments.run_directory, rows)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    unconfident = [row for row in rows
                   if row["threshold_is_confident"] == "false"]
    print("output_filename={}".format(arguments.output))
    print("processed_point_count={}".format(len(rows)))
    print("points_with_unconfident_threshold={}".format(len(unconfident)))
    print("cache_policy_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
