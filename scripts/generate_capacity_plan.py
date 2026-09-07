#!/usr/bin/env python3
"""Generate a reproducible, randomized Phase-I working-set sweep plan."""

import argparse
import os
import sys


MASK64 = (1 << 64) - 1
SPLITMIX_INCREMENT = 0x9E3779B97F4A7C15


class SplitMix64:
    """The same explicitly specified 64-bit generator used by the C code."""

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


def unsigned_64(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    if value < 0 or value > MASK64:
        raise argparse.ArgumentTypeError("value must fit in an unsigned 64-bit integer")
    return value


def generate_requested_sizes(minimum, maximum, points_per_octave):
    """Use exact integer subdivisions within successive factor-of-two ranges."""
    sizes = set()
    octave_base = minimum

    while octave_base <= maximum:
        for subdivision in range(points_per_octave):
            requested = (octave_base *
                         (points_per_octave + subdivision) //
                         points_per_octave)
            if minimum <= requested <= maximum:
                sizes.add(requested)

        if octave_base > maximum // 2:
            break
        octave_base *= 2

    sizes.add(maximum)
    return sorted(sizes)


def geometry_for_span(requested_bytes, spacing_bytes, node_bytes):
    if requested_bytes <= node_bytes:
        node_count = 2
    else:
        remaining = requested_bytes - node_bytes
        node_count = (remaining + spacing_bytes - 1) // spacing_bytes + 1
        node_count = max(node_count, 2)

    actual_bytes = (node_count - 1) * spacing_bytes + node_bytes
    return node_count, actual_bytes


def shuffle_in_place(values, generator):
    for remaining in range(len(values), 1, -1):
        selected = generator.below(remaining)
        values[remaining - 1], values[selected] = (
            values[selected], values[remaining - 1])


def build_rows(arguments):
    requested_sizes = generate_requested_sizes(
        arguments.min_bytes, arguments.max_bytes, arguments.points_per_octave)
    generator = SplitMix64(arguments.seed)
    rows = []
    global_execution_index = 0

    for trial in range(arguments.trials):
        trial_rows = []
        for plot_index, requested_bytes in enumerate(requested_sizes):
            node_count, actual_bytes = geometry_for_span(
                requested_bytes, arguments.node_spacing_bytes,
                arguments.node_bytes)
            point_seed = generator.next()
            trial_rows.append([
                trial,
                0,
                plot_index,
                requested_bytes,
                node_count,
                actual_bytes,
                point_seed,
            ])

        shuffle_in_place(trial_rows, generator)
        for trial_execution_index, row in enumerate(trial_rows):
            row[1] = trial_execution_index
            rows.append([global_execution_index] + row)
            global_execution_index += 1

    return requested_sizes, rows


def write_plan(arguments, requested_sizes, rows):
    created = False
    try:
        with open(arguments.output, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_capacity_plan_version=1\n")
            stream.write("generator=SplitMix64+Fisher-Yates\n")
            stream.write("size_generation=integer subdivisions within factor-of-two ranges\n")
            stream.write("min_bytes={}\n".format(arguments.min_bytes))
            stream.write("max_bytes={}\n".format(arguments.max_bytes))
            stream.write("points_per_octave={}\n".format(
                arguments.points_per_octave))
            stream.write("trial_count={}\n".format(arguments.trials))
            stream.write("plan_seed={}\n".format(arguments.seed))
            stream.write("node_spacing_bytes={}\n".format(
                arguments.node_spacing_bytes))
            stream.write("node_bytes={}\n".format(arguments.node_bytes))
            stream.write("unique_size_count={}\n".format(len(requested_sizes)))
            stream.write("plan_row_count={}\n".format(len(rows)))
            stream.write("data_begin\n")
            stream.write(
                "global_execution_index\ttrial\ttrial_execution_index\t"
                "plot_index\trequested_span_bytes\tnode_count\t"
                "actual_span_bytes\tpoint_seed\n")
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
        description=(
            "Generate, but do not execute, a reproducible randomized "
            "working-set sweep."))
    parser.add_argument("--min-bytes", required=True, type=positive_integer)
    parser.add_argument("--max-bytes", required=True, type=positive_integer)
    parser.add_argument("--points-per-octave", required=True,
                        type=positive_integer)
    parser.add_argument("--trials", required=True, type=positive_integer)
    parser.add_argument("--seed", required=True, type=unsigned_64)
    parser.add_argument("--node-spacing-bytes", required=True,
                        type=positive_integer)
    parser.add_argument("--node-bytes", required=True, type=positive_integer)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if arguments.min_bytes > arguments.max_bytes:
        parser.error("--min-bytes must not exceed --max-bytes")
    if arguments.node_spacing_bytes < arguments.node_bytes:
        parser.error("--node-spacing-bytes must be at least --node-bytes")
    if arguments.points_per_octave > 1024:
        parser.error("--points-per-octave must not exceed 1024")

    return arguments


def main():
    arguments = parse_arguments()
    requested_sizes, rows = build_rows(arguments)
    try:
        write_plan(arguments, requested_sizes, rows)
    except FileExistsError:
        print("error: output file already exists: {}".format(arguments.output),
              file=sys.stderr)
        return 1
    except OSError as error:
        print("error: could not write plan: {}".format(error), file=sys.stderr)
        return 1

    print("output_filename={}".format(arguments.output))
    print("unique_size_count={}".format(len(requested_sizes)))
    print("plan_row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
