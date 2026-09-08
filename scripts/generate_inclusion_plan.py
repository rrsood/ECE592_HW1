#!/usr/bin/env python3
"""Generate a reproducible Phase-I inclusion/reuse sweep plan."""

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


def parse_integer_list(text):
    values = []
    seen = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise argparse.ArgumentTypeError("empty value in list")
        value = positive_integer(part)
        if value in seen:
            raise argparse.ArgumentTypeError(
                "duplicate list value: {}".format(value))
        seen.add(value)
        values.append(value)
    return values


def shuffle_in_place(values, generator):
    for remaining in range(len(values), 1, -1):
        selected = generator.below(remaining)
        values[remaining - 1], values[selected] = (
            values[selected], values[remaining - 1])


def build_rows(arguments):
    generator = SplitMix64(arguments.seed)
    rows = []
    global_execution_index = 0
    plot_index = 0

    plot_indices = {}
    for probe_nodes in arguments.probe_nodes:
        for pressure_nodes in arguments.pressure_nodes:
            plot_indices[(probe_nodes, pressure_nodes)] = plot_index
            plot_index += 1

    for trial in range(arguments.trials):
        trial_rows = []
        for probe_nodes in arguments.probe_nodes:
            for pressure_nodes in arguments.pressure_nodes:
                trial_rows.append([
                    trial,
                    0,
                    plot_indices[(probe_nodes, pressure_nodes)],
                    probe_nodes,
                    pressure_nodes,
                    arguments.node_spacing,
                    arguments.probe_batch,
                    arguments.pressure_batch,
                    generator.next(),
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
            stream.write("ece592_inclusion_plan_version=1\n")
            stream.write("generator=SplitMix64+Fisher-Yates\n")
            stream.write("sweep=probe working set by pressure working set\n")
            stream.write("probe_node_counts={}\n".format(
                ",".join(str(value) for value in arguments.probe_nodes)))
            stream.write("pressure_node_counts={}\n".format(
                ",".join(str(value) for value in arguments.pressure_nodes)))
            stream.write("node_spacing_bytes={}\n".format(
                arguments.node_spacing))
            stream.write("probe_accesses_per_sample={}\n".format(
                arguments.probe_batch))
            stream.write("pressure_accesses_per_sample={}\n".format(
                arguments.pressure_batch))
            stream.write("unique_probe_node_count_count={}\n".format(
                len(arguments.probe_nodes)))
            stream.write("unique_pressure_node_count_count={}\n".format(
                len(arguments.pressure_nodes)))
            stream.write("trial_count={}\n".format(arguments.trials))
            stream.write("plan_seed={}\n".format(arguments.seed))
            stream.write("plan_row_count={}\n".format(len(rows)))
            stream.write("data_begin\n")
            stream.write(
                "global_execution_index\ttrial\ttrial_execution_index\t"
                "plot_index\tprobe_node_count\tpressure_node_count\t"
                "node_spacing_bytes\tprobe_accesses_per_sample\t"
                "pressure_accesses_per_sample\tpoint_seed\n")
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
            "inclusion/reuse plan."))
    parser.add_argument("--probe-nodes", required=True,
                        type=parse_integer_list)
    parser.add_argument("--pressure-nodes", required=True,
                        type=parse_integer_list)
    parser.add_argument("--node-spacing", required=True,
                        type=positive_integer)
    parser.add_argument("--probe-batch", required=True,
                        type=positive_integer)
    parser.add_argument("--pressure-batch", required=True,
                        type=positive_integer)
    parser.add_argument("--trials", required=True, type=positive_integer)
    parser.add_argument("--seed", required=True, type=unsigned_64)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    if arguments.node_spacing < 8 or arguments.node_spacing % 8 != 0:
        parser.error("--node-spacing must be a multiple of 8 and at least 8")
    if min(arguments.probe_nodes) < 2 or min(arguments.pressure_nodes) < 2:
        parser.error("all node counts must be at least 2")
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
    print("unique_probe_node_count_count={}".format(
        len(arguments.probe_nodes)))
    print("unique_pressure_node_count_count={}".format(
        len(arguments.pressure_nodes)))
    print("plan_row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
