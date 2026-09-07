#!/usr/bin/env python3
"""Compare coarse and dense capacity-transition candidates without labels."""

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


def read_transition_file(path):
    metadata = {}
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid transition metadata line")
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("invalid or duplicate metadata key")
            metadata[key] = value
        else:
            raise ValueError("transition file has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "rank", "lower_span", "upper_span", "relative_increase",
            "log2_latency_slope", "trial_disagreement_fraction",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("transition file lacks required columns")
        first_column = reader.fieldnames[0]
        found_end = False
        for record in reader:
            if record[first_column] == "data_end":
                found_end = True
                break
            if None in record:
                raise ValueError("transition row has extra fields")
            try:
                row = {
                    "rank": int(record["rank"], 10),
                    "lower_span": int(record["lower_span"], 10),
                    "upper_span": int(record["upper_span"], 10),
                    "relative_increase": float(record["relative_increase"]),
                    "log2_latency_slope": float(record["log2_latency_slope"]),
                    "trial_disagreement_fraction": float(
                        record["trial_disagreement_fraction"]),
                }
            except ValueError as error:
                raise ValueError("invalid transition numeric field") from error
            if row["lower_span"] <= 0 or row["upper_span"] <= row["lower_span"]:
                raise ValueError("invalid transition span interval")
            rows.append(row)
        if not found_end or any(line.strip() for line in stream):
            raise ValueError("transition data markers are invalid")

    required_metadata = {
        "ece592_transition_analysis_format_version",
        "cache_boundary_labels_assigned",
        "timer_overhead_subtracted",
    }
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("missing transition metadata: {}".format(
            ", ".join(sorted(missing))))
    if metadata["ece592_transition_analysis_format_version"] != "1":
        raise ValueError("unsupported transition format version")
    if metadata["cache_boundary_labels_assigned"] != "false":
        raise ValueError("comparison requires unlabeled Phase-I candidates")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("comparison requires unadjusted timer values")
    return metadata, rows


def intervals_overlap(left, right):
    return (left["lower_span"] < right["upper_span"] and
            right["lower_span"] < left["upper_span"])


def support_status(best_dense):
    if best_dense is None:
        return "not-covered-by-dense-plan"
    if best_dense["relative_increase"] >= 0.10:
        return "strong-measured-jump"
    if best_dense["relative_increase"] >= 0.05:
        return "moderate-measured-jump"
    if best_dense["relative_increase"] > 0.0:
        return "weak-measured-jump"
    return "no-upward-jump"


def build_comparison(coarse_rows, dense_rows, top_count):
    selected = sorted(coarse_rows, key=lambda row: row["rank"])[:top_count]
    comparison = []
    for coarse in selected:
        covered = [
            dense for dense in dense_rows if intervals_overlap(coarse, dense)
        ]
        best_dense = None
        if covered:
            best_dense = max(
                covered,
                key=lambda row: (row["relative_increase"],
                                 row["log2_latency_slope"]))
        comparison.append({
            "coarse_rank": coarse["rank"],
            "coarse_lower_span": coarse["lower_span"],
            "coarse_upper_span": coarse["upper_span"],
            "coarse_relative_increase": coarse["relative_increase"],
            "coarse_log2_latency_slope": coarse["log2_latency_slope"],
            "coarse_trial_disagreement_fraction":
                coarse["trial_disagreement_fraction"],
            "dense_overlapping_interval_count": len(covered),
            "dense_best_rank": best_dense["rank"] if best_dense else "",
            "dense_best_lower_span":
                best_dense["lower_span"] if best_dense else "",
            "dense_best_upper_span":
                best_dense["upper_span"] if best_dense else "",
            "dense_best_relative_increase":
                best_dense["relative_increase"] if best_dense else "",
            "dense_best_log2_latency_slope":
                best_dense["log2_latency_slope"] if best_dense else "",
            "dense_best_trial_disagreement_fraction":
                best_dense["trial_disagreement_fraction"] if best_dense else "",
            "dense_support_status": support_status(best_dense),
        })
    return comparison


def command_line():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_output(path, arguments, coarse_metadata, dense_metadata, rows):
    created = False
    columns = (
        "coarse_rank", "coarse_lower_span", "coarse_upper_span",
        "coarse_relative_increase", "coarse_log2_latency_slope",
        "coarse_trial_disagreement_fraction",
        "dense_overlapping_interval_count", "dense_best_rank",
        "dense_best_lower_span", "dense_best_upper_span",
        "dense_best_relative_increase", "dense_best_log2_latency_slope",
        "dense_best_trial_disagreement_fraction", "dense_support_status")
    try:
        with open(path, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_capacity_candidate_comparison_version=1\n")
            stream.write("coarse_transition_file={}\n".format(
                os.path.abspath(arguments.coarse)))
            stream.write("coarse_transition_sha256={}\n".format(
                sha256_file(arguments.coarse)))
            stream.write("dense_transition_file={}\n".format(
                os.path.abspath(arguments.dense)))
            stream.write("dense_transition_sha256={}\n".format(
                sha256_file(arguments.dense)))
            stream.write("source_hostname={}\n".format(
                dense_metadata.get("source_hostname",
                                   coarse_metadata.get("source_hostname",
                                                       "unknown"))))
            stream.write("source_isa={}\n".format(
                dense_metadata.get("source_isa",
                                   coarse_metadata.get("source_isa",
                                                       "unknown"))))
            stream.write("top_coarse_rank_count={}\n".format(
                arguments.top_count))
            stream.write("comparison_method=coarse_interval_vs_overlapping_dense_intervals\n")
            stream.write("dense_best_selection=largest_relative_increase_then_largest_slope\n")
            stream.write("cache_boundary_labels_assigned=false\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write("comparison_script={}\n".format(
                os.path.abspath(__file__)))
            stream.write("comparison_command={}\n".format(command_line()))
            stream.write("comparison_working_directory={}\n".format(
                os.getcwd()))
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
        description="Compare coarse and dense Phase-I capacity candidates.")
    parser.add_argument("--coarse", required=True)
    parser.add_argument("--dense", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-count", type=int, default=10)
    arguments = parser.parse_args()
    if not os.path.isfile(arguments.coarse):
        parser.error("--coarse must name an existing transition TSV")
    if not os.path.isfile(arguments.dense):
        parser.error("--dense must name an existing transition TSV")
    if arguments.top_count < 1:
        parser.error("--top-count must be positive")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    if not os.path.isdir(os.path.dirname(os.path.abspath(arguments.output))):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        coarse_metadata, coarse_rows = read_transition_file(arguments.coarse)
        dense_metadata, dense_rows = read_transition_file(arguments.dense)
        rows = build_comparison(coarse_rows, dense_rows, arguments.top_count)
        write_output(arguments.output, arguments, coarse_metadata,
                     dense_metadata, rows)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("coarse_transition_file={}".format(arguments.coarse))
    print("dense_transition_file={}".format(arguments.dense))
    print("output_filename={}".format(arguments.output))
    print("compared_coarse_candidate_count={}".format(len(rows)))
    print("cache_boundary_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
