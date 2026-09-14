#!/usr/bin/env python3
"""Fit and freeze lab-only predictions before any Hazel cache experiment."""

import argparse
import csv
import datetime
import hashlib
import math
import os
import statistics
import subprocess
import sys


REQUIRED_LAB_MACHINES = {
    "sunbird", "thunderbird", "skylark", "artemisia",
    "charnwood", "crux", "ookay", "upgrade",
}

METRICS = {
    "l1d_capacity_bytes": "log2_linear",
    "l1d_associativity": "constant_median",
    "l1d_hit_latency_ns": "linear",
    "l1_miss_penalty_ns": "linear",
    "l2_capacity_per_core_bytes": "log2_linear",
    "l2_associativity": "constant_median",
    "l2_hit_latency_ns": "linear",
    "l2_miss_penalty_ns": "linear",
    "llc_capacity_bytes": "log2_linear",
    "llc_capacity_per_core_bytes": "log2_linear",
    "llc_effective_associativity": "constant_median",
    "llc_hit_latency_ns": "linear",
    "llc_memory_penalty_ns": "linear",
    "line_size_bytes": "constant_median",
    "software_residency_rate": "linear",
    "pmu_l1_misses_per_timed_access": "linear",
    "pmu_last_cache_misses_per_timed_access": "linear",
}


def fail(message):
    raise ValueError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_plain_tsv(path):
    with open(path, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            fail("{} has no header".format(path))
        rows = list(reader)
    if not rows:
        fail("{} has no data rows".format(path))
    return reader.fieldnames, rows


def numeric(text, field, row_name):
    if text is None or text.strip() == "":
        return None
    try:
        value = float(text)
    except ValueError as error:
        raise ValueError("{} is nonnumeric for {}".format(field, row_name)) from error
    if not math.isfinite(value):
        fail("{} is non-finite for {}".format(field, row_name))
    return value


def linear_fit(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_bar = statistics.fmean(xs)
    y_bar = statistics.fmean(ys)
    denominator = sum((x - x_bar) ** 2 for x in xs)
    if denominator == 0:
        fail("a fitted series must span more than one year")
    slope = sum((x - x_bar) * (y - y_bar) for x, y in points) / denominator
    intercept = y_bar - slope * x_bar
    residuals = [y - (intercept + slope * x) for x, y in points]
    residual_se = math.sqrt(sum(value * value for value in residuals) /
                            max(1, len(points) - 2))
    total = sum((y - y_bar) ** 2 for y in ys)
    r_squared = 1.0 - sum(value * value for value in residuals) / total \
        if total > 0 else 1.0
    return intercept, slope, residual_se, r_squared, x_bar, denominator


def fit_metric(rows, metric, model):
    points = []
    for row in rows:
        year = numeric(row.get("year"), "year", row.get("machine", "row"))
        value = numeric(row.get(metric), metric, row.get("machine", "row"))
        if year is not None and value is not None:
            if model == "log2_linear" and value <= 0:
                fail("{} must be positive for log2 fitting".format(metric))
            points.append((year, math.log2(value) if model == "log2_linear" else value))
    if len(points) < 3:
        fail("{} has {} complete lab points; at least 3 are required".format(
            metric, len(points)))
    if model == "constant_median":
        values = [value for _, value in points]
        estimate = statistics.median(values)
        deviations = [abs(value - estimate) for value in values]
        spread = 1.4826 * statistics.median(deviations)
        return {
            "n": len(points), "intercept": estimate, "slope": 0.0,
            "residual_se": spread, "r_squared": "not_applicable",
            "x_bar": statistics.fmean(x for x, _ in points),
            "sxx": 0.0,
        }
    intercept, slope, residual_se, r_squared, x_bar, sxx = linear_fit(points)
    return {
        "n": len(points), "intercept": intercept, "slope": slope,
        "residual_se": residual_se, "r_squared": r_squared,
        "x_bar": x_bar, "sxx": sxx,
    }


def prediction(fit, model, year, metric):
    transformed = fit["intercept"] + fit["slope"] * year
    if model == "constant_median":
        standard = fit["residual_se"]
    else:
        leverage = 1.0 + 1.0 / fit["n"] + (
            (year - fit["x_bar"]) ** 2 / fit["sxx"])
        standard = fit["residual_se"] * math.sqrt(leverage)
    lower_t = transformed - 1.96 * standard
    upper_t = transformed + 1.96 * standard
    if model == "log2_linear":
        return 2 ** transformed, 2 ** lower_t, 2 ** upper_t
    lower = lower_t
    upper = upper_t
    if model == "linear" and "rate" in metric:
        lower, upper = max(0.0, lower), min(1.0, upper)
    return transformed, lower, upper


def git_head():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip()


def write_metadata_header(stream, kind, args):
    stream.write("ece592_phase3_{}_version=1\n".format(kind))
    stream.write("prediction_training_set=ECE_lab_machines_only\n")
    stream.write("hazel_measurements_used=false\n")
    stream.write("created_utc={}\n".format(
        datetime.datetime.now(datetime.timezone.utc).isoformat()))
    stream.write("creation_source_git_commit={}\n".format(git_head()))
    stream.write("source_lab_table={}\n".format(os.path.abspath(args.lab_table)))
    stream.write("source_lab_table_sha256={}\n".format(sha256_file(args.lab_table)))
    stream.write("source_targets={}\n".format(os.path.abspath(args.targets)))
    stream.write("source_targets_sha256={}\n".format(sha256_file(args.targets)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab-table", required=True)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--capacity-law-name", required=True,
                        help="both teammates' last names followed by Law")
    parser.add_argument("--cost-law-name", required=True,
                        help="both teammates' last names followed by Law")
    parser.add_argument("--capacity-law-metric", default="llc_capacity_per_core_bytes",
                        choices=("l1d_capacity_bytes", "l2_capacity_per_core_bytes",
                                 "llc_capacity_bytes", "llc_capacity_per_core_bytes"))
    parser.add_argument("--cost-law-metric", default="llc_memory_penalty_ns",
                        choices=("l1d_hit_latency_ns", "l1_miss_penalty_ns",
                                 "l2_hit_latency_ns", "l2_miss_penalty_ns",
                                 "llc_hit_latency_ns", "llc_memory_penalty_ns"))
    args = parser.parse_args()
    for name in (args.capacity_law_name, args.cost_law_name):
        if not name.endswith(" Law") or "-" not in name:
            parser.error("law names must contain both last names and end in ' Law'")
    if os.path.exists(args.output_directory):
        parser.error("--output-directory must not already exist")
    fields, lab_rows = read_plain_tsv(args.lab_table)
    _, targets = read_plain_tsv(args.targets)
    required_fields = {"machine", "year"}.union(METRICS)
    missing = required_fields.difference(fields)
    if missing:
        parser.error("lab table is missing columns: {}".format(", ".join(sorted(missing))))
    names = {row["machine"] for row in lab_rows}
    if names != REQUIRED_LAB_MACHINES:
        parser.error("lab table must contain exactly the eight specified lab machines")
    if any(row.get("machine", "").lower().startswith("hazel") or
           row.get("constraint", "") for row in lab_rows):
        parser.error("Hazel observations are forbidden in the frozen training table")

    fits = {metric: fit_metric(lab_rows, metric, model)
            for metric, model in METRICS.items()}
    inclusion_values = [row.get("inclusion_behavior", "").strip()
                        for row in lab_rows if row.get("inclusion_behavior", "").strip()]
    if len(inclusion_values) < 3:
        parser.error("inclusion_behavior needs at least three lab observations")
    inclusion_prediction = statistics.mode(inclusion_values)

    os.makedirs(args.output_directory)
    model_path = os.path.join(args.output_directory, "frozen_models.tsv")
    with open(model_path, "x", encoding="utf-8", newline="\n") as stream:
        write_metadata_header(stream, "prediction_models", args)
        stream.write("data_begin\n")
        stream.write("metric\tmodel\tn\tintercept\tslope_per_year\tresidual_standard_error\tr_squared\n")
        for metric, model in METRICS.items():
            fit = fits[metric]
            stream.write("{}\t{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\t{}\n".format(
                metric, model, fit["n"], fit["intercept"], fit["slope"],
                fit["residual_se"], fit["r_squared"]))
        stream.write("inclusion_behavior\tcategorical_mode\t{}\t{}\t\t\tnot_applicable\n".format(
            len(inclusion_values), inclusion_prediction))
        stream.write("data_end\n")

    prediction_path = os.path.join(args.output_directory, "frozen_hazel_predictions.tsv")
    with open(prediction_path, "x", encoding="utf-8", newline="\n") as stream:
        write_metadata_header(stream, "hazel_predictions", args)
        stream.write("uncertainty=approximate_95_percent_prediction_interval_from_lab_residuals\n")
        stream.write("data_begin\n")
        stream.write("constraint\tgeneration\tyear\tmetric\tpredicted\tlower_95\tupper_95\tmodel\n")
        for target in targets:
            year = int(target["introduction_year"])
            for metric, model in METRICS.items():
                estimate, lower, upper = prediction(fits[metric], model, year, metric)
                stream.write("{}\t{}\t{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\t{}\n".format(
                    target["constraint"], target["generation"], year, metric,
                    estimate, lower, upper, model))
            stream.write("{}\t{}\t{}\tinclusion_behavior\t{}\t\t\tcategorical_mode\n".format(
                target["constraint"], target["generation"], year,
                inclusion_prediction))
        future_year = max(int(target["introduction_year"]) for target in targets) + 5
        for metric, model in METRICS.items():
            estimate, lower, upper = prediction(fits[metric], model, future_year, metric)
            stream.write("future_five_year\tapproximately five years beyond newest target\t{}\t{}\t{:.17g}\t{:.17g}\t{:.17g}\t{}\n".format(
                future_year, metric, estimate, lower, upper, model))
        stream.write("data_end\n")

    laws_path = os.path.join(args.output_directory, "frozen_team_laws.tsv")
    with open(laws_path, "x", encoding="utf-8", newline="\n") as stream:
        write_metadata_header(stream, "team_laws", args)
        stream.write("law_scope=pooled_ECE_lab_observations_only\n")
        stream.write("data_begin\n")
        stream.write("law_name\tcategory\tmetric\tmodel\tn\tintercept\tslope_per_year\tquantitative_rule\n")
        for name, category, metric in (
                (args.capacity_law_name, "capacity_scaling", args.capacity_law_metric),
                (args.cost_law_name, "latency_cost", args.cost_law_metric)):
            model = METRICS[metric]
            fit = fits[metric]
            if model == "log2_linear":
                rule = "log2(value_bytes)=intercept+slope*year; doubling_time_years={:.6g}".format(
                    1.0 / fit["slope"] if fit["slope"] != 0 else float("inf"))
            else:
                rule = "value=intercept+slope*year"
            stream.write("{}\t{}\t{}\t{}\t{}\t{:.17g}\t{:.17g}\t{}\n".format(
                name, category, metric, model, fit["n"], fit["intercept"],
                fit["slope"], rule))
        stream.write("data_end\n")

    manifest_path = os.path.join(args.output_directory, "freeze_manifest.tsv")
    with open(manifest_path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write("ece592_phase3_freeze_manifest_version=1\n")
        stream.write("hazel_cache_runs_permitted_after_git_commit=false\n")
        stream.write("instruction=commit_this_directory_then_pass_that_commit_to_Hazel_jobs\n")
        stream.write("creation_source_git_commit={}\n".format(git_head()))
        stream.write("data_begin\n")
        stream.write("filename\tsha256\n")
        for path in (model_path, prediction_path, laws_path):
            stream.write("{}\t{}\n".format(os.path.basename(path), sha256_file(path)))
        stream.write("data_end\n")
    print("output_directory={}".format(args.output_directory))
    print("prediction_target_count={}".format(len(targets)))
    print("status=ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        sys.exit(1)
