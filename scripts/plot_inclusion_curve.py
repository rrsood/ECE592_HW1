#!/usr/bin/env python3
"""Create a Phase-I inclusion/reuse curve without assigning cache labels."""

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


DELTA_FIELD = "probe_after_minus_before_median_ticks_per_access"


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
        if reader.fieldnames is None:
            raise ValueError("processed file has no column heading")
        required = {
            "trial", "probe_node_count", "pressure_node_count",
            "node_spacing_bytes", "traversal", "timer_unit",
            "timed_sample_count", DELTA_FIELD,
        }
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError("missing processed columns: {}".format(
                ", ".join(sorted(missing))))

        found_end = False
        first_column = reader.fieldnames[0]
        for record in reader:
            if record[first_column] == "data_end":
                found_end = True
                break
            if None in record:
                raise ValueError("processed row has extra fields")
            try:
                row = {
                    "trial": int(record["trial"], 10),
                    "probe_nodes": int(record["probe_node_count"], 10),
                    "pressure_nodes": int(record["pressure_node_count"], 10),
                    "spacing": int(record["node_spacing_bytes"], 10),
                    "sample_count": int(record["timed_sample_count"], 10),
                    "delta": float(record[DELTA_FIELD]),
                    "traversal": record["traversal"],
                    "timer_unit": record["timer_unit"],
                }
            except ValueError as error:
                raise ValueError("invalid numeric processed value") from error
            if (row["trial"] < 0 or row["probe_nodes"] < 2 or
                    row["pressure_nodes"] < 2 or row["spacing"] < 8 or
                    row["sample_count"] < 1_000_000 or
                    not math.isfinite(row["delta"])):
                raise ValueError("invalid processed inclusion row")
            rows.append(row)

        if not found_end:
            raise ValueError("processed file has no data_end marker")

    required_metadata = {
        "ece592_inclusion_processed_format_version",
        "source_raw_hostname",
        "source_raw_isa",
        "source_raw_timer_unit",
        "source_raw_traversal",
        "source_raw_timed_sample_count",
        "source_plan_trial_count",
        "processed_point_count",
        "timer_overhead_subtracted",
        "cache_inclusion_labels_assigned",
    }
    missing_metadata = required_metadata.difference(metadata)
    if missing_metadata:
        raise ValueError("missing processed metadata: {}".format(
            ", ".join(sorted(missing_metadata))))
    if metadata["ece592_inclusion_processed_format_version"] != "1":
        raise ValueError("unsupported inclusion processed format")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("plot expects unadjusted timing units")
    if metadata["cache_inclusion_labels_assigned"] != "false":
        raise ValueError("plot must remain inclusion-label blind")
    if int(metadata["processed_point_count"], 10) != len(rows):
        raise ValueError("processed_point_count does not match rows")
    return metadata, int(metadata["source_plan_trial_count"], 10), rows


def aggregate_rows(rows):
    by_point = {}
    for row in rows:
        key = (row["probe_nodes"], row["pressure_nodes"], row["spacing"])
        by_point.setdefault(key, []).append(row)

    aggregated = []
    max_repeats = 0
    for probe_nodes, pressure_nodes, spacing in sorted(by_point):
        point_rows = by_point[(probe_nodes, pressure_nodes, spacing)]
        deltas = [row["delta"] for row in point_rows]
        max_repeats = max(max_repeats, len(deltas))
        aggregated.append({
            "probe_nodes": probe_nodes,
            "probe_bytes": probe_nodes * spacing,
            "pressure_nodes": pressure_nodes,
            "pressure_bytes": pressure_nodes * spacing,
            "median_delta": statistics.median(deltas),
            "minimum_delta": min(deltas),
            "maximum_delta": max(deltas),
        })
    return aggregated, max_repeats


def byte_label(value):
    if value >= 1024 * 1024 and value % (1024 * 1024) == 0:
        return "{} MiB".format(value // (1024 * 1024))
    if value >= 1024:
        return "{:.3g} KiB".format(value / 1024.0)
    return "{} B".format(value)


def gnuplot_quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_plot_data(path, aggregated):
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write(
            "probe_bytes\tpressure_bytes\tmedian_delta\tminimum_delta\t"
            "maximum_delta\n")
        for row in aggregated:
            stream.write("{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\n".format(
                row["probe_bytes"], row["pressure_bytes"],
                row["median_delta"], row["minimum_delta"],
                row["maximum_delta"]))


def write_gnuplot_script(path, data_path, pdf_path, metadata, aggregated,
                         trial_count):
    probe_sizes = sorted({row["probe_bytes"] for row in aggregated})
    colors = ("#08519c", "#238b45", "#cb181d", "#756bb1", "#636363")
    point_types = (7, 5, 9, 13, 11)
    plot_parts = []
    for index, probe_bytes in enumerate(probe_sizes):
        color = colors[index % len(colors)]
        point_type = point_types[index % len(point_types)]
        label = "probe {}".format(byte_label(probe_bytes))
        plot_parts.append(
            "{} using ($1=={}?$2:1/0):4:5 with filledcurves "
            "lc rgb '{}' notitle".format(
                gnuplot_quote(data_path), probe_bytes, color))
        plot_parts.append(
            "{} using ($1=={}?$2:1/0):3 with linespoints lw 2 pt {} "
            "ps 0.75 lc rgb '{}' title {}".format(
                gnuplot_quote(data_path), probe_bytes, point_type, color,
                gnuplot_quote(label)))

    title = "{} Phase I inclusion/reuse pressure sweep".format(
        metadata["source_raw_hostname"])
    note = ("{} trials; >=1,000,000 samples/point; positive means probe "
            "slowed after pressure; no inclusion/exclusion labels").format(
                trial_count)

    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo enhanced color font 'Sans,10' "
                     "size 7.2in,4.6in\n")
        stream.write("set output {}\n".format(gnuplot_quote(pdf_path)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("set logscale x 2\n")
        stream.write("set xzeroaxis lw 1 lc rgb '#777777'\n")
        stream.write("set key top left opaque\n")
        stream.write("set title {}\n".format(gnuplot_quote(title)))
        stream.write("set xlabel 'Pressure working-set span (bytes, log2)'\n")
        stream.write("set ylabel {}\n".format(gnuplot_quote(
            "Probe-after minus probe-before median "
            "({}/access, unadjusted)".format(
                metadata["source_raw_timer_unit"]))))
        stream.write("set label 1 {} at graph 0.99,0.03 right front "
                     "font ',8'\n".format(gnuplot_quote(note)))
        stream.write("plot " + ", \\\n+    ".join(plot_parts) + "\n")


def processing_command():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_provenance(path, input_path, output_path, metadata, trial_count,
                     point_count, max_repeats, gnuplot_version):
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("ece592_plot_provenance_version=1\n")
        stream.write("plot_type=inclusion-reuse-pressure-curve\n")
        stream.write("source_processed_file={}\n".format(
            os.path.abspath(input_path)))
        stream.write("source_processed_sha256={}\n".format(
            sha256_file(input_path)))
        stream.write("output_plot_file={}\n".format(
            os.path.abspath(output_path)))
        stream.write("output_plot_sha256={}\n".format(sha256_file(output_path)))
        stream.write("source_hostname={}\n".format(
            metadata["source_raw_hostname"]))
        stream.write("source_isa={}\n".format(metadata["source_raw_isa"]))
        stream.write("source_timer_unit={}\n".format(
            metadata["source_raw_timer_unit"]))
        stream.write("source_traversal={}\n".format(
            metadata["source_raw_traversal"]))
        stream.write("trial_count={}\n".format(trial_count))
        stream.write("unique_inclusion_point_count={}\n".format(point_count))
        stream.write("maximum_repeat_count_per_point={}\n".format(max_repeats))
        stream.write("plot_script={}\n".format(os.path.abspath(__file__)))
        stream.write("plot_command={}\n".format(processing_command()))
        stream.write("plot_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("gnuplot_version={}\n".format(gnuplot_version))
        stream.write("timer_overhead_subtracted=false\n")
        stream.write("cache_inclusion_labels_assigned=false\n")
        stream.write("background_grid_lines=false\n")
        stream.write("status=ok\n")
        stream.flush()
        os.fsync(stream.fileno())


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Plot a Phase-I inclusion/reuse processed TSV.")
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
        metadata, trial_count, rows = read_processed(arguments.input)
        aggregated, max_repeats = aggregate_rows(rows)
        output_parent = os.path.dirname(os.path.abspath(arguments.output))
        with tempfile.TemporaryDirectory(prefix="ece592_inclusion_plot_",
                                         dir=output_parent) as temporary:
            data_path = os.path.join(temporary, "inclusion.dat")
            script_path = os.path.join(temporary, "inclusion.gnuplot")
            temporary_pdf = os.path.join(temporary, "inclusion.pdf")
            write_plot_data(data_path, aggregated)
            write_gnuplot_script(script_path, data_path, temporary_pdf,
                                 metadata, aggregated, trial_count)
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
                         arguments.input, arguments.output, metadata,
                         trial_count, len(aggregated), max_repeats,
                         version_result.stdout.strip())
        print("input_filename={}".format(arguments.input))
        print("output_filename={}".format(arguments.output))
        print("trial_count={}".format(trial_count))
        print("unique_inclusion_point_count={}".format(len(aggregated)))
        print("cache_inclusion_labels_assigned=false")
        print("status=ok")
    except (OSError, ValueError, RuntimeError,
            subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
