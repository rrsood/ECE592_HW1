#!/usr/bin/env python3
"""Generate a reproducible dense plan around coarse timing transitions."""

import argparse
import os
import sys

import analyze_capacity_transitions
import generate_capacity_plan


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
    if value < 0 or value > generate_capacity_plan.MASK64:
        raise argparse.ArgumentTypeError("value must fit in uint64")
    return value


def decimal_factor(text):
    try:
        numerator, denominator = text.split("/", 1)
        numerator = int(numerator, 10)
        denominator = int(denominator, 10)
    except (AttributeError, TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("factor must be written numerator/denominator") from error
    if numerator <= 0 or denominator <= 0 or numerator < denominator:
        raise argparse.ArgumentTypeError("factor must be >= 1")
    return numerator, denominator


def read_candidates(path):
    metadata = {}
    candidates = []
    with open(path, "r", encoding="ascii", newline="") as stream:
        in_data = False
        headings = None
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")
            if line == "data_begin":
                in_data = True
                continue
            if not in_data:
                if "=" not in line:
                    raise ValueError("invalid transition metadata line")
                key, value = line.split("=", 1)
                if not key or key in metadata:
                    raise ValueError("invalid transition metadata key")
                metadata[key] = value
                continue
            if headings is None:
                headings = line.split("\t")
                continue
            if line == "data_end":
                break
            fields = line.split("\t")
            record = dict(zip(headings, fields))
            candidates.append({
                "rank": int(record["rank"], 10),
                "lower_span": int(record["lower_span"], 10),
                "upper_span": int(record["upper_span"], 10),
                "slope": float(record["log2_latency_slope"]),
                "disagreement": float(record["trial_disagreement_fraction"]),
            })
    if metadata.get("ece592_transition_analysis_format_version") != "1":
        raise ValueError("unsupported transition-analysis format version")
    if metadata.get("cache_boundary_labels_assigned") != "false":
        raise ValueError("transition file contains assigned cache labels")
    if not candidates:
        raise ValueError("transition file contains no candidate intervals")
    return metadata, sorted(candidates, key=lambda row: row["rank"])


def padded_window(candidate, numerator, denominator):
    lower = max(1, (candidate["lower_span"] * denominator) // numerator)
    upper = (candidate["upper_span"] * numerator + denominator - 1) // denominator
    if lower >= upper:
        raise ValueError("padded candidate window is empty")
    return lower, upper


def build_rows(arguments, candidates):
    selected = candidates[:arguments.top_k]
    if any(candidate["slope"] <= 0.0 for candidate in selected):
        raise ValueError("top candidates must have positive upward slope")

    requested_sizes = set()
    windows = []
    for candidate in selected:
        lower, upper = padded_window(
            candidate, arguments.padding_numerator,
            arguments.padding_denominator)
        windows.append((candidate, lower, upper))
        requested_sizes.update(generate_capacity_plan.generate_requested_sizes(
            lower, upper, arguments.points_per_octave))

    requested_sizes = sorted(requested_sizes)
    generator = generate_capacity_plan.SplitMix64(arguments.seed)
    rows = []
    global_execution_index = 0
    for trial in range(arguments.trials):
        trial_rows = []
        for plot_index, requested_bytes in enumerate(requested_sizes):
            node_count, actual_bytes = generate_capacity_plan.geometry_for_span(
                requested_bytes, arguments.node_spacing_bytes,
                arguments.node_bytes)
            trial_rows.append([
                trial, 0, plot_index, requested_bytes, node_count,
                actual_bytes, generator.next(),
            ])
        generate_capacity_plan.shuffle_in_place(trial_rows, generator)
        for trial_execution_index, row in enumerate(trial_rows):
            row[1] = trial_execution_index
            rows.append([global_execution_index] + row)
            global_execution_index += 1
    return selected, windows, requested_sizes, rows


def write_plan(arguments, source_path, source_digest, selected, windows,
               requested_sizes, rows):
    created = False
    try:
        with open(arguments.output, "x", encoding="ascii", newline="\n") as stream:
            created = True
            stream.write("ece592_capacity_plan_version=1\n")
            stream.write("generator=SplitMix64+Fisher-Yates\n")
            stream.write("size_generation=union of padded coarse transition windows\n")
            stream.write("source_transition_file={}\n".format(os.path.abspath(source_path)))
            stream.write("source_transition_sha256={}\n".format(source_digest))
            stream.write("selected_top_k={}\n".format(len(selected)))
            stream.write("selected_transition_ranks={}\n".format(
                ",".join(str(candidate["rank"]) for candidate in selected)))
            stream.write("padding_factor={}/{}\n".format(
                arguments.padding_numerator, arguments.padding_denominator))
            stream.write("min_bytes={}\n".format(min(requested_sizes)))
            stream.write("max_bytes={}\n".format(max(requested_sizes)))
            stream.write("points_per_octave={}\n".format(arguments.points_per_octave))
            stream.write("trial_count={}\n".format(arguments.trials))
            stream.write("plan_seed={}\n".format(arguments.seed))
            stream.write("node_spacing_bytes={}\n".format(arguments.node_spacing_bytes))
            stream.write("node_bytes={}\n".format(arguments.node_bytes))
            stream.write("unique_size_count={}\n".format(len(requested_sizes)))
            stream.write("plan_row_count={}\n".format(len(rows)))
            for candidate, lower, upper in windows:
                stream.write(
                    "candidate_rank_{}_window={}..{}_slope={:.17g}_trial_disagreement={:.17g}\n"
                    .format(candidate["rank"], lower, upper,
                            candidate["slope"], candidate["disagreement"]))
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
        description="Generate a dense follow-up plan from coarse transitions.")
    parser.add_argument("--transitions", required=True)
    parser.add_argument("--top-k", required=True, type=positive_integer)
    parser.add_argument("--padding-factor", required=True, type=decimal_factor)
    parser.add_argument("--points-per-octave", required=True,
                        type=positive_integer)
    parser.add_argument("--trials", required=True, type=positive_integer)
    parser.add_argument("--seed", required=True, type=unsigned_64)
    parser.add_argument("--node-spacing-bytes", required=True,
                        type=positive_integer)
    parser.add_argument("--node-bytes", required=True, type=positive_integer)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    arguments.padding_numerator, arguments.padding_denominator = \
        arguments.padding_factor
    if arguments.points_per_octave > 1024:
        parser.error("--points-per-octave must not exceed 1024")
    if arguments.node_spacing_bytes < arguments.node_bytes:
        parser.error("spacing must be at least node size")
    if not os.path.isfile(arguments.transitions):
        parser.error("--transitions must name an existing file")
    if os.path.exists(arguments.output):
        parser.error("--output must not already exist")
    if not os.path.isdir(os.path.dirname(os.path.abspath(arguments.output))):
        parser.error("output parent directory must already exist")
    return arguments


def main():
    arguments = parse_arguments()
    try:
        metadata, candidates = read_candidates(arguments.transitions)
        del metadata
        selected, windows, requested_sizes, rows = build_rows(arguments, candidates)
        write_plan(
            arguments, arguments.transitions,
            analyze_capacity_transitions.sha256_file(arguments.transitions),
            selected, windows, requested_sizes, rows)
    except (OSError, ValueError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    print("output_filename={}".format(arguments.output))
    print("selected_transition_count={}".format(len(selected)))
    print("unique_size_count={}".format(len(requested_sizes)))
    print("plan_row_count={}".format(len(rows)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
