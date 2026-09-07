#!/usr/bin/env python3
"""Create a report-facing capacity evidence summary without cache labels."""

import argparse
import csv
import hashlib
import os
import platform
import shlex
import sys


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_table(path, version_key):
    metadata = {}
    rows = []
    with open(path, "r", encoding="ascii", newline="") as stream:
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
            raise ValueError("table has no data_begin marker")

        if version_key not in metadata:
            raise ValueError("missing expected version key")

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("table has no data header")
        first_column = reader.fieldnames[0]
        found_end = False
        for record in reader:
            if record[first_column] == "data_end":
                found_end = True
                break
            if None in record:
                raise ValueError("row has extra fields")
            rows.append(record)
        if not found_end or any(line.strip() for line in stream):
            raise ValueError("table data markers are invalid")
    return metadata, rows


def float_field(record, key):
    return float(record[key])


def int_field(record, key):
    return int(record[key], 10)


def build_summary(candidate_rows, top_count):
    selected = sorted(candidate_rows,
                      key=lambda row: int_field(row, "coarse_rank"))[:top_count]
    summary = []
    for row in selected:
        summary.append({
            "evidence_rank": int_field(row, "coarse_rank"),
            "coarse_interval_bytes": "{}..{}".format(
                row["coarse_lower_span"], row["coarse_upper_span"]),
            "coarse_relative_increase": float_field(
                row, "coarse_relative_increase"),
            "coarse_trial_disagreement_fraction": float_field(
                row, "coarse_trial_disagreement_fraction"),
            "dense_overlapping_interval_count": int_field(
                row, "dense_overlapping_interval_count"),
            "dense_refined_interval_bytes": "{}..{}".format(
                row["dense_best_lower_span"], row["dense_best_upper_span"]),
            "dense_relative_increase": float_field(
                row, "dense_best_relative_increase"),
            "dense_trial_disagreement_fraction": float_field(
                row, "dense_best_trial_disagreement_fraction"),
            "dense_support_status": row["dense_support_status"],
        })
    return summary


def command_line():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_output(path, arguments, rows):
    columns = (
        "evidence_rank", "coarse_interval_bytes",
        "coarse_relative_increase", "coarse_trial_disagreement_fraction",
        "dense_overlapping_interval_count", "dense_refined_interval_bytes",
        "dense_relative_increase", "dense_trial_disagreement_fraction",
        "dense_support_status")
    created = False
    try:
        with open(path, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_capacity_evidence_summary_version=1\n")
            stream.write("coarse_dense_comparison_file={}\n".format(
                os.path.abspath(arguments.candidate_comparison)))
            stream.write("coarse_dense_comparison_sha256={}\n".format(
                sha256_file(arguments.candidate_comparison)))
            stream.write("top_count={}\n".format(arguments.top_count))
            stream.write("summary_purpose=report_evidence_for_8.2.1_and_8.2.2\n")
            stream.write("evidence_scope=coarse_and_dense_randomized_dependent_pointer_chasing\n")
            stream.write("cache_boundary_labels_assigned=false\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write("summary_script={}\n".format(os.path.abspath(__file__)))
            stream.write("summary_command={}\n".format(command_line()))
            stream.write("summary_working_directory={}\n".format(os.getcwd()))
            stream.write("python_version={}\n".format(platform.python_version()))
            stream.write("data_begin\n")
            stream.write("\t".join(columns) + "\n")
            for row in rows:
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
        description="Summarize capacity evidence for reporting.")
    parser.add_argument("--candidate-comparison", required=True)
    parser.add_argument("--top-count", required=True, type=int)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    if arguments.top_count < 1:
        parser.error("--top-count must be positive")
    if not os.path.isfile(arguments.candidate_comparison):
        parser.error("--candidate-comparison must name an existing TSV")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    if not os.path.isdir(os.path.dirname(os.path.abspath(arguments.output))):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        _, candidates = read_table(
            arguments.candidate_comparison,
            "ece592_capacity_candidate_comparison_version")
        rows = build_summary(candidates, arguments.top_count)
        write_output(arguments.output, arguments, rows)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("output_filename={}".format(arguments.output))
    print("summary_row_count={}".format(len(rows)))
    print("cache_boundary_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
