#!/usr/bin/env python3
"""Plot the Phase-I cross-level inclusion/exclusion evidence.

Input  : the processed TSV produced by process_inclusion_policy_run.py
Output : up to three vector PDFs plus a provenance sidecar for each

  <prefix>_eviction_probability.pdf
      Eviction probability against pressure footprint, one curve per series.
      This is the figure the spec asks for: it shows the condition that
      distinguishes whether an upper-level copy survives or is invalidated
      after lower-level eviction pressure.

  <prefix>_reload_latency.pdf
      Median reload latency of the same targets, before and after pressure,
      against pressure footprint.  Same experiment in latency units, so the
      magnitude of the transition can be compared with the machine's own
      measured hit and DRAM latency classes.

  <prefix>_reload_boxplots.pdf
      Distribution box plots at the footprints immediately below, at or near,
      and above the inferred LLC capacity, satisfying the global requirement
      that every major test show the measured distribution rather than a
      single average.

Figure style follows the handout: white background, no background grid lines,
black and grayscale lines and markers, distinct marker shapes, strong axes,
readable when printed in grayscale.  Measured points use solid lines and solid
markers; no prediction or extrapolation is drawn here.
"""

import argparse
import csv
import hashlib
import os
import platform
import shlex
import statistics
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402


REQUIRED_COLUMNS = (
    "series_index",
    "trial",
    "target_bytes",
    "pressure_source",
    "pressure_bytes",
    "pressure_order",
    "helper_cpu",
    "accesses_per_sample",
    "raw_timer_unit",
    "eviction_probability",
    "baseline_ticks_median",
    "after_pressure_ticks_median",
    "baseline_ticks_p05",
    "baseline_ticks_q1",
    "baseline_ticks_q3",
    "baseline_ticks_p95",
    "after_pressure_ticks_p05",
    "after_pressure_ticks_q1",
    "after_pressure_ticks_q3",
    "after_pressure_ticks_p95",
)

# Distinguishable in grayscale: shape carries the meaning, not colour.
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
GRAYS = ["black", "0.35", "0.55", "0.15", "0.70", "0.45", "0.25", "0.60"]

BASE_FONT_SIZE = 13


def configure_style():
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": False,
        "axes.edgecolor": "black",
        "axes.linewidth": 1.4,
        "font.size": BASE_FONT_SIZE,
        "axes.labelsize": BASE_FONT_SIZE + 1,
        "axes.titlesize": BASE_FONT_SIZE + 1,
        "xtick.labelsize": BASE_FONT_SIZE - 1,
        "ytick.labelsize": BASE_FONT_SIZE - 1,
        "legend.fontsize": BASE_FONT_SIZE - 2,
        "legend.frameon": False,
        "lines.linewidth": 1.8,
        "lines.markersize": 7,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "pdf.fonttype": 42,
    })


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_processed(path):
    metadata = {}
    rows = []
    with open(path, "r", encoding="ascii", newline="") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if line == "data_begin":
                break
            if "=" in line:
                key, value = line.split("=", 1)
                metadata[key] = value
        else:
            raise ValueError("processed file has no data_begin marker")
        reader = csv.DictReader(stream, delimiter="\t")
        missing = [column for column in REQUIRED_COLUMNS
                   if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("processed file is missing columns: {}".format(
                ", ".join(missing)))
        first_column = reader.fieldnames[0]
        for record in reader:
            # The trailing marker occupies the first column only.
            if record[first_column] == "data_end":
                break
            rows.append(record)
    if not rows:
        raise ValueError("processed file contains no rows")
    return metadata, rows


def byte_label(value):
    value = int(value)
    if value == 0:
        return "none"
    for unit, scale in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if value >= scale:
            scaled = value / scale
            if abs(scaled - round(scaled)) < 0.05:
                return "{:.0f} {}".format(round(scaled), unit)
            return "{:.2g} {}".format(scaled, unit)
    return "{} B".format(value)


def series_label(row):
    target = byte_label(row["target_bytes"])
    source = row["pressure_source"]
    if source == "none":
        return "{} target, no pressure".format(target)
    if source == "self":
        return "{} target, same-core pressure".format(target)
    return "{} target, helper CPU {}".format(target, row["helper_cpu"])


def aggregate(rows):
    """Collapse trials: one entry per (series, pressure footprint)."""
    grouped = {}
    for row in rows:
        key = (int(row["series_index"]), int(row["pressure_bytes"]))
        grouped.setdefault(key, []).append(row)

    aggregated = []
    for (series_index, pressure_bytes), members in sorted(grouped.items()):
        first = members[0]

        def middle(column):
            return statistics.median(float(member[column])
                                     for member in members)

        aggregated.append({
            "series_index": series_index,
            "pressure_bytes": pressure_bytes,
            "label": series_label(first),
            "pressure_source": first["pressure_source"],
            "target_bytes": int(first["target_bytes"]),
            "trial_count": len(members),
            "eviction_probability": middle("eviction_probability"),
            "baseline_median": middle("baseline_ticks_median"),
            "after_median": middle("after_pressure_ticks_median"),
            "baseline_p05": middle("baseline_ticks_p05"),
            "baseline_q1": middle("baseline_ticks_q1"),
            "baseline_q3": middle("baseline_ticks_q3"),
            "baseline_p95": middle("baseline_ticks_p95"),
            "after_p05": middle("after_pressure_ticks_p05"),
            "after_q1": middle("after_pressure_ticks_q1"),
            "after_q3": middle("after_pressure_ticks_q3"),
            "after_p95": middle("after_pressure_ticks_p95"),
        })
    return aggregated


def curves(aggregated, include_sources):
    """Group into plottable curves, dropping the zero-footprint control."""
    by_series = {}
    for entry in aggregated:
        if entry["pressure_source"] not in include_sources:
            continue
        if entry["pressure_bytes"] <= 0:
            continue
        by_series.setdefault(entry["series_index"], []).append(entry)
    for points in by_series.values():
        points.sort(key=lambda item: item["pressure_bytes"])
    return [by_series[key] for key in sorted(by_series)]


def control_levels(aggregated):
    """Median reload latency of the no-pressure control, per target size."""
    levels = {}
    for entry in aggregated:
        if entry["pressure_source"] == "none":
            levels[entry["target_bytes"]] = entry["after_median"]
    return levels


def draw_reference_lines(axes, llc_bytes, l1_bytes, l2_bytes):
    for value, text in ((l1_bytes, "L1D"), (l2_bytes, "L2"),
                        (llc_bytes, "LLC")):
        if not value:
            continue
        axes.axvline(value, color="0.5", linestyle=":", linewidth=1.2)
        axes.annotate(
            "inferred {}".format(text),
            xy=(value, 1.0), xycoords=("data", "axes fraction"),
            xytext=(3, -12), textcoords="offset points",
            rotation=90, va="top", ha="left", fontsize=BASE_FONT_SIZE - 3,
            color="0.35")


def plot_eviction_probability(path, aggregated, arguments, machine):
    points = curves(aggregated, {"helper", "self"})
    if not points:
        return False

    figure, axes = plt.subplots(figsize=(7.2, 4.6))
    for index, series in enumerate(points):
        axes.plot(
            [entry["pressure_bytes"] for entry in series],
            [entry["eviction_probability"] for entry in series],
            marker=MARKERS[index % len(MARKERS)],
            color=GRAYS[index % len(GRAYS)],
            linestyle="-", markerfacecolor=GRAYS[index % len(GRAYS)],
            label=series[0]["label"])

    draw_reference_lines(axes, arguments.llc_bytes, arguments.l1_bytes,
                         arguments.l2_bytes)
    axes.set_xscale("log", base=2)
    axes.set_ylim(-0.05, 1.05)
    axes.set_xlabel("Pressure footprint (bytes)")
    axes.set_ylabel("Probability target reload exceeds\nthe private-hit threshold")
    axes.set_title("{}: cross-level eviction of a private-resident line"
                   .format(machine))
    axes.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    figure.tight_layout()
    with PdfPages(path) as pdf:
        pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)
    return True


def plot_reload_latency(path, aggregated, arguments, machine, unit):
    points = curves(aggregated, {"helper", "self"})
    if not points:
        return False

    figure, axes = plt.subplots(figsize=(7.2, 4.6))
    for index, series in enumerate(points):
        axes.plot(
            [entry["pressure_bytes"] for entry in series],
            [entry["after_median"] for entry in series],
            marker=MARKERS[index % len(MARKERS)],
            color=GRAYS[index % len(GRAYS)],
            linestyle="-", markerfacecolor=GRAYS[index % len(GRAYS)],
            label="after pressure: {}".format(series[0]["label"]))

    for target_bytes, level in sorted(control_levels(aggregated).items()):
        axes.axhline(level, color="0.4", linestyle="--", linewidth=1.2)
        axes.annotate(
            "no-pressure control, {} target".format(byte_label(target_bytes)),
            xy=(0.02, level), xycoords=("axes fraction", "data"),
            xytext=(0, 4), textcoords="offset points",
            fontsize=BASE_FONT_SIZE - 3, color="0.35")

    draw_reference_lines(axes, arguments.llc_bytes, arguments.l1_bytes,
                         arguments.l2_bytes)
    axes.set_xscale("log", base=2)
    axes.set_xlabel("Pressure footprint (bytes)")
    axes.set_ylabel("Median target reload\n({} per timed interval)".format(unit))
    axes.set_title("{}: target reload latency after cross-level pressure"
                   .format(machine))
    axes.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    figure.tight_layout()
    with PdfPages(path) as pdf:
        pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)
    return True


def select_boxplot_points(aggregated, llc_bytes):
    """Pick footprints below, near and above the inferred LLC capacity."""
    helper = [entry for entry in aggregated
              if entry["pressure_source"] == "helper"]
    if not helper:
        helper = [entry for entry in aggregated
                  if entry["pressure_source"] == "self" and
                  entry["pressure_bytes"] > 0]
    if not helper:
        return []
    if not llc_bytes:
        helper.sort(key=lambda item: item["pressure_bytes"])
        step = max(len(helper) // 3, 1)
        return helper[::step][:3]

    below = [entry for entry in helper if entry["pressure_bytes"] < llc_bytes]
    above = [entry for entry in helper if entry["pressure_bytes"] > llc_bytes]
    near = min(helper, key=lambda item: abs(item["pressure_bytes"] - llc_bytes))
    chosen = []
    if below:
        chosen.append(max(below, key=lambda item: item["pressure_bytes"]))
    chosen.append(near)
    if above:
        chosen.append(min(above, key=lambda item: item["pressure_bytes"]))
        chosen.append(max(above, key=lambda item: item["pressure_bytes"]))
    seen = set()
    unique = []
    for entry in chosen:
        key = (entry["series_index"], entry["pressure_bytes"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def plot_boxplots(path, aggregated, arguments, machine, unit):
    chosen = select_boxplot_points(aggregated, arguments.llc_bytes)
    if not chosen:
        return False

    statistics_list = []
    positions = []
    labels = []
    for index, entry in enumerate(chosen):
        base = index * 3.0
        statistics_list.append({
            "label": "",
            "whislo": entry["baseline_p05"],
            "q1": entry["baseline_q1"],
            "med": entry["baseline_median"],
            "q3": entry["baseline_q3"],
            "whishi": entry["baseline_p95"],
            "fliers": [],
        })
        positions.append(base)
        statistics_list.append({
            "label": "",
            "whislo": entry["after_p05"],
            "q1": entry["after_q1"],
            "med": entry["after_median"],
            "q3": entry["after_q3"],
            "whishi": entry["after_p95"],
            "fliers": [],
        })
        positions.append(base + 1.0)
        labels.append((base + 0.5, byte_label(entry["pressure_bytes"])))

    figure, axes = plt.subplots(figsize=(7.6, 4.6))
    artists = axes.bxp(statistics_list, positions=positions, widths=0.8,
                       showfliers=False, patch_artist=True)
    for index, box in enumerate(artists["boxes"]):
        box.set_facecolor("white" if index % 2 == 0 else "0.75")
        box.set_edgecolor("black")
    for key in ("whiskers", "caps", "medians"):
        for artist in artists[key]:
            artist.set_color("black")

    axes.set_xticks([position for position, _ in labels])
    axes.set_xticklabels([text for _, text in labels])
    axes.set_xlabel("Pressure footprint (white: before pressure, "
                    "gray: after pressure)")
    axes.set_ylabel("Target reload\n({} per timed interval)".format(unit))
    axes.set_title("{}: reload distribution below, at and above the inferred "
                   "LLC".format(machine))
    figure.tight_layout()
    with PdfPages(path) as pdf:
        pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)
    return True


def write_provenance(path, input_path, output_paths, row_count, point_count):
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("ece592_plot_provenance_version=1\n")
        stream.write("plot_type=cross-level-inclusion-exclusion-evidence\n")
        stream.write("input_filename={}\n".format(os.path.abspath(input_path)))
        stream.write("input_sha256={}\n".format(sha256_file(input_path)))
        for output_path in output_paths:
            stream.write("output_filename={}\n".format(
                os.path.abspath(output_path)))
        stream.write("plotting_command={}\n".format(" ".join(
            shlex.quote(argument) for argument in sys.argv)))
        stream.write("plotting_working_directory={}\n".format(os.getcwd()))
        stream.write("python_version={}\n".format(platform.python_version()))
        stream.write("matplotlib_version={}\n".format(matplotlib.__version__))
        stream.write("processed_row_count={}\n".format(row_count))
        stream.write("aggregated_point_count={}\n".format(point_count))
        stream.write("cache_policy_labels_assigned=false\n")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Plot Phase-I inclusion/exclusion evidence.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--llc-bytes", type=int, default=0,
                        help="Phase-I inferred LLC capacity, drawn as a "
                             "reference line only.")
    parser.add_argument("--l1-bytes", type=int, default=0)
    parser.add_argument("--l2-bytes", type=int, default=0)
    arguments = parser.parse_args()
    if not os.path.isfile(arguments.input):
        parser.error("--input must name an existing file")
    parent = os.path.dirname(os.path.abspath(arguments.output_prefix))
    if not os.path.isdir(parent):
        parser.error("parent of --output-prefix must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    configure_style()
    try:
        _, rows = read_processed(arguments.input)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    units = {row["raw_timer_unit"] for row in rows}
    if len(units) != 1:
        print("error: mixed timer units in one processed file", file=sys.stderr)
        return 1
    unit = units.pop()

    aggregated = aggregate(rows)
    written = []

    targets = [
        (arguments.output_prefix + "_eviction_probability.pdf",
         lambda path: plot_eviction_probability(path, aggregated, arguments,
                                                arguments.machine)),
        (arguments.output_prefix + "_reload_latency.pdf",
         lambda path: plot_reload_latency(path, aggregated, arguments,
                                          arguments.machine, unit)),
        (arguments.output_prefix + "_reload_boxplots.pdf",
         lambda path: plot_boxplots(path, aggregated, arguments,
                                    arguments.machine, unit)),
    ]

    for path, draw in targets:
        if os.path.exists(path):
            print("error: output already exists: {}".format(path),
                  file=sys.stderr)
            return 1
        if draw(path):
            written.append(path)

    if not written:
        print("error: no plottable series found", file=sys.stderr)
        return 1

    provenance = arguments.output_prefix + "_plots.provenance.tsv"
    write_provenance(provenance, arguments.input, written, len(rows),
                     len(aggregated))

    for path in written:
        print("output_filename={}".format(path))
    print("provenance_filename={}".format(provenance))
    print("processed_row_count={}".format(len(rows)))
    print("aggregated_point_count={}".format(len(aggregated)))
    print("cache_policy_labels_assigned=false")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
