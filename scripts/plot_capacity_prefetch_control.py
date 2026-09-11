#!/usr/bin/env python3
"""Overlay randomized and sequential Phase-I capacity controls."""

import argparse
import csv
import hashlib
import math
import os
import platform
import shlex
import statistics
import subprocess
import sys
import tempfile


X_FIELD = "actual_span_bytes"
MEDIAN_FIELD = "elapsed_raw_ticks_per_access_unadjusted_median"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_processed(path, expected_traversal):
    metadata = {}
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" not in line:
                raise ValueError("invalid metadata in {}".format(path))
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("duplicate metadata in {}".format(path))
            metadata[key] = value
        else:
            raise ValueError("{} has no data_begin".format(path))

        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "trial", "plot_index", X_FIELD, "traversal", "timer_unit",
            "timed_sample_count", MEDIAN_FIELD,
        }
        if reader.fieldnames is None or required.difference(reader.fieldnames):
            raise ValueError("{} is missing required columns".format(path))
        first = reader.fieldnames[0]
        found_end = False
        for record in reader:
            if record[first] == "data_end":
                found_end = True
                break
            row = {
                "trial": int(record["trial"], 10),
                "plot_index": int(record["plot_index"], 10),
                "span": int(record[X_FIELD], 10),
                "samples": int(record["timed_sample_count"], 10),
                "median": float(record[MEDIAN_FIELD]),
                "traversal": record["traversal"],
                "timer_unit": record["timer_unit"],
            }
            if (row["trial"] < 0 or row["span"] <= 0 or
                    row["samples"] < 1_000_000 or
                    not math.isfinite(row["median"]) or
                    row["traversal"] != expected_traversal):
                raise ValueError("invalid row in {}".format(path))
            rows.append(row)
        if not found_end:
            raise ValueError("{} has no data_end".format(path))

    required_metadata = {
        "ece592_capacity_processed_format_version", "source_raw_hostname",
        "source_raw_isa", "source_raw_timer_unit", "source_raw_traversal",
        "source_raw_timed_sample_count", "source_plan_trial_count",
        "source_plan_unique_size_count", "source_plan_plan_row_count",
        "processed_point_count", "timer_overhead_subtracted",
    }
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("{} missing metadata: {}".format(
            path, ", ".join(sorted(missing))))
    if metadata["source_raw_traversal"] != expected_traversal:
        raise ValueError("{} has the wrong traversal".format(path))
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("timer overhead must remain unsubtracted")
    if int(metadata["processed_point_count"], 10) != len(rows):
        raise ValueError("processed point count mismatch")
    return metadata, rows


def aggregate(rows):
    values = {}
    seen = set()
    for row in rows:
        identity = (row["trial"], row["plot_index"])
        if identity in seen:
            raise ValueError("duplicate trial/plot index")
        seen.add(identity)
        values.setdefault(row["span"], []).append(row["median"])
    return {span: statistics.median(medians)
            for span, medians in values.items()}


def quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def byte_label(value):
    for divisor, suffix in ((1 << 30, "GiB"), (1 << 20, "MiB"),
                            (1 << 10, "KiB")):
        if value >= divisor:
            scaled = value / divisor
            return "{:.0f} {}".format(scaled, suffix)
    return "{} B".format(value)


def write_data(path, spans, randomized, sequential):
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write("span_bytes\trandomized_median\tsequential_median\n")
        for span in spans:
            stream.write("{}\t{:.17g}\t{:.17g}\n".format(
                span, randomized[span], sequential[span]))


def write_script(path, data_path, temporary_pdf, metadata, spans):
    powers = []
    lower = int(math.floor(math.log(min(spans), 2)))
    upper = int(math.ceil(math.log(max(spans), 2)))
    for power in range(lower, upper + 1):
        value = 1 << power
        if min(spans) <= value <= max(spans):
            powers.append(value)
    ticks = ", ".join("{} {}".format(quote(byte_label(v)), v)
                      for v in powers)
    hostname = metadata["source_raw_hostname"]
    timer_unit = metadata["source_raw_timer_unit"]
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo enhanced color font 'Helvetica,12' "
                     "size 7.2in,4.5in\n")
        stream.write("set output {}\n".format(quote(temporary_pdf)))
        stream.write("set title {}\n".format(quote(
            "{} Phase I prefetcher sanity control".format(hostname))))
        stream.write("set xlabel 'Working-set footprint'\n")
        stream.write("set ylabel {}\n".format(quote(
            "Median latency ({} / access)".format(timer_unit))))
        stream.write("set logscale x 2\n")
        stream.write("set xtics rotate by -45 ({})\n".format(ticks))
        stream.write("set border 3 linewidth 1.4\n")
        stream.write("set tics nomirror\n")
        stream.write("unset grid\n")
        stream.write("set key left top opaque box\n")
        stream.write("set style line 1 lc rgb '#111111' lw 2 pt 7 ps 0.65\n")
        stream.write("set style line 2 lc rgb '#777777' lw 2 pt 5 ps 0.65\n")
        stream.write("plot {} using 1:2 with linespoints ls 1 title "
                     "'Randomized dependent chase (primary)', \\\n".format(
                         quote(data_path)))
        stream.write("     '' using 1:3 with linespoints ls 2 title "
                     "'Sequential dependent chase (prefetch control)'\n")


def main():
    parser = argparse.ArgumentParser(
        description="Plot randomized versus sequential capacity controls.")
    parser.add_argument("--randomized", required=True)
    parser.add_argument("--sequential", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if os.path.exists(args.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(parent):
        parser.error("output parent directory must already exist")

    try:
        random_meta, random_rows = read_processed(
            args.randomized, "randomized-dependent-single-cycle")
        sequential_meta, sequential_rows = read_processed(
            args.sequential, "sequential-dependent-single-cycle")
        for key in ("source_raw_hostname", "source_raw_isa",
                    "source_raw_timer_unit", "source_plan_trial_count",
                    "source_plan_unique_size_count",
                    "source_plan_plan_row_count"):
            if random_meta[key] != sequential_meta[key]:
                raise ValueError("inputs disagree on {}".format(key))
        randomized = aggregate(random_rows)
        sequential = aggregate(sequential_rows)
        if set(randomized) != set(sequential):
            raise ValueError("inputs do not contain identical working-set sizes")
        spans = sorted(randomized)

        # Keep the temporary PDF on the destination filesystem.  The project
        # commonly lives on NFS while /tmp is a local filesystem, and an
        # atomic os.replace() cannot cross that boundary.
        with tempfile.TemporaryDirectory(
                prefix=".ece592-prefetch-", dir=parent) as temp:
            data_path = os.path.join(temp, "plot.tsv")
            script_path = os.path.join(temp, "plot.gnuplot")
            pdf_path = os.path.join(temp, "plot.pdf")
            write_data(data_path, spans, randomized, sequential)
            write_script(script_path, data_path, pdf_path, random_meta, spans)
            subprocess.run(["gnuplot", script_path], check=True)
            os.replace(pdf_path, args.output)

        provenance = args.output + ".provenance.tsv"
        command = " ".join(shlex.quote(value) for value in sys.argv)
        with open(provenance, "x", encoding="utf-8", newline="\n") as stream:
            stream.write("ece592_plot_provenance_version=1\n")
            stream.write("plot_kind=phase1_capacity_prefetch_control\n")
            stream.write("randomized_input={}\n".format(
                os.path.abspath(args.randomized)))
            stream.write("randomized_sha256={}\n".format(
                sha256_file(args.randomized)))
            stream.write("sequential_input={}\n".format(
                os.path.abspath(args.sequential)))
            stream.write("sequential_sha256={}\n".format(
                sha256_file(args.sequential)))
            stream.write("plotting_command={}\n".format(command))
            stream.write("python_version={}\n".format(platform.python_version()))

        print("randomized_input={}".format(args.randomized))
        print("sequential_input={}".format(args.sequential))
        print("output_filename={}".format(args.output))
        print("working_set_count={}".format(len(spans)))
        print("status=ok")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
