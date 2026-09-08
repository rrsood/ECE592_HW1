#!/usr/bin/env python3
"""Generate a reproducible Phase-I cross-level eviction plan."""

import argparse
import os
import sys


MASK64 = (1 << 64) - 1
SPLITMIX_INCREMENT = 0x9E3779B97F4A7C15


class SplitMix64:
    def __init__(self, seed):
        self.state = seed & MASK64

    def next(self):
        self.state = (self.state + SPLITMIX_INCREMENT) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
        return (value ^ (value >> 31)) & MASK64

    def below(self, bound):
        threshold = ((1 << 64) - bound) % bound
        while True:
            value = self.next()
            if value >= threshold:
                return value % bound


def unsigned_64(text):
    value = int(text, 0)
    if value < 0 or value > MASK64:
        raise argparse.ArgumentTypeError(
            "value must fit in an unsigned 64-bit integer")
    return value


def positive_integer(text):
    value = int(text, 0)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def parse_offset_set(text):
    values = []
    seen = set()
    for part in text.split(","):
        if part == "":
            raise argparse.ArgumentTypeError("empty offset in set")
        value = int(part, 0)
        if value < 0 or value % 8 != 0:
            raise argparse.ArgumentTypeError(
                "offsets must be nonnegative multiples of 8")
        if value in seen:
            raise argparse.ArgumentTypeError("duplicate offset: {}".format(value))
        seen.add(value)
        values.append(value)
    if len(values) < 2:
        raise argparse.ArgumentTypeError("each offset set needs at least 2 values")
    return values


def parse_offset_sets(text):
    sets = []
    for item in text.split(";"):
        if item == "":
            raise argparse.ArgumentTypeError("empty offset set")
        sets.append(parse_offset_set(item))
    return sets


def offsets_text(values):
    return ",".join(str(value) for value in values)


def shuffle_in_place(values, generator):
    for remaining in range(len(values), 1, -1):
        selected = generator.below(remaining)
        values[remaining - 1], values[selected] = (
            values[selected], values[remaining - 1])


def build_rows(arguments):
    generator = SplitMix64(arguments.seed)
    plot_indices = {}
    plot_index = 0
    for target_index, target_offsets in enumerate(arguments.target_offset_sets):
        for pressure_index, pressure_offsets in enumerate(arguments.pressure_offset_sets):
            if set(target_offsets).intersection(pressure_offsets):
                raise ValueError("target and pressure offsets overlap")
            plot_indices[(target_index, pressure_index)] = plot_index
            plot_index += 1

    rows = []
    global_index = 0
    for trial in range(arguments.trials):
        trial_rows = []
        for target_index, target_offsets in enumerate(arguments.target_offset_sets):
            for pressure_index, pressure_offsets in enumerate(arguments.pressure_offset_sets):
                trial_rows.append([
                    trial,
                    0,
                    plot_indices[(target_index, pressure_index)],
                    target_index,
                    pressure_index,
                    offsets_text(target_offsets),
                    offsets_text(pressure_offsets),
                    len(target_offsets),
                    len(pressure_offsets),
                    generator.next(),
                ])
        shuffle_in_place(trial_rows, generator)
        for trial_execution_index, row in enumerate(trial_rows):
            row[1] = trial_execution_index
            rows.append([global_index] + row)
            global_index += 1
    return rows


def write_plan(arguments, rows):
    with open(arguments.output, "x", encoding="ascii", newline="\n") as stream:
        stream.write("ece592_eviction_plan_version=1\n")
        stream.write("generator=SplitMix64+Fisher-Yates\n")
        stream.write("measurement_goal=8.2.7_cross_level_eviction_behavior\n")
        stream.write("target_offset_sets={}\n".format(
            ";".join(offsets_text(values)
                     for values in arguments.target_offset_sets)))
        stream.write("pressure_offset_sets={}\n".format(
            ";".join(offsets_text(values)
                     for values in arguments.pressure_offset_sets)))
        stream.write("target_offset_set_count={}\n".format(
            len(arguments.target_offset_sets)))
        stream.write("pressure_offset_set_count={}\n".format(
            len(arguments.pressure_offset_sets)))
        stream.write("trial_count={}\n".format(arguments.trials))
        stream.write("plan_seed={}\n".format(arguments.seed))
        stream.write("plan_row_count={}\n".format(len(rows)))
        stream.write("data_begin\n")
        stream.write(
            "global_execution_index\ttrial\ttrial_execution_index\t"
            "plot_index\ttarget_set_index\tpressure_set_index\t"
            "target_offsets_bytes\tpressure_offsets_bytes\t"
            "target_offset_count\tpressure_offset_count\tpoint_seed\n")
        for row in rows:
            stream.write("\t".join(str(value) for value in row) + "\n")
        stream.write("data_end\n")
        stream.flush()
        os.fsync(stream.fileno())


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Generate a randomized Phase-I eviction/reload plan.")
    parser.add_argument("--target-offset-sets", required=True,
                        type=parse_offset_sets)
    parser.add_argument("--pressure-offset-sets", required=True,
                        type=parse_offset_sets)
    parser.add_argument("--trials", required=True, type=positive_integer)
    parser.add_argument("--seed", required=True, type=unsigned_64)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    try:
        rows = build_rows(arguments)
        write_plan(arguments, rows)
    except FileExistsError:
        print("error: output file already exists: {}".format(arguments.output),
              file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    print("output_filename={}".format(arguments.output))
    print("plan_row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
