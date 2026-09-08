#!/usr/bin/env python3
"""Build a compact Phase-I evidence summary across machines."""

from __future__ import annotations

import argparse
import csv
import glob
import os
import statistics
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def latest_one(pattern: str) -> Path:
    matches = sorted(glob.glob(pattern))
    if not matches:
        fail(f"no file matches {pattern}")
    return Path(matches[-1])


def read_data_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_data = False
    header: list[str] | None = None

    with path.open(encoding="ascii", newline="") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line == "data_begin":
                in_data = True
                header = None
                continue
            if line == "data_end":
                break
            if not in_data:
                continue
            if header is None:
                header = line.split("\t")
                continue
            values = line.split("\t")
            rows.append(dict(zip(header, values)))

    if not rows:
        fail(f"no data rows found in {path}")
    return rows


def median(values: list[float]) -> float:
    return statistics.median(values)


def fmt_float(value: float) -> str:
    return f"{value:.6g}"


def capacity_summary(machine: str) -> tuple[str, str, str]:
    path = latest_one(f"data_processed/{machine}/capacity/phase1_capacity_evidence_summary*.tsv")
    rows = read_data_rows(path)
    intervals = [row["dense_refined_interval_bytes"] for row in rows[:4]]
    supports = [row["dense_support_status"] for row in rows[:4]]
    return path.as_posix(), ";".join(intervals), ";".join(supports)


def line_size_summary(machine: str) -> tuple[str, str, str]:
    path = latest_one(f"data_processed/{machine}/line_size/phase1_line_size_spatial_randomized*.tsv")
    rows = read_data_rows(path)
    by_offset: dict[int, list[float]] = {}
    for row in rows:
        offset = int(row["probe_offset_bytes"])
        value = float(row["elapsed_raw_ticks_per_access_unadjusted_median"])
        by_offset.setdefault(offset, []).append(value)

    medians = [(offset, median(values)) for offset, values in sorted(by_offset.items())]
    if len(medians) < 2:
        fail(f"not enough spatial offsets in {path}")

    best = None
    for (prev_offset, prev_value), (offset, value) in zip(medians, medians[1:]):
        delta = value - prev_value
        if best is None or delta > best[2]:
            best = (prev_offset, offset, delta)
    assert best is not None
    return path.as_posix(), f"{best[0]}..{best[1]}", fmt_float(best[2])


def associativity_summary(machine: str) -> tuple[str, str]:
    path = latest_one(
        f"data_processed/{machine}/associativity/phase1_associativity_conflict_coarse_randomized*.tsv"
    )
    rows = read_data_rows(path)
    by_key: dict[tuple[int, int], list[float]] = {}
    for row in rows:
        stride = int(row["conflict_stride_bytes"])
        line_count = int(row["conflict_line_count"])
        value = float(row["elapsed_raw_ticks_per_access_unadjusted_median"])
        by_key.setdefault((stride, line_count), []).append(value)

    by_stride: dict[int, list[tuple[int, float]]] = {}
    for (stride, line_count), values in by_key.items():
        by_stride.setdefault(stride, []).append((line_count, median(values)))

    jumps: list[tuple[float, int, int, int]] = []
    for stride, points in by_stride.items():
        ordered = sorted(points)
        for (prev_count, prev_value), (count, value) in zip(ordered, ordered[1:]):
            if prev_value > 0:
                jumps.append(((value - prev_value) / prev_value, stride, prev_count, count))

    jumps.sort(reverse=True)
    evidence = [f"stride{stride}:{lo}->{hi}" for _, stride, lo, hi in jumps[:5]]
    return path.as_posix(), ";".join(evidence)


def latency_summary(machine: str) -> tuple[str, str, str]:
    path = latest_one(f"data_processed/{machine}/latency/phase1_hit_latency_representatives*.tsv")
    rows = read_data_rows(path)
    values = [float(row["elapsed_raw_ticks_per_access_unadjusted_median"]) for row in rows]
    return path.as_posix(), str(len(values)), f"{fmt_float(min(values))}..{fmt_float(max(values))}"


def miss_summary(machine: str) -> tuple[str, str, str]:
    path = latest_one(f"data_processed/{machine}/latency/phase1_miss_next_level_latency_evidence*.tsv")
    rows = read_data_rows(path)
    deltas = [float(row["above_minus_below_median_ticks_per_access"]) for row in rows]
    ratios = [float(row["above_divided_by_below_median_ratio"]) for row in rows]
    return path.as_posix(), fmt_float(max(deltas)), fmt_float(max(ratios))


def eviction_summary(machine: str) -> tuple[str, str, str]:
    path = latest_one(f"data_processed/{machine}/eviction/phase1_eviction_cross_level_randomized*.tsv")
    rows = read_data_rows(path)
    deltas = [float(row["delta_median_ticks_per_target"]) for row in rows]
    ratios = [float(row["ratio_after_to_baseline"]) for row in rows]
    return path.as_posix(), fmt_float(median(deltas)), fmt_float(median(ratios))


def build_summary(machines: list[str]) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []
    for machine in machines:
        capacity_file, capacity_intervals, capacity_support = capacity_summary(machine)
        line_file, line_jump_offset, line_jump_delta = line_size_summary(machine)
        assoc_file, assoc_evidence = associativity_summary(machine)
        latency_file, latency_count, latency_range = latency_summary(machine)
        miss_file, miss_max_delta, miss_max_ratio = miss_summary(machine)
        eviction_file, eviction_median_delta, eviction_median_ratio = eviction_summary(machine)

        output_rows.append(
            {
                "machine": machine,
                "capacity_evidence_file": capacity_file,
                "top_capacity_refined_intervals_bytes": capacity_intervals,
                "capacity_support_statuses": capacity_support,
                "line_size_evidence_file": line_file,
                "largest_spatial_jump_offset_window_bytes": line_jump_offset,
                "largest_spatial_jump_ticks_per_access": line_jump_delta,
                "associativity_evidence_file": assoc_file,
                "largest_conflict_jump_windows": assoc_evidence,
                "latency_representatives_file": latency_file,
                "latency_representative_count": latency_count,
                "latency_representative_median_range_ticks_per_access": latency_range,
                "miss_latency_evidence_file": miss_file,
                "max_next_level_delta_ticks_per_access": miss_max_delta,
                "max_next_level_ratio": miss_max_ratio,
                "eviction_evidence_file": eviction_file,
                "median_eviction_delta_ticks_per_target": eviction_median_delta,
                "median_eviction_ratio": eviction_median_ratio,
                "cache_labels_assigned": "false",
                "phase1_spec_compliance_note": "randomized dependent pointer chasing; 1000000 samples per point; no cache specs used",
            }
        )
    return output_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machines", required=True, help="comma-separated machine names")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        fail(f"output file already exists: {output}")
    if output.parent:
        output.parent.mkdir(parents=True, exist_ok=True)

    machines = [machine.strip() for machine in args.machines.split(",") if machine.strip()]
    rows = build_summary(machines)

    fields = list(rows[0].keys())
    with output.open("w", encoding="ascii", newline="") as handle:
        print("ece592_phase1_machine_summary_version=1", file=handle)
        print("summary_purpose=report_table_for_phase1_freeze", file=handle)
        print("cache_specifications_used=false", file=handle)
        print("cache_labels_assigned=false", file=handle)
        print(f"summary_script={os.path.abspath(__file__)}", file=handle)
        print("data_begin", file=handle)
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        print("data_end", file=handle)

    print(f"output_filename={output}")
    print(f"machine_count={len(rows)}")
    print("cache_labels_assigned=false")
    print("cache_specifications_used=false")
    print("status=ok")


if __name__ == "__main__":
    main()
