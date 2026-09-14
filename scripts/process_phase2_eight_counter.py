#!/usr/bin/env python3
"""Build the Phase-II eight-counter normalized summary and ranked plot.

Counters that a machine's PMU does not expose (for example LLC-loads on a
CPU whose kernel/PMU has no such event) are treated as missing rather than
fatal: the affected fields are written as the MISSING token, every metric
that does not depend on them is still produced, and the per-run
missing_events column records exactly what was unavailable.  Pass
--require-complete to restore the old strict behavior.
"""

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


MACHINES = ("sunbird", "skylark", "charnwood", "ookay")
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

# Ordered preference for the "last cache" comparable pair.  Each entry is
# (load event, miss event).  A pair may be satisfied partially: a machine that
# exposes LLC-load-misses but not LLC-loads still yields miss counts and
# miss-per-access normalization, only the miss *rate* is undefined.
LAST_CACHE_EVENT_PAIRS = (
    ("LLC-loads", "LLC-load-misses"),
    ("l2d_cache_rd", "l2d_cache_refill_rd"),
)

# Token written wherever a value could not be computed because the underlying
# counter was unavailable.  Downstream readers should test for it explicitly.
MISSING = "NA"


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


def requested_events(metadata):
    """Events the run asked perf for, in recorded order."""
    requested = []
    for token in re.split(r"[,\s]+", metadata.get("events", "")):
        token = token.strip()
        if token and token not in requested:
            requested.append(token)
    return requested


def select_last_cache_events(events):
    """Pick the last-cache load/miss event names that this run actually has.

    Returns (load_event_name_or_None, miss_event_name_or_None).  A complete
    pair wins over a partial one so that a machine exposing both x86 LLC
    events is never demoted to the Arm L2D pair, or vice versa.
    """
    for load_event, miss_event in LAST_CACHE_EVENT_PAIRS:
        if load_event in events and miss_event in events:
            return load_event, miss_event
    for load_event, miss_event in LAST_CACHE_EVENT_PAIRS:
        if miss_event in events:
            return (load_event if load_event in events else None), miss_event
    for load_event, miss_event in LAST_CACHE_EVENT_PAIRS:
        if load_event in events:
            return load_event, None
    return None, None


def safe_divide(numerator, denominator):
    """Quotient, or None when either operand is missing or the divisor is 0."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def safe_rate(numerator, denominator):
    # Deliberately 100.0 * n / d, not 100.0 * (n / d): keeps results
    # bit-identical to the pre-missing-event version of this script.
    if numerator is None or denominator is None or denominator == 0:
        return None
    return 100.0 * numerator / denominator


def parse_perf_file(path, require_complete=False):
    with open(path, "r", encoding="utf-8", errors="replace") as stream:
        lines = stream.readlines()

    metadata = parse_key_value_metadata(lines)
    if "status=ok\n" not in lines and not any(
            line.rstrip("\n") == "status=ok" for line in lines):
        raise ValueError("{} did not report status=ok".format(path))

    events = {}
    unavailable_events = []
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

        # perf prints "<not supported>", "<not counted>" or "<not permitted>"
        # in the count column when an event does not exist on this PMU or the
        # kernel refused it.  Record the fact instead of silently dropping it.
        unavailable = re.match(
            r"\s*<not\s+(?:supported|counted|permitted)>\s+"
            r"([A-Za-z0-9_.-]+)(?::[A-Za-z])?\b", line)
        if unavailable is not None:
            event_name = unavailable.group(1)
            if event_name not in unavailable_events:
                unavailable_events.append(event_name)
            continue

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

    # Every event the run asked for but did not come back with, whether perf
    # labelled it unsupported or omitted it entirely.
    missing_events = [event for event in requested_events(metadata)
                      if event not in events]
    for event in unavailable_events:
        if event not in missing_events:
            missing_events.append(event)

    if require_complete and missing_events:
        raise ValueError("{} missing events: {}".format(
            path, ", ".join(missing_events)))

    last_cache_load_event, last_cache_miss_event = select_last_cache_events(
        events)
    if (require_complete
            and (last_cache_load_event is None
                 or last_cache_miss_event is None)):
        raise ValueError(
            "{} missing last-cache comparable events".format(path))

    cycles = events.get("cycles")
    instructions = events.get("instructions")
    l1_loads = events.get("L1-dcache-loads")
    l1_misses = events.get("L1-dcache-load-misses")
    last_loads = (None if last_cache_load_event is None
                  else events[last_cache_load_event])
    last_misses = (None if last_cache_miss_event is None
                   else events[last_cache_miss_event])

    return {
        "machine": machine,
        "workload": workload,
        "source_file": path,
        "source_sha256": sha256_file(path),
        "events_recorded": metadata["events"],
        "missing_events": ",".join(missing_events) if missing_events else "",
        "nodes": nodes,
        "spacing_bytes": spacing_bytes,
        "working_set_bytes": working_set_bytes,
        "timed_samples": timed_samples,
        "batch": batch,
        "timed_dependent_accesses": timed_dependent_accesses,
        "cycles": cycles,
        "instructions": instructions,
        "cache_references": events.get("cache-references"),
        "cache_misses": events.get("cache-misses"),
        "l1_dcache_loads": l1_loads,
        "l1_dcache_load_misses": l1_misses,
        "last_cache_load_event": last_cache_load_event,
        "last_cache_miss_event": last_cache_miss_event,
        "last_cache_loads": last_loads,
        "last_cache_load_misses": last_misses,
        "seconds_elapsed": elapsed_seconds,
        "cycles_per_timed_access": safe_divide(
            cycles, timed_dependent_accesses),
        "instructions_per_timed_access": safe_divide(
            instructions, timed_dependent_accesses),
        "cache_misses_per_timed_access": safe_divide(
            events.get("cache-misses"), timed_dependent_accesses),
        "l1_misses_per_timed_access": safe_divide(
            l1_misses, timed_dependent_accesses),
        "last_cache_misses_per_timed_access": safe_divide(
            last_misses, timed_dependent_accesses),
        "l1_miss_rate_percent": safe_rate(l1_misses, l1_loads),
        "last_cache_miss_rate_percent": safe_rate(last_misses, last_loads),
        "ipc": safe_divide(instructions, cycles),
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


def presented(value):
    """Render a cell, substituting the MISSING token for unavailable values."""
    if value is None:
        return MISSING
    if isinstance(value, float) and math.isnan(value):
        return MISSING
    return value


def write_summary(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("phase2_eight_counter_summary_version=2\n")
        stream.write("normalization=raw counts divided by timed_samples * batch\n")
        stream.write("last_cache_mapping=LLC-loads/LLC-load-misses on x86; "
                     "l2d_cache_rd/l2d_cache_refill_rd on Thunderbird Arm\n")
        stream.write("timed_access_definition=one dependent pointer-chase load in "
                     "the benchmark timed batch\n")
        stream.write("missing_value_token={}\n".format(MISSING))
        stream.write("missing_event_policy=counters the machine PMU does not "
                     "expose are reported as {} in every field that depends on "
                     "them and listed in missing_events; all other fields are "
                     "still computed\n".format(MISSING))
        stream.write("data_begin\n")
        fieldnames = [
            "machine", "workload", "source_file", "source_sha256",
            "events_recorded", "missing_events", "nodes", "spacing_bytes",
            "working_set_bytes",
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
            writer.writerow({key: presented(value)
                             for key, value in row.items()})
        stream.write("data_end\n")


def gnuplot_quote(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


METRIC_KEYS = {
    "cycles": "cycles_per_timed_access",
    "l1": "l1_miss_rate_percent",
    "last": "last_cache_miss_rate_percent",
}


def write_plot_data(path, rows, metric):
    """Write ranked plot data, skipping runs whose metric is unavailable.

    Returns the number of plotted points so the caller knows whether the
    subplot has anything to draw.
    """
    metric_key = METRIC_KEYS[metric]
    plotted = 0
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write("rank\tmachine\tworkload\tvalue\n")
        for workload in WORKLOADS:
            ranked = sorted(
                (row for row in rows
                 if row["workload"] == workload
                 and row[metric_key] is not None),
                key=lambda row: row[metric_key])
            for rank, row in enumerate(ranked, 1):
                stream.write("{}\t{}\t{}\t{:.17g}\n".format(
                    rank, row["machine"], row["workload"], row[metric_key]))
                plotted += 1
    return plotted


def write_gnuplot_script(path, output_pdf, data_paths, plotted_counts):
    panels = (
        ("cycles", "cycles / timed access"),
        ("l1", "L1D load miss rate (%)"),
        ("last", "Last-cache/L2D miss rate (%)"),
    )
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("set terminal pdfcairo noenhanced color font 'Sans,10' "
                     "size 8.0in,7.0in\n")
        stream.write("set output {}\n".format(gnuplot_quote(output_pdf)))
        stream.write("set datafile separator '\\t'\n")
        stream.write("set datafile missing {}\n".format(gnuplot_quote(MISSING)))
        stream.write("unset grid\n")
        stream.write("set key outside right center opaque\n")
        stream.write("set multiplot layout 3,1 title 'Phase II 8-counter ranked summary'\n")
        stream.write("set xrange [0.8:{:.1f}]\n".format(len(MACHINES) + 0.2))
        stream.write("set xtics 1\n")
        stream.write("set xlabel 'Rank within workload (lower is better)'\n")
        for index, (metric, ylabel) in enumerate(panels, 1):
            stream.write("set ylabel {}\n".format(gnuplot_quote(ylabel)))
            if plotted_counts[metric] > 0:
                stream.write("plot ")
                stream.write(plot_workload_lines(data_paths[metric]))
                stream.write("\n")
            else:
                # No machine in this run exposes the counters this panel
                # needs.  Draw an empty, labelled panel: asking gnuplot to
                # plot a data file with no valid points is a hard error.
                stream.write("set yrange [0:1]\n")
                stream.write("set label {} 'no data: required counters "
                             "unavailable on every machine' at graph 0.5,0.5 "
                             "center font ',10'\n".format(index))
                stream.write("plot 0 with lines lc rgb '#ffffff' notitle\n")
                stream.write("unset label {}\n".format(index))
                stream.write("set autoscale y\n")
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
        plotted_counts = {}
        for metric in ("cycles", "l1", "last"):
            data_path = os.path.join(tempdir, "{}.dat".format(metric))
            plotted_counts[metric] = write_plot_data(data_path, rows, metric)
            data_paths[metric] = data_path
        script_path = os.path.join(tempdir, "plot.gnuplot")
        temporary_pdf = os.path.join(tempdir, "ranked.pdf")
        write_gnuplot_script(script_path, temporary_pdf, data_paths,
                             plotted_counts)
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
            for metric in ("cycles", "l1", "last"):
                stream.write("plotted_points_{}={}\n".format(
                    metric, plotted_counts[metric]))
                stream.write("omitted_runs_{}={}\n".format(
                    metric, len(rows) - plotted_counts[metric]))
    return plotted_counts


def parse_args():
    parser = argparse.ArgumentParser(
        description="Normalize and plot Phase-II eight-counter perf results.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--plot-output", required=True)
    parser.add_argument(
        "--require-complete", action="store_true",
        help="fail when any requested counter is unavailable instead of "
             "reporting it as {}".format(MISSING))
    parser.add_argument(
        "--require-all-inputs", action="store_true",
        help="fail when a machine/workload perf file is absent instead of "
             "skipping it")
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
    skipped = []
    try:
        for machine in MACHINES:
            for workload in WORKLOADS:
                try:
                    input_path = canonical_input_path(root, machine, workload)
                except FileNotFoundError as error:
                    if args.require_all_inputs:
                        raise
                    skipped.append("{}/{}".format(machine, workload))
                    print("warning: {}".format(error), file=sys.stderr)
                    continue
                rows.append(parse_perf_file(
                    input_path, require_complete=args.require_complete))
        if not rows:
            raise ValueError("no usable perf inputs were found")
        rows.sort(key=lambda row: (
            MACHINES.index(row["machine"]), WORKLOADS.index(row["workload"])))
        write_summary(args.output, rows)
        plotted_counts = write_plot(args.plot_output, rows)
    except (OSError, RuntimeError, ValueError,
            subprocess.SubprocessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    incomplete = [row for row in rows if row["missing_events"]]
    print("output_filename={}".format(args.output))
    print("plot_output_filename={}".format(args.plot_output))
    print("machine_count={}".format(len(MACHINES)))
    print("workload_count={}".format(len(WORKLOADS)))
    print("row_count={}".format(len(rows)))
    print("skipped_input_count={}".format(len(skipped)))
    if skipped:
        print("skipped_inputs={}".format(",".join(skipped)))
    print("rows_with_missing_events={}".format(len(incomplete)))
    for row in incomplete:
        print("missing_events[{}/{}]={}".format(
            row["machine"], row["workload"], row["missing_events"]))
    for metric in ("cycles", "l1", "last"):
        print("plotted_points_{}={}".format(metric, plotted_counts[metric]))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
