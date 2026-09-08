#!/usr/bin/env python3
"""Summarize Phase-I miss / next-level latency evidence from latency points."""

import argparse
import csv
import hashlib
import os
import platform
import shlex
import sys


STAT_PREFIX = "elapsed_raw_ticks_per_access_unadjusted_"
STAT_FIELDS = (
    "minimum",
    "q1",
    "median",
    "q3",
    "maximum",
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


def read_latency_selection(path):
    metadata = {}
    rows = []

    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid metadata line")
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("invalid or duplicate metadata key")
            metadata[key] = value
        else:
            raise ValueError("latency selection has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("latency selection has no column heading")
        required = {
            "evidence_rank",
            "dense_refined_interval_bytes",
            "dense_support_status",
            "point_role",
            "actual_span_bytes",
            "trial",
            "timed_sample_count",
            "dependent_accesses_per_sample",
            "timer_overhead_raw_ticks_median",
        }
        required.update(STAT_PREFIX + field for field in STAT_FIELDS)
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError("missing latency columns: {}".format(
                ", ".join(sorted(missing))))

        found_end = False
        first_column = reader.fieldnames[0]
        for record in reader:
            if record[first_column] == "data_end":
                found_end = True
                break
            if None in record:
                raise ValueError("latency row has extra fields")
            if int(record["timed_sample_count"], 10) < 1_000_000:
                raise ValueError("latency row has fewer than 1000000 samples")
            rows.append(record)

    if not found_end:
        raise ValueError("latency selection has no data_end marker")

    required_metadata = {
        "ece592_latency_selection_format_version",
        "cache_boundary_labels_assigned",
        "timer_overhead_subtracted",
        "source_raw_hostname",
        "source_raw_isa",
        "source_raw_timer_unit",
        "source_raw_timed_sample_count",
    }
    missing_metadata = required_metadata.difference(metadata)
    if missing_metadata:
        raise ValueError("missing latency metadata: {}".format(
            ", ".join(sorted(missing_metadata))))
    if metadata["cache_boundary_labels_assigned"] != "false":
        raise ValueError("input must not assign cache boundary labels")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("input must use unadjusted raw timing units")
    return metadata, rows


def grouped_by_rank(rows):
    groups = {}
    for row in rows:
        rank = int(row["evidence_rank"], 10)
        groups.setdefault(rank, []).append(row)
    return groups


def select_role(rows, role):
    matches = [row for row in rows if row["point_role"] == role]
    if not matches:
        raise ValueError("missing role {} for evidence rank {}".format(
            role, rows[0]["evidence_rank"]))
    return sorted(matches, key=lambda row: (
        int(row["trial"], 10), int(row["actual_span_bytes"], 10)))[0]


def f(row, suffix):
    return float(row[STAT_PREFIX + suffix])


def evidence_rows(selection_rows):
    output_rows = []
    for rank, rows in sorted(grouped_by_rank(selection_rows).items()):
        below = select_role(rows, "below_refined_interval")
        upper = select_role(rows, "near_refined_upper_edge")
        above = select_role(rows, "above_refined_interval")

        below_median = f(below, "median")
        upper_median = f(upper, "median")
        above_median = f(above, "median")
        output_rows.append({
            "evidence_rank": rank,
            "dense_refined_interval_bytes":
                below["dense_refined_interval_bytes"],
            "dense_support_status": below["dense_support_status"],
            "below_span_bytes": below["actual_span_bytes"],
            "near_upper_span_bytes": upper["actual_span_bytes"],
            "above_span_bytes": above["actual_span_bytes"],
            "below_median_ticks_per_access": below_median,
            "near_upper_median_ticks_per_access": upper_median,
            "above_median_ticks_per_access": above_median,
            "above_minus_below_median_ticks_per_access":
                above_median - below_median,
            "above_divided_by_below_median_ratio":
                above_median / below_median if below_median > 0.0 else 0.0,
            "below_iqr_ticks_per_access": f(below, "q3") - f(below, "q1"),
            "above_iqr_ticks_per_access": f(above, "q3") - f(above, "q1"),
            "below_min_ticks_per_access": f(below, "minimum"),
            "above_max_ticks_per_access": f(above, "maximum"),
            "timed_sample_count": below["timed_sample_count"],
            "dependent_accesses_per_sample":
                below["dependent_accesses_per_sample"],
            "timer_overhead_raw_ticks_median":
                below["timer_overhead_raw_ticks_median"],
        })
    return output_rows


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Summarize miss/next-level latency evidence from selected "
            "Phase-I representative timing distributions."))
    parser.add_argument("--latency-representatives", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not os.path.isfile(args.latency_representatives):
        parser.error("--latency-representatives must name an existing file")
    if os.path.exists(args.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(args.output))
    if parent and not os.path.isdir(parent):
        parser.error("output parent directory must already exist")
    return args


def write_output(path, input_path, metadata, rows):
    columns = [
        "evidence_rank",
        "dense_refined_interval_bytes",
        "dense_support_status",
        "below_span_bytes",
        "near_upper_span_bytes",
        "above_span_bytes",
        "below_median_ticks_per_access",
        "near_upper_median_ticks_per_access",
        "above_median_ticks_per_access",
        "above_minus_below_median_ticks_per_access",
        "above_divided_by_below_median_ratio",
        "below_iqr_ticks_per_access",
        "above_iqr_ticks_per_access",
        "below_min_ticks_per_access",
        "above_max_ticks_per_access",
        "timed_sample_count",
        "dependent_accesses_per_sample",
        "timer_overhead_raw_ticks_median",
    ]
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("ece592_miss_latency_evidence_format_version=1\n")
        stream.write("evidence_purpose=8.2.6_miss_next_level_latency\n")
        stream.write("method=compare_representative_points_below_and_above_measured_timing_boundaries\n")
        stream.write("cache_boundary_labels_assigned=false\n")
        stream.write("timer_overhead_subtracted=false\n")
        stream.write("source_latency_representatives_file={}\n".format(
            os.path.abspath(input_path)))
        stream.write("source_latency_representatives_sha256={}\n".format(
            sha256_file(input_path)))
        for key in ("source_raw_hostname", "source_raw_isa",
                    "source_raw_timer_unit", "source_raw_traversal",
                    "source_raw_timed_sample_count"):
            stream.write("{}={}\n".format(key, metadata[key]))
        stream.write("evidence_script={}\n".format(os.path.abspath(__file__)))
        stream.write("evidence_command={}\n".format(
            " ".join(shlex.quote(argument) for argument in sys.argv)))
        stream.write("evidence_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("evidence_row_count={}\n".format(len(rows)))
        stream.write("data_begin\n")
        stream.write("\t".join(columns) + "\n")
        writer = csv.DictWriter(
            stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        for row in rows:
            writer.writerow(row)
        stream.write("data_end\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, path)


def main():
    try:
        args = parse_arguments()
        metadata, selection_rows = read_latency_selection(
            args.latency_representatives)
        rows = evidence_rows(selection_rows)
        write_output(args.output, args.latency_representatives, metadata, rows)
        print("input_filename={}".format(args.latency_representatives))
        print("output_filename={}".format(args.output))
        print("evidence_row_count={}".format(len(rows)))
        print("cache_boundary_labels_assigned=false")
        print("status=ok")
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
