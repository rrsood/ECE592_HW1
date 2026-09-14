#!/usr/bin/env python3
"""Generate a reproducible Phase-I inclusion/exclusion (Section 8.2.7) plan.

The plan is a randomized execution order over every measured point.  It is
generated but never executed here, so the exact set of points, their seeds and
their order are all committed to Git before any data exists.

A "point" is one combination of

    target footprint      how much private-resident data is probed
    pressure source       none | self | helper
    pressure footprint    swept across the inferred LLC capacity
    helper CPU            which logical CPU generates the shared-cache pressure
    pressure order        sequential | randomized traversal of the pressure set

Three families of rows are emitted:

  none    no pressure at all.  Negative control: shows the round structure by
          itself leaves the targets private-resident.

  self    the measuring thread walks the pressure set.  Positive control: it
          must slow the reload down, which proves the probe can see eviction.
          Swept across L1/L2/LLC it also yields the "which level answered the
          reload" ladder.

  helper  a thread on another physical core in the same package walks the
          pressure set.  This is the only condition that can separate the
          hypotheses, because it loads the shared LLC without ever touching
          the measuring core's private L1D/L2.

Inputs are the team's own Phase-I timing-only inferences (line size, L1D, L2
and LLC capacity).  Nothing here reads a cache specification.
"""

import argparse
import math
import os
import sys


MASK64 = (1 << 64) - 1
SPLITMIX_INCREMENT = 0x9E3779B97F4A7C15

PLAN_COLUMNS = [
    "global_execution_index",
    "trial",
    "trial_execution_index",
    "series_index",
    "plot_index",
    "target_bytes",
    "target_line_spacing_bytes",
    "pressure_source",
    "pressure_bytes",
    "pressure_line_spacing_bytes",
    "pressure_order",
    "pressure_passes",
    "helper_cpu",
    "accesses_per_sample",
    "point_seed",
]

# Rough cost of one dependent pressure access on a warm modern x86 core when
# the pressure set is larger than the LLC.  Only used for the wall-clock
# estimate printed to the operator; it never affects the emitted plan.
ESTIMATED_NANOSECONDS_PER_PRESSURE_ACCESS = 2.5
ESTIMATED_NANOSECONDS_PER_TIMED_SAMPLE = 120.0


class SplitMix64:
    """Same generator the rest of the suite uses, so seeds are comparable."""

    def __init__(self, seed):
        self.state = seed & MASK64

    def next(self):
        self.state = (self.state + SPLITMIX_INCREMENT) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
        return (value ^ (value >> 31)) & MASK64

    def below(self, bound):
        if bound <= 0 or bound > (1 << 64):
            raise ValueError("random bound is outside the supported range")
        threshold = ((1 << 64) - bound) % bound
        while True:
            value = self.next()
            if value >= threshold:
                return value % bound


def positive_integer(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def nonnegative_integer(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    if value < 0:
        raise argparse.ArgumentTypeError("value must be nonnegative")
    return value


def unsigned_64(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    if value < 0 or value > MASK64:
        raise argparse.ArgumentTypeError(
            "value must fit in an unsigned 64-bit integer")
    return value


def parse_integer_list(text):
    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise argparse.ArgumentTypeError("empty value in list")
        values.append(positive_integer(part))
    if not values:
        raise argparse.ArgumentTypeError("list must not be empty")
    return values


def parse_cpu_list(text):
    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise argparse.ArgumentTypeError("empty value in list")
        values.append(nonnegative_integer(part))
    if not values:
        raise argparse.ArgumentTypeError("list must not be empty")
    return values


def parse_float_list(text):
    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise argparse.ArgumentTypeError("empty value in list")
        try:
            value = float(part)
        except ValueError as error:
            raise argparse.ArgumentTypeError(str(error))
        if value <= 0.0:
            raise argparse.ArgumentTypeError("multiplier must be positive")
        values.append(value)
    if not values:
        raise argparse.ArgumentTypeError("list must not be empty")
    return values


def shuffle_in_place(values, generator):
    for remaining in range(len(values), 1, -1):
        selected = generator.below(remaining)
        values[remaining - 1], values[selected] = (
            values[selected], values[remaining - 1])


def round_to_multiple(value, multiple):
    """Round down, but never below one multiple."""
    rounded = (int(value) // multiple) * multiple
    return max(rounded, multiple)


def build_points(arguments):
    """Return the deduplicated list of measured points, before randomization."""
    line = arguments.line_bytes
    group = arguments.accesses_per_sample

    # One probe lap must split evenly into timed groups, so the target
    # footprint is rounded down to a whole number of groups of lines.
    target_bytes_list = []
    for requested in arguments.target_bytes:
        rounded = round_to_multiple(requested, line * group)
        if rounded // line < 2:
            raise ValueError(
                "target footprint {} is too small for line {} and "
                "--accesses-per-sample {}".format(requested, line, group))
        target_bytes_list.append(rounded)
    target_bytes_list = sorted(set(target_bytes_list))

    helper_pressure = sorted({
        round_to_multiple(multiplier * arguments.llc_bytes, line)
        for multiplier in arguments.helper_multipliers})
    self_pressure = sorted({
        round_to_multiple(value, line)
        for value in arguments.self_pressure_bytes})

    points = []
    for target_bytes in target_bytes_list:
        # Negative control: no pressure at all.
        points.append({
            "target_bytes": target_bytes,
            "pressure_source": "none",
            "pressure_bytes": 0,
            "pressure_order": "sequential",
            "pressure_passes": 0,
            "helper_cpu": -1,
        })
        # Positive control / private-eviction ladder.
        for pressure_bytes in self_pressure:
            points.append({
                "target_bytes": target_bytes,
                "pressure_source": "self",
                "pressure_bytes": pressure_bytes,
                "pressure_order": arguments.pressure_order,
                "pressure_passes": arguments.pressure_passes,
                "helper_cpu": -1,
            })
        # Discriminating condition.
        for helper_cpu in arguments.helper_cpus:
            for pressure_bytes in helper_pressure:
                points.append({
                    "target_bytes": target_bytes,
                    "pressure_source": "helper",
                    "pressure_bytes": pressure_bytes,
                    "pressure_order": arguments.pressure_order,
                    "pressure_passes": arguments.pressure_passes,
                    "helper_cpu": helper_cpu,
                })

    # A series is one curve on the evidence plot; a plot index is one point.
    series_keys = []
    for point in points:
        key = (point["target_bytes"], point["pressure_source"],
               point["helper_cpu"], point["pressure_order"])
        if key not in series_keys:
            series_keys.append(key)
    for index, point in enumerate(points):
        key = (point["target_bytes"], point["pressure_source"],
               point["helper_cpu"], point["pressure_order"])
        point["series_index"] = series_keys.index(key)
        point["plot_index"] = index

    return points


def estimate_seconds(arguments, point):
    """Wall-clock estimate for one measured point, for operator planning."""
    line = arguments.line_bytes
    target_nodes = point["target_bytes"] // line
    samples_per_round = target_nodes // arguments.accesses_per_sample
    rounds = math.ceil(arguments.samples / samples_per_round)
    pressure_nodes = point["pressure_bytes"] // line
    pressure_accesses = (rounds * pressure_nodes *
                         max(point["pressure_passes"], 0))
    timed = rounds * samples_per_round
    return (pressure_accesses * ESTIMATED_NANOSECONDS_PER_PRESSURE_ACCESS +
            timed * ESTIMATED_NANOSECONDS_PER_TIMED_SAMPLE) / 1e9


def build_rows(arguments, points):
    generator = SplitMix64(arguments.seed)
    rows = []
    global_execution_index = 0

    for trial in range(arguments.trials):
        trial_rows = []
        for point in points:
            trial_rows.append([
                trial,
                0,
                point["series_index"],
                point["plot_index"],
                point["target_bytes"],
                arguments.line_bytes,
                point["pressure_source"],
                point["pressure_bytes"],
                arguments.line_bytes,
                point["pressure_order"],
                point["pressure_passes"],
                point["helper_cpu"],
                arguments.accesses_per_sample,
                generator.next(),
            ])
        # Randomizing the execution order inside each trial keeps slow drift
        # (temperature, other users, DVFS) from aliasing onto the swept axis.
        shuffle_in_place(trial_rows, generator)
        for trial_execution_index, row in enumerate(trial_rows):
            row[1] = trial_execution_index
            rows.append([global_execution_index] + row)
            global_execution_index += 1

    return rows


def write_plan(arguments, points, rows, total_seconds):
    created = False
    try:
        with open(arguments.output, "x", encoding="ascii",
                  newline="\n") as stream:
            created = True
            stream.write("ece592_inclusion_policy_plan_version=1\n")
            stream.write("generator=SplitMix64+Fisher-Yates\n")
            stream.write("measurement_goal=8.2.7_inclusion_exclusion_behavior\n")
            stream.write(
                "sweep=pressure footprint by pressure source by target "
                "footprint\n")
            stream.write("inferred_line_bytes={}\n".format(
                arguments.line_bytes))
            stream.write("inferred_l1d_bytes={}\n".format(arguments.l1_bytes))
            stream.write("inferred_l2_bytes={}\n".format(arguments.l2_bytes))
            stream.write("inferred_llc_bytes={}\n".format(arguments.llc_bytes))
            stream.write("inferred_values_are_phase1_timing_only=true\n")
            stream.write("target_bytes_list={}\n".format(",".join(
                str(value) for value in
                sorted({point["target_bytes"] for point in points}))))
            stream.write("helper_cpu_list={}\n".format(",".join(
                str(value) for value in arguments.helper_cpus)))
            stream.write("helper_pressure_multipliers={}\n".format(",".join(
                repr(value) for value in arguments.helper_multipliers)))
            stream.write("accesses_per_sample={}\n".format(
                arguments.accesses_per_sample))
            stream.write("pressure_passes={}\n".format(
                arguments.pressure_passes))
            stream.write("pressure_order={}\n".format(arguments.pressure_order))
            stream.write("requested_samples_per_point={}\n".format(
                arguments.samples))
            stream.write("unique_point_count={}\n".format(len(points)))
            stream.write("series_count={}\n".format(
                len({point["series_index"] for point in points})))
            stream.write("trial_count={}\n".format(arguments.trials))
            stream.write("plan_seed={}\n".format(arguments.seed))
            stream.write("plan_row_count={}\n".format(len(rows)))
            stream.write("estimated_wall_clock_seconds={:.0f}\n".format(
                total_seconds))
            stream.write("data_begin\n")
            stream.write("\t".join(PLAN_COLUMNS) + "\n")
            for row in rows:
                stream.write("\t".join(str(value) for value in row) + "\n")
            stream.write("data_end\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            try:
                os.unlink(arguments.output)
            except OSError:
                pass
        raise


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=("Generate, but do not execute, a reproducible randomized "
                     "inclusion/exclusion plan."))
    parser.add_argument("--line-bytes", required=True, type=positive_integer,
                        help="Phase-I inferred cache line size.")
    parser.add_argument("--l1-bytes", required=True, type=positive_integer,
                        help="Phase-I inferred L1D capacity.")
    parser.add_argument("--l2-bytes", required=True, type=positive_integer,
                        help="Phase-I inferred L2 capacity.")
    parser.add_argument("--llc-bytes", required=True, type=positive_integer,
                        help="Phase-I inferred LLC capacity visible to the "
                             "pinned core.")
    parser.add_argument("--helper-cpus", required=True, type=parse_cpu_list,
                        help="Logical CPUs that may generate shared-cache "
                             "pressure. Each must be a different physical "
                             "core in the same package as the measuring CPU.")
    parser.add_argument("--target-bytes", type=parse_integer_list,
                        help="Probe footprints. Default: L1D/4 and L2/4.")
    parser.add_argument("--helper-multipliers", type=parse_float_list,
                        default=[0.125, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 4.0],
                        help="Helper pressure footprints as multiples of the "
                             "inferred LLC capacity.")
    parser.add_argument("--self-pressure-bytes", type=parse_integer_list,
                        help="Self-pressure footprints. Default: 2xL1, 2xL2, "
                             "LLC/2, 2xLLC.")
    parser.add_argument("--accesses-per-sample", type=positive_integer,
                        default=1,
                        help="Dependent loads per timed interval. Use 1 on "
                             "x86; use a large value on AArch64 because the "
                             "generic timer ticks far more slowly than a "
                             "single load.")
    parser.add_argument("--pressure-passes", type=positive_integer, default=1)
    parser.add_argument("--pressure-order", default="sequential",
                        choices=("sequential", "randomized"))
    parser.add_argument("--samples", type=positive_integer, default=1000000)
    parser.add_argument("--trials", required=True, type=positive_integer)
    parser.add_argument("--seed", required=True, type=unsigned_64)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if arguments.samples < 1000000:
        parser.error("--samples must be at least 1000000")
    if arguments.line_bytes < 8 or arguments.line_bytes % 8 != 0:
        parser.error("--line-bytes must be a multiple of 8 and at least 8")
    if arguments.target_bytes is None:
        arguments.target_bytes = [max(arguments.l1_bytes // 4,
                                      arguments.line_bytes * 2),
                                  max(arguments.l2_bytes // 4,
                                      arguments.line_bytes * 2)]
    if arguments.self_pressure_bytes is None:
        arguments.self_pressure_bytes = [
            2 * arguments.l1_bytes,
            2 * arguments.l2_bytes,
            max(arguments.llc_bytes // 2, arguments.line_bytes * 2),
            2 * arguments.llc_bytes,
        ]
    if len(set(arguments.helper_cpus)) != len(arguments.helper_cpus):
        parser.error("--helper-cpus must not repeat a CPU")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        points = build_points(arguments)
    except ValueError as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    rows = build_rows(arguments, points)
    per_point = {point["plot_index"]: estimate_seconds(arguments, point)
                 for point in points}
    total_seconds = sum(per_point.values()) * arguments.trials

    try:
        write_plan(arguments, points, rows, total_seconds)
    except FileExistsError:
        print("error: output file already exists: {}".format(arguments.output),
              file=sys.stderr)
        return 1
    except OSError as error:
        print("error: could not write plan: {}".format(error), file=sys.stderr)
        return 1

    slowest = max(per_point.values())
    print("output_filename={}".format(arguments.output))
    print("unique_point_count={}".format(len(points)))
    print("series_count={}".format(
        len({point["series_index"] for point in points})))
    print("plan_row_count={}".format(len(rows)))
    print("estimated_wall_clock_seconds={:.0f}".format(total_seconds))
    print("estimated_wall_clock_minutes={:.1f}".format(total_seconds / 60.0))
    print("estimated_slowest_point_seconds={:.0f}".format(slowest))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
