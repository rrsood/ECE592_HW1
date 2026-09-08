#!/usr/bin/env python3
"""Create Phase-I latency box plots from selected distribution summaries."""

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


MIN_FIELD = "elapsed_raw_ticks_per_access_unadjusted_minimum"
Q1_FIELD = "elapsed_raw_ticks_per_access_unadjusted_q1"
MEDIAN_FIELD = "elapsed_raw_ticks_per_access_unadjusted_median"
Q3_FIELD = "elapsed_raw_ticks_per_access_unadjusted_q3"
MAX_FIELD = "elapsed_raw_ticks_per_access_unadjusted_maximum"
OUTLIER_FIELD = "elapsed_raw_ticks_per_access_unadjusted_outlier_count"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_selection(path):
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
            raise ValueError("selection file has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("selection file has no data heading")
        required_columns = {
            "evidence_rank",
            "point_role",
            "actual_span_bytes",
            "trial",
            "timed_sample_count",
            MIN_FIELD,
            Q1_FIELD,
            MEDIAN_FIELD,
            Q3_FIELD,
            MAX_FIELD,
            OUTLIER_FIELD,
        }
        missing_columns = required_columns.difference(reader.fieldnames)
        if missing_columns:
            raise ValueError("missing selection columns: {}".format(
                ", ".join(sorted(missing_columns))))

        found_end = False
        first_column = reader.fieldnames[0]
        for record in reader:
            if record[first_column] == "data_end":
                if any(record[column] not in (None, "")
                       for column in reader.fieldnames[1:]):
                    raise ValueError("malformed data_end row")
                found_end = True
                break
            if None in record:
                raise ValueError("selection row has extra fields")
            try:
                row = {
                    "evidence_rank": int(record["evidence_rank"], 10),
                    "point_role": record["point_role"],
                    "actual_span_bytes": int(record["actual_span_bytes"], 10),
                    "trial": int(record["trial"], 10),
                    "sample_count": int(record["timed_sample_count"], 10),
                    "minimum": float(record[MIN_FIELD]),
                    "q1": float(record[Q1_FIELD]),
                    "median": float(record[MEDIAN_FIELD]),
                    "q3": float(record[Q3_FIELD]),
                    "maximum": float(record[MAX_FIELD]),
                    "outlier_count": int(record[OUTLIER_FIELD], 10),
                }
            except ValueError as error:
                raise ValueError("invalid numeric selection value") from error
            if (row["evidence_rank"] <= 0 or row["actual_span_bytes"] <= 0 or
                    row["trial"] < 0 or row["sample_count"] < 1_000_000 or
                    row["outlier_count"] < 0):
                raise ValueError("invalid selected latency row")
            ordered = (
                row["minimum"], row["q1"], row["median"], row["q3"],
                row["maximum"])
            if (not all(math.isfinite(value) for value in ordered) or
                    list(ordered) != sorted(ordered)):
                raise ValueError("invalid five-number summary")
            rows.append(row)

        if not found_end:
            raise ValueError("selection file has no data_end marker")
        if any(line.strip() for line in stream):
            raise ValueError("unexpected content after data_end")

    required_metadata = {
        "ece592_latency_selection_format_version",
        "selection_purpose",
        "cache_boundary_labels_assigned",
        "timer_overhead_subtracted",
        "source_raw_hostname",
        "source_raw_isa",
        "source_raw_timer_unit",
        "source_raw_traversal",
        "source_raw_timed_sample_count",
        "selected_point_count",
    }
    missing_metadata = required_metadata.difference(metadata)
    if missing_metadata:
        raise ValueError("missing selection metadata: {}".format(
            ", ".join(sorted(missing_metadata))))
    if metadata["ece592_latency_selection_format_version"] != "1":
        raise ValueError("unsupported latency selection format")
    if metadata["cache_boundary_labels_assigned"] != "false":
        raise ValueError("latency plot must remain cache-label blind")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("latency plot expects unadjusted raw timing units")
    if len(rows) != int(metadata["selected_point_count"], 10):
        raise ValueError("selected_point_count does not match row count")

    rows.sort(key=lambda row: (
        row["evidence_rank"],
        point_role_order(row["point_role"]),
        row["trial"],
        row["actual_span_bytes"]))
    return metadata, rows


def point_role_order(role):
    ordering = {
        "below_refined_interval": 0,
        "near_refined_lower_edge": 1,
        "near_refined_upper_edge": 2,
        "above_refined_interval": 3,
    }
    return ordering.get(role, 99)


def short_role(role):
    labels = {
        "below_refined_interval": "below",
        "near_refined_lower_edge": "near-low",
        "near_refined_upper_edge": "near-high",
        "above_refined_interval": "above",
    }
    return labels.get(role, role)


def byte_label(value):
    units = (
        (1024 ** 3, "GiB"),
        (1024 ** 2, "MiB"),
        (1024, "KiB"),
    )
    for divisor, suffix in units:
        if value >= divisor and value % divisor == 0:
            return "{} {}".format(value // divisor, suffix)
    if value >= 1024:
        return "{:.3g} KiB".format(value / 1024.0)
    return "{} B".format(value)


def gnuplot_quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_plot_data(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as stream:
        stream.write("# x label minimum q1 median q3 maximum outlier_count\n")
        for index, row in enumerate(rows, start=1):
            label = "r{} {} {}".format(
                row["evidence_rank"],
                short_role(row["point_role"]),
                byte_label(row["actual_span_bytes"]))
            stream.write("{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\t{:.17g}\t"
                         "{:.17g}\t{}\n".format(
                             index,
                             label,
                             row["minimum"],
                             row["q1"],
                             row["median"],
                             row["q3"],
                             row["maximum"],
                             row["outlier_count"]))


def write_gnuplot_script(path, data_path, output_path, metadata, rows):
    maximum_y = max(row["q3"] for row in rows)
    if maximum_y <= 0.0:
        maximum_y = max(row["maximum"] for row in rows)
    y_limit = maximum_y * 1.20
    if y_limit <= 0.0:
        y_limit = 1.0

    title = "{} latency representatives ({}, {})".format(
        metadata["source_raw_hostname"],
        metadata["source_raw_isa"],
        metadata["source_raw_timer_unit"])
    note = ("Box=Q1..Q3, horizontal mark=median, whiskers=min..max; "
            "selected below/near/above measured timing boundaries; "
            "no cache labels assigned")

    with open(path, "w", encoding="utf-8") as stream:
        stream.write("set terminal pdfcairo enhanced color size 12in,6in\n")
        stream.write("set output {}\n".format(gnuplot_quote(output_path)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("set key outside top center horizontal\n")
        stream.write("set title {}\n".format(gnuplot_quote(title)))
        stream.write("set xlabel 'Selected measured point'\n")
        stream.write("set ylabel {}\n".format(gnuplot_quote(
            "elapsed raw {} per dependent access".format(
                metadata["source_raw_timer_unit"]))))
        stream.write("set yrange [0:{}]\n".format(y_limit))
        stream.write("set xrange [0:{}]\n".format(len(rows) + 1))
        stream.write("set xtics rotate by -60 right font ',7'\n")
        stream.write("set xtics (")
        xtics = []
        for index, row in enumerate(rows, start=1):
            label = "r{}\\n{}".format(
                row["evidence_rank"], short_role(row["point_role"]))
            xtics.append("{} {}".format(gnuplot_quote(label), index))
        stream.write(", ".join(xtics))
        stream.write(")\n")
        stream.write("set style fill solid 0.35 border rgb '#225ea8'\n")
        stream.write("set boxwidth 0.60\n")
        stream.write("set label 1 {} at graph 0.01,0.96 left font ',8'\n".
                     format(gnuplot_quote(note)))
        stream.write("plot {} using 1:4:3:7:6 with candlesticks "
                     "lc rgb '#225ea8' title 'Q1-Q3 with min/max whiskers' "
                     "whiskerbars, \\\n".format(gnuplot_quote(data_path)))
        stream.write("     {} using 1:5:5:5:5 with candlesticks "
                     "lc rgb '#000000' notitle\n".format(
                         gnuplot_quote(data_path)))


def write_provenance(path, input_path, output_path, metadata, rows,
                     gnuplot_version):
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8", newline="") as stream:
        stream.write("ece592_latency_boxplot_provenance_version=1\n")
        stream.write("input_filename={}\n".format(os.path.abspath(input_path)))
        stream.write("input_sha256={}\n".format(sha256_file(input_path)))
        stream.write("output_filename={}\n".format(os.path.abspath(output_path)))
        stream.write("plot_script={}\n".format(os.path.abspath(__file__)))
        stream.write("plot_command={}\n".format(
            " ".join(shlex.quote(argument) for argument in sys.argv)))
        stream.write("plot_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("gnuplot_version={}\n".format(gnuplot_version))
        stream.write("source_raw_hostname={}\n".format(
            metadata["source_raw_hostname"]))
        stream.write("source_raw_isa={}\n".format(metadata["source_raw_isa"]))
        stream.write("source_raw_timer_unit={}\n".format(
            metadata["source_raw_timer_unit"]))
        stream.write("source_raw_timed_sample_count={}\n".format(
            metadata["source_raw_timed_sample_count"]))
        stream.write("boxplot_source=processed_five_number_summaries\n")
        stream.write("boxplot_count={}\n".format(len(rows)))
        stream.write("cache_boundary_labels_assigned=false\n")
        stream.write("background_grid_lines=false\n")
        stream.write("status=ok\n")
    os.replace(temporary_path, path)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Plot selected Phase-I hit-latency distributions as box plots "
            "without using cache specifications or labels."))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if not os.path.isfile(arguments.input):
        parser.error("--input must name an existing file")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(arguments.output))
    if parent and not os.path.isdir(parent):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    try:
        arguments = parse_arguments()
        metadata, rows = read_selection(arguments.input)
        output_parent = os.path.dirname(os.path.abspath(arguments.output))
        with tempfile.TemporaryDirectory(prefix="ece592_latency_plot_",
                                         dir=output_parent) as temp:
            data_path = os.path.join(temp, "latency_boxplot.tsv")
            script_path = os.path.join(temp, "latency_boxplot.gnuplot")
            temporary_pdf = os.path.join(temp, "latency_boxplot.pdf")
            write_plot_data(data_path, rows)
            write_gnuplot_script(script_path, data_path, temporary_pdf,
                                 metadata, rows)
            result = subprocess.run(
                ["gnuplot", script_path], check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise RuntimeError("gnuplot failed: {}".format(
                    result.stderr.strip()))
            if not os.path.isfile(temporary_pdf) or os.path.getsize(
                    temporary_pdf) == 0:
                raise RuntimeError("gnuplot did not create a nonempty PDF")
            os.replace(temporary_pdf, arguments.output)

        version_result = subprocess.run(
            ["gnuplot", "--version"], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        write_provenance(arguments.output + ".provenance.tsv",
                         arguments.input, arguments.output, metadata, rows,
                         version_result.stdout.strip())

        print("input_filename={}".format(arguments.input))
        print("output_filename={}".format(arguments.output))
        print("boxplot_count={}".format(len(rows)))
        print("cache_boundary_labels_assigned=false")
        print("status=ok")
    except (OSError, ValueError, RuntimeError,
            subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
