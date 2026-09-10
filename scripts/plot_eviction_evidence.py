#!/usr/bin/env python3
"""Plot corrected Phase-I cross-level eviction/reload evidence.

The input is the processed TSV produced by process_eviction_run.py.  The plot
compares the target reload latency before and after walking the pressure set.
It intentionally does not assign inclusive/exclusive/non-inclusive labels.
"""

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


REQUIRED_COLUMNS = {
    "trial",
    "target_set_index",
    "pressure_offsets_bytes",
    "pressure_offset_count",
    "timer_unit",
    "target_reloads_per_sample",
    "baseline_median_ticks_per_target",
    "after_pressure_median_ticks_per_target",
    "delta_median_ticks_per_target",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
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
                raise ValueError("invalid metadata line before data_begin")
            key, value = line.split("=", 1)
            if not key or key in metadata:
                raise ValueError("invalid or duplicate metadata key")
            metadata[key] = value
        else:
            raise ValueError("processed file has no data_begin marker")

        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("processed file has no column header")
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing:
            raise ValueError("missing required columns: {}".format(
                ", ".join(sorted(missing))))

        first_column = reader.fieldnames[0]
        found_end = False
        for record in reader:
            if record[first_column] == "data_end":
                found_end = True
                break
            if None in record:
                raise ValueError("processed row has extra fields")
            row = {
                "trial": int(record["trial"], 10),
                "target_set": int(record["target_set_index"], 10),
                "pressure_count": int(record["pressure_offset_count"], 10),
                "pressure_offsets": record["pressure_offsets_bytes"],
                "timer_unit": record["timer_unit"],
                "reloads": int(record["target_reloads_per_sample"], 10),
                "baseline": float(record[
                    "baseline_median_ticks_per_target"]),
                "after": float(record[
                    "after_pressure_median_ticks_per_target"]),
                "delta": float(record["delta_median_ticks_per_target"]),
            }
            if (row["trial"] < 0 or row["target_set"] < 0 or
                    row["pressure_count"] < 2 or row["reloads"] < 2):
                raise ValueError("invalid nonnegative/integer field")
            for key in ("baseline", "after", "delta"):
                if not math.isfinite(row[key]):
                    raise ValueError("non-finite timing value")
            rows.append(row)

        if not found_end:
            raise ValueError("processed file has no data_end marker")

    required_metadata = {
        "ece592_eviction_processed_format_version",
        "summary_purpose",
        "timer_overhead_subtracted",
        "cache_policy_labels_assigned",
    }
    missing_metadata = required_metadata.difference(metadata)
    if missing_metadata:
        raise ValueError("missing metadata keys: {}".format(
            ", ".join(sorted(missing_metadata))))
    if metadata["ece592_eviction_processed_format_version"] != "1":
        raise ValueError("unsupported eviction processed format")
    if metadata["timer_overhead_subtracted"] != "false":
        raise ValueError("plot expects unadjusted timing units")
    if metadata["cache_policy_labels_assigned"] != "false":
        raise ValueError("plot must not use assigned cache-policy labels")
    if not rows:
        raise ValueError("no eviction rows to plot")
    return metadata, rows


def infer_pressure_footprint(row):
    offsets = [int(value, 10) for value in row["pressure_offsets"].split(",")]
    if len(offsets) != row["pressure_count"]:
        raise ValueError("pressure offset count does not match offset list")
    if len(offsets) < 2:
        return 0
    sorted_offsets = sorted(offsets)
    stride = min(
        later - earlier
        for earlier, later in zip(sorted_offsets, sorted_offsets[1:])
        if later > earlier)
    return row["pressure_count"] * stride


def byte_label(value):
    if value >= 1024:
        kib = value / 1024
        if value % 1024 == 0:
            return "{} KiB".format(value // 1024)
        return "{:.1f} KiB".format(kib)
    return "{} B".format(value)


def aggregate(rows):
    by_key = {}
    for row in rows:
        key = (row["target_set"], row["pressure_count"])
        by_key.setdefault(key, []).append(row)

    output = []
    for key in sorted(by_key):
        group = by_key[key]
        baselines = [row["baseline"] for row in group]
        afters = [row["after"] for row in group]
        deltas = [row["delta"] for row in group]
        pressure_footprints = [infer_pressure_footprint(row) for row in group]
        if len(set(pressure_footprints)) != 1:
            raise ValueError("mixed pressure footprints for one condition")
        output.append({
            "target_set": key[0],
            "pressure_count": key[1],
            "pressure_footprint": pressure_footprints[0],
            "repeat_count": len(group),
            "baseline_median": statistics.median(baselines),
            "baseline_min": min(baselines),
            "baseline_max": max(baselines),
            "after_median": statistics.median(afters),
            "after_min": min(afters),
            "after_max": max(afters),
            "delta_median": statistics.median(deltas),
        })
    return output


def quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_plot_data(path, rows):
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write(
            "x\tlabel\ttarget_set\tpressure_count\trepeat_count\t"
            "pressure_footprint_bytes\tbaseline_median\tbaseline_min\tbaseline_max\t"
            "after_median\tafter_min\tafter_max\tdelta_median\n")
        for index, row in enumerate(rows, 1):
            label = "target {} / {}".format(
                row["target_set"], byte_label(row["pressure_footprint"]))
            stream.write(
                "{}\t{}\t{}\t{}\t{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\t"
                "{:.17g}\t{:.17g}\t{:.17g}\t{:.17g}\n".format(
                    index, label, row["target_set"], row["pressure_count"],
                    row["repeat_count"], row["pressure_footprint"],
                    row["baseline_median"],
                    row["baseline_min"], row["baseline_max"],
                    row["after_median"], row["after_min"], row["after_max"],
                    row["delta_median"]))


def write_gnuplot_script(path, data_path, output_path, title, ylabel):
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "set terminal pdfcairo enhanced color font 'Sans,10' "
            "size 7.2in,4.6in\n")
        stream.write("set output {}\n".format(quote(output_path)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("unset grid\n")
        stream.write("set key outside right center opaque\n")
        stream.write("set border lw 1.5\n")
        stream.write("set style fill solid 0.35 border\n")
        stream.write("set boxwidth 0.32\n")
        stream.write("set xtics rotate by -35\n")
        stream.write("set yrange [0:*]\n")
        stream.write("set title {}\n".format(quote(title)))
        stream.write("set xlabel 'Target-set / pressure footprint condition'\n")
        stream.write("set ylabel {}\n".format(quote(ylabel)))
        stream.write(
            "plot "
            "{} using ($1-0.18):7:8:9:xtic(2) with yerrorbars "
            "lc rgb '#08519c' pt 7 title 'baseline reload', \\\n"
            "     {} using ($1-0.18):7 with boxes "
            "lc rgb '#9ecae1' notitle, \\\n"
            "     {} using ($1+0.18):10:11:12 with yerrorbars "
            "lc rgb '#a50f15' pt 5 title 'after pressure reload', \\\n"
            "     {} using ($1+0.18):10 with boxes "
            "lc rgb '#fb6a4a' notitle\n".format(
                quote(data_path), quote(data_path),
                quote(data_path), quote(data_path)))


def write_provenance(path, input_path, output_path, row_count,
                     aggregate_count, gnuplot_version):
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("ece592_plot_provenance_version=1\n")
        stream.write("plot_type=cross-level-eviction-reload-evidence\n")
        stream.write("input_filename={}\n".format(os.path.abspath(input_path)))
        stream.write("input_sha256={}\n".format(sha256_file(input_path)))
        stream.write("output_filename={}\n".format(os.path.abspath(output_path)))
        stream.write("plotting_command={}\n".format(" ".join(
            shlex.quote(argument) for argument in sys.argv)))
        stream.write("plotting_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("gnuplot_version={}\n".format(gnuplot_version))
        stream.write("raw_row_count={}\n".format(row_count))
        stream.write("aggregated_condition_count={}\n".format(aggregate_count))
        stream.write("cache_policy_labels_assigned=false\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot corrected Phase-I eviction/reload evidence.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not os.path.isfile(args.input):
        parser.error("--input must name an existing file")
    if os.path.exists(args.output):
        parser.error("--output must not already exist")
    parent = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(parent):
        parser.error("output parent directory must already exist")
    return args


def main():
    args = parse_args()
    metadata, rows = read_processed(args.input)
    aggregated = aggregate(rows)
    timer_units = sorted({row["timer_unit"] for row in rows})
    if len(timer_units) != 1:
        raise ValueError("mixed timer units in one processed file")

    with tempfile.TemporaryDirectory(prefix="ece592_eviction_plot_") as tmpdir:
        data_path = os.path.join(tmpdir, "eviction_plot_data.tsv")
        script_path = os.path.join(tmpdir, "plot.gnuplot")
        write_plot_data(data_path, aggregated)
        title = "{} Phase I cross-level eviction/reload evidence".format(
            os.path.normpath(args.input).split(os.sep)[1]
            if len(os.path.normpath(args.input).split(os.sep)) > 2
            else "Phase I")
        ylabel = "Median target reload latency ({}/target, unadjusted)".format(
            timer_units[0])
        write_gnuplot_script(script_path, data_path, args.output, title, ylabel)
        completed = subprocess.run(
            ["gnuplot", "--version"], check=True, text=True,
            stdout=subprocess.PIPE)
        gnuplot_version = completed.stdout.strip()
        subprocess.run(["gnuplot", script_path], check=True)

    provenance = args.output + ".provenance.tsv"
    write_provenance(provenance, args.input, args.output, len(rows),
                     len(aggregated), gnuplot_version)
    print("input_filename={}".format(args.input))
    print("output_filename={}".format(args.output))
    print("raw_row_count={}".format(len(rows)))
    print("aggregated_condition_count={}".format(len(aggregated)))
    print("cache_policy_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
