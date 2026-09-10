#!/usr/bin/env python3
"""Timing-only cache-residency estimator.

The estimator reads raw ECE 592 timing TSV files.  It calibrates one
hit-like distribution and one miss-like distribution, chooses a threshold from
the calibration data, then classifies target timing samples without PMU input.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
from pathlib import Path


RAW_ELAPSED_FIELD = "elapsed_raw_ticks"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        fail("cannot compute percentile of an empty list")
    if probability <= 0.0:
        return sorted_values[0]
    if probability >= 1.0:
        return sorted_values[-1]

    position = (len(sorted_values) - 1) * probability
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    fraction = position - lower_index
    return lower + (upper - lower) * fraction


def read_raw_per_access_ticks(path: Path) -> tuple[dict[str, str], list[float]]:
    metadata: dict[str, str] = {}
    values: list[float] = []
    in_data = False
    header: list[str] | None = None
    elapsed_index = -1

    with path.open(encoding="ascii", newline="") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line == "data_begin":
                in_data = True
                continue
            if line == "data_end":
                break

            if not in_data:
                if "=" in line:
                    key, value = line.split("=", 1)
                    metadata[key] = value
                continue

            if header is None:
                header = line.split("\t")
                if RAW_ELAPSED_FIELD not in header:
                    fail(f"{path} is missing {RAW_ELAPSED_FIELD}")
                elapsed_index = header.index(RAW_ELAPSED_FIELD)
                continue

            fields = line.split("\t")
            if len(fields) <= elapsed_index:
                fail(f"malformed data row in {path}")
            elapsed_ticks = float(fields[elapsed_index])
            batch = float(metadata.get("dependent_accesses_per_sample", "0"))
            if batch <= 0.0:
                fail(f"{path} is missing a valid dependent_accesses_per_sample")
            values.append(elapsed_ticks / batch)

    if not values:
        fail(f"{path} contains no raw timing samples")
    return metadata, values


def describe(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "count": float(len(values)),
        "minimum": ordered[0],
        "p05": percentile(ordered, 0.05),
        "q1": percentile(ordered, 0.25),
        "median": percentile(ordered, 0.50),
        "q3": percentile(ordered, 0.75),
        "p95": percentile(ordered, 0.95),
        "maximum": ordered[-1],
        "mean": statistics.fmean(values),
    }


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        fail("cannot compute confidence interval for zero samples")
    z = 1.959963984540054
    phat = successes / total
    denominator = 1.0 + z * z / total
    center = phat + z * z / (2.0 * total)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * total)) / total)
    return (center - margin) / denominator, (center + margin) / denominator


def choose_threshold(hit_stats: dict[str, float],
                     miss_stats: dict[str, float]) -> tuple[float, str]:
    if hit_stats["median"] >= miss_stats["median"]:
        fail("hit calibration median is not below miss calibration median")

    if hit_stats["p95"] < miss_stats["p05"]:
        return (
            (hit_stats["p95"] + miss_stats["p05"]) / 2.0,
            "midpoint_between_hit_p95_and_miss_p05",
        )

    return (
        (hit_stats["median"] + miss_stats["median"]) / 2.0,
        "midpoint_between_overlapping_calibration_medians",
    )


def fraction_leq(values: list[float], threshold: float) -> float:
    return sum(1 for value in values if value <= threshold) / len(values)


def write_output(args: argparse.Namespace,
                 hit_metadata: dict[str, str],
                 miss_metadata: dict[str, str],
                 target_metadata: dict[str, str],
                 hit_stats: dict[str, float],
                 miss_stats: dict[str, float],
                 target_stats: dict[str, float],
                 threshold: float,
                 threshold_rule: str,
                 hit_like_count: int,
                 target_count: int,
                 interval: tuple[float, float],
                 hit_calibration_hit_rate: float,
                 miss_calibration_false_hit_rate: float) -> None:
    output = Path(args.output)
    if output.exists():
        fail(f"output file already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    estimate = hit_like_count / target_count
    balanced_calibration_accuracy = (
        hit_calibration_hit_rate + (1.0 - miss_calibration_false_hit_rate)
    ) / 2.0

    with output.open("w", encoding="ascii") as handle:
        print("ece592_software_hit_rate_estimate_version=1", file=handle)
        print("metric=timing_derived_cache_hit_rate", file=handle)
        print("pmu_counters_used=false", file=handle)
        print(f"estimator_script={os.path.abspath(__file__)}", file=handle)
        print(f"hit_calibration_file={args.hit_calibration}", file=handle)
        print(f"miss_calibration_file={args.miss_calibration}", file=handle)
        print(f"target_file={args.target}", file=handle)
        print(f"timer_unit={target_metadata.get('timer_unit', 'unknown')}", file=handle)
        print(
            "dependent_accesses_per_sample={}".format(
                target_metadata.get("dependent_accesses_per_sample", "unknown")
            ),
            file=handle,
        )
        print(f"threshold_rule={threshold_rule}", file=handle)
        print(f"threshold_ticks_per_access={threshold:.17g}", file=handle)
        print("classification_rule=sample_is_hit_like_if_ticks_per_access_le_threshold", file=handle)
        print(f"hit_calibration_median_ticks_per_access={hit_stats['median']:.17g}", file=handle)
        print(f"miss_calibration_median_ticks_per_access={miss_stats['median']:.17g}", file=handle)
        print(f"target_median_ticks_per_access={target_stats['median']:.17g}", file=handle)
        print(f"hit_calibration_hit_like_fraction={hit_calibration_hit_rate:.17g}", file=handle)
        print(f"miss_calibration_false_hit_like_fraction={miss_calibration_false_hit_rate:.17g}", file=handle)
        print(f"balanced_calibration_accuracy={balanced_calibration_accuracy:.17g}", file=handle)
        print("data_begin", file=handle)
        print(
            "\t".join(
                [
                    "target_sample_count",
                    "hit_like_sample_count",
                    "estimated_hit_rate",
                    "wilson_95_low",
                    "wilson_95_high",
                    "target_minimum_ticks_per_access",
                    "target_p05_ticks_per_access",
                    "target_q1_ticks_per_access",
                    "target_median_ticks_per_access",
                    "target_q3_ticks_per_access",
                    "target_p95_ticks_per_access",
                    "target_maximum_ticks_per_access",
                ]
            ),
            file=handle,
        )
        print(
            "\t".join(
                [
                    str(target_count),
                    str(hit_like_count),
                    f"{estimate:.17g}",
                    f"{interval[0]:.17g}",
                    f"{interval[1]:.17g}",
                    f"{target_stats['minimum']:.17g}",
                    f"{target_stats['p05']:.17g}",
                    f"{target_stats['q1']:.17g}",
                    f"{target_stats['median']:.17g}",
                    f"{target_stats['q3']:.17g}",
                    f"{target_stats['p95']:.17g}",
                    f"{target_stats['maximum']:.17g}",
                ]
            ),
            file=handle,
        )
        print("data_end", file=handle)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate a cache hit-like fraction from timing only."
    )
    parser.add_argument("--hit-calibration", required=True)
    parser.add_argument("--miss-calibration", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    hit_metadata, hit_values = read_raw_per_access_ticks(Path(args.hit_calibration))
    miss_metadata, miss_values = read_raw_per_access_ticks(Path(args.miss_calibration))
    target_metadata, target_values = read_raw_per_access_ticks(Path(args.target))

    hit_stats = describe(hit_values)
    miss_stats = describe(miss_values)
    target_stats = describe(target_values)
    threshold, threshold_rule = choose_threshold(hit_stats, miss_stats)

    hit_like_count = sum(1 for value in target_values if value <= threshold)
    interval = wilson_interval(hit_like_count, len(target_values))

    hit_calibration_hit_rate = fraction_leq(hit_values, threshold)
    miss_calibration_false_hit_rate = fraction_leq(miss_values, threshold)

    write_output(
        args,
        hit_metadata,
        miss_metadata,
        target_metadata,
        hit_stats,
        miss_stats,
        target_stats,
        threshold,
        threshold_rule,
        hit_like_count,
        len(target_values),
        interval,
        hit_calibration_hit_rate,
        miss_calibration_false_hit_rate,
    )

    print(f"output_filename={args.output}")
    print(f"target_sample_count={len(target_values)}")
    print(f"hit_like_sample_count={hit_like_count}")
    print(f"estimated_hit_rate={hit_like_count / len(target_values):.17g}")
    print("pmu_counters_used=false")
    print("status=ok")


if __name__ == "__main__":
    main()
