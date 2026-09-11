#!/usr/bin/env python3
"""Compare true dependent-load latency with eight-lane load throughput."""

import argparse
import csv
import hashlib
import math
import os
import platform
import shlex
import subprocess
import sys
import tempfile


METRIC = "elapsed_raw_ticks_per_access_unadjusted"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_summary(path, expected_kind):
    metadata = {}
    selected = None
    with open(path, "r", encoding="ascii", newline="") as stream:
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
        required = {"metric", "count", "p05", "q1", "median", "q3", "p95"}
        if reader.fieldnames is None or required.difference(reader.fieldnames):
            raise ValueError("{} is missing distribution columns".format(path))
        found_end = False
        for record in reader:
            if record["metric"] == "data_end":
                found_end = True
                break
            if record["metric"] == METRIC:
                selected = {key: float(record[key])
                            for key in ("p05", "q1", "median", "q3", "p95")}
                selected["count"] = int(record["count"], 10)
        if not found_end:
            raise ValueError("{} has no data_end".format(path))

    required_metadata = {
        "ece592_summary_format_version", "source_hostname", "source_isa",
        "source_timer_unit", "source_node_count",
        "source_node_spacing_bytes", "source_timed_sample_count",
        "source_traversal", "timer_overhead_subtracted",
    }
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("{} missing metadata: {}".format(
            path, ", ".join(sorted(missing))))
    if metadata["ece592_summary_format_version"] != "1":
        raise ValueError("unsupported summary version")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("diagnostic expects unadjusted timer values")
    if int(metadata["source_timed_sample_count"], 10) < 1_000_000:
        raise ValueError("diagnostic requires at least 1000000 samples")
    expected_traversal = {
        "dependent": "randomized-dependent-single-cycle",
        "independent": "randomized-eight-lane-independent-chains",
    }[expected_kind]
    if metadata["source_traversal"] != expected_traversal:
        raise ValueError("{} is not a {} result".format(path, expected_kind))
    if expected_kind == "independent":
        if (metadata.get("source_measurement_dependency") !=
                "independent-eight-lane" or
                metadata.get("source_result_semantics") !=
                "throughput-not-load-latency"):
            raise ValueError("independent-result semantics are missing")
    if selected is None:
        raise ValueError("{} has no per-access distribution".format(path))
    if selected["count"] < 1_000_000:
        raise ValueError("distribution has fewer than 1000000 samples")
    ordered = [selected[key] for key in ("p05", "q1", "median", "q3", "p95")]
    if not all(math.isfinite(value) for value in ordered) or ordered != sorted(ordered):
        raise ValueError("invalid distribution ordering")
    return metadata, selected


def quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_data(path, dependent, independent):
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write("x\tp05\tq1\tmedian\tq3\tp95\n")
        for index, values in enumerate((dependent, independent), start=1):
            stream.write("{}\t{}\t{}\t{}\t{}\t{}\n".format(
                index, values["p05"], values["q1"], values["median"],
                values["q3"], values["p95"]))


def write_gnuplot(path, data_path, pdf_path, metadata):
    footprint = (int(metadata["source_node_count"], 10) *
                 int(metadata["source_node_spacing_bytes"], 10))
    timer_unit = metadata["source_timer_unit"]
    hostname = metadata["source_hostname"]
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo enhanced color font 'Helvetica,12' "
                     "size 7.2in,4.5in\n")
        stream.write("set output {}\n".format(quote(pdf_path)))
        stream.write("set title {}\n".format(quote(
            "{}: dependency diagnostic ({} KiB resident set)".format(
                hostname, footprint // 1024))))
        stream.write("set ylabel {}\n".format(quote(
            "Unadjusted cost ({} / load)".format(timer_unit))))
        stream.write("set xrange [0.4:2.6]\n")
        stream.write("set xtics ('Dependent chain (latency)' 1, "
                     "'8 independent chains (throughput)' 2)\n")
        stream.write("set border 3 linewidth 1.4\nset tics nomirror\nunset grid\n")
        stream.write("set style fill solid 0.35 border\nset boxwidth 0.48\n")
        stream.write("set style line 1 lc rgb '#222222' lw 2\n")
        stream.write("plot {} using 1:3:2:6:5 with candlesticks ls 1 "
                     "title 'box: Q1-Q3; whiskers: P05-P95', \\\n".format(
                         quote(data_path)))
        stream.write("     '' using 1:4:4:4:4 with candlesticks "
                     "lc rgb '#b2182b' lw 3 notitle\n")


def main():
    parser = argparse.ArgumentParser(
        description="Plot dependent latency versus independent-load throughput.")
    parser.add_argument("--dependent", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if os.path.exists(args.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(parent):
        parser.error("output parent directory must already exist")

    try:
        dep_meta, dependent = read_summary(args.dependent, "dependent")
        ind_meta, independent = read_summary(args.independent, "independent")
        for key in ("source_hostname", "source_isa", "source_timer_unit",
                    "source_node_count", "source_node_spacing_bytes",
                    "source_timed_sample_count"):
            if dep_meta[key] != ind_meta[key]:
                raise ValueError("inputs disagree on {}".format(key))
        with tempfile.TemporaryDirectory(
                prefix=".ece592-dependency-", dir=parent) as temp:
            data_path = os.path.join(temp, "plot.tsv")
            script_path = os.path.join(temp, "plot.gnuplot")
            pdf_path = os.path.join(temp, "plot.pdf")
            write_data(data_path, dependent, independent)
            write_gnuplot(script_path, data_path, pdf_path, dep_meta)
            subprocess.run(["gnuplot", script_path], check=True)
            os.replace(pdf_path, args.output)

        provenance = args.output + ".provenance.tsv"
        with open(provenance, "x", encoding="ascii", newline="\n") as stream:
            stream.write("ece592_plot_provenance_version=1\n")
            stream.write("plot_kind=phase1_dependency_diagnostic\n")
            stream.write("dependent_input={}\n".format(
                os.path.abspath(args.dependent)))
            stream.write("dependent_sha256={}\n".format(
                sha256_file(args.dependent)))
            stream.write("independent_input={}\n".format(
                os.path.abspath(args.independent)))
            stream.write("independent_sha256={}\n".format(
                sha256_file(args.independent)))
            stream.write("plotting_command={}\n".format(
                " ".join(shlex.quote(value) for value in sys.argv)))
            stream.write("python_version={}\n".format(platform.python_version()))

        print("dependent_input={}".format(args.dependent))
        print("independent_input={}".format(args.independent))
        print("output_filename={}".format(args.output))
        print("dependent_median_ticks_per_access={}".format(
            dependent["median"]))
        print("independent_throughput_ticks_per_access={}".format(
            independent["median"]))
        print("status=ok")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
