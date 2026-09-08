#!/usr/bin/env python3
"""Generate a reproducible Phase-I spatial-locality offset sweep plan."""

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
        raise argparse.ArgumentTypeError(
            "value must fit in an unsigned 64-bit integer")
    return value


def parse_offset_list(text):
    offsets = []
    seen = set()

    for part in text.split(","):
        part = part.strip()
        if not part:
            raise argparse.ArgumentTypeError("empty offset in list")
        value = positive_integer(part)
        if value in seen:
            raise argparse.ArgumentTypeError(
                "duplicate probe offset: {}".format(value))
        seen.add(value)
        offsets.append(value)

    return offsets


def shuffle_in_place(values, generator):
    for remaining in range(len(values), 1, -1):
        selected = generator.below(remaining)
        values[remaining - 1], values[selected] = (
            values[selected], values[remaining - 1])


def build_rows(arguments):
    generator = SplitMix64(arguments.seed)
    rows = []
    global_execution_index = 0

    for trial in range(arguments.trials):
        trial_rows = []
        for plot_index, probe_offset in enumerate(arguments.probe_offsets):
            point_seed = generator.next()
            trial_rows.append([
                trial,
                0,
                plot_index,
                arguments.region_count,
                arguments.region_spacing_bytes,
                probe_offset,
                point_seed,
            ])

        shuffle_in_place(trial_rows, generator)
        for trial_execution_index, row in enumerate(trial_rows):
            row[1] = trial_execution_index
            rows.append([global_execution_index] + row)
            global_execution_index += 1

    return rows


def write_plan(arguments, rows):
    created = False
    try:
        with open(arguments.output, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_spatial_plan_version=1\n")
            stream.write("generator=SplitMix64+Fisher-Yates\n")
            stream.write("offset_generation=explicit user-provided offsets\n")
            stream.write("region_count={}\n".format(arguments.region_count))
            stream.write("region_spacing_bytes={}\n".format(
                arguments.region_spacing_bytes))
            stream.write("probe_offsets_bytes={}\n".format(
                ",".join(str(value) for value in arguments.probe_offsets)))
            stream.write("unique_offset_count={}\n".format(
                len(arguments.probe_offsets)))
            stream.write("trial_count={}\n".format(arguments.trials))
            stream.write("plan_seed={}\n".format(arguments.seed))
            stream.write("plan_row_count={}\n".format(len(rows)))
            stream.write("data_begin\n")
            stream.write(
                "global_execution_index\ttrial\ttrial_execution_index\t"
                "plot_index\tregion_count\tregion_spacing_bytes\t"
                "probe_offset_bytes\tpoint_seed\n")
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
            "spatial-locality probe-offset sweep."))
    parser.add_argument("--region-count", required=True, type=positive_integer)
    parser.add_argument("--region-spacing-bytes", required=True,
                        type=positive_integer)
    parser.add_argument("--probe-offsets", required=True,
                        type=parse_offset_list,
                        help="comma-separated byte offsets to test")
    parser.add_argument("--trials", required=True, type=positive_integer)
    parser.add_argument("--seed", required=True, type=unsigned_64)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if arguments.region_count < 2:
        parser.error("--region-count must be at least 2")
    if arguments.region_spacing_bytes < 16:
        parser.error("--region-spacing-bytes must be at least 16")
    if arguments.region_spacing_bytes % 8 != 0:
        parser.error("--region-spacing-bytes must be a multiple of 8")
    for offset in arguments.probe_offsets:
        if offset % 8 != 0:
            parser.error("all probe offsets must be multiples of 8")
        if offset < 8:
            parser.error("all probe offsets must be at least 8 bytes")
        if offset > arguments.region_spacing_bytes - 8:
            parser.error(
                "probe offsets must leave room for one pointer-sized node")

    return arguments


def main():
    arguments = parse_arguments()
    rows = build_rows(arguments)
    try:
        write_plan(arguments, rows)
    except FileExistsError:
        print("error: output file already exists: {}".format(arguments.output),
              file=sys.stderr)
        return 1
    except OSError as error:
        print("error: could not write plan: {}".format(error), file=sys.stderr)
        return 1

    print("output_filename={}".format(arguments.output))
    print("unique_offset_count={}".format(len(arguments.probe_offsets)))
    print("plan_row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
