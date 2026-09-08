#!/usr/bin/env python3
"""Select timing-only representative latency points from a capacity sweep."""

import argparse
import csv
import hashlib
import os
import platform
import shlex
import sys


STAT_COLUMNS = (
    "elapsed_raw_ticks_per_access_unadjusted_mean",
    "elapsed_raw_ticks_per_access_unadjusted_population_stddev",
    "elapsed_raw_ticks_per_access_unadjusted_minimum",
    "elapsed_raw_ticks_per_access_unadjusted_p05",
    "elapsed_raw_ticks_per_access_unadjusted_q1",
    "elapsed_raw_ticks_per_access_unadjusted_median",
    "elapsed_raw_ticks_per_access_unadjusted_q3",
    "elapsed_raw_ticks_per_access_unadjusted_p95",
    "elapsed_raw_ticks_per_access_unadjusted_maximum",
    "elapsed_raw_ticks_per_access_unadjusted_outlier_count",
    "timer_overhead_raw_ticks_median",
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


def read_tsv_with_metadata(path):
    metadata = {}
    rows = []

    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid metadata line in {}".format(path))
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("invalid or duplicate metadata key")
            metadata[key] = value
        else:
            raise ValueError("file has no data_begin marker: {}".format(path))

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("file has no data header: {}".format(path))
        first_column = reader.fieldnames[0]
        for record in reader:
            if record[first_column] == "data_end":
                break
            if None in record:
                raise ValueError("row has extra fields in {}".format(path))
            rows.append(record)

    return metadata, rows


def parse_interval(text):
    lower, upper = text.split("..", 1)
    return int(lower, 10), int(upper, 10)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Select representative hit-latency points from timing-only "
            "capacity data, without assigning cache labels."))
    parser.add_argument("--processed-capacity", required=True)
    parser.add_argument("--capacity-evidence", required=True)
    parser.add_argument("--top-count", required=True, type=int)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if arguments.top_count <= 0:
        parser.error("--top-count must be positive")
    if not os.path.isfile(arguments.processed_capacity):
        parser.error("--processed-capacity must name an existing file")
    if not os.path.isfile(arguments.capacity_evidence):
        parser.error("--capacity-evidence must name an existing file")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(arguments.output))
    if not os.path.isdir(parent):
        parser.error("output parent directory must already exist")
    return arguments


def processing_command():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def capacity_points(rows):
    required = {
        "actual_span_bytes",
        "trial",
        "raw_filename",
        "raw_sha256",
        "timed_sample_count",
        "dependent_accesses_per_sample",
    }
    required.update(STAT_COLUMNS)

    points = []
    for row in rows:
        missing = required.difference(row)
        if missing:
            raise ValueError("processed capacity row is missing: {}".format(
                ", ".join(sorted(missing))))
        sample_count = int(row["timed_sample_count"], 10)
        if sample_count < 1_000_000:
            raise ValueError("latency point has fewer than 1000000 samples")
        points.append({
            "span": int(row["actual_span_bytes"], 10),
            "trial": int(row["trial"], 10),
            "row": row,
        })

    if not points:
        raise ValueError("processed capacity file contains no rows")
    return sorted(points, key=lambda point: (point["span"], point["trial"]))


def evidence_boundaries(rows, top_count):
    boundaries = []
    for row in rows:
        if len(boundaries) >= top_count:
            break
        rank = int(row["evidence_rank"], 10)
        lower, upper = parse_interval(row["dense_refined_interval_bytes"])
        boundaries.append({
            "rank": rank,
            "lower": lower,
            "upper": upper,
            "support": row["dense_support_status"],
        })
    if not boundaries:
        raise ValueError("capacity evidence file contains no boundaries")
    return boundaries


def nearest_point(points, target):
    return min(points, key=lambda point: (
        abs(point["span"] - target), point["span"], point["trial"]))


def side_point(points, boundary, want_below):
    if want_below:
        candidates = [point for point in points if point["span"] < boundary]
        if candidates:
            return max(candidates, key=lambda point: (point["span"], point["trial"]))
    else:
        candidates = [point for point in points if point["span"] > boundary]
        if candidates:
            return min(candidates, key=lambda point: (point["span"], point["trial"]))
    return nearest_point(points, boundary)


def selected_rows(points, boundaries):
    selections = []
    seen = set()
    for boundary in boundaries:
        candidates = (
            ("below_refined_interval", side_point(points, boundary["lower"], True)),
            ("near_refined_lower_edge", nearest_point(points, boundary["lower"])),
            ("near_refined_upper_edge", nearest_point(points, boundary["upper"])),
            ("above_refined_interval", side_point(points, boundary["upper"], False)),
        )
        for role, point in candidates:
            key = (boundary["rank"], role, point["span"], point["trial"])
            if key in seen:
                continue
            seen.add(key)
            selections.append((boundary, role, point))
    return selections


def write_output(path, processed_path, evidence_path, processed_metadata,
                 evidence_metadata, selections):
    columns = [
        "evidence_rank",
        "dense_refined_interval_bytes",
        "dense_support_status",
        "point_role",
        "actual_span_bytes",
        "trial",
        "raw_filename",
        "raw_sha256",
        "timed_sample_count",
        "dependent_accesses_per_sample",
    ]
    columns.extend(STAT_COLUMNS)

    created = False
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write("ece592_latency_selection_format_version=1\n")
            stream.write("selection_purpose=8.2.5_hit_latency_distribution_evidence\n")
            stream.write("cache_boundary_labels_assigned=false\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write("source_processed_capacity_file={}\n".format(
                os.path.abspath(processed_path)))
            stream.write("source_processed_capacity_sha256={}\n".format(
                sha256_file(processed_path)))
            stream.write("source_capacity_evidence_file={}\n".format(
                os.path.abspath(evidence_path)))
            stream.write("source_capacity_evidence_sha256={}\n".format(
                sha256_file(evidence_path)))
            for key in ("source_raw_hostname", "source_raw_isa",
                        "source_raw_timer_unit", "source_raw_traversal",
                        "source_raw_timed_sample_count"):
                stream.write("{}={}\n".format(key, processed_metadata[key]))
            stream.write("source_evidence_scope={}\n".format(
                evidence_metadata.get("evidence_scope", "not-recorded")))
            stream.write("selection_rule=nearest measured points below near and above each refined timing boundary\n")
            stream.write("selection_script={}\n".format(
                os.path.abspath(__file__)))
            stream.write("selection_command={}\n".format(processing_command()))
            stream.write("selection_working_directory={}\n".format(os.getcwd()))
            stream.write("python_version={}\n".format(platform.python_version()))
            stream.write("selected_point_count={}\n".format(len(selections)))
            stream.write("data_begin\n")
            stream.write("\t".join(columns) + "\n")
            writer = csv.DictWriter(
                stream, fieldnames=columns, delimiter="\t",
                lineterminator="\n")
            for boundary, role, point in selections:
                source = point["row"]
                output = {
                    "evidence_rank": boundary["rank"],
                    "dense_refined_interval_bytes": "{}..{}".format(
                        boundary["lower"], boundary["upper"]),
                    "dense_support_status": boundary["support"],
                    "point_role": role,
                    "actual_span_bytes": point["span"],
                    "trial": point["trial"],
                    "raw_filename": source["raw_filename"],
                    "raw_sha256": source["raw_sha256"],
                    "timed_sample_count": source["timed_sample_count"],
                    "dependent_accesses_per_sample":
                        source["dependent_accesses_per_sample"],
                }
                for column in STAT_COLUMNS:
                    output[column] = source[column]
                writer.writerow(output)
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


def main():
    arguments = parse_arguments()
    try:
        processed_metadata, processed_rows = read_tsv_with_metadata(
            arguments.processed_capacity)
        evidence_metadata, evidence_rows = read_tsv_with_metadata(
            arguments.capacity_evidence)
        if processed_metadata.get("ece592_capacity_processed_format_version") != "1":
            raise ValueError("unsupported processed capacity format")
        if processed_metadata.get("timer_overhead_subtracted") != "false":
            raise ValueError("latency selection requires unadjusted timer values")
        if processed_metadata.get("source_raw_traversal") != \
                "randomized-dependent-single-cycle":
            raise ValueError("latency selection requires randomized dependent data")
        points = capacity_points(processed_rows)
        boundaries = evidence_boundaries(evidence_rows, arguments.top_count)
        selections = selected_rows(points, boundaries)
        write_output(arguments.output, arguments.processed_capacity,
                     arguments.capacity_evidence, processed_metadata,
                     evidence_metadata, selections)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("output_filename={}".format(arguments.output))
    print("selected_point_count={}".format(len(selections)))
    print("cache_boundary_labels_assigned=false")
    print("timer_overhead_subtracted=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
