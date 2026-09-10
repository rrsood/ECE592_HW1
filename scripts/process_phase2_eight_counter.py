#!/usr/bin/env python3
"""Build the Phase-II eight-counter normalized summary and ranked plot."""

import argparse
import csv
import hashlib
import math
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile


MACHINES = ("thunderbird", "artemisia", "crux", "upgrade")
WORKLOADS = ("l1_resident", "last_cache_sized", "larger_than_last_cache")
EVENT_FIELDS = (
    "cycles",
    "instructions",
    "cache-references",
    "cache-misses",
    "L1-dcache-loads",
    "L1-dcache-load-misses",
    "LLC-loads",
    "LLC-load-misses",
    "l2d_cache_rd",
    "l2d_cache_refill_rd",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def parse_key_value_metadata(lines):
    metadata = {}
    for line in lines:
        line = line.rstrip("\n")
        if line == "data_begin":
            break
        if "=" in line:
            key, value = line.split("=", 1)
            metadata[key] = value
    return metadata


def parse_perf_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as stream:
        lines = stream.readlines()

    metadata = parse_key_value_metadata(lines)
    if "status=ok\n" not in lines and not any(
            line.rstrip("\n") == "status=ok" for line in lines):
        raise ValueError("{} did not report status=ok".format(path))

    events = {}
    elapsed_seconds = None
    batch = None
    for line in lines:
        command_batch = re.search(r"--batch\s+(\d+)", line)
        if command_batch is not None:
            batch = int(command_batch.group(1), 10)

        elapsed = re.search(r"([0-9]+(?:\.[0-9]+)?)\s+seconds time elapsed",
                            line)
        if elapsed is not None:
            elapsed_seconds = float(elapsed.group(1))

        event = re.match(
            r"\s*([0-9][0-9,]*)\s+([A-Za-z0-9_.-]+)(?::[A-Za-z])?\b", line)
        if event is not None:
            event_name = event.group(2)
            if event_name in EVENT_FIELDS:
                events[event_name] = int(event.group(1).replace(",", ""), 10)

    required_metadata = {"machine", "workload", "nodes", "spacing_bytes",
                         "timed_samples", "events"}
    missing = required_metadata.difference(metadata)
    if missing:
        raise ValueError("{} missing metadata: {}".format(
            path, ", ".join(sorted(missing))))
    if elapsed_seconds is None:
        raise ValueError("{} missing elapsed time".format(path))
    if batch is None:
        raise ValueError("{} missing --batch in recorded command".format(path))

    machine = metadata["machine"]
    workload = metadata["workload"]
    nodes = int(metadata["nodes"], 10)
    spacing_bytes = int(metadata["spacing_bytes"], 10)
    timed_samples = int(metadata["timed_samples"], 10)
    working_set_bytes = int(metadata.get(
        "working_set_bytes", str(nodes * spacing_bytes)), 10)
    timed_dependent_accesses = timed_samples * batch

    for required_event in (
            "cycles", "instructions", "cache-references", "cache-misses",
            "L1-dcache-loads", "L1-dcache-load-misses"):
        if required_event not in events:
            raise ValueError("{} missing event {}".format(path, required_event))

    if "LLC-loads" in events and "LLC-load-misses" in events:
        last_cache_load_event = "LLC-loads"
        last_cache_miss_event = "LLC-load-misses"
    elif "l2d_cache_rd" in events and "l2d_cache_refill_rd" in events:
        last_cache_load_event = "l2d_cache_rd"
        last_cache_miss_event = "l2d_cache_refill_rd"
    else:
        raise ValueError("{} missing last-cache comparable events".format(path))

    l1_loads = events["L1-dcache-loads"]
    l1_misses = events["L1-dcache-load-misses"]
    last_loads = events[last_cache_load_event]
    last_misses = events[last_cache_miss_event]

    def safe_rate(numerator, denominator):
        if denominator == 0:
            return float("nan")
        return 100.0 * numerator / denominator

    return {
        "machine": machine,
        "workload": workload,
        "source_file": path,
        "source_sha256": sha256_file(path),
        "events_recorded": metadata["events"],
        "nodes": nodes,
        "spacing_bytes": spacing_bytes,
        "working_set_bytes": working_set_bytes,
        "timed_samples": timed_samples,
        "batch": batch,
        "timed_dependent_accesses": timed_dependent_accesses,
        "cycles": events["cycles"],
        "instructions": events["instructions"],
        "cache_references": events["cache-references"],
        "cache_misses": events["cache-misses"],
        "l1_dcache_loads": l1_loads,
        "l1_dcache_load_misses": l1_misses,
        "last_cache_load_event": last_cache_load_event,
        "last_cache_miss_event": last_cache_miss_event,
        "last_cache_loads": last_loads,
        "last_cache_load_misses": last_misses,
        "seconds_elapsed": elapsed_seconds,
        "cycles_per_timed_access": events["cycles"] / timed_dependent_accesses,
        "instructions_per_timed_access": (
            events["instructions"] / timed_dependent_accesses),
        "cache_misses_per_timed_access": (
            events["cache-misses"] / timed_dependent_accesses),
        "l1_misses_per_timed_access": l1_misses / timed_dependent_accesses,
        "last_cache_misses_per_timed_access": (
            last_misses / timed_dependent_accesses),
        "l1_miss_rate_percent": safe_rate(l1_misses, l1_loads),
        "last_cache_miss_rate_percent": safe_rate(last_misses, last_loads),
        "ipc": events["instructions"] / events["cycles"],
    }


def canonical_input_path(root, machine, workload):
    directory = os.path.join(root, "pmu", machine, "phase2_eight_counter_v1")
    preferred = []
    if workload == "last_cache_sized":
        preferred.append(os.path.join(directory, "perf_stat_last_cache_sized_v2.txt"))
    preferred.append(os.path.join(directory, "perf_stat_{}_v1.txt".format(workload)))
    for path in preferred:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("missing input for {} {}".format(machine, workload))


def write_summary(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("phase2_eight_counter_summary_version=1\n")
        stream.write("normalization=raw counts divided by timed_samples * batch\n")
        stream.write("last_cache_mapping=LLC-loads/LLC-load-misses on x86; "
                     "l2d_cache_rd/l2d_cache_refill_rd on Thunderbird Arm\n")
        stream.write("timed_access_definition=one dependent pointer-chase load in "
                     "the benchmark timed batch\n")
        stream.write("data_begin\n")
        fieldnames = [
            "machine", "workload", "source_file", "source_sha256",
            "events_recorded", "nodes", "spacing_bytes", "working_set_bytes",
            "timed_samples", "batch", "timed_dependent_accesses",
            "cycles", "instructions", "cache_references", "cache_misses",
            "l1_dcache_loads", "l1_dcache_load_misses",
            "last_cache_load_event", "last_cache_miss_event",
            "last_cache_loads", "last_cache_load_misses", "seconds_elapsed",
            "cycles_per_timed_access", "instructions_per_timed_access",
            "cache_misses_per_timed_access", "l1_misses_per_timed_access",
            "last_cache_misses_per_timed_access", "l1_miss_rate_percent",
            "last_cache_miss_rate_percent", "ipc",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t",
                                extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        stream.write("data_end\n")


def gnuplot_quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_plot_data(path, rows, metric):
    metric_key = {
        "cycles": "cycles_per_timed_access",
        "l1": "l1_miss_rate_percent",
        "last": "last_cache_miss_rate_percent",
    }[metric]
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write("rank\tmachine\tworkload\tvalue\n")
        for workload in WORKLOADS:
            ranked = sorted(
                (row for row in rows if row["workload"] == workload),
                key=lambda row: row[metric_key])
            for rank, row in enumerate(ranked, 1):
                stream.write("{}\t{}\t{}\t{:.17g}\n".format(
                    rank, row["machine"], row["workload"], row[metric_key]))


def write_gnuplot_script(path, output_pdf, data_paths):
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo noenhanced color font 'Sans,10' "
                     "size 8.0in,7.0in\n")
        stream.write("set output {}\n".format(gnuplot_quote(output_pdf)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("set datafile missing ''\n")
        stream.write("unset grid\n")
        stream.write("set key outside right center opaque\n")
        stream.write("set multiplot layout 3,1 title 'Phase II 8-counter ranked summary'\n")
        stream.write("set xrange [0.8:4.2]\n")
        stream.write("set xtics 1\n")
        stream.write("set xlabel 'Rank within workload (lower is better)'\n")
        stream.write("set ylabel 'cycles / timed access'\n")
        stream.write("plot ")
        stream.write(plot_workload_lines(data_paths["cycles"]))
        stream.write("\n")
        stream.write("set ylabel 'L1D load miss rate (%)'\n")
        stream.write("plot ")
        stream.write(plot_workload_lines(data_paths["l1"]))
        stream.write("\n")
        stream.write("set ylabel 'Last-cache/L2D miss rate (%)'\n")
        stream.write("plot ")
        stream.write(plot_workload_lines(data_paths["last"]))
        stream.write("\n")
        stream.write("unset multiplot\n")


def plot_workload_lines(data_path):
    parts = []
    styles = {
        "l1_resident": ("pt 7 lw 2", "L1 resident"),
        "last_cache_sized": ("pt 5 lw 2", "last-cache sized"),
        "larger_than_last_cache": ("pt 9 lw 2", "larger than last-cache"),
    }
    for workload in WORKLOADS:
        style, title = styles[workload]
        parts.append(
            "{} using (strcol(3) eq {} ? $1 : 1/0):4 with linespoints {} "
            "title {}".format(
                gnuplot_quote(data_path), gnuplot_quote(workload),
                style, gnuplot_quote(title)))
        parts.append(
            "{} using (strcol(3) eq {} ? $1 : 1/0):4:2 with labels "
            "offset char 0,0.7 font ',7' notitle".format(
                gnuplot_quote(data_path), gnuplot_quote(workload)))
    return ", \\\n+     ".join(parts)


def write_plot(path, rows):
    output_path = os.path.abspath(path)
    provenance_path = output_path + ".provenance.tsv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with tempfile.TemporaryDirectory(
            prefix=".ece592-phase2-8ctr-", dir=os.path.dirname(output_path)) as tempdir:
        data_paths = {}
        for metric in ("cycles", "l1", "last"):
            data_path = os.path.join(tempdir, "{}.dat".format(metric))
            write_plot_data(data_path, rows, metric)
            data_paths[metric] = data_path
        script_path = os.path.join(tempdir, "plot.gnuplot")
        temporary_pdf = os.path.join(tempdir, "ranked.pdf")
        write_gnuplot_script(script_path, temporary_pdf, data_paths)
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
            stream.write("plot_type=phase2-eight-counter-ranked-summary\n")
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
        description="Normalize and plot Phase-II eight-counter perf results.")
    parser.add_argument("--repo-root", default=".")
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
    root = os.path.abspath(args.repo_root)
    rows = []
    try:
        for machine in MACHINES:
            for workload in WORKLOADS:
                rows.append(parse_perf_file(
                    canonical_input_path(root, machine, workload)))
        rows.sort(key=lambda row: (
            MACHINES.index(row["machine"]), WORKLOADS.index(row["workload"])))
        write_summary(args.output, rows)
        write_plot(args.plot_output, rows)
    except (OSError, RuntimeError, ValueError,
            subprocess.SubprocessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("output_filename={}".format(args.output))
    print("plot_output_filename={}".format(args.plot_output))
    print("machine_count={}".format(len(MACHINES)))
    print("workload_count={}".format(len(WORKLOADS)))
    print("row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
