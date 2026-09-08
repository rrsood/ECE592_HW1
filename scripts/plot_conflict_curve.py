#!/usr/bin/env python3
"""Create a specification-blind Phase-I associativity/conflict curve."""

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


MEDIAN_FIELD = "elapsed_raw_ticks_per_access_unadjusted_median"
Q1_FIELD = "elapsed_raw_ticks_per_access_unadjusted_q1"
Q3_FIELD = "elapsed_raw_ticks_per_access_unadjusted_q3"


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
        required_columns = {
            "trial", "conflict_line_count", "conflict_stride_bytes",
            "traversal", "timer_unit", "timed_sample_count",
            MEDIAN_FIELD, Q1_FIELD, Q3_FIELD,
        }
        missing_columns = required_columns.difference(reader.fieldnames)
        if missing_columns:
            raise ValueError("missing processed columns: {}".format(
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
                raise ValueError("processed row has extra fields")
            try:
                row = {
                    "trial": int(record["trial"], 10),
                    "line_count": int(record["conflict_line_count"], 10),
                    "stride": int(record["conflict_stride_bytes"], 10),
                    "sample_count": int(record["timed_sample_count"], 10),
                    "median": float(record[MEDIAN_FIELD]),
                    "q1": float(record[Q1_FIELD]),
                    "q3": float(record[Q3_FIELD]),
                    "traversal": record["traversal"],
                    "timer_unit": record["timer_unit"],
                }
            except ValueError as error:
                raise ValueError("invalid numeric processed value") from error
            if (row["trial"] < 0 or row["line_count"] < 2 or
                    row["stride"] <= 0 or row["sample_count"] < 1_000_000 or
                    not all(math.isfinite(row[key])
                            for key in ("median", "q1", "q3")) or
                    not row["q1"] <= row["median"] <= row["q3"]):
                raise ValueError("invalid processed conflict row")
            rows.append(row)

        if not found_end:
            raise ValueError("processed file has no data_end marker")
        if any(line.strip() for line in stream):
            raise ValueError("unexpected content after data_end")

    required_metadata = {
        "ece592_conflict_processed_format_version",
        "source_raw_hostname",
        "source_raw_isa",
        "source_raw_timer_unit",
        "source_raw_traversal",
        "source_raw_timed_sample_count",
        "source_plan_trial_count",
        "processed_point_count",
        "timer_overhead_subtracted",
    }
    missing_metadata = required_metadata.difference(metadata)
    if missing_metadata:
        raise ValueError("missing processed metadata: {}".format(
            ", ".join(sorted(missing_metadata))))
    if metadata["ece592_conflict_processed_format_version"] != "1":
        raise ValueError("unsupported processed format version")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("conflict curve requires unadjusted timer values")
    if metadata["source_raw_traversal"] != \
            "randomized-conflict-dependent-cycle":
        raise ValueError("conflict curve must use randomized conflict traversal")

    try:
        declared_points = int(metadata["processed_point_count"], 10)
        declared_trials = int(metadata["source_plan_trial_count"], 10)
    except ValueError as error:
        raise ValueError("invalid processed metadata count") from error
    if declared_points != len(rows) or declared_trials < 1 or not rows:
        raise ValueError("processed point/trial count does not match data")

    for row in rows:
        if (row["traversal"] != metadata["source_raw_traversal"] or
                row["timer_unit"] != metadata["source_raw_timer_unit"]):
            raise ValueError("row traversal or timer unit changed within sweep")

    return metadata, declared_trials, rows


def aggregate_rows(trial_count, rows):
    by_point = {}
    for row in rows:
        by_point.setdefault((row["stride"], row["line_count"]), []).append(row)

    aggregated = []
    maximum_repeat_count = 0
    for stride, line_count in sorted(by_point):
        point_rows = sorted(
            by_point[(stride, line_count)], key=lambda row: row["trial"])
        if any(row["trial"] < 0 or row["trial"] >= trial_count
               for row in point_rows):
            raise ValueError("point contains invalid trial number")
        maximum_repeat_count = max(maximum_repeat_count, len(point_rows))
        aggregated.append({
            "stride": stride,
            "line_count": line_count,
            "aggregate_median": statistics.median(
                row["median"] for row in point_rows),
            "iqr_envelope_low": min(row["q1"] for row in point_rows),
            "iqr_envelope_high": max(row["q3"] for row in point_rows),
        })
    return aggregated, maximum_repeat_count


def gnuplot_quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_plot_data(path, aggregated):
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write(
            "conflict_stride_bytes\tconflict_line_count\taggregate_median\t"
            "iqr_low\tiqr_high\n")
        for point in aggregated:
            stream.write("{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\n".format(
                point["stride"], point["line_count"],
                point["aggregate_median"], point["iqr_envelope_low"],
                point["iqr_envelope_high"]))


def write_gnuplot_script(path, data_path, temporary_pdf, metadata,
                         aggregated, trial_count):
    strides = sorted({point["stride"] for point in aggregated})
    title = "{} Phase I randomized conflict-set sweep".format(
        metadata["source_raw_hostname"])
    note = ("{} trials; >=1,000,000 samples/point; timer overhead not "
            "subtracted".format(trial_count))
    colors = ("#08519c", "#238b45", "#cb181d", "#756bb1", "#636363",
              "#e6550d", "#31a354", "#6baed6")
    point_types = (7, 5, 9, 13, 11, 3, 1, 15)

    plot_parts = []
    for index, stride in enumerate(strides):
        color = colors[index % len(colors)]
        point_type = point_types[index % len(point_types)]
        label = "stride {} B".format(stride)
        plot_parts.append(
            "{} using ($1=={}?$2:1/0):4:5 with filledcurves "
            "lc rgb '{}' notitle".format(
                gnuplot_quote(data_path), stride, color))
        plot_parts.append(
            "{} using ($1=={}?$2:1/0):3 with linespoints lw 2 pt {} "
            "ps 0.65 lc rgb '{}' title {}".format(
                gnuplot_quote(data_path), stride, point_type, color,
                gnuplot_quote(label)))

    minimum_line_count = min(point["line_count"] for point in aggregated)
    maximum_line_count = max(point["line_count"] for point in aggregated)

    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo enhanced color font 'Sans,10' "
                     "size 7.2in,4.6in\n")
        stream.write("set output {}\n".format(gnuplot_quote(temporary_pdf)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("set yrange [0:*]\n")
        stream.write("set xrange [{}:{}]\n".format(
            minimum_line_count, maximum_line_count))
        stream.write("set xtics 1\n")
        stream.write("set key top left opaque\n")
        stream.write("set title {}\n".format(gnuplot_quote(title)))
        stream.write("set xlabel 'Simultaneously live candidate-conflict lines'\n")
        stream.write(
            "set ylabel 'Median latency (timer ticks/dependent access, unadjusted)'\n")
        stream.write("set label 1 {} at graph 0.99,0.03 right front "
                     "font ',8'\n".format(gnuplot_quote(note)))
        stream.write("plot " + ", \\\n+    ".join(plot_parts) + "\n")


def processing_command():
    return " ".join(shlex.quote(argument) for argument in sys.argv)


def write_provenance(path, input_path, input_digest, output_path,
                     metadata, trial_count, point_count, stride_count,
                     maximum_repeat_count, gnuplot_version):
    created = False
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write("ece592_plot_provenance_version=1\n")
            stream.write("plot_type=associativity-conflict-curve\n")
            stream.write("source_processed_file={}\n".format(
                os.path.abspath(input_path)))
            stream.write("source_processed_sha256={}\n".format(input_digest))
            stream.write("output_plot_file={}\n".format(
                os.path.abspath(output_path)))
            stream.write("output_plot_sha256={}\n".format(
                sha256_file(output_path)))
            stream.write("source_hostname={}\n".format(
                metadata["source_raw_hostname"]))
            stream.write("source_isa={}\n".format(metadata["source_raw_isa"]))
            stream.write("source_timer_unit={}\n".format(
                metadata["source_raw_timer_unit"]))
            stream.write("source_traversal={}\n".format(
                metadata["source_raw_traversal"]))
            stream.write("trial_count={}\n".format(trial_count))
            stream.write("unique_conflict_stride_count={}\n".format(
                stride_count))
            stream.write("unique_conflict_point_count={}\n".format(
                point_count))
            stream.write("maximum_repeat_count_per_conflict_point={}\n".format(
                maximum_repeat_count))
            stream.write("x_field=conflict_line_count\n")
            stream.write("curve_group=conflict_stride_bytes\n")
            stream.write("y_field={}\n".format(MEDIAN_FIELD))
            stream.write("central_curve=median of per-repeat medians\n")
            stream.write("band=minimum Q1 to maximum Q3 across repeats\n")
            stream.write("timer_overhead_subtracted=false\n")
            stream.write("associativity_boundaries_annotated=false\n")
            stream.write("plotting_script={}\n".format(
                os.path.abspath(__file__)))
            stream.write("plotting_command={}\n".format(processing_command()))
            stream.write("plotting_working_directory={}\n".format(os.getcwd()))
            stream.write("python_version={}\n".format(
                platform.python_version()))
            stream.write("gnuplot_version={}\n".format(gnuplot_version))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def create_plot(arguments, metadata, trial_count, aggregated,
                maximum_repeat_count):
    output_path = os.path.abspath(arguments.output)
    provenance_path = output_path + ".provenance.tsv"
    output_parent = os.path.dirname(output_path)
    input_digest = sha256_file(arguments.input)
    output_created = False
    strides = sorted({point["stride"] for point in aggregated})

    with tempfile.TemporaryDirectory(
            prefix=".ece592-conflict-plot-", dir=output_parent) as temporary:
        data_path = os.path.join(temporary, "conflict.dat")
        script_path = os.path.join(temporary, "conflict.gnuplot")
        temporary_pdf = os.path.join(temporary, "conflict.pdf")
        write_plot_data(data_path, aggregated)
        write_gnuplot_script(script_path, data_path, temporary_pdf, metadata,
                             aggregated, trial_count)
        completed = subprocess.run(
            ["gnuplot", script_path], check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode != 0:
            raise RuntimeError("gnuplot failed: {}".format(
                completed.stderr.strip()))
        if not os.path.isfile(temporary_pdf) or os.path.getsize(temporary_pdf) == 0:
            raise RuntimeError("gnuplot did not create a nonempty PDF")

        try:
            os.link(temporary_pdf, output_path)
            output_created = True
            version = subprocess.run(
                ["gnuplot", "--version"], check=True, text=True,
                stdout=subprocess.PIPE).stdout.strip()
            write_provenance(
                provenance_path, arguments.input, input_digest, output_path,
                metadata, trial_count, len(aggregated), len(strides),
                maximum_repeat_count, version)
        except Exception:
            if output_created:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            raise


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Plot an unannotated Phase-I associativity/conflict curve.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if not os.path.isfile(arguments.input):
        parser.error("--input must name an existing processed TSV file")
    if not arguments.output.lower().endswith(".pdf"):
        parser.error("--output must use a .pdf extension")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    if os.path.exists(os.path.abspath(arguments.output) + ".provenance.tsv"):
        parser.error("plot provenance output must not already exist")
    if not os.path.isdir(os.path.dirname(os.path.abspath(arguments.output))):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        metadata, trial_count, rows = read_processed(arguments.input)
        aggregated, maximum_repeat_count = aggregate_rows(trial_count, rows)
        create_plot(arguments, metadata, trial_count, aggregated,
                    maximum_repeat_count)
    except (OSError, RuntimeError, ValueError,
            subprocess.SubprocessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("input_filename={}".format(arguments.input))
    print("output_filename={}".format(arguments.output))
    print("trial_count={}".format(trial_count))
    print("maximum_repeat_count_per_conflict_point={}".format(
        maximum_repeat_count))
    print("unique_conflict_point_count={}".format(len(aggregated)))
    print("associativity_boundaries_annotated=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
