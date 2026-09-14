#!/usr/bin/env python3
"""Create the required Phase-III chronological vector plots with gnuplot."""

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile


PLOTS = [
    ("01_l1d_capacity", [("l1d_capacity_bytes", "L1D capacity")], "bytes", True),
    ("02_l1d_associativity", [("l1d_associativity", "L1D ways")], "ways", False),
    ("03_l1d_hit_latency", [("l1d_hit_latency_ns", "L1D hit")], "ns/access", False),
    ("04_l1_miss_penalty", [("l1_miss_penalty_ns", "L1 miss penalty")], "ns/access", False),
    ("05_l2_capacity_per_core", [("l2_capacity_per_core_bytes", "L2/core")], "bytes/core", True),
    ("06_l2_associativity", [("l2_associativity", "L2 ways")], "ways", False),
    ("07_l2_hit_latency", [("l2_hit_latency_ns", "L2 hit")], "ns/access", False),
    ("08_l2_miss_penalty", [("l2_miss_penalty_ns", "L2 miss penalty")], "ns/access", False),
    ("09_llc_capacity", [("llc_capacity_bytes", "LLC domain"),
                         ("llc_capacity_per_core_bytes", "LLC/core")], "bytes", True),
    ("10_llc_effective_associativity", [("llc_effective_associativity", "LLC effective ways")], "ways/bound", False),
    ("11_llc_latency_penalty", [("llc_hit_latency_ns", "LLC hit"),
                                ("llc_memory_penalty_ns", "LLC-to-memory penalty")], "ns/access", False),
    ("12_line_size", [("line_size_bytes", "line size")], "bytes", False),
    ("14_software_residency", [("software_residency_rate", "timing-derived residency")], "fraction", False),
    ("15a_pmu_l1_misses", [("pmu_l1_misses_per_timed_access", "L1D misses")], "misses/timed access", False),
    ("15b_pmu_last_cache_misses", [("pmu_last_cache_misses_per_timed_access", "last-cache misses")], "misses/timed access", False),
]
VENDORS = [("Intel", 7), ("AMD", 9), ("Ampere", 5), ("Arm", 5)]


def read_wrapped(path):
    rows = []
    with open(path, encoding="utf-8", newline="") as stream:
        for line in stream:
            if line.rstrip("\n") == "data_begin":
                break
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if row[reader.fieldnames[0]] == "data_end":
                break
            rows.append(row)
    return rows


def numeric(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def predictions(path):
    result = {}
    for row in read_wrapped(path):
        if numeric(row.get("predicted")) is None:
            continue
        result.setdefault(row["metric"], []).append(row)
    return result


def quote(text):
    return "'{}'".format(text.replace("'", "''"))


def write_series(path, points):
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        for point in sorted(set(points)):
            stream.write("\t".join(
                "{:.17g}".format(value) if isinstance(value, float) else str(value)
                for value in point) + "\n")


def plot_numeric(master, predicted, uncertainty, output_dir, stem, series,
                 ylabel, logscale):
    temp_dir = tempfile.mkdtemp(prefix=".phase3-plot-", dir=output_dir)
    try:
        commands = []
        styles = [1, 2]
        for metric_index, (metric, label) in enumerate(series):
            lab_points = [(int(row["year"]), numeric(row.get(metric)), row["vendor"])
                          for row in master if row["role"] == "lab" and numeric(row.get(metric)) is not None]
            if not lab_points:
                continue
            max_lab_year = max(point[0] for point in lab_points)
            for vendor, point_type in VENDORS:
                points = [(year, value) for year, value, row_vendor in lab_points
                          if row_vendor == vendor or (vendor == "Arm" and row_vendor not in {"Intel", "AMD", "Ampere"})]
                if points:
                    path = os.path.join(temp_dir, "{}_{}_lab.tsv".format(metric, vendor))
                    write_series(path, points)
                    commands.append("{} using 1:2 with linespoints ls {} pt {} title {}".format(
                        quote(path), styles[metric_index], point_type, quote("{} {} lab".format(vendor, label))))
            hazel = [(int(row["year"]), numeric(row.get(metric))) for row in master
                     if row["role"] == "hazel" and numeric(row.get(metric)) is not None]
            if hazel:
                path = os.path.join(temp_dir, "{}_hazel.tsv".format(metric))
                write_series(path, hazel)
                commands.append("{} using 1:2 with points ls {} pt 13 ps 1.5 title {}".format(
                    quote(path), styles[metric_index], quote("{} Hazel held-out".format(label))))
            future = [(int(row["year"]), float(row["predicted"]))
                      for row in predicted.get(metric, []) if int(row["year"]) > max_lab_year]
            if future:
                anchors = [(year, value) for year, value, _ in lab_points if year == max_lab_year]
                anchor = (max_lab_year, sum(value for _, value in anchors) / len(anchors))
                path = os.path.join(temp_dir, "{}_prediction.tsv".format(metric))
                intervals = {
                    int(row["year"]): (float(row["lower_95"]),
                                        float(row["upper_95"]))
                    for row in predicted.get(metric, [])
                    if int(row["year"]) > max_lab_year
                }
                prediction_points = [(anchor[0], anchor[1], anchor[1], anchor[1])]
                prediction_points.extend(
                    (year, value, intervals[year][0], intervals[year][1])
                    for year, value in future)
                write_series(path, prediction_points)
                commands.append("{} using 1:2 with lines ls {} dt 2 title {}".format(
                    quote(path), styles[metric_index], quote("{} frozen prediction".format(label))))
                commands.append("{} using 1:2:3:4 with yerrorbars ls {} notitle".format(
                    quote(path), styles[metric_index]))
            for role, point_type in (("lab", 7), ("hazel", 13)):
                error_points = []
                for row in master:
                    key = (role, row["machine"], row.get("constraint", ""), metric)
                    value = numeric(row.get(metric))
                    if row["role"] == role and value is not None and key in uncertainty:
                        low, high = uncertainty[key]
                        error_points.append((int(row["year"]), value, low, high))
                if error_points:
                    path = os.path.join(
                        temp_dir, "{}_{}_uncertainty.tsv".format(metric, role))
                    write_series(path, error_points)
                    commands.append(
                        "{} using 1:2:3:4 with yerrorbars lc rgb 'black' pt {} notitle".format(
                            quote(path), point_type))
        if not commands:
            return False
        output = os.path.join(output_dir, stem + ".pdf")
        script = os.path.join(temp_dir, "plot.gp")
        with open(script, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("set terminal pdfcairo enhanced color font 'Helvetica,11' size 5.2in,3.4in\n")
            stream.write("set output {}\n".format(quote(output)))
            stream.write("set border linewidth 1.4\nset tics out nomirror\nunset grid\n")
            stream.write("set xlabel 'Processor-generation introduction year'\n")
            stream.write("set ylabel {}\n".format(quote(ylabel)))
            stream.write("set key outside top center horizontal\n")
            stream.write("set style line 1 lc rgb '#000000' lw 1.7 ps 0.9\n")
            stream.write("set style line 2 lc rgb '#666666' lw 1.7 ps 0.9\n")
            if logscale:
                stream.write("set logscale y 2\nset format y '2^{%L}'\n")
            continuation = ", " + "\\" + "\n  "
            stream.write("plot " + continuation.join(commands) + "\n")
        subprocess.run(["gnuplot", script], check=True)
        return True
    finally:
        shutil.rmtree(temp_dir)


def plot_inclusion(master, output_dir):
    mapping = {"uncertain": 0, "non-inclusive/non-exclusive": 1,
               "exclusive/victim-like": 2, "inclusive": 3}
    points = []
    for row in master:
        value = row.get("inclusion_behavior", "").strip().lower()
        if value in mapping:
            points.append((int(row["year"]), mapping[value], row["role"]))
    if not points:
        return False
    temp_dir = tempfile.mkdtemp(prefix=".phase3-inclusion-", dir=output_dir)
    try:
        lab = os.path.join(temp_dir, "lab.tsv")
        hazel = os.path.join(temp_dir, "hazel.tsv")
        write_series(lab, [(x, y) for x, y, role in points if role == "lab"])
        write_series(hazel, [(x, y) for x, y, role in points if role == "hazel"])
        output = os.path.join(output_dir, "13_inclusion_behavior.pdf")
        script = os.path.join(temp_dir, "plot.gp")
        with open(script, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("set terminal pdfcairo font 'Helvetica,11' size 5.2in,3.4in\n")
            stream.write("set output {}\nunset grid\nset border linewidth 1.4\nset tics out nomirror\n".format(quote(output)))
            stream.write("set xlabel 'Processor-generation introduction year'\nset ylabel 'Observed inclusion behavior'\n")
            stream.write("set yrange [-0.5:3.5]\nset ytics ('uncertain' 0, 'NINE' 1, 'exclusive/victim-like' 2, 'inclusive' 3)\n")
            commands = [
                "{} using 1:2 with linespoints lc rgb 'black' pt 7 title 'lab timing evidence'".format(
                    quote(lab))
            ]
            if any(role == "hazel" for _, _, role in points):
                commands.append(
                    "{} using 1:2 with points lc rgb 'black' pt 13 ps 1.5 title 'Hazel held-out'".format(
                        quote(hazel)))
            continuation = ", " + "\\" + "\n     "
            stream.write("plot " + continuation.join(commands) + "\n")
        subprocess.run(["gnuplot", script], check=True)
        return True
    finally:
        shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", required=True)
    parser.add_argument("--frozen-predictions", required=True)
    parser.add_argument("--uncertainty",
                        help="optional long TSV using phase3/uncertainty_template.tsv")
    parser.add_argument("--output-directory", required=True)
    args = parser.parse_args()
    if shutil.which("gnuplot") is None:
        parser.error("gnuplot is required")
    if os.path.exists(args.output_directory):
        parser.error("--output-directory must not already exist")
    os.makedirs(args.output_directory)
    master = read_wrapped(args.master)
    predicted = predictions(args.frozen_predictions)
    uncertainty = {}
    if args.uncertainty:
        with open(args.uncertainty, encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                key = (row["role"], row["machine"], row["constraint"], row["metric"])
                uncertainty[key] = (
                    float(row["lower_95"]), float(row["upper_95"]))
    count = sum(plot_numeric(master, predicted, uncertainty,
                             args.output_directory, *item)
                for item in PLOTS)
    count += int(plot_inclusion(master, args.output_directory))
    print("output_directory={}".format(args.output_directory))
    print("plot_count={}".format(count))
    print("hazel_used_to_refit_predictions=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        sys.exit(1)
