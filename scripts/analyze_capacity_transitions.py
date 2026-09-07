#!/usr/bin/env python3
"""Rank adjacent timing transitions without assigning cache-level labels."""

import argparse
import csv
import hashlib
import math
import os
import platform
import shlex
import statistics
import sys


MEDIAN_FIELD = "elapsed_raw_ticks_per_access_unadjusted_median"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_processed(path):
    metadata = {}
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid processed metadata line")
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("invalid or duplicate processed metadata key")
            metadata[key] = value
        else:
            raise ValueError("processed file has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        required = {"trial", "plot_index", "actual_span_bytes", MEDIAN_FIELD}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("processed file lacks transition columns")
        first_column = reader.fieldnames[0]
        found_end = False
        for record in reader:
            if record[first_column] == "data_end":
                found_end = True
                break
            if None in record:
                raise ValueError("processed row has extra fields")
            try:
                rows.append({
                    "trial": int(record["trial"], 10),
                    "plot_index": int(record["plot_index"], 10),
                    "span": int(record["actual_span_bytes"], 10),
                    "median": float(record[MEDIAN_FIELD]),
                })
            except ValueError as error:
                raise ValueError("invalid processed transition value") from error
        if not found_end or any(line.strip() for line in stream):
            raise ValueError("processed data markers are invalid")

    required_metadata = {
        "ece592_capacity_processed_format_version",
        "source_raw_traversal",
        "timer_overhead_subtracted",
        "source_plan_trial_count",
        "processed_point_count",
    }
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("missing processed metadata: {}".format(
            ", ".join(sorted(missing))))
    if metadata["ece592_capacity_processed_format_version"] != "1":
        raise ValueError("unsupported processed format version")
    if metadata["source_raw_traversal"] != \
            "randomized-dependent-single-cycle":
        raise ValueError("transition analysis requires randomized traversal")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("transition analysis requires unadjusted values")

    try:
        trial_count = int(metadata["source_plan_trial_count"], 10)
        point_count = int(metadata["processed_point_count"], 10)
    except ValueError as error:
        raise ValueError("invalid processed count metadata") from error
    if trial_count < 1 or point_count != len(rows):
        raise ValueError("processed count metadata does not match rows")

    by_span = {}
    for row in rows:
        if row["span"] <= 0 or row["median"] <= 0:
            raise ValueError("non-positive span or latency")
        by_span.setdefault(row["span"], []).append(row)

    points = []
    maximum_repeat_count = 0
    for span, span_rows in by_span.items():
        if len(span_rows) < 1:
            raise ValueError("working-set size has no measurements")
        if any(row["trial"] < 0 or row["trial"] >= trial_count
               for row in span_rows):
            raise ValueError("working-set size contains invalid trial number")
        maximum_repeat_count = max(maximum_repeat_count, len(span_rows))
        repeat_rows = sorted(span_rows, key=lambda row: (
            row["trial"], row["plot_index"]))
        points.append({
            "span": span,
            "plot_index": min(row["plot_index"] for row in span_rows),
            "repeat_medians": [row["median"] for row in repeat_rows],
            "median": statistics.median(
                row["median"] for row in span_rows),
        })
    points.sort(key=lambda point: point["span"])
    if len(points) < 2:
        raise ValueError("at least two working-set sizes are required")
    return metadata, trial_count, maximum_repeat_count, points


def build_transitions(points):
    transitions = []
    for index, (lower, upper) in enumerate(zip(points, points[1:])):
        span_ratio = upper["span"] / lower["span"]
        latency_ratio = upper["median"] / lower["median"]
        log_slope = math.log2(latency_ratio) / math.log2(span_ratio)
        relative_increase = latency_ratio - 1.0
        central = (lower["median"] + upper["median"]) / 2.0
        trial_disagreement = max(
            abs(value - point["median"]) / point["median"]
            for point in (lower, upper)
            for value in point["repeat_medians"])
        transitions.append({
            "interval_index": index,
            "lower_span": lower["span"],
            "upper_span": upper["span"],
            "lower_plot_index": lower["plot_index"],
            "upper_plot_index": upper["plot_index"],
            "lower_median": lower["median"],
            "upper_median": upper["median"],
            "span_ratio": span_ratio,
            "relative_increase": relative_increase,
            "log2_latency_slope": log_slope,
            "trial_disagreement_fraction": trial_disagreement,
            "rank": 0,
        })

    ranked = sorted(
        transitions,
        key=lambda row: (-row["log2_latency_slope"], row["lower_span"]))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return transitions


def processing_command():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_output(path, input_path, input_digest, metadata, trial_count,
                 maximum_repeat_count, transitions):
    created = False
    try:
        with open(path, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_transition_analysis_format_version=1\n")
            stream.write("source_processed_file={}\n".format(
                os.path.abspath(input_path)))
            stream.write("source_processed_sha256={}\n".format(input_digest))
            stream.write("source_hostname={}\n".format(
                metadata.get("source_raw_hostname", "unknown")))
            stream.write("source_isa={}\n".format(
                metadata.get("source_raw_isa", "unknown")))
            stream.write("source_timer_unit={}\n".format(
                metadata.get("source_raw_timer_unit", "unknown")))
            stream.write("source_traversal={}\n".format(
                metadata["source_raw_traversal"]))
            stream.write("trial_count={}\n".format(trial_count))
            stream.write("maximum_repeat_count_per_working_set={}\n".format(
                maximum_repeat_count))
            stream.write("comparison=adjacent_sorted_actual_span_points\n")
            stream.write("central_value=median_of_repeat_medians\n")
            stream.write("slope=log2(upper_median/lower_median)/log2(upper_span/lower_span)\n")
            stream.write("rank=descending_upward_log2_latency_slope\n")
            stream.write("cache_boundary_labels_assigned=false\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write("analysis_script={}\n".format(os.path.abspath(__file__)))
            stream.write("analysis_command={}\n".format(processing_command()))
            stream.write("analysis_working_directory={}\n".format(os.getcwd()))
            stream.write("python_version={}\n".format(platform.python_version()))
            stream.write("data_begin\n")
            columns = (
                "rank", "interval_index", "lower_span", "upper_span",
                "lower_plot_index", "upper_plot_index", "lower_median",
                "upper_median", "span_ratio", "relative_increase",
                "log2_latency_slope", "trial_disagreement_fraction")
            stream.write("\t".join(columns) + "\n")
            for row in sorted(transitions, key=lambda item: item["lower_span"]):
                stream.write("\t".join(
                    "{:.17g}".format(row[column])
                    if isinstance(row[column], float) else str(row[column])
                    for column in columns) + "\n")
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
        description="Rank adjacent capacity-sweep timing transitions.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    if not os.path.isfile(arguments.input):
        parser.error("--input must name an existing processed TSV")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    if not os.path.isdir(os.path.dirname(os.path.abspath(arguments.output))):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        metadata, trial_count, maximum_repeat_count, points = read_processed(
            arguments.input)
        transitions = build_transitions(points)
        write_output(arguments.output, arguments.input,
                     sha256_file(arguments.input), metadata, trial_count,
                     maximum_repeat_count, transitions)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("input_filename={}".format(arguments.input))
    print("output_filename={}".format(arguments.output))
    print("adjacent_interval_count={}".format(len(transitions)))
    print("maximum_repeat_count_per_working_set={}".format(
        maximum_repeat_count))
    print("cache_boundary_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
