#!/usr/bin/env python3
"""Combine frozen lab observations and held-out Hazel observations."""

import argparse
import csv
import hashlib
import os
import sys


IDENTIFIERS = [
    "role", "machine", "constraint", "year", "vendor", "isa",
    "microarchitecture", "cpu_model", "process_nm", "llc_domain_core_count",
]
METRICS = [
    "l1d_capacity_bytes", "l1d_associativity", "l1d_hit_latency_ns",
    "l1_miss_penalty_ns", "l2_capacity_per_core_bytes", "l2_associativity",
    "l2_hit_latency_ns", "l2_miss_penalty_ns", "llc_capacity_bytes",
    "llc_capacity_per_core_bytes", "llc_effective_associativity",
    "llc_hit_latency_ns", "llc_memory_penalty_ns", "line_size_bytes",
    "inclusion_behavior", "software_residency_rate",
    "pmu_l1_misses_per_timed_access", "pmu_last_cache_misses_per_timed_access",
]
TRACE = ["timing_freeze_commit", "first_cache_run_job_id", "raw_archive_sha256"]
COLUMNS = IDENTIFIERS + METRICS + TRACE


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path, role):
    with open(path, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"machine", "year", "vendor", "isa", "microarchitecture"}.union(METRICS)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = required.difference(reader.fieldnames or [])
            raise ValueError("{} is missing: {}".format(path, ", ".join(sorted(missing))))
        rows = []
        for source in reader:
            if not any(value.strip() for value in source.values() if value is not None):
                continue
            row = {column: source.get(column, "").strip() for column in COLUMNS}
            row["role"] = role
            if role == "lab" and row["constraint"]:
                raise ValueError("lab rows must not have a Hazel constraint")
            if role == "hazel" and not row["constraint"]:
                raise ValueError("Hazel row {} lacks constraint".format(row["machine"]))
            try:
                int(row["year"])
            except ValueError as error:
                raise ValueError("{} has invalid year".format(row["machine"])) from error
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", required=True)
    parser.add_argument("--hazel", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if os.path.exists(args.output):
        parser.error("--output must not already exist")
    rows = read_rows(args.lab, "lab") + read_rows(args.hazel, "hazel")
    names = set()
    for row in rows:
        key = (row["role"], row["machine"], row["constraint"])
        if key in names:
            parser.error("duplicate system row: {}".format(key))
        names.add(key)
    rows.sort(key=lambda row: (int(row["year"]), row["vendor"], row["machine"]))
    parent = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(parent):
        parser.error("output parent directory must already exist")
    with open(args.output, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("ece592_phase3_chronological_master_version=1\n")
        stream.write("year_convention=first_public_introduction_year_of_represented_generation\n")
        stream.write("lab_source={}\n".format(os.path.abspath(args.lab)))
        stream.write("lab_source_sha256={}\n".format(sha256_file(args.lab)))
        stream.write("hazel_source={}\n".format(os.path.abspath(args.hazel)))
        stream.write("hazel_source_sha256={}\n".format(sha256_file(args.hazel)))
        stream.write("hazel_used_to_refit_predictions=false\n")
        stream.write("data_begin\n")
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        stream.write("data_end\n")
    print("output_filename={}".format(args.output))
    print("system_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        sys.exit(1)
