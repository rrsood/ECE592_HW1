#!/usr/bin/env python3
"""Combine software-only hit-rate estimates with PMU comparison evidence."""

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


MACHINES = ("thunderbird", "artemisia", "crux", "upgrade")
WORKLOADS = ("l1_resident", "last_cache_sized", "larger_than_last_cache")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_software_estimate(path):
    metadata = {}
    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\n")
            if line == "data_begin":
                break
            if "=" in line:
                key, value = line.split("=", 1)
                metadata[key] = value
        else:
            raise ValueError("{} has no data_begin".format(path))
        reader = csv.DictReader(stream, delimiter="\t")
        row = next(reader)
    return metadata, row


def read_pmu_summary(path):
    rows = {}
    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream:
            if line.rstrip("\n") == "data_begin":
                break
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if row[reader.fieldnames[0]] == "data_end":
                break
            rows[(row["machine"], row["workload"])] = row
    return rows


def build_rows(root, pmu_summary):
    rows = []
    for machine in MACHINES:
        for workload in WORKLOADS:
            software_path = os.path.join(
                root, "data_processed", machine, "software_hit_rate_batch8",
                "phase2_sw_hit_rate_{}_v1.tsv".format(workload))
            if not os.path.isfile(software_path):
                raise FileNotFoundError(software_path)
            if (machine, workload) not in pmu_summary:
                raise ValueError("missing PMU summary for {} {}".format(
                    machine, workload))

            metadata, software = read_software_estimate(software_path)
            pmu = pmu_summary[(machine, workload)]

            software_hit_rate = float(software["estimated_hit_rate"])
            l1_misses_per_access = float(pmu["l1_misses_per_timed_access"])
            last_cache_misses_per_access = float(
                pmu["last_cache_misses_per_timed_access"])
            pmu_l1_not_miss_proxy = max(
                0.0, min(1.0, 1.0 - l1_misses_per_access))
            pmu_cache_resident_proxy = max(
                0.0, min(1.0, 1.0 - last_cache_misses_per_access))
            absolute_error = abs(software_hit_rate - pmu_cache_resident_proxy)
            relative_error = (
                absolute_error / pmu_cache_resident_proxy
                if pmu_cache_resident_proxy > 0.0
                else float("nan"))

            rows.append({
                "machine": machine,
                "workload": workload,
                "software_estimate_file": os.path.abspath(software_path),
                "software_estimate_sha256": sha256_file(software_path),
                "software_estimated_hit_rate": software["estimated_hit_rate"],
                "software_wilson_95_low": software["wilson_95_low"],
                "software_wilson_95_high": software["wilson_95_high"],
                "software_balanced_calibration_accuracy": metadata[
                    "balanced_calibration_accuracy"],
                "software_threshold_ticks_per_access": metadata[
                    "threshold_ticks_per_access"],
                "pmu_source_file": pmu["source_file"],
                "pmu_events_recorded": pmu["events_recorded"],
                "pmu_last_cache_load_event": pmu["last_cache_load_event"],
                "pmu_last_cache_miss_event": pmu["last_cache_miss_event"],
                "pmu_l1_miss_rate_percent": pmu["l1_miss_rate_percent"],
                "pmu_l1_misses_per_timed_access": (
                    pmu["l1_misses_per_timed_access"]),
                "pmu_l1_not_miss_proxy": "{:.17g}".format(
                    pmu_l1_not_miss_proxy),
                "pmu_last_cache_miss_rate_percent": (
                    pmu["last_cache_miss_rate_percent"]),
                "pmu_last_cache_misses_per_timed_access": (
                    pmu["last_cache_misses_per_timed_access"]),
                "pmu_cache_resident_proxy": "{:.17g}".format(
                    pmu_cache_resident_proxy),
                "absolute_error_vs_pmu_cache_resident_proxy": "{:.17g}".format(
                    absolute_error),
                "relative_error_vs_pmu_cache_resident_proxy": (
                    "not_defined" if math.isnan(relative_error)
                    else "{:.17g}".format(relative_error)),
                "comparison_note": (
                    "primary PMU proxy = max(0, min(1, 1 - PMU last-cache "
                    "misses per timed access)); L1D not-miss proxy is retained "
                    "as context; PMU and software runs use different batch "
                    "sizes, so compare trend more than exact identity"),
            })
    return rows


def write_summary(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fieldnames = [
        "machine", "workload", "software_estimate_file",
        "software_estimate_sha256", "software_estimated_hit_rate",
        "software_wilson_95_low", "software_wilson_95_high",
        "software_balanced_calibration_accuracy",
        "software_threshold_ticks_per_access", "pmu_source_file",
        "pmu_events_recorded", "pmu_last_cache_load_event",
        "pmu_last_cache_miss_event", "pmu_l1_miss_rate_percent",
        "pmu_l1_misses_per_timed_access", "pmu_l1_not_miss_proxy",
        "pmu_last_cache_miss_rate_percent",
        "pmu_last_cache_misses_per_timed_access",
        "pmu_cache_resident_proxy",
        "absolute_error_vs_pmu_cache_resident_proxy",
        "relative_error_vs_pmu_cache_resident_proxy", "comparison_note",
    ]
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("software_hit_rate_pmu_comparison_version=1\n")
        stream.write("software_metric=timing-derived hit-like fraction\n")
        stream.write("pmu_comparison_metric=bounded cache-resident proxy\n")
        stream.write("pmu_proxy=max(0,min(1,1-last_cache_misses_per_timed_access))\n")
        stream.write("l1_not_miss_proxy_retained_as_context=true\n")
        stream.write("software_runs=batch8 timing only, no PMU counters\n")
        stream.write("data_begin\n")
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        stream.write("data_end\n")


def gnuplot_quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_plot_data(path, rows):
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write("x\tmachine\tworkload\tsoftware\tpmu_cache_resident_proxy\tpmu_l1_proxy\n")
        x = 0
        for workload_index, workload in enumerate(WORKLOADS):
            for machine_index, machine in enumerate(MACHINES):
                row = next(row for row in rows
                           if row["machine"] == machine and
                           row["workload"] == workload)
                x = workload_index * (len(MACHINES) + 1) + machine_index + 1
                stream.write("{}\t{}\t{}\t{}\t{}\n".format(
                    x, machine, workload, row["software_estimated_hit_rate"],
                    row["pmu_cache_resident_proxy"],
                    row["pmu_l1_not_miss_proxy"]))


def write_gnuplot_script(path, data_path, output_pdf):
    xtics = []
    for workload_index, workload in enumerate(WORKLOADS):
        center = workload_index * (len(MACHINES) + 1) + (len(MACHINES) + 1) / 2
        label = workload.replace("_", " ")
        xtics.append("{} {:.1f}".format(gnuplot_quote(label), center))
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo noenhanced color font 'Sans,10' "
                     "size 8.0in,4.8in\n")
        stream.write("set output {}\n".format(gnuplot_quote(output_pdf)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("unset grid\n")
        stream.write("set title 'Software-only hit-rate estimator vs PMU cache-resident proxy'\n")
        stream.write("set ylabel 'hit-like / cache-resident fraction'\n")
        stream.write("set yrange [0:1.05]\n")
        stream.write("set xrange [0:{}]\n".format(
            len(WORKLOADS) * (len(MACHINES) + 1)))
        stream.write("set xtics rotate by -20 ({})\n".format(", ".join(xtics)))
        stream.write("set key outside right center opaque\n")
        stream.write("plot {} using 1:4 with points pt 7 ps 1.0 "
                     "title 'software estimate', \\\n".format(
                         gnuplot_quote(data_path)))
        stream.write("     {} using 1:5 with points pt 5 ps 1.0 "
                     "title 'PMU cache-resident proxy', \\\n".format(
                         gnuplot_quote(data_path)))
        stream.write("     {} using 1:4:2 with labels offset char 0,0.8 "
                     "font ',7' notitle\n".format(gnuplot_quote(data_path)))


def write_plot(path, rows):
    output_path = os.path.abspath(path)
    provenance_path = output_path + ".provenance.tsv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with tempfile.TemporaryDirectory(
            prefix=".ece592-sw-hit-plot-", dir=os.path.dirname(output_path)) as temp:
        data_path = os.path.join(temp, "software_hit_rate.dat")
        script_path = os.path.join(temp, "plot.gnuplot")
        temporary_pdf = os.path.join(temp, "software_hit_rate.pdf")
        write_plot_data(data_path, rows)
        write_gnuplot_script(script_path, data_path, temporary_pdf)
        completed = subprocess.run(
            ["gnuplot", script_path], check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode != 0:
            raise RuntimeError("gnuplot failed: {}".format(
                completed.stderr.strip()))
        os.link(temporary_pdf, output_path)
        version = subprocess.run(
            ["gnuplot", "--version"], check=True, text=True,
            stdout=subprocess.PIPE).stdout.strip()
        with open(provenance_path, "x", encoding="utf-8", newline="\n") as stream:
            stream.write("ece592_plot_provenance_version=1\n")
            stream.write("plot_type=software-hit-rate-pmu-comparison\n")
            stream.write("output_plot_file={}\n".format(output_path))
            stream.write("output_plot_sha256={}\n".format(sha256_file(output_path)))
            stream.write("plotting_script={}\n".format(os.path.abspath(__file__)))
            stream.write("plotting_command={}\n".format(
                " ".join(shlex.quote(arg) for arg in sys.argv)))
            stream.write("plotting_working_directory={}\n".format(os.getcwd()))
            stream.write("python_version={}\n".format(platform.python_version()))
            stream.write("gnuplot_version={}\n".format(version))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine software-only hit estimates and PMU comparison data.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--pmu-summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--plot-output", required=True)
    args = parser.parse_args()
    if os.path.exists(args.output):
        parser.error("--output must not already exist")
    if os.path.exists(args.plot_output):
        parser.error("--plot-output must not already exist")
    if os.path.exists(os.path.abspath(args.plot_output) + ".provenance.tsv"):
        parser.error("plot provenance output must not already exist")
    return args


def main():
    args = parse_args()
    try:
        root = os.path.abspath(args.repo_root)
        pmu_summary = read_pmu_summary(args.pmu_summary)
        rows = build_rows(root, pmu_summary)
        write_summary(args.output, rows)
        write_plot(args.plot_output, rows)
    except (OSError, RuntimeError, ValueError,
            subprocess.SubprocessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    print("output_filename={}".format(args.output))
    print("plot_output_filename={}".format(args.plot_output))
    print("row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
